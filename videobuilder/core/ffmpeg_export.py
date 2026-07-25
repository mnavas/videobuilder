"""Builds and runs ffmpeg export commands.

export_timeline() renders a full multi-track Project to a video via a single
ffmpeg filter graph (trim/concat/xfade/overlay/drawtext) -- see
_TimelineGraphBuilder below.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from typing import Callable, Optional

from .media_probe import FfmpegNotFoundError, probe
from .models import Clip, ClipType, Project, TrackKind

ProgressCallback = Optional[Callable[[float], None]]

MIN_TRANSITION_SECONDS = 0.05

# libx264's default preset ("medium") is tuned for offline encoding where
# time doesn't matter. Measured on a real 3-clip-with-crossfades, ~3-minute
# 1280x720 timeline: medium=69s, veryfast=33s (2.1x faster, similar file
# size). For a desktop app where a slower/older machine is common and the
# user is sitting there watching a progress bar, that trade is clearly
# worth it -- this is not a compression-ratio tool, it's an editor.
X264_PRESET = "veryfast"


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise FfmpegNotFoundError(
            "ffmpeg was not found on PATH. Install ffmpeg and ensure "
            "'ffmpeg' is available in your terminal."
        )


def _run_with_progress(cmd: list[str], total_duration: float, on_progress: ProgressCallback) -> None:
    """Run an ffmpeg command, parsing stderr 'time=' to report 0..1 progress."""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    time_re = re.compile(r"out_time=(\d+):(\d+):(\d+\.\d+)")
    stderr_lines: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        stderr_lines.append(line)
        if on_progress and total_duration > 0:
            match = time_re.search(line)
            if match:
                h, m, s = match.groups()
                elapsed = int(h) * 3600 + int(m) * 60 + float(s)
                on_progress(min(1.0, elapsed / total_duration))
    process.wait()
    if process.returncode != 0:
        tail = "".join(stderr_lines[-40:])
        raise RuntimeError(f"ffmpeg failed (exit {process.returncode}):\n{tail}")
    if on_progress:
        on_progress(1.0)


def _escape_drawtext(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\\'")
    text = text.replace("%", "\\%")
    return text


class _TimelineGraphBuilder:
    """Builds an ffmpeg -filter_complex graph for a full multi-track Project.

    Folds the video track left-to-right into one stream (gaps filled with
    black; any timeline overlap between adjacent clips blends them with
    xfade/acrossfade using the overlap itself as the transition length),
    mirrors the same fold for each clip's own audio, overlays title clips via
    drawtext, and mixes in the dedicated audio (music) track via adelay+amix.
    """

    def __init__(self, project: Project):
        self.project = project
        self.input_args: list[str] = []
        self.filters: list[str] = []
        self._label_counter = 0
        self._clip_input_index: dict[int, int] = {}
        self._has_audio_cache: dict[str, bool] = {}

    def _new_label(self, prefix: str) -> str:
        self._label_counter += 1
        return f"{prefix}{self._label_counter}"

    def _has_audio(self, path: str) -> bool:
        if path not in self._has_audio_cache:
            try:
                self._has_audio_cache[path] = probe(path).has_audio
            except Exception:
                self._has_audio_cache[path] = False
        return self._has_audio_cache[path]

    def build(self) -> tuple[list[str], str, str, str, float]:
        """Returns (input_args, filter_complex, video_label, audio_label, total_duration)."""
        self._input_count = 0
        video_track = next((t for t in self.project.tracks if t.kind == TrackKind.VIDEO), None)
        audio_track = next((t for t in self.project.tracks if t.kind == TrackKind.AUDIO), None)
        text_track = next((t for t in self.project.tracks if t.kind == TrackKind.TEXT), None)

        video_clips = sorted(video_track.clips, key=lambda c: c.start_time) if video_track else []
        audio_clips = sorted(audio_track.clips, key=lambda c: c.start_time) if audio_track else []
        text_clips = sorted(text_track.clips, key=lambda c: c.start_time) if text_track else []

        for clip in video_clips:
            self._register_input(clip)
        for clip in audio_clips:
            self._register_input(clip)

        if video_clips:
            video_label, audio_label, total_duration, overlaps = self._fold_video_and_audio(video_clips)
        else:
            total_duration = max((c.end_time for c in audio_clips), default=1.0)
            video_label = self._black_filler(total_duration)
            audio_label = self._silence_filler(total_duration)
            overlaps = []

        if text_clips:
            video_label = self._apply_titles(video_label, video_clips, overlaps, text_clips)

        if audio_clips:
            audio_label = self._mix_music(audio_label, video_clips, overlaps, audio_clips)

        return self.input_args, "; ".join(self.filters), video_label, audio_label, total_duration

    def _register_input(self, clip: Clip) -> None:
        index = self._input_count
        if clip.clip_type == ClipType.IMAGE:
            self.input_args += ["-loop", "1", "-t", f"{clip.duration:.6f}", "-i", clip.source_path]
        else:
            self.input_args += ["-i", clip.source_path]
        self._clip_input_index[id(clip)] = index
        self._input_count += 1

    def _black_filler(self, duration: float) -> str:
        label = self._new_label("blk")
        w, h, fps = self.project.width, self.project.height, self.project.fps
        self.filters.append(f"color=c=black:s={w}x{h}:d={duration:.6f}:r={fps}[{label}]")
        return label

    def _silence_filler(self, duration: float) -> str:
        label = self._new_label("sil")
        self.filters.append(
            f"anullsrc=channel_layout=stereo:sample_rate=44100,atrim=duration={duration:.6f}[{label}]"
        )
        return label

    def _normalized_clip_video(self, clip: Clip) -> str:
        idx = self._clip_input_index[id(clip)]
        w, h, fps = self.project.width, self.project.height, self.project.fps
        label = self._new_label("v")
        scale_pad = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
        if clip.clip_type == ClipType.IMAGE:
            self.filters.append(f"[{idx}:v]{scale_pad}[{label}]")
        else:
            self.filters.append(
                f"[{idx}:v]trim=start={clip.in_point:.6f}:end={clip.out_point:.6f},"
                f"setpts=PTS-STARTPTS,{scale_pad}[{label}]"
            )
        return label

    def _normalized_clip_audio(self, clip: Clip) -> str:
        label = self._new_label("a")
        if clip.clip_type == ClipType.IMAGE or not self._has_audio(clip.source_path):
            self.filters.append(
                f"anullsrc=channel_layout=stereo:sample_rate=44100,atrim=duration={clip.duration:.6f}[{label}]"
            )
        else:
            idx = self._clip_input_index[id(clip)]
            self.filters.append(
                f"[{idx}:a]atrim=start={clip.in_point:.6f}:end={clip.out_point:.6f},"
                f"asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo[{label}]"
            )
        return label

    def _overlap_for(self, prev_clip: Clip, clip: Clip) -> float:
        """Any timeline overlap between adjacent clips is treated as a
        crossfade of that length -- what you see on the timeline is what
        renders, with no separate "mark as crossfade" step."""
        raw = prev_clip.end_time - clip.start_time
        if raw <= MIN_TRANSITION_SECONDS:
            return 0.0
        return min(raw, prev_clip.duration * 0.9, clip.duration * 0.9)

    def _fold_video_and_audio(self, video_clips: list[Clip]) -> tuple[str, str, float, list[float]]:
        w, h, fps = self.project.width, self.project.height, self.project.fps
        acc_video: Optional[str] = None
        acc_audio: Optional[str] = None
        acc_duration = 0.0
        overlaps: list[float] = [0.0]

        for i, clip in enumerate(video_clips):
            v_label = self._normalized_clip_video(clip)
            a_label = self._normalized_clip_audio(clip)

            gap = clip.start_time - (video_clips[i - 1].end_time if i > 0 else 0.0)
            gap = gap if gap > MIN_TRANSITION_SECONDS else 0.0
            overlap = self._overlap_for(video_clips[i - 1], clip) if i > 0 else 0.0
            if i > 0:
                overlaps.append(overlap)

            if i == 0:
                if gap > 0:
                    gap_v = self._black_filler(gap)
                    gap_a = self._silence_filler(gap)
                    v_cat, a_cat = self._new_label("vcat"), self._new_label("acat")
                    self.filters.append(f"[{gap_v}][{v_label}]concat=n=2:v=1:a=0[{v_cat}]")
                    self.filters.append(f"[{gap_a}][{a_label}]concat=n=2:v=0:a=1[{a_cat}]")
                    acc_video, acc_audio = v_cat, a_cat
                    acc_duration = gap + clip.duration
                else:
                    acc_video, acc_audio = v_label, a_label
                    acc_duration = clip.duration
                continue

            if overlap > 0:
                vx, ax = self._new_label("vx"), self._new_label("ax")
                offset = acc_duration - overlap
                self.filters.append(
                    f"[{acc_video}][{v_label}]xfade=transition=fade:duration={overlap:.6f}:offset={offset:.6f}[{vx}]"
                )
                self.filters.append(f"[{acc_audio}][{a_label}]acrossfade=d={overlap:.6f}[{ax}]")
                acc_video, acc_audio = vx, ax
                acc_duration = acc_duration + clip.duration - overlap
            else:
                v_segs, a_segs = [acc_video], [acc_audio]
                if gap > 0:
                    v_segs.append(self._black_filler(gap))
                    a_segs.append(self._silence_filler(gap))
                    acc_duration += gap
                v_segs.append(v_label)
                a_segs.append(a_label)
                v_cat, a_cat = self._new_label("vcat"), self._new_label("acat")
                v_ins = "".join(f"[{s}]" for s in v_segs)
                a_ins = "".join(f"[{s}]" for s in a_segs)
                self.filters.append(f"{v_ins}concat=n={len(v_segs)}:v=1:a=0[{v_cat}]")
                self.filters.append(f"{a_ins}concat=n={len(a_segs)}:v=0:a=1[{a_cat}]")
                acc_video, acc_audio = v_cat, a_cat
                acc_duration += clip.duration

        return acc_video, acc_audio, acc_duration, overlaps

    def _rendered_time(self, t: float, video_clips: list[Clip], overlaps: list[float]) -> float:
        shrink = 0.0
        for j in range(1, len(video_clips)):
            if video_clips[j].start_time <= t:
                shrink += overlaps[j]
        return max(0.0, t - shrink)

    def _apply_titles(self, video_label: str, video_clips: list[Clip], overlaps: list[float], text_clips: list[Clip]) -> str:
        w, h, fps = self.project.width, self.project.height, self.project.fps
        label = video_label
        for clip in text_clips:
            rs = self._rendered_time(clip.start_time, video_clips, overlaps)
            re = self._rendered_time(clip.end_time, video_clips, overlaps)
            if re <= rs:
                continue
            new_label = self._new_label("vt")
            escaped = _escape_drawtext(clip.text or "")
            self.filters.append(
                f"[{label}]drawtext=text='{escaped}':fontcolor=white:fontsize=36:"
                f"x=(w-text_w)/2:y=h-text_h-40:box=1:boxcolor=black@0.5:boxborderw=8:"
                f"enable='between(t\\,{rs:.6f}\\,{re:.6f})'[{new_label}]"
            )
            label = new_label
        return label

    def _mix_music(self, audio_label: str, video_clips: list[Clip], overlaps: list[float], audio_clips: list[Clip]) -> str:
        delayed_labels = []
        for clip in audio_clips:
            idx = self._clip_input_index[id(clip)]
            trimmed = self._new_label("m")
            self.filters.append(
                f"[{idx}:a]atrim=start={clip.in_point:.6f}:end={clip.out_point:.6f},"
                f"asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo[{trimmed}]"
            )
            rs = self._rendered_time(clip.start_time, video_clips, overlaps)
            delay_ms = max(0, int(round(rs * 1000)))
            delayed = self._new_label("md")
            self.filters.append(f"[{trimmed}]adelay=delays={delay_ms}|{delay_ms}[{delayed}]")
            delayed_labels.append(delayed)

        if len(delayed_labels) == 1:
            music_label = delayed_labels[0]
        else:
            music_label = self._new_label("mmix")
            ins = "".join(f"[{s}]" for s in delayed_labels)
            self.filters.append(f"{ins}amix=inputs={len(delayed_labels)}:duration=longest:dropout_transition=0[{music_label}]")

        final_label = self._new_label("afinal")
        self.filters.append(f"[{audio_label}][{music_label}]amix=inputs=2:duration=longest:dropout_transition=0[{final_label}]")
        return final_label


def export_timeline(project: Project, output_path: str, on_progress: ProgressCallback = None) -> None:
    """Export a full multi-track Project (Video Maker) to a video file."""
    require_ffmpeg()
    builder = _TimelineGraphBuilder(project)
    input_args, filter_complex, video_label, audio_label, total_duration = builder.build()

    cmd = ["ffmpeg", "-y", *input_args, "-filter_complex", filter_complex]
    cmd += ["-map", f"[{video_label}]", "-map", f"[{audio_label}]"]
    cmd += ["-t", f"{total_duration:.6f}"]
    cmd += ["-r", str(project.fps), "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", X264_PRESET, "-c:a", "aac"]
    cmd += ["-progress", "pipe:1", "-loglevel", "error", output_path]

    _run_with_progress(cmd, total_duration, on_progress)
