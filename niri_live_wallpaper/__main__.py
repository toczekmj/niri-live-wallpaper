"""Command line: `nlw` opens the TUI, `nlw run` plays the wallpaper (used by the systemd unit).

Also runnable as `python -m niri_live_wallpaper` or `./nlw.py` from a checkout. Logging is set up
here, once, for whichever mode runs.
"""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys

from . import __version__, paths


def _log_to_journal() -> None:
    # systemd puts stderr in the journal and adds timestamps itself.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(levelname)s %(name)s: %(message)s")


def _log_to_file() -> None:
    # curses owns the terminal, so the TUI logs to a small rotating file instead.
    paths.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(paths.LOG_FILE, maxBytes=256_000, backupCount=1)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="nlw", description="Video wallpapers for niri + DankMaterialShell.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    commands.add_parser("run", help="play the selected wallpaper in the foreground "
                                    "(what the systemd service runs)")
    args = parser.parse_args(argv)

    if args.command == "run":
        from . import service
        _log_to_journal()
        return service.run()

    from . import tui  # imported here so the service never loads curses
    _log_to_file()
    tui.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
