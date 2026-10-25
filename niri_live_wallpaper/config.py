"""The settings file (config.json): schema, defaults, migrations and access helpers.

The file is plain JSON so people can read and fix it by hand. It stores *choices* only; things
that can be looked up (screen resolutions, video properties) are never saved.

Schema, version 2:

    version             int    format version, see CURRENT_VERSION
    wallpaper           str    current video: a file name in paths.VIDEO_DIR
    last_change         float  Unix time the wallpaper last changed (drives cycling)
    cycle               {"mode": "off"|"hourly"|"daily"|"weekly"|"custom",
                         "minutes": int}   custom interval, kept when a preset is chosen
    autostart_prompted  bool   the "start at login?" question was asked
    ask_fps             bool   ask to lower the frame rate on import (default True)
    ask_screens         bool   open the per-screen editor on import (default False)
    videos              {file name: video settings}, see video_entry()

Both the TUI and the background service write this file, so every write is a load-modify-save
(update()) and the file is replaced atomically.

To change the format: bump CURRENT_VERSION, add a function to MIGRATIONS that upgrades a dict
from the previous version, and add a test to tests/test_config.py.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

from . import paths

log = logging.getLogger(__name__)

Config = dict[str, Any]

CURRENT_VERSION = 2


def _v1_to_v2(cfg: Config) -> Config:
    """Custom cycle intervals were stored as "hours"; they are "minutes" now (hh:mm input)."""
    cycle = cfg.get("cycle")
    if isinstance(cycle, dict) and "hours" in cycle:
        hours = cycle.pop("hours")
        if hours and "minutes" not in cycle:
            cycle["minutes"] = round(hours * 60)
    return cfg


# from-version -> function returning the dict upgraded to from-version + 1.
# Files written before versioning existed count as version 1.
MIGRATIONS: dict[int, Callable[[Config], Config]] = {
    1: _v1_to_v2,
}


def migrate(cfg: Config) -> Config:
    version = cfg.get("version", 1)
    if not isinstance(version, int) or version > CURRENT_VERSION:
        # Written by a newer version of the app: use what we understand, don't rewrite it.
        log.warning("config version %r is newer than this app understands (%d)",
                    version, CURRENT_VERSION)
        return cfg
    while version < CURRENT_VERSION:
        cfg = MIGRATIONS[version](cfg)
        version += 1
    cfg["version"] = CURRENT_VERSION
    return cfg


def load() -> Config:
    try:
        data = json.loads(paths.CONFIG_FILE.read_text())
    except FileNotFoundError:
        data = {}
    except (OSError, ValueError) as e:
        log.error("could not read %s, using defaults: %s", paths.CONFIG_FILE, e)
        data = {}
    return migrate(data if isinstance(data, dict) else {})


def update(**changes: Any) -> Config:
    """Apply changes to the file on disk and return the new config. None removes a key."""
    cfg = load()
    for key, value in changes.items():
        if value is None:
            cfg.pop(key, None)
        else:
            cfg[key] = value
    paths.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = paths.CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2) + "\n")
    os.replace(tmp, paths.CONFIG_FILE)
    return cfg


# --------------------------------------------------------------------------- simple settings

def ask_fps(cfg: Config) -> bool:
    return cfg.get("ask_fps", True)


def ask_screens(cfg: Config) -> bool:
    return cfg.get("ask_screens", False)


# --------------------------------------------------------------------------- per-video settings

def video_entry(cfg: Config, name: str) -> dict[str, Any] | None:
    """Settings of one video, or None if the user was never asked about it:

        {"fps": int | None,       all screens: frame-rate cap, None = original
         "scale": int,            all screens: % of native resolution, missing = 100
         "screens": {output name: {"fps": ..., "scale": ...}}}
                                  per-screen overrides; a missing key = same as all screens
    """
    return cfg.get("videos", {}).get(name)


def save_video_entry(name: str, entry: dict[str, Any]) -> Config:
    videos = load().get("videos", {})
    videos[name] = entry
    return update(videos=videos)


def forget_video(name: str) -> None:
    videos = load().get("videos", {})
    if videos.pop(name, None) is not None:
        update(videos=videos)


def screen_settings(cfg: Config, name: str, output: str) -> tuple[int | None, int]:
    """Effective (fps cap or None for original, resolution percent) of a video on one output."""
    entry = video_entry(cfg, name) or {}
    override = entry.get("screens", {}).get(output, {})
    fps = override["fps"] if "fps" in override else entry.get("fps")
    scale = override["scale"] if "scale" in override else entry.get("scale", 100)
    return (fps if isinstance(fps, int) else None), (scale or 100)
