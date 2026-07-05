"""Preview player: plays a single selected clip (video, audio, or static
image), or flips through a sequence of image clips at their configured
per-image durations (e.g. previewing a slideshow run on the timeline)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.models import ClipType
from .thumbnail_utils import load_scaled_qimage


def _format_ms(ms: int) -> str:
    seconds = ms // 1000
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class PreviewPlayer(QWidget):
    position_changed = Signal(int)  # ms
    duration_changed = Signal(int)  # ms

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)

        self._stack = QStackedWidget()
        self._video_widget = QVideoWidget()
        self._player.setVideoOutput(self._video_widget)
        self._stack.addWidget(self._video_widget)

        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet("background: #222;")
        self._stack.addWidget(self._image_label)

        self._empty_label = QLabel("Click a clip in the media pool or timeline below to preview it here")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet("background: #222; color: #888;")
        self._stack.addWidget(self._empty_label)
        self._stack.setCurrentWidget(self._empty_label)

        layout = QVBoxLayout(self)
        layout.addWidget(self._stack, stretch=1)

        controls = QHBoxLayout()
        self._play_btn = QPushButton("▶")
        self._play_btn.clicked.connect(self.toggle_play)
        controls.addWidget(self._play_btn)

        self._position_label = QLabel("00:00")
        controls.addWidget(self._position_label)

        self._scrubber = QSlider(Qt.Orientation.Horizontal)
        self._scrubber.sliderMoved.connect(self._on_scrub)
        controls.addWidget(self._scrubber, stretch=1)

        self._duration_label = QLabel("00:00")
        controls.addWidget(self._duration_label)
        layout.addLayout(controls)

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)

        self._current_type: ClipType | None = None
        self._sequence_frames: list[tuple[str, float]] = []
        self._sequence_index = 0
        self._sequence_timer = QTimer(self)
        self._sequence_timer.setSingleShot(True)
        self._sequence_timer.timeout.connect(self._advance_sequence)
        # Nothing is loaded yet -- without this, the button looks clickable
        # but toggle_play() silently no-ops, which reads as "broken".
        self._play_btn.setEnabled(False)
        self._scrubber.setEnabled(False)

    # --- Loading ---------------------------------------------------------------

    def load(self, path: str, clip_type: ClipType, text: str | None = None) -> None:
        self._stop_sequence()
        self._current_type = clip_type
        if clip_type == ClipType.IMAGE:
            self._player.stop()
            pixmap = QPixmap(path).scaled(
                self._image_label.size() if self._image_label.size().width() > 0 else QPixmap(path).size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._image_label.setPixmap(pixmap)
            self._stack.setCurrentWidget(self._image_label)
            self._scrubber.setEnabled(False)
            self._play_btn.setEnabled(False)
        elif clip_type == ClipType.TEXT:
            self._player.stop()
            pixmap = QPixmap(400, 300)
            pixmap.fill(Qt.GlobalColor.black)
            painter = QPainter(pixmap)
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(
                pixmap.rect(),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                text or "",
            )
            painter.end()
            self._image_label.setPixmap(pixmap)
            self._stack.setCurrentWidget(self._image_label)
            self._scrubber.setEnabled(False)
            self._play_btn.setEnabled(False)
        else:
            self._stack.setCurrentWidget(self._video_widget if clip_type == ClipType.VIDEO else self._empty_label)
            self._scrubber.setEnabled(True)
            self._play_btn.setEnabled(True)
            self._player.setSource(QUrl.fromLocalFile(path))

    def load_image_sequence(self, frames: list[tuple[str, float]]) -> None:
        """frames: (path, duration_seconds) in display order. Lets Play flip
        through them at their own durations -- e.g. previewing a run of
        image clips on the timeline like a slideshow, instead of only being
        able to see one still frame at a time."""
        self._player.stop()
        self._current_type = ClipType.IMAGE
        self._sequence_frames = frames
        self._sequence_index = 0
        self._scrubber.setEnabled(False)
        if frames:
            self._show_sequence_frame(0)
            self._stack.setCurrentWidget(self._image_label)
            self._play_btn.setEnabled(True)
        else:
            self._play_btn.setEnabled(False)

    def clear(self) -> None:
        self._stop_sequence()
        self._player.stop()
        self._current_type = None
        self._stack.setCurrentWidget(self._empty_label)

    # --- Controls ---------------------------------------------------------------

    def toggle_play(self) -> None:
        if self._sequence_frames:
            if self._sequence_timer.isActive():
                self._sequence_timer.stop()
                self._play_btn.setText("▶")
            else:
                self._play_btn.setText("⏸")
                self._sequence_timer.start(int(self._sequence_frames[self._sequence_index][1] * 1000))
            return
        if self._current_type not in (ClipType.VIDEO, ClipType.AUDIO):
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _stop_sequence(self) -> None:
        self._sequence_timer.stop()
        self._sequence_frames = []
        self._sequence_index = 0

    def _show_sequence_frame(self, index: int) -> None:
        path, _ = self._sequence_frames[index]
        image = load_scaled_qimage(path, self._image_label.size())
        self._image_label.setPixmap(QPixmap.fromImage(image))

    def _advance_sequence(self) -> None:
        if not self._sequence_frames:
            return
        self._sequence_index = (self._sequence_index + 1) % len(self._sequence_frames)
        self._show_sequence_frame(self._sequence_index)
        self._sequence_timer.start(int(self._sequence_frames[self._sequence_index][1] * 1000))

    def seek_ms(self, ms: int) -> None:
        self._player.setPosition(ms)

    # --- Signal handlers ---------------------------------------------------------------

    def _on_scrub(self, value: int) -> None:
        self._player.setPosition(value)

    def _on_position_changed(self, position: int) -> None:
        if not self._scrubber.isSliderDown():
            self._scrubber.setValue(position)
        self._position_label.setText(_format_ms(position))
        self.position_changed.emit(position)

    def _on_duration_changed(self, duration: int) -> None:
        self._scrubber.setRange(0, max(0, duration))
        self._duration_label.setText(_format_ms(duration))
        self.duration_changed.emit(duration)

    def _on_state_changed(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self._play_btn.setText("⏸" if playing else "▶")
