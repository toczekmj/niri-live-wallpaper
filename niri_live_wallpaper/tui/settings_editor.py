"""Frame-rate, resolution and fit choices for one video or image: the import questions and the
per-screen editor.

The editor works on a copy of the video's settings dict (format: config.video_entry()) and
returns the new one; saving is up to the caller.
"""

from __future__ import annotations

import copy
import curses
from collections.abc import Callable
from typing import Any

from .. import config, fit
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
CUSTOM = _Marker("CUSTOM")  # ask the user to type a value
CANCEL = _Marker("CANCEL")  # dialog dismissed, change nothing


class SettingsEditor:
    def __init__(
        self, screen: curses.window, dialogs: Dialogs, redraw: Callable[[], None]
    ) -> None:
        self.screen = screen
        self.dialogs = dialogs
        self.redraw = redraw  # repaints the main screen under the dialogs

    # ---- the simple import question

    def ask_import_fps(
        self, name: str, info: VideoInfo, reason: str
    ) -> int | None | _Marker:
        """Frame-rate question for a newly imported video.
        Returns an fps cap, None for "keep original", or CANCEL."""
        caps = [f for f in FPS_CHOICES if f < info.fps - 0.5]
        options = [f"{f} fps" for f in caps] + [
            "Custom…",
            f"Keep original ({info.fps:.3g} fps)",
        ]
        default = caps.index(30) if 30 in caps else len(options) - 1
        self.redraw()
        i = self.dialogs.choose(
            f"{name} is {info.fps:.3g} fps. {reason}", options, default
        )
        if i is None:
            return CANCEL
        if i < len(caps):
            return caps[i]
        if i == len(caps):
            n = self.dialogs.ask_number(
                f"Frame rate for {name} (fps)", 1, max(1, int(info.fps))
            )
            return CANCEL if n is None else (None if n >= info.fps - 0.5 else n)
        return None

    # ---- how a picture fits the screen

    def pick_fit(
        self,
        name: str,
        info: VideoInfo,
        outputs: list[Output],
        current: Any,
        reason: str = "How should it fit the screen?",
        inherit_label: str | None = None,
        on_preview: Callable[[Any], None] | None = None,
    ) -> tuple[str, str] | _Marker:
        """Fit mode, then (when cropping would happen on `outputs`) which part to keep.
        `current` is (fit key, align key) or INHERIT. Returns (fit key, align key), INHERIT
        (only offered with inherit_label), or CANCEL.

        on_preview(value) is called with what each highlighted option would give, in the same
        forms as the return value; on CANCEL it is called with `current` again."""

        def show(value: Any) -> None:
            if on_preview:
                on_preview(value)

        keys: list[Any] = [m.key for m in fit.MODES]
        labels = [m.label for m in fit.MODES]
        if inherit_label is not None:
            keys.insert(0, INHERIT)
            labels.insert(0, f"Same as all screens ({inherit_label})")
        mode, align = current if current is not INHERIT else (fit.DEFAULT_FIT, fit.DEFAULT_ALIGN)
        show(current)  # the menu opens on the current choice: show it
        self.redraw()

        def show_mode(i: int) -> None:
            if keys[i] is INHERIT:
                show(INHERIT)
            else:  # keep the crop focus while browsing, it only matters for "fill"
                show((keys[i], align if keys[i] == "fill" else fit.DEFAULT_ALIGN))

        i = self.dialogs.choose(
            f"{name} is {info.width}×{info.height}. {reason}",
            labels,
            keys.index(INHERIT if current is INHERIT else mode),
            on_highlight=show_mode,
        )
        if i is None:
            show(current)
            return CANCEL
        if keys[i] is INHERIT:
            return INHERIT
        mode = keys[i]
        crops = not outputs or any(
            fit.aspect_differs(info.width, info.height, o.width, o.height) for o in outputs
        )
        if mode != "fill" or not crops:
            return mode, align if mode == "fill" else fit.DEFAULT_ALIGN
        aligns = [a[0] for a in fit.ALIGNS]
        self.redraw()
        show((mode, align))  # (the picture may still show another focus from a previous highlight)
        j = self.dialogs.choose(
            "Which part of the picture should stay visible?",
            [a[1] for a in fit.ALIGNS],
            aligns.index(align),
            on_highlight=lambda j: show((mode, aligns[j])),
        )
        if j is None:
            show(current)
            return CANCEL
        return mode, aligns[j]

    # ---- the per-screen editor

    def edit(
        self,
        name: str,
        info: VideoInfo,
        entry: dict[str, Any],
        outputs: list[Output],
        heading: str | None = None,
        on_change: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any] | _Marker:
        """Table with a row for all screens and one per output; columns frame rate, resolution
        and fit (images only have fit). on_change(settings) is called after every change, so the
        caller can show it live. Esc or Done keeps the settings and returns them; c or q cancels
        and returns CANCEL (the caller puts back what it showed)."""
        entry = copy.deepcopy(entry)
        rows: list[Output | None] = [None, *outputs]  # None = "All screens"
        columns = ["fit"] if info.is_image else ["fps", "scale", "fit"]
        # row == len(rows) is the Done button
        row, col = 0, 0
        while True:
            self._draw(name, info, entry, rows, columns, row, col, heading)
            key = self.dialogs.wait_for_key()
            if key in (curses.KEY_UP, ord("k")):
                row = (row - 1) % (len(rows) + 1)
            elif key in (curses.KEY_DOWN, ord("j")):
                row = (row + 1) % (len(rows) + 1)
            elif key in (curses.KEY_LEFT, ord("h")):
                col = (col - 1) % len(columns)
            elif key in (curses.KEY_RIGHT, ord("l"), ord("\t")):
                col = (col + 1) % len(columns)
            elif key in (ord("c"), ord("q")):
                return CANCEL
            elif key == style.ESC:
                break
            elif key in style.ENTER:
                if row == len(rows):
                    break
                before = copy.deepcopy(entry)
                self._change_cell(name, entry, rows[row], columns[col], info, outputs, on_change)
                if on_change and entry != before and columns[col] != "fit":
                    on_change(self._tidy(entry))  # (fit reports its own changes, as you browse)
        return self._tidy(entry)

    @staticmethod
    def _tidy(entry: dict[str, Any]) -> dict[str, Any]:
        """A copy of `entry` without the defaults the editor leaves lying around."""
        entry = copy.deepcopy(entry)
        if entry.get("scale") == 100:
            entry.pop("scale")  # 100 is the default; keep the file minimal
        return entry

    def _change_cell(
        self,
        name: str,
        entry: dict[str, Any],
        output: Output | None,
        column: str,
        info: VideoInfo,
        outputs: list[Output],
        on_change: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        if column == "fit":
            self._change_fit(name, entry, output, info, outputs, on_change)
            return
        all_fps, all_scale = entry.get("fps"), entry.get("scale", 100)
        if output is None:
            value = (
                self._pick_fps("Frame rate on all screens", info.fps, all_fps)
                if column == "fps"
                else self._pick_scale("Resolution on all screens", all_scale)
            )
            if value is not CANCEL:
                entry[column] = value
            return

        screens = entry.setdefault("screens", {})
        override = screens.setdefault(output.name, {})
        current = override.get(column, INHERIT)
        if column == "fps":
            value = self._pick_fps(
                f"Frame rate on {output.name}",
                info.fps,
                current,
                inherit_label=fps_text(all_fps),
            )
        else:
            value = self._pick_scale(
                f"Resolution on {output.name}",
                current,
                output,
                inherit_label=scale_text(all_scale, output.width, output.height),
            )
        if value is INHERIT:
            override.pop(column, None)
        elif value is not CANCEL:
            override[column] = value
        # Drop empty dicts so the file only lists real overrides.
        if not override:
            screens.pop(output.name)
        if not screens:
            entry.pop("screens")

    def _change_fit(
        self,
        name: str,
        entry: dict[str, Any],
        output: Output | None,
        info: VideoInfo,
        outputs: list[Output],
        on_change: Callable[[dict[str, Any]], None] | None,
    ) -> None:
        """Change the fit of one row, reporting each highlighted option through on_change as the
        user browses; leaves `entry` as it was if the user cancels."""
        original = copy.deepcopy(entry)
        shown = self._tidy(original)

        def show(value: Any) -> None:
            nonlocal shown
            entry.clear()
            entry.update(copy.deepcopy(original))
            self._store_fit(entry, output, value)
            now = self._tidy(entry)
            if on_change and now != shown:
                shown = now
                on_change(now)

        if output is None:
            current: Any = (entry.get("fit", fit.DEFAULT_FIT), entry.get("align", fit.DEFAULT_ALIGN))
            rows, reason, inherit_label = outputs, "How should it fit the screen?", None
        else:
            override = entry.get("screens", {}).get(output.name, {})
            current = (
                (override["fit"], override.get("align", fit.DEFAULT_ALIGN))
                if "fit" in override
                else INHERIT
            )
            all_fit = (entry.get("fit", fit.DEFAULT_FIT), entry.get("align", fit.DEFAULT_ALIGN))
            rows, reason = [output], f"How should it fit {output.name}?"
            inherit_label = fit.short_label(*all_fit)
        value = self.pick_fit(name, info, rows, current, reason, inherit_label, on_preview=show)
        show(current if value is CANCEL else value)

    @staticmethod
    def _store_fit(entry: dict[str, Any], output: Output | None, value: Any) -> None:
        """Write a fit choice (or INHERIT) for one row of `entry`, tidying up empty overrides."""
        if output is None:
            config.set_fit(entry, *value)
            return
        screens = entry.setdefault("screens", {})
        override = screens.setdefault(output.name, {})
        if value is INHERIT:
            override.pop("fit", None)
            override.pop("align", None)
        else:
            config.set_fit(override, *value, keep_default=True)
        if not override:
            screens.pop(output.name)
        if not screens:
            entry.pop("screens")

    def _draw(
        self,
        name: str,
        info: VideoInfo,
        entry: dict[str, Any],
        rows: list[Output | None],
        columns: list[str],
        row: int,
        col: int,
        heading: str | None,
    ) -> None:
        self.redraw()
        h, w = self.screen.getmaxyx()
        box_w, box_h = min(100, w - 2), min(len(rows) + 10, h - 2)
        win = curses.newwin(
            box_h, box_w, max(0, (h - box_h) // 2), max(0, (w - box_w) // 2)
        )
        win.box()
        titles = {"fps": "Frame rate", "scale": "Resolution", "fit": "Fit"}
        x_of = dict(zip(columns, (20, 44, 70) if len(columns) == 3 else (20,)))

        def put(y: int, x: int, text: str, attr: int = 0) -> None:
            put_clipped(win, y, x, text, max(0, box_w - x - 2), attr)

        put(1, 3, heading or f"Settings for {name}", curses.A_BOLD)
        source = f"Source: {info.width}×{info.height}"
        put(2, 3, source if info.is_image else f"{source} · {info.fps:.3g} fps", curses.A_DIM)
        put(4, 3, "Screen", curses.A_DIM)
        for column in columns:
            put(4, x_of[column], titles[column], curses.A_DIM)
        for i, output in enumerate(rows):
            put(5 + i, 3, "All screens" if output is None else output.name)
            for j, column in enumerate(columns):
                text, inherited = self._cell(column, entry, output)
                put(
                    5 + i,
                    x_of[column],
                    ("= " if inherited else "") + text,
                    (curses.A_REVERSE if (row, col) == (i, j) else 0)
                    | (curses.A_DIM if inherited else 0),
                )
        put(
            6 + len(rows),
            3,
            " Done ",
            curses.A_REVERSE if row == len(rows) else curses.A_BOLD,
        )
        put(
            8 + len(rows),
            3,
            '↑↓←→ move   enter change (shown live)   Esc keep   c cancel   "= " = same as all screens',
            curses.A_DIM,
        )
        win.refresh()

    @staticmethod
    def _cell(column: str, entry: dict[str, Any], output: Output | None) -> tuple[str, bool]:
        """Text of one table cell and whether it is inherited from the "All screens" row."""
        if output is None:
            source, inherited = entry, False
        else:
            override = entry.get("screens", {}).get(output.name, {})
            inherited = column not in override  # a fit override always carries its "fit" key
            source = entry if inherited else override
        if column == "fps":
            return fps_text(source.get("fps")), inherited
        if column == "scale":
            size = (output.width, output.height) if output else ()
            return scale_text(source.get("scale", 100), *size), inherited
        mode = source.get("fit", fit.DEFAULT_FIT)
        return fit.short_label(mode, source.get("align", fit.DEFAULT_ALIGN)), inherited

    # ---- choice dialogs for one cell

    def _pick(
        self,
        title: str,
        values: list[Any],
        labels: list[str],
        current: Any,
        ask_custom: Callable[[], Any],
    ) -> Any:
        """Returns the chosen value (possibly INHERIT), or CANCEL."""
        # A typed-in value that isn't one of the presets highlights "Custom…".
        default = values.index(current) if current in values else values.index(CUSTOM)
        i = self.dialogs.choose(title, labels, default)
        if i is None:
            return CANCEL
        return ask_custom() if values[i] is CUSTOM else values[i]

    def _pick_fps(
        self,
        title: str,
        source_fps: float,
        current: Any,
        inherit_label: str | None = None,
    ) -> Any:
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

    def _pick_scale(
        self,
        title: str,
        current: Any,
        output: Output | None = None,
        inherit_label: str | None = None,
    ) -> Any:
        size = (output.width, output.height) if output else (None, None)
        values: list[Any] = []
        labels: list[str] = []
        if inherit_label is not None:
            values.append(INHERIT)
            labels.append(f"Same as all screens ({inherit_label})")
        values += [*SCALE_CHOICES, CUSTOM]
        labels += [scale_text(s, *size) for s in SCALE_CHOICES] + ["Custom %…"]

        def ask_custom() -> Any:
            n = self.dialogs.ask_number(
                "Resolution in % of the screen's native size", 10, 100
            )
            return CANCEL if n is None else n

        return self._pick(title, values, labels, current, ask_custom)
