"""The settings file (config.json): schema, defaults, migrations and access helpers.

The file is plain JSON so people can read and fix it by hand. It stores *choices* only; things
that can be looked up (screen resolutions, video properties) are never saved.

Schema, version 2:

    version             int    format version, see CURRENT_VERSION
    wallpaper           str    current video: a file name in paths.VIDEO_DIR
    last_change         float  Unix time the wallpaper last changed (drives cycling)
    cycle               {"mode": "off"|"hourly"|"daily"|"weekly"|"custom",
                         "minutes": int}   custom interval, kept when a preset is chosen; the
                        cycle of "all files" (a playlist has its own, see "playlists")
    autostart_prompted  bool   the "start at login?" question was asked
    ask_fps             bool   ask to lower the frame rate on import (default True)
    ask_screens         bool   open the per-screen editor on import (default False)
    videos              {file name: video settings}, see video_entry()
    playlists           {playlist name: {"items": {file name: video settings or null},
                                         "cycle": {...}}}: a playlist lists files of the library,
                        each with its own copy of the settings (null = the user was never asked),
                        and has its own cycle (same format as above; missing = off), see
                        "Playlists" below
    playlist            str    the active playlist: shown in the TUI and the only files that play;
                        missing = all files of the library

Both the TUI and the background service write this file, so every write is a load-modify-save
(update()) and the file is replaced atomically.

To change the format: bump CURRENT_VERSION, add a function to MIGRATIONS that upgrades a dict
from the previous version, and add a test to tests/test_config.py.
"""

from __future__ import annotations

import copy
import json
import logging
import os
from collections.abc import Callable
from typing import Any

from . import fit, paths

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
        log.warning(
            "config version %r is newer than this app understands (%d)",
            version,
            CURRENT_VERSION,
        )
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


# Playlists. A playlist lists files of the library; each entry in it holds that file's settings *in
# that playlist*. Adding a file copies its settings, after that the two are independent: photo1.png
# can fill-and-crop in one playlist and have black bars in another. While a playlist is active
# (cfg["playlist"]), every settings function below works on its entries, so the rest of the app
# doesn't need to know; with none active they work on the library's own settings (cfg["videos"]).

def active_playlist(cfg: Config) -> str | None:
    """The active playlist's name, or None (all files); ignores a name that no longer exists."""
    name = cfg.get("playlist")
    return name if name in cfg.get("playlists", {}) else None


def playlist_items(cfg: Config, playlist: str) -> dict[str, dict[str, Any] | None]:
    """File name -> settings of the files in `playlist` (the dict lives inside `cfg`)."""
    return cfg["playlists"][playlist].setdefault("items", {})


def _active_items(cfg: Config) -> dict[str, dict[str, Any] | None] | None:
    playlist = active_playlist(cfg)
    return playlist_items(cfg, playlist) if playlist else None


def cycle_settings(cfg: Config) -> dict[str, Any]:
    """The cycle setting that applies now: the active playlist's, or the one for all files."""
    playlist = active_playlist(cfg)
    source = cfg["playlists"][playlist] if playlist else cfg
    return source.get("cycle", {})


def cycle_changes(cfg: Config, cycle: dict[str, Any]) -> Config:
    """The changes for update() that make `cycle` the cycle setting that applies now."""
    playlist = active_playlist(cfg)
    if not playlist:
        return {"cycle": cycle}
    playlists = copy.deepcopy(cfg["playlists"])
    playlists[playlist]["cycle"] = cycle
    return {"playlists": playlists}


def video_entry(cfg: Config, name: str) -> dict[str, Any] | None:
    """Settings of one file (in the active playlist, if `name` is in it), or None if the user was
    never asked about it:

    {"fps": int | None,       all screens: frame-rate cap, None = original
     "scale": int,            all screens: % of native resolution, missing = 100
     "screens": {output name: {"fps": ..., "scale": ...}}}
                              per-screen overrides; a missing key = same as all screens

    How it fits a screen of another shape is "fit" (fit.MODES key) and "align" (fit.ALIGNS key, the
    part kept when cropping), both for all screens and in the per-screen overrides; missing = "fill",
    "center". An override's "fit" and "align" belong together: "fit" there is always stored, even
    when it is "fill", so it can undo a different fit set for all screens.
    """
    items = _active_items(cfg)
    if items is not None and name in items:
        return items[name]
    return cfg.get("videos", {}).get(name)


def entries_of(cfg: Config, name: str) -> list[dict[str, Any] | None]:
    """The settings of `name` everywhere: the library's own, then one per playlist it is in."""
    entries = [cfg.get("videos", {}).get(name)]
    for playlist in cfg.get("playlists", {}):
        items = playlist_items(cfg, playlist)
        if name in items:
            entries.append(items[name])
    return entries


def set_fit(target: dict[str, Any], mode: str, align: str, keep_default: bool = False) -> None:
    """Store a fit choice in an entry (or a per-screen override, with keep_default=True), leaving
    out the defaults so the file only lists real choices."""
    target.pop("fit", None)
    target.pop("align", None)
    if mode != fit.DEFAULT_FIT or keep_default:
        target["fit"] = mode
    if mode == "fill" and align != fit.DEFAULT_ALIGN:
        target["align"] = align


def screen_fit(cfg: Config, name: str, output: str) -> tuple[str, str]:
    """Effective (fit mode, crop focus) of a file on one output; the defaults for unknown values."""
    return screen_fit_of(video_entry(cfg, name) or {}, output)


def screen_fit_of(entry: dict[str, Any], output: str) -> tuple[str, str]:
    """Like screen_fit(), for a settings entry."""
    override = entry.get("screens", {}).get(output, {})
    source = override if "fit" in override else entry
    mode, align = source.get("fit", fit.DEFAULT_FIT), source.get("align", fit.DEFAULT_ALIGN)
    return (mode, align) if fit.valid(mode, align) else (fit.DEFAULT_FIT, fit.DEFAULT_ALIGN)


def save_video_entry(name: str, entry: dict[str, Any]) -> Config:
    """Store the settings of `name` (in the active playlist, if it is in it)."""
    cfg = load()
    items = _active_items(cfg)
    if items is not None and name in items:
        items[name] = entry
        return update(playlists=cfg["playlists"])
    videos = cfg.get("videos", {})
    videos[name] = entry
    return update(videos=videos)


def forget_video(name: str) -> None:
    """Back to "never asked" for `name` (in the active playlist, if it is in it)."""
    cfg = load()
    items = _active_items(cfg)
    if items is not None and name in items:
        if items[name] is not None:
            items[name] = None
            update(playlists=cfg["playlists"])
    elif cfg.get("videos", {}).pop(name, None) is not None:
        update(videos=cfg["videos"])


def purge_video(name: str) -> None:
    """Remove every trace of `name`: its settings in the library and in all playlists."""
    cfg = load()
    changes: dict[str, Any] = {}
    if cfg.get("videos", {}).pop(name, "-") != "-":
        changes["videos"] = cfg["videos"]
    for playlist in cfg.get("playlists", {}):
        if playlist_items(cfg, playlist).pop(name, "-") != "-":
            changes["playlists"] = cfg["playlists"]
    if changes:
        update(**changes)


def screen_settings(cfg: Config, name: str, output: str) -> tuple[int | None, int]:
    """Effective (fps cap or None for original, resolution percent) of a video on one output."""
    return screen_settings_of(video_entry(cfg, name) or {}, output)


def screen_settings_of(entry: dict[str, Any], output: str) -> tuple[int | None, int]:
    """Like screen_settings(), for a settings entry."""
    override = entry.get("screens", {}).get(output, {})
    fps = override["fps"] if "fps" in override else entry.get("fps")
    scale = override["scale"] if "scale" in override else entry.get("scale", 100)
    return (fps if isinstance(fps, int) else None), (scale or 100)
