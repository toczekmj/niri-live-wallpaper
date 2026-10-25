"""Wallpaper cycling: the schedule maths.

Everything here is pure (no I/O, the current time is passed in), so it can be tested directly.
The background service does the actual switching.

Intervals are measured from the last change, not by the clock: "every day" means 24 h after the
last change. That survives reboots and suspend: a change that came due while the machine was off
happens on the next check after it wakes.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config


@dataclass(frozen=True)
class CycleMode:
    key: str              # stored in config["cycle"]["mode"]
    label: str            # shown in the menu
    minutes: int | None   # interval; None = user-defined ("custom")


MODES = (
    CycleMode("off", "Off", 0),
    CycleMode("hourly", "Every hour", 60),
    CycleMode("daily", "Every day", 24 * 60),
    CycleMode("weekly", "Every week", 7 * 24 * 60),
    CycleMode("custom", "Custom interval (hh:mm)…", None),
)
MAX_MINUTES = 30 * 24 * 60
DEFAULT_CUSTOM_MINUTES = 60


def interval_minutes(cfg: Config) -> int | None:
    """Interval in minutes, or None when cycling is off."""
    cycle = cfg.get("cycle", {})
    key = cycle.get("mode", "off")
    if key == "custom":
        return cycle.get("minutes") or None
    return next((m.minutes for m in MODES if m.key == key), 0) or None


def saved_custom_minutes(cfg: Config) -> int:
    """The last custom interval, to prefill the hh:mm dialog."""
    return cfg.get("cycle", {}).get("minutes") or DEFAULT_CUSTOM_MINUTES


def new_cycle_settings(cfg: Config, mode_key: str, custom_minutes: int | None) -> dict:
    """The "cycle" value after choosing a mode. Choosing a preset keeps the last custom interval."""
    cycle = dict(cfg.get("cycle", {}))
    cycle["mode"] = mode_key
    cycle["minutes"] = custom_minutes if custom_minutes is not None else saved_custom_minutes(cfg)
    return cycle


def format_interval(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m" if h and m else f"{h}h" if h else f"{m}m"


def parse_interval(text: str) -> int:
    """"H:MM" or "H" -> minutes. Raises ValueError with a message meant for the user."""
    hours, sep, mins = text.partition(":")
    if not hours.isdigit() and not (sep and hours == ""):
        raise ValueError("Use hh:mm, e.g. 1:30 or 0:45")
    if sep and not (mins.isdigit() and len(mins) <= 2 and int(mins) < 60):
        raise ValueError("Minutes must be 00–59")
    total = int(hours or 0) * 60 + int(mins or 0)
    if not 1 <= total <= MAX_MINUTES:
        raise ValueError(f"Choose between 0:01 and {MAX_MINUTES // 60}:00")
    return total


def label(cfg: Config) -> str:
    minutes = interval_minutes(cfg)
    if not minutes:
        return "off"
    presets = {"hourly": "every hour", "daily": "every day", "weekly": "every week"}
    return presets.get(cfg["cycle"]["mode"], f"every {format_interval(minutes)}")


def seconds_until_next(cfg: Config, now: float) -> float | None:
    """Seconds until the next change (negative when overdue), or None when cycling is off."""
    minutes = interval_minutes(cfg)
    if not minutes:
        return None
    return cfg.get("last_change", 0) + minutes * 60 - now


def is_due(cfg: Config, now: float, video_count: int) -> bool:
    remaining = seconds_until_next(cfg, now)
    return remaining is not None and remaining <= 0 and video_count >= 2


def next_video(videos: list[str], current: str | None) -> str:
    """The video after `current` in list order, wrapping around (the first if current is unknown)."""
    i = videos.index(current) if current in videos else -1
    return videos[(i + 1) % len(videos)]
