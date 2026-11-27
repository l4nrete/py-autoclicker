from enum import Enum
from typing import Optional
import evdev
from pydantic import BaseModel, Field, field_validator, model_validator


class ClickButton(str, Enum):
    LEFT = "BTN_LEFT"
    RIGHT = "BTN_RIGHT"
    MIDDLE = "BTN_MIDDLE"
    SIDE = "BTN_SIDE"
    EXTRA = "BTN_EXTRA"


class ClickMode(str, Enum):
    SINGLE = "single"
    DOUBLE = "double"
    TRIPLE = "triple"
    HOLD = "hold"
    SEQUENCE = "sequence"
    INFINITE = "infinite"


class MacroAction(BaseModel):
    action_type: str = Field(..., description="click, move, wait, or key")
    button: Optional[ClickButton] = None
    x: Optional[int] = Field(None, ge=0)
    y: Optional[int] = Field(None, ge=0)
    duration_ms: Optional[float] = Field(None, gt=0.0)
    key_code: Optional[str] = None


class ProfileConfig(BaseModel):
    name: str = Field("Default", description="Profile display name")
    button: ClickButton = Field(ClickButton.LEFT, description="Mouse button to emulate")
    mode: ClickMode = Field(ClickMode.INFINITE, description="Clicking mode")
    cps: float = Field(10.0, gt=0.0, le=200.0, description="Target clicks per second")

    # Humanization settings
    use_temporal_jitter: bool = Field(True, description="Apply Gaussian jitter to intervals")
    temporal_jitter_stddev_ms: float = Field(5.0, ge=0.0, description="Jitter standard deviation in ms")
    use_spatial_jitter: bool = Field(False, description="Slightly randomize cursor position before clicks")
    spatial_jitter_radius: int = Field(3, ge=0, le=100, description="Max spatial offset in pixels")
    click_duration_min_ms: float = Field(40.0, ge=1.0, description="Min button hold duration in ms")
    click_duration_max_ms: float = Field(85.0, ge=1.0, description="Max button hold duration in ms")

    # Safety & user override
    user_override_timeout_sec: float = Field(3.0, ge=0.0, description="Auto-pause duration on manual mouse movement")
    max_clicks: Optional[int] = Field(None, ge=1, description="Stop after N clicks (None = unlimited)")

    # Global hotkeys (evdev key names)
    toggle_hotkey: str = Field("KEY_F6", description="Start/Stop hotkey")
    pause_hotkey: str = Field("KEY_F7", description="Pause/Resume hotkey")
    emergency_stop_hotkey: str = Field("KEY_ESC", description="Immediate kill-switch hotkey")

    macro_actions: list[MacroAction] = Field(default_factory=list, description="Optional macro steps")

    @field_validator("toggle_hotkey", "pause_hotkey", "emergency_stop_hotkey")
    @classmethod
    def normalize_hotkey(cls, val: str) -> str:
        cleaned = val.strip().upper()
        if not cleaned.startswith("KEY_"):
            cleaned = f"KEY_{cleaned}"
        if cleaned not in evdev.ecodes.ecodes:
            raise ValueError(f"Unknown evdev key code: {val}")
        return cleaned

    @model_validator(mode="after")
    def check_durations(self) -> "ProfileConfig":
        if self.click_duration_min_ms > self.click_duration_max_ms:
            raise ValueError("click_duration_min_ms cannot exceed click_duration_max_ms")
        return self


class AppConfig(BaseModel):
    active_profile: str = Field("default")
    profiles: dict[str, ProfileConfig] = Field(
        default_factory=lambda: {
            "default": ProfileConfig(name="Default"),
            "gaming": ProfileConfig(
                name="Gaming / Rapid",
                cps=16.0,
                use_temporal_jitter=True,
                temporal_jitter_stddev_ms=4.0,
                use_spatial_jitter=True,
                spatial_jitter_radius=2,
                click_duration_min_ms=25.0,
                click_duration_max_ms=45.0,
            ),
        }
    )
