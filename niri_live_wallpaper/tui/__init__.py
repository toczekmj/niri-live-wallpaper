"""The interactive terminal UI (curses)."""

from __future__ import annotations

import curses
import os

from .. import paths


def run() -> None:
    from .app import App

    paths.VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("ESCDELAY", "25")  # curses waits 1 s after Esc by default; feels broken
    curses.wrapper(lambda screen: App(screen).run())
