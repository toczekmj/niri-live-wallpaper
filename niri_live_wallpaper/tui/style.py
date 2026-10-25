"""Colours and keys shared by the TUI modules."""

from __future__ import annotations

import curses

# Colour pair numbers (see init()).
HEADER, OK, ERROR, WARNING = 1, 2, 3, 4

ESC = 27
ENTER = (ord(" "), curses.KEY_ENTER, 10, 13)  # space confirms too
BACKSPACE = (curses.KEY_BACKSPACE, 127, 8)

# How long getch() waits before the main loop refreshes the video list and status (ms).
IDLE_TIMEOUT_MS = 1000


def init() -> None:
    curses.curs_set(0)
    curses.use_default_colors()  # -1 = the terminal's own background
    curses.init_pair(HEADER, curses.COLOR_CYAN, -1)
    curses.init_pair(OK, curses.COLOR_GREEN, -1)
    curses.init_pair(ERROR, curses.COLOR_RED, -1)
    curses.init_pair(WARNING, curses.COLOR_YELLOW, -1)


def color(pair: int) -> int:
    return curses.color_pair(pair)
