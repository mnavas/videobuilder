"""Project data model for the VideoBuilder timeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ClipType(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    TEXT = "text"


class TrackKind(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"


@dataclass
class Clip:
    """A single clip placed on a track.

    in_point / out_point are seconds into the source media that bound the
    trimmed region. start_time is where the clip begins on the timeline.
    duration is derived as out_point - in_point, except for TEXT clips
    (no source media) where it's authoritative.
    """

    source_path: str
    clip_type: ClipType
    start_time: float
    in_point: float = 0.0
    out_point: float = 0.0
    text: Optional[str] = None

    @property
    def duration(self) -> float:
        return max(0.0, self.out_point - self.in_point)

    @property
    def end_time(self) -> float:
        return self.start_time + self.duration

    def to_dict(self) -> dict:
        return {
            "source_path": self.source_path,
            "clip_type": self.clip_type.value,
            "start_time": self.start_time,
            "in_point": self.in_point,
            "out_point": self.out_point,
            "text": self.text,
        }

    @staticmethod
    def from_dict(data: dict) -> "Clip":
        return Clip(
            source_path=data["source_path"],
            clip_type=ClipType(data["clip_type"]),
            start_time=data["start_time"],
            in_point=data.get("in_point", 0.0),
            out_point=data.get("out_point", 0.0),
            text=data.get("text"),
        )


@dataclass
class Track:
    kind: TrackKind
    clips: list[Clip] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"kind": self.kind.value, "clips": [c.to_dict() for c in self.clips]}

    @staticmethod
    def from_dict(data: dict) -> "Track":
        return Track(
            kind=TrackKind(data["kind"]),
            clips=[Clip.from_dict(c) for c in data.get("clips", [])],
        )


@dataclass
class Project:
    name: str = "Untitled Project"
    width: int = 1280
    height: int = 720
    fps: float = 30.0
    tracks: list[Track] = field(default_factory=list)

    def total_duration(self) -> float:
        end = 0.0
        for track in self.tracks:
            for clip in track.clips:
                end = max(end, clip.end_time)
        return end

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "tracks": [t.to_dict() for t in self.tracks],
        }

    @staticmethod
    def from_dict(data: dict) -> "Project":
        return Project(
            name=data.get("name", "Untitled Project"),
            width=data.get("width", 1280),
            height=data.get("height", 720),
            fps=data.get("fps", 30.0),
            tracks=[Track.from_dict(t) for t in data.get("tracks", [])],
        )
