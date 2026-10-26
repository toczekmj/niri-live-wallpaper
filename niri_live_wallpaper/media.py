"""Video files: reading their properties (ffprobe), grabbing a still (ffmpeg), encoding copies.

This module knows how to drive ffmpeg; *what* to encode is decided in variants.py.
"""

from __future__ import annotations

import enum
import json
import logging
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import paths, proc

log = logging.getLogger(__name__)

IMAGE_EXTENSIONS = (
    "png",
    "jpg",
    "jpeg",
    "webp",
    "bmp",
    "avif",
    "jxl",
)  # not gif: that plays as a video


def is_image(path: Path) -> bool:
    """A still image (shown as is, never re-encoded). Decided by extension."""
    return path.suffix.lower().lstrip(".") in IMAGE_EXTENSIONS


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    fps: float
    duration: float  # seconds, 0 if unknown
    has_audio: bool
    is_image: bool = False


def parse_rate(rate: str) -> float:
    """ffprobe frame rate ("30000/1001", "25/1", "0/0") -> frames per second, 0.0 if unknown."""
    try:
        num, _, den = rate.partition("/")
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(path: Path) -> VideoInfo | None:
    """Properties of the first video stream, or None if the file can't be read.
    Cached per file modification time, since the TUI asks for every video on every redraw."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    return _probe(str(path), mtime)


@lru_cache(maxsize=256)
def _probe(
    path: str, mtime: float
) -> VideoInfo | None:  # mtime is only part of the cache key
    result = proc.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height,avg_frame_rate,r_frame_rate:format=duration",
            "-of",
            "json",
            path,
        ],
        timeout=15,
    )
    if not proc.succeeded(result):
        return None
    try:
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        video = next(s for s in streams if s.get("codec_type") == "video")
        return VideoInfo(
            width=int(video["width"]),
            height=int(video["height"]),
            fps=parse_rate(video.get("avg_frame_rate", ""))
            or parse_rate(video.get("r_frame_rate", "")),
            duration=float(data.get("format", {}).get("duration") or 0),
            has_audio=any(s.get("codec_type") == "audio" for s in streams),
            is_image=is_image(Path(path)),
        )
    except (ValueError, KeyError, TypeError, StopIteration) as e:
        log.warning("unexpected ffprobe output for %s: %s", path, e)
        return None


def extract_frame(video: Path) -> Path | None:
    """A JPEG still of `video` (cached in paths.FRAME_DIR), or None if ffmpeg fails."""
    paths.FRAME_DIR.mkdir(parents=True, exist_ok=True)
    frame = paths.FRAME_DIR / f"{video.name}.jpg"
    if frame.exists() and frame.stat().st_mtime >= video.stat().st_mtime:
        return frame
    # Seek 1s in to skip black intro frames; fall back to the first frame for very short clips.
    for seek in ("1", "0"):
        result = proc.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-ss",
                seek,
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(frame),
            ],
            timeout=30,
        )
        if proc.succeeded(result) and frame.exists():
            return frame
    return None


def render_still(src: Path, dst: Path, filtergraph: str) -> bool:
    """Render an image through an ffmpeg -filter_complex graph into a JPEG. dst only appears
    once it is complete."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f"{dst.name}.{os.getpid()}.part.jpg")  # the TUI and the service may both render
    result = proc.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(src),
                       "-filter_complex", filtergraph, "-frames:v", "1", "-q:v", "2", str(tmp)],
                      timeout=120)
    if proc.succeeded(result) and tmp.exists():
        os.replace(tmp, dst)
        return True
    tmp.unlink(missing_ok=True)
    return False


class EncodeResult(enum.Enum):
    OK = "ok"
    CANCELLED = "cancelled"
    FAILED = "failed"


def encode(
    src: Path,
    dst: Path,
    video_filter: str,
    duration: float,
    on_progress: Callable[[float], bool],
    filter_complex: bool = False,
) -> EncodeResult:
    """Encode src -> dst through an ffmpeg filter, video only (no audio, subtitles or data).
    With filter_complex, video_filter is a filter graph with one input and one output.

    Tries VA-API HEVC first (on the author's Radeon 780M it used about half the CPU time of x264),
    then libx264. on_progress(fraction done) is called as ffmpeg reports progress; returning True
    cancels. dst only appears once the encode has finished.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f"{dst.name}.{os.getpid()}.part.mp4")  # the TUI and the service may both encode
    # -nostdin: ffmpeg otherwise reads the terminal for its own keys (q, ?, …) and steals the
    # TUI's keypresses, including the Esc meant to cancel this encode.
    base = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-nostats",
        "-progress",
        "pipe:1",
        "-y",
    ]
    # A filter graph picks its own input; -map would add the source stream next to its output.
    video_only = ["-an", "-sn", "-dn"] if filter_complex else ["-map", "0:v:0", "-an", "-sn", "-dn"]
    filter_flag = "-filter_complex" if filter_complex else "-vf"
    attempts = []
    if paths.VAAPI_DEVICE.exists():
        attempts.append(
            base
            + [
                "-vaapi_device",
                str(paths.VAAPI_DEVICE),
                "-i",
                str(src),
                *video_only,
                filter_flag,
                f"{video_filter},format=nv12,hwupload",
                "-c:v",
                "hevc_vaapi",
                "-rc_mode",
                "CQP",
                "-qp",
                "26",
                str(tmp),
            ]
        )
    attempts.append(
        base
        + [
            "-i",
            str(src),
            *video_only,
            filter_flag,
            video_filter,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "21",
            "-pix_fmt",
            "yuv420p",
            str(tmp),
        ]
    )

    for cmd in attempts:
        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except FileNotFoundError:
            log.error("ffmpeg is not installed")
            return EncodeResult.FAILED
        cancelled = False
        for line in process.stdout:
            if not (line.startswith("out_time_us=") and duration):
                continue
            try:
                fraction = int(line.split("=", 1)[1]) / 1e6 / duration
            except ValueError:  # "out_time_us=N/A" at the very start
                continue
            if on_progress(min(max(fraction, 0.0), 1.0)):
                cancelled = True
                process.kill()
                break
        process.wait()
        if cancelled:
            tmp.unlink(missing_ok=True)
            return EncodeResult.CANCELLED
        if process.returncode == 0 and tmp.exists():
            os.replace(tmp, dst)
            return EncodeResult.OK
        log.warning(
            "encoding with %s failed (exit %s)",
            cmd[cmd.index("-c:v") + 1],
            process.returncode,
        )
        tmp.unlink(missing_ok=True)
    return EncodeResult.FAILED
