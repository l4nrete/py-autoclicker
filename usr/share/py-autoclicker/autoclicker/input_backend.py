import logging
import selectors
import threading
from typing import Callable, Optional

import evdev
from evdev import InputDevice, UInput, ecodes

logger = logging.getLogger(__name__)


class InputBackend:
    """Low-level virtual input device managed via Linux uinput."""

    VIRTUAL_MOUSE_NAME = "py-autoclicker-virtual-mouse"

    def __init__(self, screen_width: int = 1920, screen_height: int = 1080):
        self.width = int(screen_width)
        self.height = int(screen_height)
        self.rel_device: Optional[UInput] = None
        self._pressed_keys: set[int] = set()
        self._lock = threading.Lock()
        self._initialize_device()

    def _initialize_device(self) -> None:
        # Expose standard mouse capabilities so libinput/Mutter binds it cleanly
        caps = {
            ecodes.EV_KEY: [
                ecodes.BTN_LEFT,
                ecodes.BTN_RIGHT,
                ecodes.BTN_MIDDLE,
                ecodes.BTN_SIDE,
                ecodes.BTN_EXTRA,
            ],
            ecodes.EV_REL: [
                ecodes.REL_X,
                ecodes.REL_Y,
                ecodes.REL_WHEEL,
            ],
        }
        self.rel_device = UInput(
            caps,
            name=self.VIRTUAL_MOUSE_NAME,
            vendor=0x046D,
            product=0xC077,
        )
        logger.info("Virtual uinput mouse initialized.")

    def move_relative(self, dx: int, dy: int) -> None:
        if not self.rel_device:
            return
        with self._lock:
            if dx != 0:
                self.rel_device.write(ecodes.EV_REL, ecodes.REL_X, int(dx))
            if dy != 0:
                self.rel_device.write(ecodes.EV_REL, ecodes.REL_Y, int(dy))
            self.rel_device.syn()

    def click_button(self, btn_code: int, press: bool) -> None:
        if not self.rel_device:
            return
        state = 1 if press else 0
        with self._lock:
            self.rel_device.write(ecodes.EV_KEY, btn_code, state)
            self.rel_device.syn()
            if press:
                self._pressed_keys.add(btn_code)
            else:
                self._pressed_keys.discard(btn_code)

    def release_all(self) -> None:
        """Ensure no virtual buttons remain stuck down on exit."""
        if not self.rel_device:
            return
        with self._lock:
            for code in list(self._pressed_keys):
                try:
                    self.rel_device.write(ecodes.EV_KEY, code, 0)
                except Exception:
                    pass
            try:
                self.rel_device.syn()
            except Exception:
                pass
            self._pressed_keys.clear()

    def close(self) -> None:
        self.release_all()
        if self.rel_device:
            try:
                self.rel_device.close()
            except Exception:
                pass
            self.rel_device = None
        logger.info("Virtual uinput device closed.")


class PhysicalInputMonitor:
    """Monitors physical /dev/input/event* devices using selectors for hotkeys and user activity."""

    MOUSE_MOVE_DEADZONE = 5

    def __init__(
        self,
        on_hotkey: Optional[Callable[[str, int], None]] = None,
        on_user_activity: Optional[Callable[[], None]] = None,
    ):
        self.on_hotkey = on_hotkey
        self.on_user_activity = on_user_activity
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._devices: dict[int, InputDevice] = {}

    def _discover_devices(self, selector: selectors.DefaultSelector) -> None:
        for path in evdev.list_devices():
            try:
                dev = InputDevice(path)
                # Anti-echo loop: skip our own virtual uinput device
                if dev.name.startswith("py-autoclicker-"):
                    dev.close()
                    continue

                caps = dev.capabilities()
                if ecodes.EV_KEY in caps or ecodes.EV_REL in caps:
                    selector.register(dev.fd, selectors.EVENT_READ, dev)
                    self._devices[dev.fd] = dev
                else:
                    dev.close()
            except (PermissionError, OSError):
                continue

    def _monitor_loop(self) -> None:
        selector = selectors.DefaultSelector()
        self._discover_devices(selector)
        logger.info(f"Listening to {len(self._devices)} physical input device(s).")

        try:
            while not self._stop_event.is_set():
                events = selector.select(timeout=0.2)
                for key, _ in events:
                    dev: InputDevice = key.data
                    try:
                        for event in dev.read():
                            # Trigger hotkeys strictly on initial press (value == 1), ignoring auto-repeat (2)
                            if event.type == ecodes.EV_KEY and event.value == 1:
                                key_name = ecodes.KEY.get(event.code) or ecodes.BTN.get(event.code)
                                if isinstance(key_name, list):
                                    key_name = key_name[0]
                                if key_name and self.on_hotkey:
                                    self.on_hotkey(key_name, event.code)

                            # Trigger User Override only on intentional physical mouse movement
                            elif event.type == ecodes.EV_REL and event.code in (ecodes.REL_X, ecodes.REL_Y):
                                if abs(event.value) >= self.MOUSE_MOVE_DEADZONE and self.on_user_activity:
                                    self.on_user_activity()
                    except OSError:
                        selector.unregister(dev.fd)
                        self._devices.pop(dev.fd, None)
        finally:
            for dev in self._devices.values():
                try:
                    selector.unregister(dev.fd)
                    dev.close()
                except Exception:
                    pass
            self._devices.clear()
            selector.close()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="PhysicalInputMonitor")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
