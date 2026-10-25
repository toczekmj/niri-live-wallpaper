"""Per-screen optimized copies ("variants") of a video.

For each screen, a video is played from a copy made for that screen when that saves work: scaled
down to cover the screen at the chosen resolution and cropped (the same framing as mpv's
panscan=1.0), capped to the chosen frame rate, without audio. When the original is already no
bigger and no faster than needed, the original is played.

Copies live in paths.OPTIMIZED_DIR/<video>/<width>x<height>@<fps or "src">.mp4. The file name
records what was encoded, so an existing file means the work is done, and two screens with the
same target share one file.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import config, media, paths
from .config import Config
from .media import EncodeResult, VideoInfo
from .niri import Output


@dataclass(frozen=True)
class ScreenJob:
    """What one screen should show: its size and the effective settings for the video."""
    output: str
    width: int
    height: int
    fps: int | None   # frame-rate cap, None = original
    scale: int        # % of the screen's native resolution


@dataclass(frozen=True)
class Variant:
    filename: str        # e.g. "3440x1440@30.mp4"
    video_filter: str    # ffmpeg -vf argument that produces it


def jobs_for(cfg: Config, name: str, outputs: list[Output]) -> list[ScreenJob]:
    return [ScreenJob(o.name, o.width, o.height, *config.screen_settings(cfg, name, o.name))
            for o in outputs]


def scaled_size(width: int, height: int, scale: int) -> tuple[int, int]:
    """Size at `scale` percent, rounded to even numbers (the encoders need even sizes)."""
    return (max(2, round(width * scale / 100 / 2) * 2),
            max(2, round(height * scale / 100 / 2) * 2))


def plan(info: VideoInfo | None, job: ScreenJob) -> Variant | None:
    """The copy `job` needs, or None when the original is already fine (or can't be read)."""
    if not info or not job.width or not job.height:
        return None
    width, height = job.width, job.height
    if job.scale != 100:
        width, height = scaled_size(width, height, job.scale)
    downscale = max(width / info.width, height / info.height) < 0.999
    lower_fps = job.fps is not None and info.fps > job.fps + 0.5
    if not downscale and not lower_fps:
        return None

    filters = []
    if lower_fps:
        filters.append(f"fps={job.fps}")
    if downscale:
        # Cover the target, crop the overflow: same framing as mpv's panscan=1.0.
        filters.append(f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                       f"crop={width}:{height}")
        size = f"{width}x{height}"
    else:
        size = f"{info.width // 2 * 2}x{info.height // 2 * 2}"
        if size != f"{info.width}x{info.height}":
            filters.append("crop=trunc(iw/2)*2:trunc(ih/2)*2")  # encoders need even sizes
    return Variant(f"{size}@{job.fps or 'src'}.mp4", ",".join(filters))


def variant_path(name: str, variant: Variant) -> Path:
    return paths.OPTIMIZED_DIR / name / variant.filename


def path_to_play(name: str, job: ScreenJob) -> Path:
    """The copy for `job` if it is needed and exists, otherwise the original file."""
    variant = plan(media.probe(paths.VIDEO_DIR / name), job)
    if variant is not None and variant_path(name, variant).exists():
        return variant_path(name, variant)
    return paths.VIDEO_DIR / name


def ensure(name: str, jobs: list[ScreenJob],
           on_progress: Callable[[str, Path, float], bool]) -> tuple[EncodeResult, list[str]]:
    """Encode the missing copies of `name` for `jobs`.

    on_progress(output, copy path, fraction) returning True cancels. Returns the overall result
    and the outputs whose copy failed (those keep playing the original).
    """
    src = paths.VIDEO_DIR / name
    info = media.probe(src)
    done: set[Path] = set()
    failed: list[str] = []
    for job in jobs:
        variant = plan(info, job)
        if variant is None:
            continue
        path = variant_path(name, variant)
        if path.exists() or path in done:
            continue
        result = media.encode(src, path, variant.video_filter, info.duration,
                              lambda f, out=job.output, p=path: on_progress(out, p, f))
        if result is EncodeResult.CANCELLED:
            return result, failed
        if result is EncodeResult.FAILED:
            failed.append(job.output)
        done.add(path)
    return (EncodeResult.FAILED if failed else EncodeResult.OK), failed


def prune(name: str, jobs: list[ScreenJob]) -> None:
    """Delete copies of `name` that none of `jobs` would play (e.g. after a settings change)."""
    info = media.probe(paths.VIDEO_DIR / name)
    keep = {variant_path(name, v) for v in (plan(info, job) for job in jobs) if v is not None}
    for file in (paths.OPTIMIZED_DIR / name).glob("*.mp4"):
        if file not in keep:
            file.unlink(missing_ok=True)


def remove_all(name: str) -> None:
    shutil.rmtree(paths.OPTIMIZED_DIR / name, ignore_errors=True)
