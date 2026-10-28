"""Per-screen optimized copies ("variants") of a video.

For each screen, a video is played from a copy made for that screen when that saves work: scaled
down for the screen at the chosen resolution, capped to the chosen frame rate, without audio. How
it is scaled follows the fit (fit.py): "fill" covers the screen and crops the overflow (from the
chosen edge), "fit" shrinks to fit inside it, "stretch" distorts it to the screen's shape, "blur"
fits it inside over a blurred copy of itself, and "center" shows the original size, so only the
frame rate is capped. When the original is already no bigger and no faster than needed, the
original is played.

Images are never re-encoded, except with the "blur" fit: then each screen gets a JPEG of the image
on its blurred backdrop.

Copies live in paths.OPTIMIZED_DIR/<video>/<width>x<height>@<fps or "src"><-fit>.mp4, where <-fit>
is "-fit", "-blur", "-stretch" or the crop edge ("-left") and missing for the plain "fill". The
file name records what was encoded, so an existing file means the work is done, and two screens
with the same target share one file.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import config, fit, media, paths
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
    fit_mode: str = fit.DEFAULT_FIT     # images only, see fit.py
    align: str = fit.DEFAULT_ALIGN


@dataclass(frozen=True)
class Variant:
    filename: str        # e.g. "3440x1440@30.mp4"
    video_filter: str    # ffmpeg -vf argument that produces it, or a graph if `graph`
    graph: bool = False  # video_filter is a -filter_complex graph (one input, one output)


def jobs_for(cfg: Config, name: str, outputs: list[Output]) -> list[ScreenJob]:
    """What each screen should show of `name`, with its settings in the active playlist (if any)."""
    return jobs_for_entry(config.video_entry(cfg, name), outputs)


def jobs_for_entry(entry: dict | None, outputs: list[Output]) -> list[ScreenJob]:
    entry = entry or {}
    return [ScreenJob(o.name, o.width, o.height, *config.screen_settings_of(entry, o.name),
                      *config.screen_fit_of(entry, o.name))
            for o in outputs]


def jobs_everywhere(cfg: Config, name: str, outputs: list[Output]) -> list[ScreenJob]:
    """The jobs of `name` under all its settings: the library's own and those in every playlist
    it is in. For prune(): a copy one playlist needs must not go because another doesn't."""
    return [job for entry in config.entries_of(cfg, name) for job in jobs_for_entry(entry, outputs)]


def scaled_size(width: int, height: int, scale: int) -> tuple[int, int]:
    """Size at `scale` percent, rounded to even numbers (the encoders need even sizes)."""
    return (max(2, round(width * scale / 100 / 2) * 2),
            max(2, round(height * scale / 100 / 2) * 2))


def filename(size: str, fps: int | None, tag: str = "", extension: str = "mp4") -> str:
    return f"{size}@{fps or 'src'}{'-' + tag if tag else ''}.{extension}"


def plan(info: VideoInfo | None, job: ScreenJob) -> Variant | None:
    """The copy `job` needs, or None when the original is already fine (or can't be read)."""
    if not info or not job.width or not job.height:
        return None
    mode = job.fit_mode
    if mode in ("fit", "blur", "stretch") and not fit.aspect_differs(
            info.width, info.height, job.width, job.height):
        mode = "fill"  # same shape as the screen: they all look alike
    if info.is_image:
        if mode != "blur":
            return None  # the player does the other fits
        return Variant(filename(f"{job.width}x{job.height}", None, "blur", "jpg"),
                       fit.blur_filter(job.width, job.height), graph=True)

    width, height = job.width, job.height
    if job.scale != 100:
        width, height = scaled_size(width, height, job.scale)
    lower_fps = job.fps is not None and info.fps > job.fps + 0.5
    fps_filter = f"fps={job.fps}"

    if mode == "blur":  # always a copy: the bars are part of the picture
        graph = (fps_filter + "," if lower_fps else "") + fit.blur_filter(width, height)
        return Variant(filename(f"{width}x{height}", job.fps, "blur"), graph, graph=True)

    # The factor that shrinks the video to the target: "fit" lands inside it, the others cover it.
    ratio_to = min if mode == "fit" else max
    ratio = ratio_to(width / info.width, height / info.height)
    downscale = mode != "center" and ratio < 0.999
    if not downscale and not lower_fps:
        return None

    filters = [fps_filter] if lower_fps else []
    tag = ""
    if downscale and mode == "fit":
        width, height = (max(2, round(side * ratio / 2) * 2) for side in (info.width, info.height))
        filters.append(f"scale={width}:{height}")
        tag = "fit"
    elif downscale and mode == "stretch":
        filters.append(f"scale={width}:{height}")
        tag = "stretch"
    elif downscale:
        # Cover the target, crop the overflow: same framing as mpv's panscan=1.0 (+ video-align).
        crop = f"crop={width}:{height}"
        if job.align != fit.DEFAULT_ALIGN:
            x, y = fit.crop_offsets(job.align)
            crop += f":(iw-ow)*{x:g}:(ih-oh)*{y:g}"
            tag = job.align
        filters.append(f"scale={width}:{height}:force_original_aspect_ratio=increase,{crop}")
    if downscale:
        size = f"{width}x{height}"
    else:
        size = f"{info.width // 2 * 2}x{info.height // 2 * 2}"
        if size != f"{info.width}x{info.height}":
            filters.append("crop=trunc(iw/2)*2:trunc(ih/2)*2")  # encoders need even sizes
    return Variant(filename(size, job.fps, tag), ",".join(filters))


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
    if info is None:  # unreadable: nothing can be planned, the original plays
        return EncodeResult.OK, []
    done: set[Path] = set()
    failed: list[str] = []
    for job in jobs:
        variant = plan(info, job)
        if variant is None:
            continue
        path = variant_path(name, variant)
        if path.exists() or path in done:
            continue
        report = lambda f, out=job.output, p=path: on_progress(out, p, f)
        if info.is_image:
            if report(0.0):
                return EncodeResult.CANCELLED, failed
            result = (EncodeResult.OK if media.render_still(src, path, variant.video_filter)
                      else EncodeResult.FAILED)
        else:
            result = media.encode(src, path, variant.video_filter, info.duration, report,
                                  filter_complex=variant.graph)
        if result is EncodeResult.CANCELLED:
            return result, failed
        if result is EncodeResult.FAILED:
            failed.append(job.output)
        done.add(path)
    return (EncodeResult.FAILED if failed else EncodeResult.OK), failed


def prune(name: str, jobs: list[ScreenJob]) -> None:
    """Delete copies of `name` that none of `jobs` would play (e.g. after a settings change). Pass
    jobs_everywhere() so other playlists' copies stay."""
    info = media.probe(paths.VIDEO_DIR / name)
    keep = {variant_path(name, v) for v in (plan(info, job) for job in jobs) if v is not None}
    for file in (paths.OPTIMIZED_DIR / name).glob("*@*"):
        if file not in keep:
            file.unlink(missing_ok=True)


def remove_all(name: str) -> None:
    shutil.rmtree(paths.OPTIMIZED_DIR / name, ignore_errors=True)
