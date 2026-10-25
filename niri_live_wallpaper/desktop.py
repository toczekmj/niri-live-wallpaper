"""Desktop helpers: clipboard, opening a folder in the file manager, the fzf file picker."""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from . import proc
from .library import VIDEO_EXTENSIONS

log = logging.getLogger(__name__)


def copy_to_clipboard(text: str) -> bool:
    # wl-copy forks a child that serves the clipboard and keeps the pipes open, so don't capture
    # its output (we'd wait for that child forever).
    return proc.succeeded(proc.run(["wl-copy"], input=text, capture=False, timeout=5))


def open_folder(folder: Path) -> bool:
    """Show `folder` in the file manager. Returns False if nothing could be launched.

    Prefers the FileManager1 D-Bus API, which opens a real file manager (Thunar, Nautilus, …).
    Falls back to xdg-open, which uses the inode/directory default; on some systems that is a
    terminal.
    """
    result = proc.run(
        ["gdbus", "call", "--session", "--dest", "org.freedesktop.FileManager1",
         "--object-path", "/org/freedesktop/FileManager1",
         "--method", "org.freedesktop.FileManager1.ShowFolders", f"['{folder.as_uri()}']", ""],
        timeout=10,
    )
    if proc.succeeded(result):
        return True
    try:
        subprocess.Popen(["xdg-open", str(folder)], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError as e:
        log.warning("could not open %s: %s", folder, e)
        return False


def pick_videos(search_root: Path) -> tuple[list[Path], str | None]:
    """Let the user fuzzy-find videos under `search_root` with fzf. Tab marks several files;
    Enter without marks picks the highlighted one. Returns (picked files, error message);
    no files and no error means the user cancelled.

    Takes over the terminal: the caller must suspend curses first. fzf is interactive, so there is
    no timeout.
    """
    problem = fzf_problem()
    if problem:
        return [], problem
    fd = next((name for name in ("fd", "fdfind") if proc.available(name)), None)  # Debian: fdfind
    if fd:
        lister = [fd, "--type", "f", "--absolute-path",
                  *[a for ext in VIDEO_EXTENSIONS for a in ("-e", ext)], ".", str(search_root)]
    else:  # find: skip hidden directories, like fd does
        names = [a for ext in VIDEO_EXTENSIONS for a in ("-o", "-iname", f"*.{ext}")][1:]
        lister = ["find", str(search_root), "-path", "*/.*", "-prune", "-o",
                  "-type", "f", "(", *names, ")", "-print"]
    preview = ("ffprobe -v error -select_streams v:0 "
               "-show_entries format=duration,size:stream=codec_name,width,height,r_frame_rate "
               "-of default=noprint_wrappers=1 {}")

    files = subprocess.Popen(lister, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        result = subprocess.run(
            ["fzf", "--multi", "--bind=ctrl-a:toggle-all",
             "--prompt=Import videos > ", "--scheme=path", "--height=100%", "--layout=reverse",
             "--header=Tab: mark   Ctrl-A: mark all shown   Enter: import   Esc: cancel",
             "--preview", preview, "--preview-window=down,7,wrap"],
            # stderr is left alone: some fzf versions draw their interface on it.
            stdin=files.stdout, stdout=subprocess.PIPE, text=True,
        )
    finally:
        files.stdout.close()
        files.terminate()
    if result.returncode == 2:  # fzf's exit code for errors
        return [], "fzf failed (see the terminal output above); fzf 0.33 or newer is needed"
    return (parse_selection(result.stdout) if result.returncode == 0 else []), None


FZF_MIN_VERSION = (0, 33)  # --scheme=path


def fzf_problem() -> str | None:
    """Why the import picker can't run, or None."""
    result = proc.run(["fzf", "--version"], timeout=5)
    if result is None:
        return "fzf is not installed"
    version = parse_version(result.stdout)
    if version and version < FZF_MIN_VERSION:
        return (f"fzf {'.'.join(map(str, version))} is too old; "
                f"{'.'.join(map(str, FZF_MIN_VERSION))} or newer is needed")
    return None


def parse_version(text: str) -> tuple[int, ...] | None:
    """"0.74.5 (c0a193e0)" -> (0, 74, 5)."""
    match = re.match(r"\s*(\d+(?:\.\d+)+)", text)
    return tuple(int(n) for n in match.group(1).split(".")) if match else None


def parse_selection(fzf_output: str) -> list[Path]:
    """fzf prints one selected path per line."""
    return [Path(line) for line in fzf_output.splitlines() if line.strip()]
