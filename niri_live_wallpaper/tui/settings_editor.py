"""Frame-rate and resolution choices for one video: the import question and the per-screen editor.

The editor works on a copy of the video's settings dict (format: config.video_entry()) and
returns the new one; saving is up to the caller.
"""

from __future__ import annotations

import copy
import curses
from typing import Any, Callable

from ..media import VideoInfo
from ..niri import Output
from . import style
from .dialogs import Dialogs, put_clipped
from .formatting import fps_text, scale_text

FPS_CHOICES = (60, 30, 24, 12)
SCALE_CHOICES = (100, 75, 50, 33)  # % of the screen's native resolution


class _Marker:
    """A unique choice value, distinct from every real setting (including None = "original")."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return self.name


INHERIT = _Marker("INHERIT")  # "same as all screens": remove the per-screen override
CUSTOM = _Marker("CUSTOM")    # ask the user to type a value
CANCEL = _Marker("CANCEL")    # dialog dismissed, change nothing


class SettingsEditor:
    def __init__(self, screen: curses.window, dialogs: Dialogs, redraw: Callable[[], None]) -> None:
        self.screen = screen
        self.dialogs = dialogs
        self.redraw = redraw  # repaints the main screen under the dialogs

    # ---- the simple import question

    def ask_import_fps(self, name: str, info: VideoInfo, reason: str) -> int | None | _Marker:
        """Frame-rate question for a newly imported video.
        Returns an fps cap, None for "keep original", or CANCEL."""
        caps = [f for f in FPS_CHOICES if f < info.fps - 0.5]
        options = [f"{f} fps" for f in caps] + ["Custom…", f"Keep original ({info.fps:.3g} fps)"]
        default = caps.index(30) if 30 in caps else len(options) - 1
        self.redraw()
        i = self.dialogs.choose(f"{name} is {info.fps:.3g} fps. {reason}", options, default)
        if i is None:
            return CANCEL
        if i < len(caps):
            return caps[i]
        if i == len(caps):
            n = self.dialogs.ask_number(f"Frame rate for {name} (fps)", 1, max(1, int(info.fps)))
            return CANCEL if n is None else (None if n >= info.fps - 0.5 else n)
        return None

    # ---- the per-screen editor

    def edit(self, name: str, info: VideoInfo, entry: dict[str, Any], outputs: list[Output],
             heading: str | None = None) -> dict[str, Any]:
        """Table with a row for all screens and one per output; columns frame rate and resolution.
        Changes apply as you go; Esc or Done closes. Returns the new settings."""
        entry = copy.deepcopy(entry)
        rows: list[Output | None] = [None, *outputs]  # None = "All screens"
        row, col = 0, 0  # row == len(rows) is the Done button; col 0 = frame rate, 1 = resolution
        while True:
            self._draw(name, info, entry, rows, row, col, heading)
            key = self.dialogs.wait_for_key()
            if key in (curses.KEY_UP, ord("k")):
                row = (row - 1) % (len(rows) + 1)
            elif key in (curses.KEY_DOWN, ord("j")):
                row = (row + 1) % (len(rows) + 1)
            elif key in (curses.KEY_LEFT, curses.KEY_RIGHT, ord("h"), ord("l"), ord("\t")):
                col = 1 - col
            elif key in (style.ESC, ord("q")):
                break
            elif key in style.ENTER:
                if row == len(rows):
                    break
                self._change_cell(entry, rows[row], col, info)
        if entry.get("scale") == 100:
            entry.pop("scale")  # 100 is the default; keep the file minimal
        return entry

    def _change_cell(self, entry: dict[str, Any], output: Output | None, col: int,
                     info: VideoInfo) -> None:
        key = "fps" if col == 0 else "scale"
        all_fps, all_scale = entry.get("fps"), entry.get("scale", 100)
        if output is None:
            value = (self._pick_fps("Frame rate on all screens", info.fps, all_fps) if col == 0
                     else self._pick_scale("Resolution on all screens", all_scale))
            if value is not CANCEL:
                entry[key] = value
            return

        screens = entry.setdefault("screens", {})
        override = screens.setdefault(output.name, {})
        current = override.get(key, INHERIT)
        if col == 0:
            value = self._pick_fps(f"Frame rate on {output.name}", info.fps, current,
                                   inherit_label=fps_text(all_fps))
        else:
            value = self._pick_scale(f"Resolution on {output.name}", current, output,
                                     inherit_label=scale_text(all_scale, output.width, output.height))
        if value is INHERIT:
            override.pop(key, None)
        elif value is not CANCEL:
            override[key] = value
        # Drop empty dicts so the file only lists real overrides.
        if not override:
            screens.pop(output.name)
        if not screens:
            entry.pop("screens")

    def _draw(self, name: str, info: VideoInfo, entry: dict[str, Any], rows: list[Output | None],
              row: int, col: int, heading: str | None) -> None:
        self.redraw()
        h, w = self.screen.getmaxyx()
        box_w, box_h = min(84, w - 2), min(len(rows) + 10, h - 2)
        win = curses.newwin(box_h, box_w, max(0, (h - box_h) // 2), max(0, (w - box_w) // 2))
        win.box()
        x_fps, x_res = 20, 44

        def put(y: int, x: int, text: str, attr: int = 0) -> None:
            put_clipped(win, y, x, text, max(0, box_w - x - 2), attr)

        put(1, 3, heading or f"Settings for {name}", curses.A_BOLD)
        put(2, 3, f"Source: {info.width}×{info.height} · {info.fps:.3g} fps", curses.A_DIM)
        put(4, 3, "Screen", curses.A_DIM)
        put(4, x_fps, "Frame rate", curses.A_DIM)
        put(4, x_res, "Resolution", curses.A_DIM)
        all_fps, all_scale = entry.get("fps"), entry.get("scale", 100)
        for i, output in enumerate(rows):
            if output is None:
                label, fps, scale, fps_inherited, scale_inherited, size = (
                    "All screens", all_fps, all_scale, False, False, ())
            else:
                override = entry.get("screens", {}).get(output.name, {})
                fps_inherited, scale_inherited = "fps" not in override, "scale" not in override
                fps = all_fps if fps_inherited else override["fps"]
                scale = all_scale if scale_inherited else override["scale"]
                label, size = output.name, (output.width, output.height)
            put(5 + i, 3, label)
            put(5 + i, x_fps, ("= " if fps_inherited else "") + fps_text(fps),
                (curses.A_REVERSE if (row, col) == (i, 0) else 0)
                | (curses.A_DIM if fps_inherited else 0))
            put(5 + i, x_res, ("= " if scale_inherited else "") + scale_text(scale, *size),
                (curses.A_REVERSE if (row, col) == (i, 1) else 0)
                | (curses.A_DIM if scale_inherited else 0))
        put(6 + len(rows), 3, " Done ", curses.A_REVERSE if row == len(rows) else curses.A_BOLD)
        put(8 + len(rows), 3, "↑↓←→ move   enter change   Esc done   \"= \" same as all screens",
            curses.A_DIM)
        win.refresh()

    # ---- choice dialogs for one cell

    def _pick(self, title: str, values: list[Any], labels: list[str], current: Any,
              ask_custom: Callable[[], Any]) -> Any:
        """Returns the chosen value (possibly INHERIT), or CANCEL."""
        # A typed-in value that isn't one of the presets highlights "Custom…".
        default = values.index(current) if current in values else values.index(CUSTOM)
        i = self.dialogs.choose(title, labels, default)
        if i is None:
            return CANCEL
        return ask_custom() if values[i] is CUSTOM else values[i]

    def _pick_fps(self, title: str, source_fps: float, current: Any,
                  inherit_label: str | None = None) -> Any:
        values: list[Any] = []
        labels: list[str] = []
        if inherit_label is not None:
            values.append(INHERIT)
            labels.append(f"Same as all screens ({inherit_label})")
        for fps in FPS_CHOICES:
            if fps < source_fps - 0.5:  # only rates that actually lower it
                values.append(fps)
                labels.append(f"{fps} fps")
        values += [CUSTOM, None]
        labels += ["Custom…", f"Original ({source_fps:.3g} fps)"]

        def ask_custom() -> Any:
            n = self.dialogs.ask_number("Frame rate (fps)", 1, max(1, int(source_fps)))
            return CANCEL if n is None else (None if n >= source_fps - 0.5 else n)

        return self._pick(title, values, labels, current, ask_custom)

    def _pick_scale(self, title: str, current: Any, output: Output | None = None,
                    inherit_label: str | None = None) -> Any:
        size = (output.width, output.height) if output else (None, None)
        values: list[Any] = []
        labels: list[str] = []
        if inherit_label is not None:
            values.append(INHERIT)
            labels.append(f"Same as all screens ({inherit_label})")
        values += [*SCALE_CHOICES, CUSTOM]
        labels += [scale_text(s, *size) for s in SCALE_CHOICES] + ["Custom %…"]

        def ask_custom() -> Any:
            n = self.dialogs.ask_number("Resolution in % of the screen's native size", 10, 100)
            return CANCEL if n is None else n

        return self._pick(title, values, labels, current, ask_custom)
