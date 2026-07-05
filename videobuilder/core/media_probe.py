"""Wraps ffprobe to extract media metadata."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional


class FfmpegNotFoundError(RuntimeError):
    pass


@dataclass
class MediaInfo:
    duration: float
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    has_video: bool = False
    has_audio: bool = False


def _require_ffprobe() -> None:
    if shutil.which("ffprobe") is None:
        raise FfmpegNotFoundError(
            "ffprobe was not found on PATH. Install ffmpeg and ensure "
            "'ffprobe' is available in your terminal."
        )


def probe(path: str) -> MediaInfo:
    """Run ffprobe on a media file and return duration/resolution/fps."""
    _require_ffprobe()
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {result.stderr.strip()}")

    data = json.loads(result.stdout)
    fmt = data.get("format", {})
    duration = float(fmt.get("duration", 0.0) or 0.0)

    width = height = fps = None
    has_video = has_audio = False
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and width is None:
            has_video = True
            width = stream.get("width")
            height = stream.get("height")
            rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate")
            if rate and rate != "0/0":
                num, _, den = rate.partition("/")
                try:
                    fps = float(num) / float(den) if den else float(num)
                except (ValueError, ZeroDivisionError):
                    fps = None
            stream_duration = stream.get("duration")
            if duration == 0.0 and stream_duration:
                duration = float(stream_duration)
        elif stream.get("codec_type") == "audio":
            has_audio = True
            stream_duration = stream.get("duration")
            if duration == 0.0 and stream_duration:
                duration = float(stream_duration)

    return MediaInfo(
        duration=duration,
        width=width,
        height=height,
        fps=fps,
        has_video=has_video,
        has_audio=has_audio,
    )


def image_size(path: str) -> tuple[int, int]:
    """Read an image's pixel dimensions via Pillow."""
    from PIL import Image

    with Image.open(path) as img:
        return img.size
