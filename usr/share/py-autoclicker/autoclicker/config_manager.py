import logging
import os
import tomllib
from pathlib import Path
from typing import Optional

from .models import AppConfig, ClickButton, ProfileConfig

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "py-autoclicker"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.toml"


def _format_toml_value(val) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, str):
        escaped = val.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(val, (int, float)):
        return str(val)
    raise TypeError(f"Unsupported TOML value type: {type(val)}")


def _serialize_config(config: AppConfig) -> str:
    lines = [
        "# Py-Autoclicker configuration file",
        f"active_profile = {_format_toml_value(config.active_profile)}",
        "",
    ]
    for key, profile in config.profiles.items():
        lines.append(f"[profiles.{key}]")
        data = profile.model_dump(mode="json", exclude={"macro_actions"})
        for field_name, field_val in data.items():
            if field_val is None:
                continue
            lines.append(f"{field_name} = {_format_toml_value(field_val)}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def create_default_config() -> AppConfig:
    return AppConfig(
        active_profile="default",
        profiles={
            "default": ProfileConfig(
                name="Default Desktop",
                button=ClickButton.LEFT,
                cps=10.0,
                use_temporal_jitter=True,
                temporal_jitter_stddev_ms=5.0,
            ),
            "gaming": ProfileConfig(
                name="Fast Gaming",
                button=ClickButton.LEFT,
                cps=18.0,
                use_temporal_jitter=True,
                temporal_jitter_stddev_ms=3.5,
                use_spatial_jitter=True,
                spatial_jitter_radius=2,
                click_duration_min_ms=25.0,
                click_duration_max_ms=45.0,
            ),
        },
    )


class ConfigManager:
    """Handles loading, creating, and atomically saving TOML profiles."""

    def __init__(self, path: Optional[str | Path] = None):
        self.path = Path(path).expanduser() if path else DEFAULT_CONFIG_PATH

    def load(self) -> AppConfig:
        if not self.path.exists():
            logger.info(f"Config not found at {self.path}. Creating defaults.")
            cfg = create_default_config()
            self.save(cfg)
            return cfg

        try:
            with open(self.path, "rb") as f:
                raw_data = tomllib.load(f)
            return AppConfig(**raw_data)
        except Exception as e:
            logger.error(f"Failed to parse {self.path}: {e}. Falling back to defaults.")
            return create_default_config()

    def save(self, config: AppConfig) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.path.with_suffix(".tmp")
            content = _serialize_config(config)
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, self.path)
            logger.info(f"Configuration saved to {self.path}")
            return True
        except Exception as e:
            logger.error(f"Could not save configuration: {e}")
            return False
