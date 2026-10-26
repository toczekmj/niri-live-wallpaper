"""The background service (`nlw run`, started by systemd): plays the wallpaper.

Runs one mpvpaper per screen, each showing that screen's copy of the current video (variants.py).
It wakes up every RUN_TICK seconds, exactly when a cycle change is due, or straight away on
SIGUSR1 (sent by the TUI after a change, see systemd.reload()). Each time it re-reads the config
and the list of screens, and then:

  - switches to the next video if a cycle change is due,
  - encodes missing copies while the old wallpaper keeps playing,
  - restarts only the screens whose file changed,
  - hands DMS a still of the video when the video changed (dms.py).

If an mpvpaper process dies (e.g. its screen was unplugged), the service exits with an error and
systemd restarts it with the current screens.
"""

from __future__ import annotations

import logging
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import NamedTuple

from . import config, cycling, dms, fit, library, media, niri, paths, proc, systemd, variants
from .media import EncodeResult

log = logging.getLogger(__name__)

RUN_TICK = 30  # seconds between checks when nothing else wakes us

# no-audio: never decode or play sound, even if the file has an audio track.
# hwdec=auto-safe: GPU decoding when available.
# quiet: no status line, otherwise mpv logs "V: 00:00:17 / ..." to the journal twice a second.
# How the picture is fitted to the screen is added per screen (fit.mpv_options()).
MPV_OPTIONS = "no-audio loop-file=inf hwdec=auto-safe quiet"
# Images: show forever instead of looping, which would reload the file in a tight loop.
MPV_IMAGE_OPTIONS = "no-audio image-display-duration=inf quiet"


class Play(NamedTuple):
    """What one output shows: a file and the mpv options to show it with."""
    path: Path
    options: str


def play_for(name: str, job: variants.ScreenJob | None) -> Play:
    original = paths.VIDEO_DIR / name
    path = variants.path_to_play(name, job) if job else original
    mode, align = (job.fit_mode, job.align) if job else (fit.DEFAULT_FIT, fit.DEFAULT_ALIGN)
    if path != original:
        # The copy is already framed for the screen: cropped, or with its blurred bars.
        if mode in ("fill", "blur"):
            mode, align = "fill", fit.DEFAULT_ALIGN  # (fill: any rounding slack is cropped)
    elif mode == "blur":
        mode = "fit"  # no copy (yet, or the shapes match): black bars rather than a crop
    base = MPV_IMAGE_OPTIONS if media.is_image(path) else MPV_OPTIONS
    return Play(path, f"{base} {fit.mpv_options(mode, align)}")


class Players:
    """The running mpvpaper processes, one per output."""

    def __init__(self) -> None:
        self.processes: dict[str, subprocess.Popen] = {}
        self.playing: dict[str, Play] = {}

    def show(self, wanted: dict[str, Play]) -> dict[str, Play]:
        """Make each output play what `wanted` says. Returns the outputs that changed.

        Only outputs whose file changed are touched. New players start before the old ones stop,
        so the screen doesn't flash black while switching.
        """
        changed = {out: path for out, path in wanted.items() if self.playing.get(out) != path}
        started = {out: self._start(out, path) for out, path in changed.items()}
        time.sleep(1)  # let the new surfaces map before removing the old ones
        self._stop({out: p for out, p in self.processes.items() if out in changed or out not in wanted})
        self.processes = {out: p for out, p in self.processes.items()
                          if out in wanted and out not in changed}
        self.processes.update(started)
        self.playing = dict(wanted)
        return changed

    def any_exited(self) -> bool:
        return any(p.poll() is not None for p in self.processes.values())

    def stop_all(self) -> None:
        self._stop(self.processes)
        self.processes, self.playing = {}, {}

    @staticmethod
    def _start(output: str, play: Play) -> subprocess.Popen:
        # -p: pause when the compositor stops sending frame callbacks (wallpaper hidden).
        # stdin=DEVNULL: mpv reads keys from a terminal; when `nlw run` is started by hand,
        # several players would fight over it.
        return subprocess.Popen(["mpvpaper", "-p", "-o", play.options, output, str(play.path)],
                                stdin=subprocess.DEVNULL)

    @staticmethod
    def _stop(processes: dict[str, subprocess.Popen]) -> None:
        for p in processes.values():
            p.terminate()
        for p in processes.values():
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


def run() -> int:
    """Main loop of the service. Returns the process exit code."""
    if not proc.available("mpvpaper"):
        log.error("mpvpaper is not installed (yay -S mpvpaper)")
        return systemd.EXIT_NO_RESTART

    stop, wake = threading.Event(), threading.Event()

    def on_stop(*_: object) -> None:
        stop.set()
        wake.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, on_stop)
    signal.signal(signal.SIGUSR1, lambda *_: wake.set())

    players = Players()
    prepared = None      # (video, jobs) whose copies were already ensured
    themed_video = None  # video DMS was last given a frame of
    try:
        while not stop.is_set():
            wake.clear()
            cfg = config.load()
            videos, now = library.list_videos(), time.time()
            if cycling.is_due(cfg, now, len(videos)):
                cfg = config.update(wallpaper=cycling.next_video(videos, cfg.get("wallpaper")),
                                    last_change=now)

            name = cfg.get("wallpaper")
            if not name or not (paths.VIDEO_DIR / name).is_file():
                log.error("no wallpaper selected (or file missing): %s", name)
                return systemd.EXIT_NO_RESTART

            outputs = niri.outputs()
            jobs = variants.jobs_for(cfg, name, outputs)
            if (name, jobs) != prepared:
                result, failed = variants.ensure(name, jobs, lambda *_: stop.is_set())
                if result is EncodeResult.CANCELLED:
                    break  # we are stopping
                if failed:
                    log.warning("optimizing %s failed for %s; playing the original",
                                name, ", ".join(failed))
                prepared = (name, jobs)

            wanted = ({job.output: play_for(name, job) for job in jobs}
                      or {"ALL": play_for(name, None)})  # not on niri / no output info
            if wanted != players.playing:
                changed = players.show(wanted)
                log.info("playing %s: %s", name,
                         ", ".join(f"{out}={play.path.name}" for out, play in changed.items()))
                if name != themed_video:
                    dms.sync_theme(paths.VIDEO_DIR / name, [o.name for o in outputs])
                    themed_video = name
            elif players.any_exited():
                log.error("an mpvpaper process exited unexpectedly")
                return 1  # systemd restarts us

            remaining = cycling.seconds_until_next(cfg, time.time())
            wake.wait(RUN_TICK if remaining is None else min(RUN_TICK, max(1, remaining)))
    finally:
        players.stop_all()
    return 0
