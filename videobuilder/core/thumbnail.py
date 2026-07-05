"""Generates a still-frame thumbnail for a video file via ffmpeg."""
from __future__ import annotations

import shutil
import subprocess

from .ffmpeg_export import FfmpegNotFoundError


def generate_video_thumbnail(video_path: str, out_path: str, at_seconds: float = 0.5) -> None:
    if shutil.which("ffmpeg") is None:
        raise FfmpegNotFoundError("ffmpeg was not found on PATH.")

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(at_seconds),
        "-i",
        video_path,
        "-frames:v",
        "1",
        "-vf",
        "scale=160:-1",
        "-loglevel",
        "error",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Thumbnail generation failed for {video_path}: {result.stderr.strip()}")
