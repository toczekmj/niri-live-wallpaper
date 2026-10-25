"""Modal dialogs drawn over the main screen: yes/no, pick one option, type a short value."""

from __future__ import annotations

import curses
from typing import Callable, TypeVar

from . import style

T = TypeVar("T")


def put_clipped(win: curses.window, y: int, x: int, text: str, width: int, attr: int = 0) -> None:
    """addnstr that ignores text not fitting a small terminal: better clipped than crashing."""
    try:
        win.addnstr(y, x, text, width, attr)
    except curses.error:
        pass


class Dialogs:
    def __init__(self, screen: curses.window) -> None:
        self.screen = screen

    def _window(self, lines: list[str], width: int | None = None) -> tuple[curses.window, int]:
        """A centred window big enough for `lines`. Returns it with its width."""
        h, w = self.screen.getmaxyx()
        box_w = min((width or max(len(line) for line in lines)) + 6, w - 2)
        box_h = min(len(lines) + 4, h - 2)
        win = curses.newwin(box_h, box_w, max(0, (h - box_h) // 2), max(0, (w - box_w) // 2))
        return win, box_w

    def wait_for_key(self) -> int:
        """Block until a key is pressed (the main loop otherwise times out to refresh)."""
        self.screen.timeout(-1)
        try:
            return self.screen.getch()
        finally:
            self.screen.timeout(style.IDLE_TIMEOUT_MS)

    def confirm(self, question: str) -> bool:
        text = f"{question} [y/n]"
        win, box_w = self._window([text])
        win.box()
        put_clipped(win, 2, 3, text, box_w - 6, curses.A_BOLD)
        win.refresh()
        while True:
            key = self.wait_for_key()
            if key in (ord("y"), ord("Y")):
                return True
            if key in (ord("n"), ord("N"), style.ESC, ord("q")):
                return False

    def choose(self, title: str, options: list[str], default: int = 0) -> int | None:
        """Pick one of `options` with ↑↓ and enter. Returns its index, or None on Esc."""
        selected = default
        win, box_w = self._window([title, ""] + [f" › {o} " for o in options])
        while True:
            win.erase()
            win.box()
            put_clipped(win, 1, 3, title, box_w - 6, curses.A_BOLD)
            for i, option in enumerate(options):
                put_clipped(win, 3 + i, 3, f" › {option} ", box_w - 6,
                          curses.A_REVERSE if i == selected else 0)
            win.refresh()
            key = self.wait_for_key()
            if key in (curses.KEY_UP, ord("k")):
                selected = (selected - 1) % len(options)
            elif key in (curses.KEY_DOWN, ord("j")):
                selected = (selected + 1) % len(options)
            elif key in style.ENTER:
                return selected
            elif key in (style.ESC, ord("q")):
                return None

    def ask_input(self, prompt: str, hint: str, allowed: str, parse: Callable[[str], T],
                  text: str = "") -> T | None:
        """Read a short line made of `allowed` characters.

        parse(text) returns the value or raises ValueError with a message to show under the input.
        Returns the parsed value, or None on Esc.
        """
        error = ""
        win, box_w = self._window([prompt, "", "", ""], width=max(len(prompt), len(hint), 40))
        curses.curs_set(1)
        try:
            while True:
                win.erase()
                win.box()
                put_clipped(win, 1, 3, prompt, box_w - 6, curses.A_BOLD)
                put_clipped(win, 4, 3, error or hint, box_w - 6,
                          style.color(style.ERROR) if error else curses.A_DIM)
                put_clipped(win, 2, 3, f"> {text}", box_w - 6)  # last, so the cursor ends up here
                win.refresh()
                key = self.wait_for_key()
                if key == style.ESC:
                    return None
                if key in style.BACKSPACE:
                    text = text[:-1]
                elif 0 <= key < 256 and chr(key) in allowed and len(text) < 8:
                    text += chr(key)
                elif key in (curses.KEY_ENTER, 10, 13):
                    try:
                        return parse(text)
                    except ValueError as e:
                        error = str(e)
        finally:
            curses.curs_set(0)

    def ask_number(self, prompt: str, low: int, high: int) -> int | None:
        """Read a whole number in [low, high]. Returns it, or None on Esc."""
        def parse(text: str) -> int:
            if text and low <= int(text) <= high:
                return int(text)
            raise ValueError(f"Enter a number from {low} to {high}")

        return self.ask_input(prompt, f"{low}–{high}, enter to confirm, Esc to cancel",
                              "0123456789", parse)
