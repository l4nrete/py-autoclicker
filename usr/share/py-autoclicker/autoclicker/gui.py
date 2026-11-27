import logging
import threading
import time
from collections import deque
from datetime import datetime
from typing import Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk

from .config_manager import ConfigManager
from .engine import AutoclickerEngine, EngineState
from .models import AppConfig, ClickButton


class GUIEventLogHandler(logging.Handler):
    """Thread-safe log handler feeding engine events into the GTK TextView."""

    def __init__(self, max_lines: int = 80):
        super().__init__()
        self.records: deque[str] = deque(maxlen=max_lines)
        self._lock = threading.Lock()
        self.dirty = False

    def emit(self, record: logging.LogRecord) -> None:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        msg = self.format(record)
        with self._lock:
            self.records.append(f"[{ts}] [{record.levelname}] {msg}")
            self.dirty = True

    def add_manual(self, level: str, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with self._lock:
            self.records.append(f"[{ts}] [{level}] {msg}")
            self.dirty = True

    def consume_text(self) -> Optional[str]:
        with self._lock:
            if not self.dirty:
                return None
            self.dirty = False
            return "\n".join(self.records)


class AutoclickerWindow(Adw.ApplicationWindow):
    """Native GTK4 + Libadwaita window for Py-Autoclicker."""

    BUTTON_OPTIONS = [
        ("Left Button (BTN_LEFT)", ClickButton.LEFT),
        ("Right Button (BTN_RIGHT)", ClickButton.RIGHT),
        ("Middle Button (BTN_MIDDLE)", ClickButton.MIDDLE),
        ("Side Back (BTN_SIDE)", ClickButton.SIDE),
        ("Side Forward (BTN_EXTRA)", ClickButton.EXTRA),
    ]

    def __init__(
        self,
        app: Adw.Application,
        engine: AutoclickerEngine,
        app_config: AppConfig,
        cfg_mgr: ConfigManager,
    ):
        super().__init__(application=app, title="Py-Autoclicker")
        self.engine = engine
        self.app_config = app_config
        self.cfg_mgr = cfg_mgr
        self.profile_keys = list(app_config.profiles.keys())
        self.start_time = time.time()
        self._syncing_ui = False

        self.set_default_size(520, 760)
        self.set_size_request(440, 620)
        self._install_css()

        self.log_handler = GUIEventLogHandler(max_lines=100)
        self.log_handler.setFormatter(logging.Formatter("%(message)s"))
        logging.getLogger().addHandler(self.log_handler)
        self.log_handler.add_manual("INFO", f"Loaded config from {self.cfg_mgr.path}")

        self._build_ui()
        self._load_profile_into_ui()

        self._timer_id = GLib.timeout_add(100, self._on_tick)
        self.connect("close-request", self._on_close_request)

    def _install_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(b"""
        .status-card { border-radius: 14px; padding: 16px; transition: background-color 200ms ease; }
        .status-idle { background-color: alpha(@warning_color, 0.16); border: 1px solid alpha(@warning_color, 0.45); }
        .status-running { background-color: alpha(@success_color, 0.20); border: 1px solid alpha(@success_color, 0.55); }
        .status-paused { background-color: alpha(@accent_color, 0.18); border: 1px solid alpha(@accent_color, 0.50); }
        .status-override { background-color: alpha(@error_color, 0.18); border: 1px solid alpha(@error_color, 0.50); }
        .big-counter { font-size: 28px; font-weight: 800; font-variant-numeric: tabular-nums; }
        .status-badge { font-size: 13px; font-weight: 700; letter-spacing: 0.8px; }
        .log-view { font-family: monospace; font-size: 11.5px; }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build_ui(self) -> None:
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(
            Adw.WindowTitle(
                title="Py-Autoclicker",
                subtitle=f"Wayland / Mutter • {self.engine.screen_width}x{self.engine.screen_height}",
            )
        )

        save_btn = Gtk.Button(label="Save", tooltip_text="Save settings to config.toml")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save_clicked)
        header.pack_start(save_btn)

        reset_btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Reset click counter")
        reset_btn.connect("clicked", self._on_reset_clicked)
        header.pack_end(reset_btn)

        toolbar.add_top_bar(header)

        scrolled = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        clamp = Adw.Clamp(maximum_size=600, margin_top=16, margin_bottom=20, margin_start=16, margin_end=16)
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)

        # Status card
        self.status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.status_box.add_css_class("status-card")
        self.status_box.add_css_class("status-idle")

        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.state_label = Gtk.Label(label="● IDLE", halign=Gtk.Align.START, hexpand=True)
        self.state_label.add_css_class("status-badge")
        self.uptime_label = Gtk.Label(label="00:00")
        self.uptime_label.add_css_class("dim-label")
        top_row.append(self.state_label)
        top_row.append(self.uptime_label)

        metrics = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        c_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        self.clicks_label = Gtk.Label(label="0", halign=Gtk.Align.START)
        self.clicks_label.add_css_class("big-counter")
        c_cap = Gtk.Label(label="Total Clicks", halign=Gtk.Align.START)
        c_cap.add_css_class("dim-label")
        c_col.append(self.clicks_label)
        c_col.append(c_cap)

        cps_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.cps_label = Gtk.Label(label="0.0", halign=Gtk.Align.END)
        self.cps_label.add_css_class("big-counter")
        cps_cap = Gtk.Label(label="Actual CPS", halign=Gtk.Align.END)
        cps_cap.add_css_class("dim-label")
        cps_col.append(self.cps_label)
        cps_col.append(cps_cap)

        metrics.append(c_col)
        metrics.append(cps_col)
        self.cps_progress = Gtk.ProgressBar()

        self.status_box.append(top_row)
        self.status_box.append(metrics)
        self.status_box.append(self.cps_progress)
        main_box.append(self.status_box)

        # Control buttons
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, homogeneous=True)
        self.toggle_btn = Gtk.Button(label=f"Start ({self.engine.profile.toggle_hotkey})", height_request=44)
        self.toggle_btn.add_css_class("suggested-action")
        self.toggle_btn.add_css_class("pill")
        self.toggle_btn.connect("clicked", lambda _: self.engine.toggle_running())

        self.pause_btn = Gtk.Button(label=f"Pause ({self.engine.profile.pause_hotkey})", height_request=44)
        self.pause_btn.add_css_class("pill")
        self.pause_btn.connect("clicked", lambda _: self.engine.toggle_pause())

        controls.append(self.toggle_btn)
        controls.append(self.pause_btn)
        main_box.append(controls)

        # Profile &amp; click parameters
        click_group = Adw.PreferencesGroup(title="Profile &amp; Click Settings")

        self.profile_row = Adw.ComboRow(title="Active Preset")
        display_names = [f"{self.app_config.profiles[k].name} ({k})" for k in self.profile_keys]
        self.profile_row.set_model(Gtk.StringList.new(display_names))
        if self.app_config.active_profile in self.profile_keys:
            self.profile_row.set_selected(self.profile_keys.index(self.app_config.active_profile))
        self.profile_row.connect("notify::selected", self._on_profile_changed)
        click_group.add(self.profile_row)

        self.button_row = Adw.ComboRow(title="Mouse Button")
        self.button_row.set_model(Gtk.StringList.new([opt[0] for opt in self.BUTTON_OPTIONS]))
        self.button_row.connect("notify::selected", self._on_button_changed)
        click_group.add(self.button_row)

        self.cps_row = Adw.SpinRow(
            title="Target Speed (CPS)",
            subtitle="Clicks per second (0.5 – 200.0)",
            adjustment=Gtk.Adjustment(value=10.0, lower=0.5, upper=200.0, step_increment=0.5, page_increment=5.0),
            digits=1,
        )
        self.cps_row.connect("notify::value", self._on_cps_changed)
        click_group.add(self.cps_row)

        self.limit_row = Adw.SpinRow(
            title="Click Limit",
            subtitle="0 = infinite loop until stopped",
            adjustment=Gtk.Adjustment(value=0, lower=0, upper=1_000_000, step_increment=10, page_increment=100),
            digits=0,
        )
        self.limit_row.connect("notify::value", self._on_limit_changed)
        click_group.add(self.limit_row)

        main_box.append(click_group)

        # Humanization &amp; safety
        human_group = Adw.PreferencesGroup(title="Humanization &amp; Safety")

        self.t_jitter_row = Adw.SwitchRow(title="Temporal Jitter (Gaussian)")
        self.t_jitter_row.connect("notify::active", self._on_t_jitter_toggled)
        human_group.add(self.t_jitter_row)

        self.s_jitter_row = Adw.SwitchRow(title="Spatial Jitter (Cursor Micro-Drift)")
        self.s_jitter_row.connect("notify::active", self._on_s_jitter_toggled)
        human_group.add(self.s_jitter_row)

        self.override_row = Adw.SpinRow(
            title="User Override Pause (sec)",
            subtitle="Auto-pause when moving physical mouse",
            adjustment=Gtk.Adjustment(value=3.0, lower=0.0, upper=30.0, step_increment=0.5, page_increment=1.0),
            digits=1,
        )
        self.override_row.connect("notify::value", self._on_override_changed)
        human_group.add(self.override_row)

        self.hotkeys_row = Adw.ActionRow(title="Global Hotkeys")
        self.hotkeys_row.add_prefix(Gtk.Image.new_from_icon_name("input-keyboard-symbolic"))
        human_group.add(self.hotkeys_row)

        main_box.append(human_group)

        # Event log
        log_group = Adw.PreferencesGroup(title="Diagnostics")
        expander = Adw.ExpanderRow(title="Engine Event Log", subtitle="evdev &amp; state machine events", expanded=True)
        log_scroll = Gtk.ScrolledWindow(
            min_content_height=130,
            max_content_height=180,
            margin_top=6,
            margin_bottom=6,
            margin_start=8,
            margin_end=8,
        )
        self.log_buffer = Gtk.TextBuffer()
        self.log_view = Gtk.TextView(
            buffer=self.log_buffer, editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR
        )
        self.log_view.add_css_class("log-view")
        log_scroll.set_child(self.log_view)
        expander.add_row(log_scroll)
        log_group.add(expander)
        main_box.append(log_group)

        clamp.set_child(main_box)
        scrolled.set_child(clamp)
        toolbar.set_content(scrolled)
        self.set_content(toolbar)

    def _load_profile_into_ui(self) -> None:
        self._syncing_ui = True
        p = self.engine.profile
        btn_idx = next((i for i, opt in enumerate(self.BUTTON_OPTIONS) if opt[1] == p.button), 0)
        self.button_row.set_selected(btn_idx)
        self.cps_row.set_value(p.cps)
        self.limit_row.set_value(float(p.max_clicks or 0))
        self.t_jitter_row.set_active(p.use_temporal_jitter)
        self.t_jitter_row.set_subtitle(f"Gaussian deviation ±{p.temporal_jitter_stddev_ms:.1f} ms")
        self.s_jitter_row.set_active(p.use_spatial_jitter)
        self.s_jitter_row.set_subtitle(f"Random offset within ±{p.spatial_jitter_radius} px")
        self.override_row.set_value(p.user_override_timeout_sec)
        self.hotkeys_row.set_subtitle(
            f"Toggle: {p.toggle_hotkey}  •  Pause: {p.pause_hotkey}  •  Kill-Switch: {p.emergency_stop_hotkey}"
        )
        self._syncing_ui = False

    def _on_profile_changed(self, row: Adw.ComboRow, _param) -> None:
        if self._syncing_ui:
            return
        idx = row.get_selected()
        if 0 <= idx < len(self.profile_keys):
            key = self.profile_keys[idx]
            self.app_config.active_profile = key
            self.engine.set_profile(self.app_config.profiles[key])
            self._load_profile_into_ui()

    def _on_save_clicked(self, _btn: Gtk.Button) -> None:
        if self.cfg_mgr.save(self.app_config):
            self.log_handler.add_manual("INFO", "Configuration saved to disk.")

    def _on_reset_clicked(self, _btn: Gtk.Button) -> None:
        self.engine.click_count = 0
        self.log_handler.add_manual("WARNING", "Click counter reset to 0.")

    def _on_button_changed(self, row: Adw.ComboRow, _param) -> None:
        if self._syncing_ui:
            return
        idx = row.get_selected()
        if 0 <= idx < len(self.BUTTON_OPTIONS):
            self.engine.profile.button = self.BUTTON_OPTIONS[idx][1]

    def _on_cps_changed(self, row: Adw.SpinRow, _param) -> None:
        if not self._syncing_ui:
            self.engine.profile.cps = round(float(row.get_value()), 1)

    def _on_limit_changed(self, row: Adw.SpinRow, _param) -> None:
        if not self._syncing_ui:
            val = int(row.get_value())
            self.engine.profile.max_clicks = val if val > 0 else None

    def _on_t_jitter_toggled(self, row: Adw.SwitchRow, _param) -> None:
        if not self._syncing_ui:
            self.engine.profile.use_temporal_jitter = bool(row.get_active())

    def _on_s_jitter_toggled(self, row: Adw.SwitchRow, _param) -> None:
        if not self._syncing_ui:
            self.engine.profile.use_spatial_jitter = bool(row.get_active())

    def _on_override_changed(self, row: Adw.SpinRow, _param) -> None:
        if not self._syncing_ui:
            self.engine.profile.user_override_timeout_sec = round(float(row.get_value()), 1)

    def _on_tick(self) -> bool:
        if self.engine.state == EngineState.STOPPED:
            self.close()
            return False

        for cls in ("status-idle", "status-running", "status-paused", "status-override"):
            self.status_box.remove_css_class(cls)

        state = self.engine.state
        if state == EngineState.RUNNING:
            self.status_box.add_css_class("status-running")
            self.state_label.set_text("● RUNNING")
            self.toggle_btn.set_label(f"Stop ({self.engine.profile.toggle_hotkey})")
            self.toggle_btn.remove_css_class("suggested-action")
            self.toggle_btn.add_css_class("destructive-action")
        elif state == EngineState.PAUSED:
            self.status_box.add_css_class("status-paused")
            self.state_label.set_text("❚❚ PAUSED")
        elif state == EngineState.USER_OVERRIDE:
            self.status_box.add_css_class("status-override")
            self.state_label.set_text("✋ USER OVERRIDE")
        else:
            self.status_box.add_css_class("status-idle")
            self.state_label.set_text("● IDLE")
            self.toggle_btn.set_label(f"Start ({self.engine.profile.toggle_hotkey})")
            self.toggle_btn.remove_css_class("destructive-action")
            self.toggle_btn.add_css_class("suggested-action")

        uptime = int(time.time() - self.start_time)
        self.uptime_label.set_text(f"Uptime {uptime // 60:02d}:{uptime % 60:02d}")
        self.clicks_label.set_text(f"{self.engine.click_count:,}")

        measured = float(self.engine.current_cps_measured)
        target = max(float(self.engine.profile.cps), 0.1)
        self.cps_label.set_text(f"{measured:.1f}")
        self.cps_progress.set_fraction(min(1.0, measured / target))

        log_text = self.log_handler.consume_text()
        if log_text is not None:
            self.log_buffer.set_text(log_text)
            self.log_view.scroll_to_iter(self.log_buffer.get_end_iter(), 0.0, False, 0.0, 1.0)

        return True

    def _on_close_request(self, _win) -> bool:
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = 0
        self.cfg_mgr.save(self.app_config)
        self.engine.shutdown()
        return False


class AutoclickerGUIApp(Adw.Application):
    def __init__(self, engine: AutoclickerEngine, app_config: AppConfig, cfg_mgr: ConfigManager):
        super().__init__(application_id="io.github.pyautoclicker.App")
        self.engine = engine
        self.app_config = app_config
        self.cfg_mgr = cfg_mgr
        self.window: Optional[AutoclickerWindow] = None

    def do_activate(self) -> None:
        if not self.window:
            self.window = AutoclickerWindow(self, self.engine, self.app_config, self.cfg_mgr)
        self.window.present()


def run_gui(engine: AutoclickerEngine, app_config: AppConfig, cfg_mgr: ConfigManager) -> int:
    return AutoclickerGUIApp(engine, app_config, cfg_mgr).run(None)
