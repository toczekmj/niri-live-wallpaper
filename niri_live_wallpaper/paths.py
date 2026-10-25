"""Every file and directory the app reads or writes, in one place.

XDG base directories are honoured (XDG_CONFIG_HOME, XDG_DATA_HOME, XDG_CACHE_HOME,
XDG_STATE_HOME), which also lets tests relocate everything.

Other modules use these as `paths.NAME` at call time rather than `from .paths import NAME`, so a
test can patch a single attribute here and every user sees it.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_ID = "niri-live-wallpaper"


def _xdg_dir(variable: str, default: str) -> Path:
    return Path(os.environ.get(variable) or Path.home() / default)


HOME = Path.home()
CONFIG_HOME = _xdg_dir("XDG_CONFIG_HOME", ".config")

# Our own files.
VIDEO_DIR = _xdg_dir("XDG_DATA_HOME", ".local/share") / APP_ID / "videos"
CONFIG_FILE = CONFIG_HOME / APP_ID / "config.json"
CACHE_DIR = _xdg_dir("XDG_CACHE_HOME", ".cache") / APP_ID
FRAME_DIR = CACHE_DIR / "frames"          # stills handed to DMS for theming
OPTIMIZED_DIR = CACHE_DIR / "optimized"   # per-screen copies, see variants.py
LOG_FILE = _xdg_dir("XDG_STATE_HOME", ".local/state") / APP_ID / "tui.log"
UNIT_FILE = CONFIG_HOME / "systemd/user" / f"{APP_ID}.service"

# Other programs' files, read only.
NIRI_CONFIG_DIR = CONFIG_HOME / "niri"
DMS_SETTINGS = CONFIG_HOME / "DankMaterialShell/settings.json"

# GPU device used for VA-API encoding (the first render node).
VAAPI_DEVICE = Path("/dev/dri/renderD128")


def tilde(path: Path) -> str:
    """Path for display, with the home directory shortened to ~."""
    text = path.as_posix()
    home = HOME.as_posix()
    if text == home or text.startswith(home + "/"):
        return "~" + text[len(home):]
    return text
