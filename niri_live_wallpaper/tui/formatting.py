"""Turning settings and media info into the short texts shown in the TUI."""

from __future__ import annotations

from typing import Any

from ..media import VideoInfo
from ..variants import scaled_size


def fps_text(fps: int | None) -> str:
    return "original" if fps is None else f"{fps} fps"


def scale_text(scale: int, width: int | None = None, height: int | None = None) -> str:
    """"native" / "50%", plus the resulting size when the screen size is given."""
    name = "native" if scale == 100 else f"{scale}%"
    if width and height:
        w, h = scaled_size(width, height, scale) if scale != 100 else (width, height)
        return f"{name} ({w}×{h})"
    return name


FIT_TEXTS = {"fit": "black bars", "blur": "blurred bars", "stretch": "stretched", "center": "original size"}


def fit_text(entry: dict[str, Any] | None) -> str:
    """" · black bars" for an image's non-default fit, "" for the default."""
    entry = entry or {}
    text = FIT_TEXTS.get(entry.get("fit", ""))
    if text is None and entry.get("align", "center") != "center":
        text = f"crop to {entry['align']}"
    return f" · {text}" if text else ""


def copy_text(stem: str) -> str:
    """What an optimized copy is, from its file name (variants.filename()): "3440×1440 @ 30 fps,
    blurred bars"."""
    size, _, rest = stem.partition("@")
    fps, _, tag = rest.partition("-")
    parts = [size.replace("x", "×") + (f" @ {fps} fps" if fps != "src" else "")]
    if tag:
        parts.append(FIT_TEXTS.get(tag, f"cropped to {tag}"))
    return ", ".join(parts)


def human_duration(seconds: float) -> str:
    minutes = max(0, int(seconds)) // 60
    days, minutes = divmod(minutes, 60 * 24)
    hours, minutes = divmod(minutes, 60)
    if days:
        return f"{days}d {hours}h"
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def describe_video(info: VideoInfo | None, entry: dict[str, Any] | None) -> str:
    """The grey summary next to a video, e.g. "3840×2160 · 60 fps → 30 fps · per-screen"."""
    if not info:
        return ""
    if info.is_image:
        return f"{info.width}×{info.height} · image{fit_text(entry)}{' · per-screen' if (entry or {}).get('screens') else ''}"
    text = f"{info.width}×{info.height} · {info.fps:.3g} fps"
    entry = entry or {}
    fps = entry.get("fps")
    if isinstance(fps, int) and info.fps > fps + 0.5:
        text += f" → {fps} fps"
    if entry.get("scale", 100) != 100:
        text += f" · {entry['scale']}% res"
    text += fit_text(entry)
    if entry.get("screens"):
        text += " · per-screen"
    return text


def import_summary(imported: list[str], existing: list[str], failed: list[str]) -> str:
    """Message after an import. Arguments are file names (failed ones may include the reason)."""
    if len(imported) == 1:
        head = f"Imported {imported[0]}. Press space to set it as your wallpaper"
    elif imported:
        head = f"Imported {len(imported)} wallpapers. Press space to set one as your wallpaper"
    elif existing and not failed:
        return (f"{existing[0]} is already imported" if len(existing) == 1
                else f"All {len(existing)} wallpapers are already imported")
    else:
        head = "Nothing imported"
    extras = []
    if existing:
        extras.append(f"{len(existing)} already imported")
    if failed:
        extras.append(f"failed: {', '.join(failed)}")
    return head + (f" ({'; '.join(extras)})" if extras else "")
