"""The systemd user service that runs the wallpaper in the background.

The TUI never plays video itself. "Apply now" is `systemctl --user restart` and "start at login"
is `systemctl --user enable`, so both use the same unit and the same code path (service.py).
"""

from __future__ import annotations

import logging
import os
import signal
import sys
from pathlib import Path

from . import paths, proc

log = logging.getLogger(__name__)

UNIT = f"{paths.APP_ID}.service"

# service.py exits with this when there is nothing to play; the unit tells systemd not to restart.
EXIT_NO_RESTART = 2

# Directory containing the niri_live_wallpaper package: the checkout, or site-packages if installed.
_PACKAGE_PARENT = Path(__file__).resolve().parent.parent


def unit_text() -> str:
    return f"""[Unit]
Description=Niri Live Wallpaper (mpvpaper)
PartOf=graphical-session.target
After=graphical-session.target dms.service
Requisite=graphical-session.target

[Service]
ExecStart={sys.executable} -m niri_live_wallpaper run
Environment="PYTHONPATH={_PACKAGE_PARENT}"
Restart=on-failure
RestartSec=2
RestartPreventExitStatus={EXIT_NO_RESTART}
TimeoutStopSec=10

[Install]
WantedBy=graphical-session.target
"""


def _systemctl(*args: str, timeout: float = 60) -> tuple[bool, str]:
    """Returns (success, error text)."""
    result = proc.run(["systemctl", "--user", *args], timeout=timeout)
    if result is None:
        return False, "systemctl is not available or timed out"
    return result.returncode == 0, (result.stderr or result.stdout).strip()


def ensure_unit() -> None:
    """Write the unit file if it is missing or stale (e.g. the app was moved)."""
    text = unit_text()
    if paths.UNIT_FILE.exists() and paths.UNIT_FILE.read_text() == text:
        return
    paths.UNIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    paths.UNIT_FILE.write_text(text)
    _systemctl("daemon-reload")


def is_enabled() -> bool:
    result = proc.run(["systemctl", "--user", "is-enabled", UNIT], timeout=10)
    return result is not None and result.stdout.strip() == "enabled"


def is_active() -> bool:
    result = proc.run(["systemctl", "--user", "is-active", UNIT], timeout=10)
    return result is not None and result.stdout.strip() == "active"


def restart() -> tuple[bool, str]:
    ensure_unit()
    return _systemctl("restart", UNIT)


def stop() -> tuple[bool, str]:
    return _systemctl("stop", UNIT)


def set_enabled(enabled: bool) -> tuple[bool, str]:
    ensure_unit()
    return _systemctl("enable" if enabled else "disable", UNIT)


def reload() -> None:
    """Ask a running service to re-read the config now instead of on its next tick (RUN_TICK).

    Only the main process gets SIGUSR1; the mpvpaper children would quit on it. We signal the PID
    ourselves because `systemctl kill` spells the option --kill-who up to systemd 249 and
    --kill-whom from 252 on. If this fails, the service still picks the change up on its next tick.
    """
    result = proc.run(["systemctl", "--user", "show", "--property=MainPID", "--value", UNIT],
                      timeout=10)
    try:
        pid = int(result.stdout.strip()) if result else 0
        if pid > 0:
            os.kill(pid, signal.SIGUSR1)
    except (ValueError, OSError) as e:
        log.warning("could not signal the service: %s", e)


def session_problem() -> str | None:
    """Why the service can't run in this session, or None if it can.

    The service needs a systemd user manager, and niri must have been started as a session
    (niri-session, a display manager, uwsm): that activates graphical-session.target and imports
    WAYLAND_DISPLAY / NIRI_SOCKET into systemd, so mpvpaper can reach the compositor.
    """
    if not proc.available("systemctl"):
        return "systemd isn't available; the background service needs a systemd user session"
    result = proc.run(["systemctl", "--user", "is-active", "graphical-session.target"], timeout=10)
    if result is None:
        return "can't reach the systemd user manager"
    if result.stdout.strip() != "active":
        return ("graphical-session.target isn't active: start niri with niri-session "
                "or a display manager, not plain `niri`")
    return None
