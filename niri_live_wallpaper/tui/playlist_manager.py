"""The "Playlists" popup: create, rename, delete playlists, and add or remove their files.

It is a loop of fuzzy-finder (fzf) menus drawn in a box in the middle of the terminal. An action
that needs typing or a yes/no (a name, a delete) leaves fzf, asks in a curses dialog, then comes
back. Every change is saved as it happens (config.update); what to *do* about it (switching the
playlist that plays, telling the service) is up to the caller, from the returned Result.
"""

from __future__ import annotations

import curses
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from .. import config, desktop, library, playlists
from .dialogs import Dialogs

NEW, ALL = "\x00new", "\x00all"  # row keys that can't be playlist names

HEADER = ("Enter: switch to it   Ctrl-R: rename   Ctrl-D: delete   "
          "Ctrl-A: add files   Ctrl-X: remove files   Esc: close")
KEYS = ("ctrl-r", "ctrl-d", "ctrl-a", "ctrl-x")


@dataclass
class Result:
    switch: bool = False            # the user chose what to play: `playlist` (None = all files)
    playlist: str | None = None
    message: str = ""
    error: bool = False


class PlaylistManager:
    def __init__(self, screen: curses.window, dialogs: Dialogs, redraw: Callable[[], None]) -> None:
        self.screen = screen
        self.dialogs = dialogs
        self.redraw = redraw  # repaints the main screen under the dialogs

    @contextmanager
    def _fzf_terminal(self) -> Iterator[None]:
        """Hand the terminal to fzf, then take it back."""
        curses.def_prog_mode()
        curses.endwin()
        try:
            yield
        finally:
            curses.reset_prog_mode()
            self.screen.refresh()

    # ---- the main menu

    def run(self) -> Result:
        result = Result()
        while True:
            cfg = config.load()
            active = config.active_playlist(cfg)
            rows = [(NEW, "✚  New playlist…"),
                    (ALL, f"{'●' if active is None else '○'}  All wallpapers (no playlist)")]
            for name in playlists.names(cfg):
                count = len(playlists.files(cfg, name))
                mark, noun = "●" if name == active else "○", "file" if count == 1 else "files"
                rows.append((name, f"{mark}  {name}   · {count} {noun}"))
            with self._fzf_terminal():
                key, picked, error = desktop.fzf_menu(rows, "Playlists", "Playlist > ", HEADER,
                                                      expect=KEYS)
            if error:
                return Result(message=error, error=True)
            if key is None:  # Esc
                return result
            target = picked[0]
            if key == "" and target == NEW:
                result.message = self._create()
            elif key == "":
                return Result(True, None if target == ALL else target, result.message)
            elif target in (NEW, ALL):
                continue  # these keys mean nothing on the special rows
            elif key == "ctrl-r":
                result.message = self._rename(target) or result.message
            elif key == "ctrl-d":
                result.message = self._delete(target) or result.message
            elif key == "ctrl-a":
                result.message = self._add_files(target) or result.message
            elif key == "ctrl-x":
                result.message = self._remove_files(target) or result.message

    # ---- actions (each returns a message for the status line, "" if nothing happened)

    def _create(self) -> str:
        self.redraw()
        cfg = config.load()
        name = self.dialogs.ask_text("New playlist name", "enter to create, Esc to cancel",
                                     lambda text: playlists.clean_name(cfg, text))
        if name is None:
            return ""
        config.update(**playlists.create(cfg, name))
        added = self._add_files(name)  # most want files in it straight away; Esc there skips
        return added or f"Created the playlist {name}"

    def _rename(self, old: str) -> str:
        self.redraw()
        cfg = config.load()
        new = self.dialogs.ask_text(f"Rename {old} to", "enter to rename, Esc to cancel",
                                    lambda text: playlists.clean_name(cfg, text, renaming=old), text=old)
        if new is None or new == old:
            return ""
        config.update(**playlists.rename(cfg, old, new))
        return f"Renamed {old} to {new}"

    def _delete(self, name: str) -> str:
        self.redraw()
        if not self.dialogs.confirm(f"Delete the playlist {name}? The files stay in the library"):
            return ""
        config.update(**playlists.delete(config.load(), name))
        return f"Deleted the playlist {name}"

    def _add_files(self, name: str) -> str:
        cfg = config.load()
        present = set(playlists.files(cfg, name))
        candidates = [f for f in library.list_videos() if f not in present]
        if not candidates:
            return ""
        with self._fzf_terminal():
            _, picked, _ = desktop.fzf_menu(
                [(f, f) for f in candidates], f"Add to {name}", "Add > ",
                "Tab: mark   Ctrl-A: mark all shown   Enter: add   Esc: skip", multi=True)
        if not picked:
            return ""
        config.update(**playlists.add(cfg, name, picked))
        return f"Added {len(picked)} {'file' if len(picked) == 1 else 'files'} to {name}"

    def _remove_files(self, name: str) -> str:
        cfg = config.load()
        files = playlists.files(cfg, name)
        if not files:
            return ""
        with self._fzf_terminal():
            _, picked, _ = desktop.fzf_menu(
                [(f, f) for f in files], f"Remove from {name}", "Remove > ",
                "Tab: mark   Ctrl-A: mark all shown   Enter: remove from the playlist "
                "(files stay in the library)   Esc: skip", multi=True)
        if not picked:
            return ""
        config.update(**playlists.remove(cfg, name, picked))
        return f"Removed {len(picked)} {'file' if len(picked) == 1 else 'files'} from {name}"

    # ---- from the main screen

    def add_to_playlists(self, file: str) -> Result:
        """Pick playlists to add `file` to (Tab marks several)."""
        cfg = config.load()
        names = playlists.names(cfg)
        if not names:
            return Result(message="No playlists yet. Press p to create one", error=True)
        rows = [(n, f"{'✓' if file in config.playlist_items(cfg, n) else ' '}  {n}") for n in names]
        with self._fzf_terminal():
            _, picked, error = desktop.fzf_menu(
                rows, f"Add {file}", "Playlist > ",
                "Tab: mark   Enter: add to the marked (or highlighted) playlists   Esc: cancel",
                multi=True)
        if error:
            return Result(message=error, error=True)
        added = [n for n in picked if file not in config.playlist_items(cfg, n)]
        for name in added:
            config.update(**playlists.add(config.load(), name, [file]))
        if not picked:
            return Result()
        return Result(message=(f"Added {file} to {', '.join(added)}" if added
                               else f"{file} is already in the chosen playlists"))
