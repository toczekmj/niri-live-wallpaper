"""The video library: the files in paths.VIDEO_DIR."""

from __future__ import annotations

import shutil
from pathlib import Path

from . import config, paths, variants

VIDEO_EXTENSIONS = ("mp4", "mkv", "webm", "mov", "avi", "m4v", "gif")


def list_videos() -> list[str]:
    """File names of the videos in the library, sorted case-insensitively."""
    if not paths.VIDEO_DIR.is_dir():
        return []
    return sorted(
        (p.name for p in paths.VIDEO_DIR.iterdir()
         if p.is_file() and p.suffix.lower().lstrip(".") in VIDEO_EXTENSIONS),
        key=str.lower,
    )


def import_video(src: Path) -> tuple[str, bool]:
    """Copy src into the library. Returns (file name, already_present).

    A file with the same name and size counts as already imported; a different file with the same
    name gets a " (1)", " (2)", … suffix.
    """
    paths.VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    dest = paths.VIDEO_DIR / src.name
    if dest.exists() and dest.stat().st_size == src.stat().st_size:
        return dest.name, True
    n = 1
    while dest.exists():
        dest = paths.VIDEO_DIR / f"{src.stem} ({n}){src.suffix}"
        n += 1
    shutil.copy2(src, dest)
    return dest.name, False


def delete_video(name: str) -> None:
    """Remove a video and everything derived from it: copies, theme frame, its settings."""
    (paths.VIDEO_DIR / name).unlink(missing_ok=True)
    (paths.FRAME_DIR / f"{name}.jpg").unlink(missing_ok=True)
    variants.remove_all(name)
    config.forget_video(name)
