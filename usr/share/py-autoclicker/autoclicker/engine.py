import atexit
import logging
import random
import signal
import sys
import threading
import time
from enum import Enum
from typing import Optional

from evdev import ecodes

from .display import MutterDisplayManager
from .input_backend import InputBackend, PhysicalInputMonitor
from .models import ClickButton, ProfileConfig

logger = logging.getLogger(__name__)


class EngineState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    USER_OVERRIDE = "USER_OVERRIDE"
    STOPPED = "STOPPED"


class HybridSleeper:
    """Interruptible high-precision sleeper combining Event.wait and perf_counter spin-wait."""

    def __init__(self, stop_event: threading.Event, pause_event: threading.Event):
        self.stop_event = stop_event
        self.pause_event = pause_event

    def sleep(self, duration_sec: float) -> bool:
        if duration_sec <= 0:
            return not self.stop_event.is_set() and not self.pause_event.is_set()

        target = time.perf_counter() + duration_sec
        while True:
            if self.stop_event.is_set() or self.pause_event.is_set():
                return False

            remaining = target - time.perf_counter()
            if remaining <= 0.0015:
                break
            time.sleep(min(0.01, remaining))

        while time.perf_counter() < target:
            if self.stop_event.is_set() or self.pause_event.is_set():
                return False

        return not self.stop_event.is_set()


class AutoclickerEngine:
    """Core state machine and humanization engine for Linux Wayland/X11."""

    BUTTON_MAP = {
        ClickButton.LEFT: ecodes.BTN_LEFT,
        ClickButton.RIGHT: ecodes.BTN_RIGHT,
        ClickButton.MIDDLE: ecodes.BTN_MIDDLE,
        ClickButton.SIDE: ecodes.BTN_SIDE,
        ClickButton.EXTRA: ecodes.BTN_EXTRA,
    }

    def __init__(self, profile: ProfileConfig):
        self.profile = profile
        self.state = EngineState.IDLE
        self._lock = threading.Lock()
        self._shutdown_done = False

        w, h, _ = MutterDisplayManager.get_virtual_screen_geometry()
        self.screen_width = w
        self.screen_height = h

        self.backend = InputBackend(self.screen_width, self.screen_height)

        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self.sleeper = HybridSleeper(self._stop_event, self._pause_event)

        self.monitor = PhysicalInputMonitor(
            on_hotkey=self._on_hotkey,
            on_user_activity=self._on_user_activity,
        )

        self._worker: Optional[threading.Thread] = None
        self._override_timer: Optional[threading.Timer] = None

        self.click_count = 0
        self.current_cps_measured = 0.0
        self._timestamps: list[float] = []

        atexit.register(self.shutdown)
        signal.signal(signal.SIGINT, self._on_signal)
        signal.signal(signal.SIGTERM, self._on_signal)

    def set_profile(self, profile: ProfileConfig) -> None:
        with self._lock:
            self.profile = profile
        logger.info(f"Switched active profile to '{profile.name}' ({profile.cps:.1f} CPS)")

    def _on_signal(self, signum: int, _frame) -> None:
        logger.info(f"Received signal {signum}, shutting down...")
        self.shutdown()
        sys.exit(0)

    def shutdown(self) -> None:
        with self._lock:
            if self._shutdown_done:
                return
            self._shutdown_done = True
            self.state = EngineState.STOPPED

        self._stop_event.set()
        self._pause_event.set()

        if self._override_timer and self._override_timer.is_alive():
            self._override_timer.cancel()
        if self.monitor:
            self.monitor.stop()
        if self.backend:
            self.backend.release_all()
            self.backend.close()
        logger.info("Engine shut down cleanly.")

    def _ensure_worker_running(self) -> None:
        if not self._worker or not self._worker.is_alive():
            self._stop_event.clear()
            self._worker = threading.Thread(target=self._click_loop, daemon=True, name="ClickerWorker")
            self._worker.start()

    def _on_hotkey(self, key_name: str, _code: int) -> None:
        if key_name == self.profile.toggle_hotkey:
            self.toggle_running()
        elif key_name == self.profile.pause_hotkey:
            self.toggle_pause()
        elif key_name == self.profile.emergency_stop_hotkey:
            logger.warning(f"Emergency kill-switch triggered ({key_name})!")
            self.shutdown()

    def _on_user_activity(self) -> None:
        with self._lock:
            if self.state != EngineState.RUNNING or self.profile.user_override_timeout_sec <= 0:
                return
            self.state = EngineState.USER_OVERRIDE
            self._pause_event.set()
            self.current_cps_measured = 0.0
            timeout = self.profile.user_override_timeout_sec
            logger.info(f"Physical mouse moved: entering USER_OVERRIDE for {timeout:.1f}s")

        if self._override_timer and self._override_timer.is_alive():
            self._override_timer.cancel()

        self._override_timer = threading.Timer(timeout, self._resume_from_override)
        self._override_timer.daemon = True
        self._override_timer.start()

    def _resume_from_override(self) -> None:
        with self._lock:
            if self.state == EngineState.USER_OVERRIDE:
                self.state = EngineState.RUNNING
                self._pause_event.clear()
                self._ensure_worker_running()
                logger.info("Resuming after User Override timeout.")

    def toggle_running(self) -> None:
        with self._lock:
            if self.state in (EngineState.IDLE, EngineState.PAUSED, EngineState.USER_OVERRIDE):
                self.state = EngineState.RUNNING
                self._pause_event.clear()
                self._ensure_worker_running()
                logger.info("State -> RUNNING")
            elif self.state == EngineState.RUNNING:
                self.state = EngineState.IDLE
                self._pause_event.set()
                self.current_cps_measured = 0.0
                logger.info("State -> IDLE")

    def toggle_pause(self) -> None:
        with self._lock:
            if self.state == EngineState.RUNNING:
                self.state = EngineState.PAUSED
                self._pause_event.set()
                self.current_cps_measured = 0.0
                logger.info("State -> PAUSED")
            elif self.state == EngineState.PAUSED:
                self.state = EngineState.RUNNING
                self._pause_event.clear()
                self._ensure_worker_running()
                logger.info("State -> RUNNING")

    def start(self) -> None:
        self.monitor.start()
        logger.info("Input monitor started.")

    def _next_interval(self) -> float:
        base = 1.0 / max(self.profile.cps, 0.1)
        if not self.profile.use_temporal_jitter:
            return max(0.001, base)
        stddev = self.profile.temporal_jitter_stddev_ms / 1000.0
        return max(0.001, random.gauss(base, stddev))

    def _click_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._pause_event.is_set() or self.state != EngineState.RUNNING:
                time.sleep(0.03)
                continue

            if self.profile.max_clicks is not None and self.click_count >= self.profile.max_clicks:
                logger.info(f"Reached target limit ({self.profile.max_clicks} clicks).")
                with self._lock:
                    self.state = EngineState.IDLE
                    self.current_cps_measured = 0.0
                break

            btn_code = self.BUTTON_MAP.get(self.profile.button, ecodes.BTN_LEFT)

            if self.profile.use_spatial_jitter and self.profile.spatial_jitter_radius > 0:
                r = self.profile.spatial_jitter_radius
                dx, dy = random.randint(-r, r), random.randint(-r, r)
                if dx != 0 or dy != 0:
                    self.backend.move_relative(dx, dy)

            self.backend.click_button(btn_code, press=True)

            max_allowed_hold_ms = (1000.0 / max(self.profile.cps, 0.1)) * 0.45
            low_ms = min(self.profile.click_duration_min_ms, max_allowed_hold_ms)
            high_ms = min(self.profile.click_duration_max_ms, max_allowed_hold_ms)
            hold_sec = max(0.001, random.uniform(low_ms, max(low_ms, high_ms)) / 1000.0)

            if not self.sleeper.sleep(hold_sec):
                self.backend.click_button(btn_code, press=False)
                if self._stop_event.is_set():
                    break
                continue

            self.backend.click_button(btn_code, press=False)

            now = time.perf_counter()
            self.click_count += 1
            self._timestamps.append(now)
            self._timestamps = [t for t in self._timestamps if now - t <= 1.0]
            self.current_cps_measured = float(len(self._timestamps))

            if not self.sleeper.sleep(self._next_interval()):
                if self._stop_event.is_set():
                    break
                continue
