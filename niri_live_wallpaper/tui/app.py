"""The main screen: setup checks, video list, actions, status line, and what each key does.

The app doesn't play video. It edits config.json and controls the systemd service (systemd.py),
which runs service.py.
"""

from __future__ import annotations

import curses
import logging
import time
from pathlib import Path
from typing import Any

from .. import checks, config, cycling, desktop, dms, library, media, niri, paths, proc, systemd, variants
from ..media import EncodeResult
from . import style
from .dialogs import Dialogs
from .formatting import describe_video, human_duration, import_summary
from .settings_editor import CANCEL, SettingsEditor

log = logging.getLogger(__name__)

# (key, label). None labels are built from the current state in App.action_label().
ACTIONS = [
    ("import", "Import videos (fuzzy finder, Tab marks several)"),
    ("open", "Open video folder in file manager"),
    ("stop", "Stop live wallpaper"),
    ("cycle", None),
    ("autostart", None),
    ("askfps", None),
    ("askscreens", None),
    ("quit", "Quit"),
]

FPS_ASK_ABOVE = 30  # the import question is asked for videos faster than this

# A list entry: ("video", file name) or ("action", action key).
Item = tuple[str, str]

HEADER_ROWS = 9  # title, separator, "Setup", three checks, two config lines, separator
SETUP_CHECK_EVERY = 5  # idle ticks between setup re-checks (each runs a few programs)
FOOTER_ROWS = 5  # separator, status, message, two lines of key help


class App:
    def __init__(self, screen: curses.window) -> None:
        self.screen = screen
        self.dialogs = Dialogs(screen)
        self.editor = SettingsEditor(screen, self.dialogs, redraw=self.draw)
        self.cfg = config.load()
        self.videos = library.list_videos()
        self.cursor = 0
        self.message, self.message_is_error = "", False
        self.has_mpvpaper = proc.available("mpvpaper")
        self.ticks = 0
        self.refresh_status()
        style.init()
        self.screen.timeout(style.IDLE_TIMEOUT_MS)

    # ------------------------------------------------------------------ state

    def items(self) -> list[Item]:
        return [("video", v) for v in self.videos] + [("action", key) for key, _ in ACTIONS]

    def selected(self) -> Item:
        return self.items()[self.cursor]

    def refresh_status(self, setup_checks: bool = True) -> None:
        """Things that can change outside the app: the service state and the setup checks."""
        self.autostart = systemd.is_enabled()
        self.active = systemd.is_active()
        if setup_checks:
            self.checks = [
                checks.niri_config(niri.layer_rule_present(), niri.background_transparent()),
                checks.other_wallpapers(dms.builtin_wallpaper_enabled(), niri.other_background_surfaces()),
                checks.session(systemd.session_problem()),
            ]

    def rescan(self) -> None:
        """Re-read the video folder (files dropped in) and the config (the service may have
        cycled), keeping the cursor on the same entry."""
        items = self.items()
        current = items[self.cursor] if self.cursor < len(items) else None
        self.videos = library.list_videos()
        self.cfg = config.load()
        items = self.items()
        self.cursor = items.index(current) if current in items else min(self.cursor, len(items) - 1)

    def say(self, text: str, error: bool = False) -> None:
        self.message, self.message_is_error = text, error
        if error and text:
            log.warning("%s", text)

    def action_label(self, action: str) -> str:
        if action == "cycle":
            return f"Cycle wallpapers: [{cycling.label(self.cfg)}]"
        if action == "autostart":
            return f"Start at login: [{'on' if self.autostart else 'off'}]"
        if action == "askfps":
            on = config.ask_fps(self.cfg)
            return f"Ask to lower frame rate on import (>{FPS_ASK_ABOVE} fps): [{'on' if on else 'off'}]"
        if action == "askscreens":
            on = config.ask_screens(self.cfg)
            return f"Ask for per-screen frame rate & resolution on import: [{'on' if on else 'off'}]"
        return dict(ACTIONS)[action]

    # ------------------------------------------------------------------ drawing

    def put(self, y: int, x: int, text: str, attr: int = 0) -> None:
        h, w = self.screen.getmaxyx()
        if 0 <= y < h and x < w:
            try:
                self.screen.addnstr(y, x, text, w - x - 1, attr)
            except curses.error:
                pass

    def draw(self) -> None:
        self.screen.erase()
        self._draw_header()
        self._draw_list()
        self._draw_footer()
        self.screen.refresh()

    def _draw_header(self) -> None:
        _, w = self.screen.getmaxyx()
        looks = {checks.OK: ("✓", style.color(style.OK)),
                 checks.PROBLEM: ("✗", style.color(style.WARNING)),
                 checks.INFO: ("–", curses.A_DIM)}
        self.put(0, 1, "Niri Live Wallpaper", curses.A_BOLD)
        self.put(1, 1, "─" * (w - 3), curses.A_DIM)
        self.put(2, 1, "Setup", style.color(style.HEADER) | curses.A_BOLD)
        niri_check, wallpaper_check, session_check = self.checks
        mark, attr = looks[niri_check.status]
        self.put(3, 1, f"{mark} {niri_check.text}", attr)
        # Plain text at column 0, no box: mouse selection copies exactly these lines.
        config_attr = curses.A_DIM if niri_check.status == checks.OK else curses.A_BOLD
        self.put(4, 0, niri.LAYER_RULE, config_attr)
        self.put(5, 0, niri.TRANSPARENT_BACKGROUND, config_attr)
        for y, check in ((6, wallpaper_check), (7, session_check)):
            mark, attr = looks[check.status]
            self.put(y, 1, f"{mark} {check.text}", attr)
        self.put(8, 1, "─" * (w - 3), curses.A_DIM)

    def _draw_list(self) -> None:
        h, _ = self.screen.getmaxyx()
        heading = style.color(style.HEADER) | curses.A_BOLD
        # Rows: ("header", text) | ("item", index into items()) | ("note", text) | ("blank", "")
        rows: list[tuple[str, Any]] = [("header", f"Videos  ({paths.tilde(paths.VIDEO_DIR)})")]
        if self.videos:
            rows += [("item", i) for i in range(len(self.videos))]
        else:
            rows.append(("note", "No videos yet. Import one or drop files into the folder."))
        rows += [("blank", ""), ("header", "Actions")]
        rows += [("item", len(self.videos) + i) for i in range(len(ACTIONS))]

        body_height = max(1, h - HEADER_ROWS - FOOTER_ROWS)
        cursor_row = rows.index(("item", self.cursor))
        scroll = max(0, cursor_row - body_height + 1)  # keep the cursor visible

        items = self.items()
        name_width = max((len(v) for v in self.videos), default=0) + 2
        for y, (kind, value) in enumerate(rows[scroll:scroll + body_height], start=HEADER_ROWS):
            if kind == "header":
                self.put(y, 1, value, heading)
            elif kind == "note":
                self.put(y, 3, value, curses.A_DIM)
            elif kind == "item":
                highlight = curses.A_REVERSE if value == self.cursor else 0
                item_kind, item = items[value]
                if item_kind == "video":
                    current = item == self.cfg.get("wallpaper")
                    self.put(y, 1, f" {'●' if current else '○'} {item} ",
                             highlight | (style.color(style.OK) if current else 0))
                    details = describe_video(media.probe(paths.VIDEO_DIR / item),
                                             config.video_entry(self.cfg, item))
                    self.put(y, 4 + name_width, details, curses.A_DIM)
                else:
                    self.put(y, 1, f" › {self.action_label(item)} ", highlight)

    def _draw_footer(self) -> None:
        h, w = self.screen.getmaxyx()
        y = h - FOOTER_ROWS
        self.put(y, 1, "─" * (w - 3), curses.A_DIM)
        status = [f"wallpaper: {'playing' if self.active else 'stopped'}",
                  f"autostart: {'on' if self.autostart else 'off'}"]
        remaining = cycling.seconds_until_next(self.cfg, time.time())
        if remaining is not None:
            status.append(f"cycle: {cycling.label(self.cfg)}, next in {human_duration(remaining)}")
        if not self.has_mpvpaper:
            status.append("mpvpaper: NOT INSTALLED (yay -S mpvpaper)")
        self.put(y + 1, 1, "   ".join(status),
                 style.color(style.ERROR) if not self.has_mpvpaper else curses.A_DIM)
        if self.message:
            self.put(y + 2, 1, self.message,
                     style.color(style.ERROR if self.message_is_error else style.OK))
        self.put(y + 3, 1, "↑↓/jk move   space/enter select wallpaper or run action   "
                           "e fps/resolution   d delete   s stop", curses.A_DIM)
        self.put(y + 4, 1, "i import   o open folder   a autostart   c copy niri config   q quit",
                 curses.A_DIM)

    # ------------------------------------------------------------------ per-video settings

    def edit_video(self, name: str, heading: str | None = None) -> bool:
        """Open the settings editor for `name` and save the result (even if unchanged, so the
        import question isn't asked again). Returns True if the settings changed."""
        info = media.probe(paths.VIDEO_DIR / name)
        if not info:
            self.say(f"Could not read {name}", error=True)
            return False
        before = config.video_entry(self.cfg, name)
        after = self.editor.edit(name, info, before or {}, niri.outputs(), heading)
        self.cfg = config.save_video_entry(name, after)
        return after != (before or {})

    def maybe_ask(self, name: str) -> None:
        """First import or selection of a video: open the per-screen editor or ask about the frame
        rate, depending on the two "Ask … on import" toggles."""
        if config.video_entry(self.cfg, name) is not None:
            return
        if config.ask_screens(self.cfg):
            self.edit_video(name, heading=f"{name}: frame rate & resolution per screen")
            return
        if not config.ask_fps(self.cfg):
            return
        info = media.probe(paths.VIDEO_DIR / name)
        if not info or info.fps <= FPS_ASK_ABOVE + 0.5:
            return
        choice = self.editor.ask_import_fps(name, info, "Convert to a lower frame rate to save power?")
        if choice is not CANCEL:
            self.cfg = config.save_video_entry(name, {"fps": choice})

    def optimize(self, name: str, prefix: str = "") -> EncodeResult:
        """Encode the per-screen copies `name` needs, showing progress (after `prefix`, e.g.
        "(2/3) "). Esc cancels."""
        jobs = variants.jobs_for(self.cfg, name, niri.outputs())
        if not jobs:
            return EncodeResult.OK
        last_draw = 0.0

        def progress(output: str, copy: Path, fraction: float) -> bool:
            nonlocal last_draw
            if time.monotonic() - last_draw > 0.2:
                last_draw = time.monotonic()
                size, _, fps = copy.stem.partition("@")
                target = size.replace("x", "×") + (f" @ {fps} fps" if fps != "src" else "")
                self.say(f"{prefix}Optimizing {name} for {output} ({target})… {fraction:.0%}"
                         "   Esc to cancel")
                self.draw()
            self.screen.timeout(0)  # peek for Esc without blocking the encode
            key = self.screen.getch()
            self.screen.timeout(style.IDLE_TIMEOUT_MS)
            return key == style.ESC

        self.say(f"{prefix}Optimizing {name}…")
        self.draw()
        result, failed = variants.ensure(name, jobs, progress)
        if result is EncodeResult.CANCELLED:
            self.say("Optimization cancelled; the original file is played until it's done", error=True)
        elif failed:
            self.say(f"Optimizing failed for {', '.join(failed)}; the original file is played there",
                     error=True)
        else:
            self.say("")
        return result

    # ------------------------------------------------------------------ actions

    def set_wallpaper(self, name: str) -> None:
        self.maybe_ask(name)  # also covers files dropped in via the file manager
        self.optimize(name)
        self.cfg = config.update(wallpaper=name, last_change=time.time())

        if not self.cfg.get("autostart_prompted"):
            self.cfg = config.update(autostart_prompted=True)
            self.draw()
            if self.dialogs.confirm("Start your live wallpaper automatically at login?"):
                self.toggle_autostart(force=True)

        if not self.has_mpvpaper:
            self.say(f"Saved {name}. Install mpvpaper to play it: yay -S mpvpaper", error=True)
            return
        ok, error = systemd.restart()
        self.refresh_status()
        if ok:
            self.say(f"Live wallpaper set to {name}")
        else:
            self.say(f"Failed to start {systemd.UNIT}: "
                     f"{error or 'see journalctl --user -u ' + systemd.UNIT}", error=True)

    def edit_settings(self) -> None:
        kind, name = self.selected()
        if kind != "video":
            self.say("Move to a video to edit its frame rate & resolution")
            return
        if not self.edit_video(name):
            if not self.message_is_error:
                self.say("Settings unchanged")
            return
        # Copies only the old settings needed go. A disconnected screen's copy is rebuilt by the
        # service when that screen comes back.
        variants.prune(name, variants.jobs_for(self.cfg, name, niri.outputs()))
        self.optimize(name)
        if name == self.cfg.get("wallpaper") and self.active:
            systemd.reload()  # the service restarts only the screens whose file changed
        if not self.message_is_error:
            self.say(f"Saved settings for {name}")

    def set_cycle(self) -> None:
        current = self.cfg.get("cycle", {}).get("mode", "off")
        default = next((i for i, m in enumerate(cycling.MODES) if m.key == current), 0)
        self.draw()
        i = self.dialogs.choose("Change to the next video:", [m.label for m in cycling.MODES], default)
        if i is None:
            return
        mode = cycling.MODES[i]
        custom_minutes = None
        if mode.minutes is None:
            saved = cycling.saved_custom_minutes(self.cfg)
            custom_minutes = self.dialogs.ask_input(
                "Change to the next video every (hh:mm):",
                "e.g. 1:30 or 0:45 (2 = 2:00), enter to confirm, Esc to cancel",
                "0123456789:", cycling.parse_interval,
                text=f"{saved // 60}:{saved % 60:02d}",
            )
            if custom_minutes is None:
                return
        changes: dict[str, Any] = {"cycle": cycling.new_cycle_settings(self.cfg, mode.key, custom_minutes)}
        if cycling.interval_minutes(self.cfg) is None:
            changes["last_change"] = time.time()  # turning cycling on: count from now, don't switch now
        self.cfg = config.update(**changes)
        if self.active:
            systemd.reload()
        if mode.key == "off":
            self.say("Cycling off")
        else:
            note = "" if len(self.videos) > 1 else " (needs at least 2 videos)"
            self.say(f"Cycling {cycling.label(self.cfg)}{note}")

    def toggle_ask_fps(self) -> None:
        on = not config.ask_fps(self.cfg)
        self.cfg = config.update(ask_fps=on)
        self.say(f"Frame rate question on import {'enabled' if on else 'disabled'}")

    def toggle_ask_screens(self) -> None:
        on = not config.ask_screens(self.cfg)
        self.cfg = config.update(ask_screens=on)
        self.say("Per-screen settings editor opens on import" if on
                 else "Per-screen settings question on import disabled (edit later with e)")

    def stop(self) -> None:
        if not self.active:
            self.say("Live wallpaper is not running")
            return
        ok, error = systemd.stop()
        self.refresh_status()
        if not ok:
            self.say(f"Failed to stop {systemd.UNIT}: {error}", error=True)
        elif self.autostart:
            self.say("Stopped. It will start again at login (press a to turn that off)")
        else:
            self.say("Stopped. Select a video to start it again")

    def delete(self) -> None:
        kind, name = self.selected()
        if kind != "video":
            self.say("Move to a video to delete it")
            return
        is_current = name == self.cfg.get("wallpaper")
        question = f"Delete {name}?" + (" It is your current wallpaper." if is_current else "")
        if not self.dialogs.confirm(question):
            self.say("Delete cancelled")
            return
        if is_current:
            if self.active:
                systemd.stop()
            self.cfg = config.update(wallpaper=None)
        try:
            library.delete_video(name)
        except OSError as e:
            self.say(f"Delete failed: {e}", error=True)
            return
        self.rescan()
        self.refresh_status()
        self.say(f"Deleted {name}" + (" and stopped the wallpaper" if is_current else ""))

    def copy_rule(self) -> None:
        if desktop.copy_to_clipboard(niri.STATIONARY_SNIPPET):
            self.say("Copied the two niri config lines to the clipboard")
        else:
            self.say("Copy failed (is wl-clipboard installed?). Select the line with the mouse instead",
                     error=True)

    def toggle_autostart(self, force: bool | None = None) -> None:
        enable = (not self.autostart) if force is None else force
        ok, error = systemd.set_enabled(enable)
        self.refresh_status()
        if ok:
            self.say(f"Start at login {'enabled' if enable else 'disabled'}")
        else:
            self.say(error, error=True)

    def import_videos(self) -> None:
        """Pick one or more videos with fzf, copy them in, then ask about and optimize each."""
        problem = desktop.fzf_problem()
        if problem:
            self.say(problem, error=True)
            return
        curses.def_prog_mode()  # hand the terminal to fzf, then take it back
        curses.endwin()
        try:
            picks, error = desktop.pick_videos(paths.HOME)
        finally:
            curses.reset_prog_mode()
            self.screen.refresh()
        if error:
            self.say(error, error=True)
            return
        if not picks:
            self.say("Import cancelled")
            return

        def counter(i: int) -> str:
            return f"({i}/{len(picks)}) " if len(picks) > 1 else ""

        imported, existing, failed = [], [], []
        for i, src in enumerate(picks, 1):
            self.say(f"{counter(i)}Copying {src.name}…")
            self.draw()
            try:
                name, existed = library.import_video(src)
            except OSError as e:
                log.warning("importing %s failed: %s", src, e)
                failed.append(f"{src.name} ({e.strerror or e})")
                continue
            (existing if existed else imported).append(name)
        self.rescan()
        if imported or existing:
            self.cursor = self.videos.index((imported or existing)[0])

        # All questions first, so the encoding afterwards can run unattended.
        for name in imported:
            self.maybe_ask(name)
        note = ""
        for i, name in enumerate(imported, 1):
            result = self.optimize(name, counter(i) if len(imported) > 1 else "")
            if result is EncodeResult.CANCELLED:
                note = "optimizing cancelled, originals play for now"
                break
            if result is EncodeResult.FAILED:
                note = "optimizing failed on some screens, originals play there"
        self.say(import_summary(imported, existing, failed) + (f" · {note}" if note else ""),
                 error=bool(failed or note))

    def open_folder(self) -> None:
        paths.VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        if desktop.open_folder(paths.VIDEO_DIR):
            self.say("Opened video folder. New files show up here automatically")
        else:
            self.say("Could not open a file manager", error=True)

    def activate(self) -> bool:
        """Space/enter on the selected entry. Returns False to quit."""
        kind, value = self.selected()
        if kind == "video":
            self.set_wallpaper(value)
            return True
        handler = {
            "import": self.import_videos, "open": self.open_folder, "stop": self.stop,
            "cycle": self.set_cycle, "autostart": self.toggle_autostart,
            "askfps": self.toggle_ask_fps, "askscreens": self.toggle_ask_screens,
        }.get(value)
        if handler is None:  # "quit"
            return False
        handler()
        return True

    # ------------------------------------------------------------------ main loop

    def run(self) -> None:
        shortcuts = {
            ord("i"): self.import_videos, ord("o"): self.open_folder, ord("a"): self.toggle_autostart,
            ord("d"): self.delete, curses.KEY_DC: self.delete,
            ord("e"): self.edit_settings, ord("f"): self.edit_settings,
            ord("s"): self.stop, ord("c"): self.copy_rule,
        }
        while True:
            self.draw()
            key = self.screen.getch()
            count = len(self.items())
            if key == -1:  # idle timeout: pick up dropped-in files and outside changes
                self.ticks += 1
                self.rescan()
                self.refresh_status(setup_checks=self.ticks % SETUP_CHECK_EVERY == 0)
                continue
            self.say("")  # a key press clears the last message
            if key in (curses.KEY_UP, ord("k")):
                self.cursor = (self.cursor - 1) % count
            elif key in (curses.KEY_DOWN, ord("j")):
                self.cursor = (self.cursor + 1) % count
            elif key in (curses.KEY_HOME, ord("g")):
                self.cursor = 0
            elif key in (curses.KEY_END, ord("G")):
                self.cursor = count - 1
            elif key in style.ENTER:
                if not self.activate():
                    return
            elif key in shortcuts:
                shortcuts[key]()
            elif key in (ord("q"), style.ESC):
                return
