import argparse
import logging
import os
import sys
import time

from .config_manager import DEFAULT_CONFIG_PATH, ConfigManager
from .engine import AutoclickerEngine, EngineState
from .models import ClickButton, ProfileConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("AutoclickerMain")


def check_device_permissions() -> bool:
    """Verify read/write access to /dev/uinput and /dev/input/event* before initializing."""
    if not os.path.exists("/dev/uinput") or not os.access("/dev/uinput", os.W_OK):
        print(
            "\n[ERROR] Missing write permission for /dev/uinput.\n"
            "To allow non-root access on Ubuntu / GNOME Wayland, run:\n\n"
            "  sudo modprobe uinput\n"
            "  echo 'uinput' | sudo tee /etc/modules-load.d/uinput.conf\n"
            "  sudo groupadd -f input\n"
            "  sudo usermod -aG input $USER\n"
            "  echo 'KERNEL==\"uinput\", MODE=\"0660\", GROUP=\"input\", OPTIONS+=\"static_node=uinput\"' | sudo tee /etc/udev/rules.d/99-uinput.rules\n"
            "  sudo udevadm control --reload-rules && sudo udevadm trigger\n\n"
            "Then log out and log back in for the group membership to take effect.\n",
            file=sys.stderr,
        )
        return False
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wayland Autoclicker for Linux (GTK4 / Headless)")
    parser.add_argument(
        "--config",
        type=str,
        default=str(DEFAULT_CONFIG_PATH),
        help=f"Path to TOML config file (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument("--profile", type=str, help="Profile key from config.toml to activate")
    parser.add_argument("--cps", type=float, help="Override target CPS")
    parser.add_argument(
        "--button",
        type=str,
        choices=["BTN_LEFT", "BTN_RIGHT", "BTN_MIDDLE", "BTN_SIDE", "BTN_EXTRA"],
        help="Override mouse button",
    )
    parser.add_argument("--headless", action="store_true", help="Run in background without a GUI window")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not check_device_permissions():
        sys.exit(1)

    config_manager = ConfigManager(args.config)
    app_config = config_manager.load()

    if args.profile and args.profile in app_config.profiles:
        app_config.active_profile = args.profile

    profile = app_config.profiles.get(app_config.active_profile, ProfileConfig())

    if args.cps is not None:
        profile.cps = args.cps
    if args.button is not None:
        profile.button = ClickButton(args.button)

    logger.info(f"Starting engine with profile '{profile.name}' ({profile.cps} CPS, {profile.button.value})")

    engine = AutoclickerEngine(profile)
    engine.start()

    if args.headless:
        logger.info("Running in headless mode. Press Ctrl+C or ESC to exit.")
        try:
            while engine.state != EngineState.STOPPED:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            engine.shutdown()
    else:
        from .gui import run_gui

        try:
            run_gui(engine, app_config, config_manager)
        finally:
            engine.shutdown()


if __name__ == "__main__":
    main()
