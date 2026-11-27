import logging
from typing import Any

from dasbus.connection import SessionMessageBus
from dasbus.error import DBusError

logger = logging.getLogger(__name__)


class MutterDisplayManager:
    """Queries logical display geometry from GNOME Mutter over D-Bus."""

    BUS_NAME = "org.gnome.Mutter.DisplayConfig"
    OBJECT_PATH = "/org/gnome/Mutter/DisplayConfig"

    @classmethod
    def get_virtual_screen_geometry(cls) -> tuple[int, int, list[dict[str, Any]]]:
        """Returns (total_width, total_height, monitors_info) in logical coordinates."""
        try:
            bus = SessionMessageBus()
            proxy = bus.get_proxy(cls.BUS_NAME, cls.OBJECT_PATH)
            state = proxy.GetCurrentState()

            # state[1]: physical monitors, state[2]: logical monitors
            physical_monitors = state[1]
            logical_monitors = state[2]

            if not logical_monitors:
                raise ValueError("Mutter returned an empty logical monitor list")

            # Map connector name -> active logical resolution
            connector_res: dict[str, tuple[int, int]] = {}
            for phys in physical_monitors:
                connector = phys[0][0]
                for mode in phys[1]:
                    # mode[6] contains properties dict; 'is-current' marks active mode
                    if mode[6].get("is-current", False):
                        connector_res[connector] = (int(mode[1]), int(mode[2]))
                        break

            monitors_info: list[dict[str, Any]] = []
            max_x = 0
            max_y = 0

            for lm in logical_monitors:
                lx, ly, scale, _transform, primary, linked_monitors, _props = lm
                w, h = 1920, 1080
                if linked_monitors:
                    first_conn = linked_monitors[0][0]
                    if first_conn in connector_res:
                        phys_w, phys_h = connector_res[first_conn]
                        w = int(round(phys_w / float(scale)))
                        h = int(round(phys_h / float(scale)))

                monitors_info.append({
                    "x": int(lx),
                    "y": int(ly),
                    "width": w,
                    "height": h,
                    "scale": float(scale),
                    "primary": bool(primary),
                })
                max_x = max(max_x, int(lx) + w)
                max_y = max(max_y, int(ly) + h)

            logger.info(f"Detected virtual desktop geometry: {max_x}x{max_y} ({len(monitors_info)} display(s))")
            return max_x, max_y, monitors_info

        except (DBusError, Exception) as e:
            logger.warning(f"Mutter D-Bus query failed ({e}). Using 1920x1080 fallback.")
            return 1920, 1080, [{"x": 0, "y": 0, "width": 1920, "height": 1080, "scale": 1.0, "primary": True}]
