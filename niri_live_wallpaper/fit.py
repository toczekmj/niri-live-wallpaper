"""How an image or video is fitted to a screen whose shape differs from its own.

Everything here is pure. The settings are stored per file and screen (config.screen_fit()); the
service turns them into mpv options (mpv_options()). "blur" also needs a copy rendered for each
screen (blur_filter(), used by variants.py), and so do the other modes when a video is scaled down.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FitMode:
    key: str     # stored in config as "fit"
    label: str   # shown in the menu
    short: str   # shown in the settings table


MODES = (
    FitMode("fill", "Fill the screen, crop the overflow", "Fill"),
    FitMode("fit", "Fit inside, black bars", "Black bars"),
    FitMode("blur", "Fit inside, blurred copy behind", "Blurred bars"),
    FitMode("stretch", "Stretch to the screen (distorts)", "Stretch"),
    FitMode("center", "Original size, centered", "Original size"),
)
DEFAULT_FIT = "fill"

# Which part survives when "fill" crops: the key, its label, and mpv's video-align-x/y (-1 … 1).
ALIGNS = (
    ("center", "Center", (0, 0)),
    ("left", "Left edge", (-1, 0)),
    ("right", "Right edge", (1, 0)),
    ("top", "Top edge", (0, -1)),
    ("bottom", "Bottom edge", (0, 1)),
)
DEFAULT_ALIGN = "center"

# Aspect ratios closer than this look the same; nothing to crop or pad.
ASPECT_TOLERANCE = 0.02

BLUR_SHRINK = 16  # the blurred backdrop is made at 1/16 size and scaled back up: cheap and smooth


def short_label(mode: str, align: str = DEFAULT_ALIGN) -> str:
    """"Fill", "Fill · left", "Black bars", …"""
    label = next(m.short for m in MODES if m.key == mode)
    return f"{label} · {align}" if mode == "fill" and align != DEFAULT_ALIGN else label


def crop_offsets(align: str) -> tuple[float, float]:
    """Where the crop window sits in the overflow, 0 = start, 0.5 = middle, 1 = end (x, y)."""
    x, y = next(a[2] for a in ALIGNS if a[0] == align)
    return (x + 1) / 2, (y + 1) / 2


def valid(fit: object, align: object) -> bool:
    return fit in {m.key for m in MODES} and align in {a[0] for a in ALIGNS}


def aspect_differs(width: int, height: int, screen_width: int, screen_height: int) -> bool:
    if not (width and height and screen_width and screen_height):
        return False
    return abs((width / height) / (screen_width / screen_height) - 1) > ASPECT_TOLERANCE


def mpv_options(fit: str, align: str = DEFAULT_ALIGN) -> str:
    """mpv options that show an image the way `fit` says ("blur" assumes the pre-rendered copy,
    which already has the screen's size, so it needs no more than "fit")."""
    if fit == "stretch":
        return "keepaspect=no"
    if fit == "center":
        return "video-unscaled=yes"
    if fit == "fill":
        x, y = next(a[2] for a in ALIGNS if a[0] == align)
        return f"panscan=1.0 video-align-x={x} video-align-y={y}"
    return "panscan=0"


def blur_filter(width: int, height: int) -> str:
    """ffmpeg -filter_complex: the image fitted inside width×height over a blurred, cropped
    copy of itself that fills the screen."""
    return (f"split[a][b];"
            f"[a]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
            f"scale=iw/{BLUR_SHRINK}:ih/{BLUR_SHRINK},boxblur=3:3,scale={width}:{height}[bg];"
            f"[b]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2")
