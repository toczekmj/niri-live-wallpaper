"""Talking to DankMaterialShell (DMS): its built-in wallpaper setting and its theme.

DMS takes its colour scheme (matugen) and lock-screen background from its wallpaper *path*, not
from what is on screen. So with DMS's own wallpaper disabled, we still hand it a still frame of
the video and the theme keeps matching.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from . import media, paths, proc

log = logging.getLogger(__name__)


def builtin_wallpaper_enabled() -> bool | None:
    """Whether DMS draws its own wallpaper; None if DMS's settings can't be read (no DMS?).
    The "Disable Built-in Wallpapers" toggle stores screenPreferences.wallpaper = []."""
    try:
        prefs = json.loads(paths.DMS_SETTINGS.read_text()).get("screenPreferences", {})
    except (OSError, ValueError, AttributeError):
        return None
    return prefs.get("wallpaper") != []


def set_wallpaper(image: Path, output_names: list[str]) -> None:
    def call(*args: str) -> str | None:
        result = proc.run(["dms", "ipc", "call", "wallpaper", *args], timeout=10)
        return result.stdout if result else None

    reply = call("set", str(image))
    if reply is None or "ERROR" not in reply:
        return
    # DMS's per-monitor mode refuses `set`, so set every output individually.
    for name in output_names:
        call("setFor", name, str(image))


def sync_theme(video: Path, output_names: list[str]) -> None:
    """Point DMS at a still of `video` (the file itself for an image), so its colours and lock
    screen match the wallpaper."""
    if media.is_image(video):
        if proc.available("dms"):
            set_wallpaper(video, output_names)
        return
    if not (proc.available("ffmpeg") and proc.available("dms")):
        return
    frame = media.extract_frame(video)
    if frame:
        set_wallpaper(frame, output_names)
    else:
        log.warning("could not extract a frame from %s for the DMS theme", video.name)
