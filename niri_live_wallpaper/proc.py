"""Running external programs.

This app is mostly glue around other programs (niri, systemd, ffmpeg, mpvpaper, DMS), so short
calls go through `run()` to share the same rules: an argument list (never a shell), a timeout,
no terminal input (stdin is /dev/null, so programs like ffmpeg can't steal the TUI's keypresses),
and a missing program or a hang is logged and returned as None instead of raising. Callers decide
what a failure means for them; usually that one feature is unavailable.

Long-running or streaming processes (mpvpaper players, ffmpeg encodes, fzf) use subprocess.Popen
directly in their own modules.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

log = logging.getLogger(__name__)


def run(
    args: list[str],
    *,
    timeout: float = 10,
    input: str | None = None,
    capture: bool = True,
) -> subprocess.CompletedProcess[str] | None:
    """Run a program to completion. Returns None if it isn't installed or timed out.

    capture=False discards output instead of capturing it, which is needed for programs that fork
    a background child holding the pipes open (wl-copy).
    """
    streams = {"capture_output": True} if capture else {
        "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    try:
        if input is None:
            streams["stdin"] = subprocess.DEVNULL
        return subprocess.run(args, input=input, text=True, timeout=timeout, **streams)
    except FileNotFoundError:
        log.warning("%s is not installed", args[0])
    except subprocess.TimeoutExpired:
        log.warning("%s timed out after %ss: %s", args[0], timeout, " ".join(args))
    except OSError as e:
        log.warning("could not run %s: %s", args[0], e)
    return None


def succeeded(result: subprocess.CompletedProcess[str] | None) -> bool:
    return result is not None and result.returncode == 0


def available(program: str) -> bool:
    return shutil.which(program) is not None
