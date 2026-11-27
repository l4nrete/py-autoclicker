# ⚡ Py-Autoclicker (Wayland & X11)

A native, low-level auto-clicker for modern Linux desktops (**GNOME / Mutter on Wayland**, KDE, Hyprland, Sway, and X11), built on top of Linux kernel `evdev`/`uinput` subsystems and a **GTK4 + Libadwaita** user interface.

Unlike legacy X11 tools (`xdotool`, `pynput`, `pyautogui`) that are blocked by Wayland compositor security policies, `py-autoclicker` operates cleanly at the virtual input device level with zero-relogin permissions via `systemd-logind` (`uaccess`).

---

## ✨ Features

- **True Wayland & X11 Compatibility:** Emulates a standard virtual mouse via `uinput` and listens for global hotkeys across all windows and fullscreen apps via `evdev` + `epoll` (`selectors`).
- **Native GNOME / Libadwaita UI:** Clean adaptive interface with real-time telemetry, actual CPS measurement, live event log, and automatic system dark/light theme support.
- **Humanization & Anti-Detect:**
  - **Gaussian Temporal Jitter:** Natural click interval distribution around the target CPS.
  - **Realistic Click Duration:** Randomized hold delay (`DOWN` → `UP`) so clicks are reliably registered by games and Wayland clients.
  - **Spatial Micro-Drift:** Optional random cursor offset within a configurable pixel radius before clicking.
- **Built-in Safety Mechanisms:**
  - **User Override:** Automatically pauses clicking whenever you move your physical mouse, resuming smoothly after a configurable timeout.
  - **Emergency Kill-Switch (`ESC`):** Dedicated high-priority input listener stops execution immediately regardless of active delays.
  - **Stuck-Button Protection:** Guaranteed `KEY_UP` / `BTN_UP` cleanup on exit, `SIGINT`, or `SIGTERM`.
- **TOML Profiles & Headless Mode:** Switch presets (`default`, `gaming`) on the fly in the GUI or run as a background CLI tool with `--headless`.

---

## 📦 Installation

### Ubuntu / Debian / Linux Mint (`.deb`)
Download the pre-built `.deb` from [Releases](../../releases) or build from source:
```bash
chmod +x build_deb.sh
./build_deb.sh
sudo apt install ./py-autoclicker_1.0.0-1_all.deb
```

### Arch Linux / Manjaro / EndeavourOS (`PKGBUILD`)
```bash
makepkg -si
```

### Fedora / Nobara (`.rpm`)
```bash
sudo dnf install rpm-build
chmod +x build_rpm.sh
./build_rpm.sh
sudo dnf install ./py-autoclicker-1.0.0-1.*.noarch.rpm
```

All packages automatically load the `uinput` kernel module and apply `TAG+="uaccess"` udev rules—**no logout or manual `input` group configuration required**.

---

## ⌨️ Default Controls & CLI Usage

| Shortcut | Action |
| :--- | :--- |
| **`F6`** | Start / Stop clicking |
| **`F7`** | Pause / Resume |
| **`ESC`** | Emergency Kill-Switch (immediate shutdown) |

### Command-Line Options
```bash
# Launch GUI (default)
py-autoclicker

# Launch GUI with a specific preset
py-autoclicker --profile gaming

# Override speed and mouse button
py-autoclicker --cps 15.0 --button BTN_RIGHT

# Run in background without GUI
py-autoclicker --headless --cps 12.0
```

---

## ⚙️ Configuration

User profiles are stored in `~/.config/py-autoclicker/config.toml` (created automatically on first launch):

```toml
active_profile = "default"

[profiles.default]
name = "Default Desktop"
button = "BTN_LEFT"
mode = "infinite"
cps = 10.0

use_temporal_jitter = true
temporal_jitter_stddev_ms = 5.0
use_spatial_jitter = false
spatial_jitter_radius = 3
click_duration_min_ms = 40.0
click_duration_max_ms = 85.0

user_override_timeout_sec = 3.0
toggle_hotkey = "KEY_F6"
pause_hotkey = "KEY_F7"
emergency_stop_hotkey = "KEY_ESC"
```

---

## 🏗️ Architecture Overview

```text
autoclicker/
├── models.py          # Pydantic v2 schemas & evdev keycode validation
├── config_manager.py  # Atomic TOML profile loader & serializer
├── display.py         # Logical multi-monitor geometry via GNOME Mutter D-Bus
├── input_backend.py   # uinput virtual mouse & epoll physical device monitor
├── engine.py          # Thread-safe state machine, HybridSleeper & humanizer
├── gui.py             # GTK4 + Libadwaita interface
└── main.py            # CLI entrypoint & lifecycle management
```

---

## 📄 License

MIT License

## 🛠️ Credits & Workflow

Designed, architected, tested on real Wayland hardware, and packaged for Debian/Arch/Fedora by **sunako** using an AI-assisted code generation and iterative auditing workflow.

