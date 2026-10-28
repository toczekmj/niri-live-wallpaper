"""Playlists ("sets"): named lists of files from the library, each file with its own settings.

The functions here only work out *what to change*: they take the config and return the changes for
config.update(), so the rules can be tested without files. Where the settings of a playlist's files
live and how they are looked up is described in config.py.

A playlist is shown and played in the order of the library (alphabetical), the same as with no
playlist, so cycling goes through the same list the TUI shows.
"""

from __future__ import annotations

import copy
from typing import Any

from .config import Config, active_playlist, playlist_items

NAME_MAX = 40
Changes = dict[str, Any]


def names(cfg: Config) -> list[str]:
    return sorted(cfg.get("playlists", {}), key=str.lower)


def files(cfg: Config, playlist: str) -> list[str]:
    """File names in `playlist`, sorted like the library."""
    return sorted(playlist_items(cfg, playlist), key=str.lower)


def clean_name(cfg: Config, text: str, renaming: str | None = None) -> str:
    """The playlist name to use for `text`. Raises ValueError with a message for the user.
    `renaming` is the playlist being renamed, which may keep its own name (or change its case)."""
    name = " ".join(text.split())
    if not name:
        raise ValueError("Type a name")
    if len(name) > NAME_MAX:
        raise ValueError(f"At most {NAME_MAX} characters")
    taken = {n.lower() for n in cfg.get("playlists", {}) if n != renaming}
    if name.lower() in taken:
        raise ValueError(f"There is already a playlist called {name}")
    return name


def create(cfg: Config, name: str) -> Changes:
    return {"playlists": {**cfg.get("playlists", {}), name: {"items": {}}}}


def rename(cfg: Config, old: str, new: str) -> Changes:
    """Same position, same files, same settings; the active playlist stays active."""
    playlists = {(new if key == old else key): value for key, value in cfg["playlists"].items()}
    changes: Changes = {"playlists": playlists}
    if cfg.get("playlist") == old:
        changes["playlist"] = new
    return changes


def delete(cfg: Config, name: str) -> Changes:
    """Deleting the active playlist goes back to all files. The files stay in the library."""
    playlists = {key: value for key, value in cfg["playlists"].items() if key != name}
    changes: Changes = {"playlists": playlists}
    if cfg.get("playlist") == name:
        changes["playlist"] = None
    return changes


def add(cfg: Config, name: str, file_names: list[str]) -> Changes:
    """Add files to a playlist, each with a copy of its settings from the library. Files already
    in the playlist keep their playlist settings."""
    playlists = copy.deepcopy(cfg["playlists"])
    items = playlists[name].setdefault("items", {})
    for file in file_names:
        if file not in items:
            items[file] = copy.deepcopy(cfg.get("videos", {}).get(file))
    return {"playlists": playlists}


def remove(cfg: Config, name: str, file_names: list[str]) -> Changes:
    """Take files out of a playlist (they stay in the library) together with their playlist
    settings."""
    playlists = copy.deepcopy(cfg["playlists"])
    items = playlists[name].setdefault("items", {})
    for file in file_names:
        items.pop(file, None)
    return {"playlists": playlists}


def share_with_library(cfg: Config, name: str, file_names: list[str]) -> Changes:
    """Files imported straight into a playlist were set up there; give the library the same
    settings if it has none, so they aren't asked about again in the "all files" view."""
    videos = copy.deepcopy(cfg.get("videos", {}))
    items = playlist_items(cfg, name)
    for file in file_names:
        if items.get(file) is not None and videos.get(file) is None:
            videos[file] = copy.deepcopy(items[file])
    return {"videos": videos}


def activate(name: str | None) -> Changes:
    """Show and play a playlist; None = all files."""
    return {"playlist": name}


def first_to_play(cfg: Config, library_files: list[str]) -> str | None:
    """The file to switch to when the active playlist doesn't contain the current wallpaper:
    its first file that exists, None if there is nothing to switch to."""
    playlist = active_playlist(cfg)
    if not playlist:
        return None
    present = set(library_files)
    return next((f for f in files(cfg, playlist) if f in present), None)
