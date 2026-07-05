"""Multi-track timeline: drag clips from the media pool, trim, split, scrub.

v1 scope: exactly one track per kind (video/audio/text) — see analysis.md
non-goals. Dragging a clip to overlap the previous one on the same track
automatically creates a crossfade of that overlap's length at export time.
"""
from __future__ import annotations

import os
from typing import Callable, Optional

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.media_probe import probe
from ..core.models import Clip, ClipType, Project, Track, TrackKind
from .thumbnail_utils import load_scaled_qimage

PIXELS_PER_SECOND_DEFAULT = 60.0
PIXELS_PER_SECOND_RANGE = (10.0, 400.0)
TRACK_HEIGHT = 64
RULER_HEIGHT = 28
EDGE_GRAB_PX = 8
SNAP_PX = 8
MIN_CLIP_SECONDS = 0.1
DEFAULT_IMAGE_TEXT_SECONDS = 3.0

TRACK_LABELS = {TrackKind.VIDEO: "Video", TrackKind.AUDIO: "Audio", TrackKind.TEXT: "Titles"}
TRACK_ROW_COLORS = {
    TrackKind.VIDEO: QColor("#1f3a52"),
    TrackKind.AUDIO: QColor("#244a24"),
    TrackKind.TEXT: QColor("#4a3a1f"),
}
CLIP_COLORS = {
    ClipType.VIDEO: QColor("#3a6ea5"),
    ClipType.IMAGE: QColor("#3a6ea5"),
    ClipType.AUDIO: QColor("#4a8a4a"),
    ClipType.TEXT: QColor("#a5763a"),
}
TICK_INTERVALS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600]


def _format_seconds(t: float) -> str:
    total = int(round(t))
    return f"{total // 60}:{total % 60:02d}"


class ClipItem(QGraphicsRectItem):
    HEIGHT_PADDING = 6

    def __init__(self, clip: Clip, track_index: int, timeline: "TimelineWidget"):
        super().__init__()
        self.clip = clip
        self.track_index = track_index
        self.timeline = timeline
        self._drag_mode: Optional[str] = None
        self._drag_anchor_scene_x = 0.0
        self._drag_orig_start = 0.0
        self._drag_orig_in = 0.0
        self._drag_orig_out = 0.0

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(1)
        # paint() always sets its own pen explicitly; without this, the item's
        # *default* 1px pen still pads its bounding rect/hit-test shape by
        # ~0.5px per side, creating an ambiguous click zone exactly where two
        # adjacent clips touch -- right where a trim-edge click is aimed.
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.update_geometry()

    def update_geometry(self) -> None:
        pps = self.timeline.pixels_per_second
        y = RULER_HEIGHT + self.track_index * TRACK_HEIGHT + self.HEIGHT_PADDING / 2
        h = TRACK_HEIGHT - self.HEIGHT_PADDING
        w = max(self.clip.duration * pps, 4.0)
        self.setRect(0, 0, w, h)
        self.setPos(self.clip.start_time * pps, y)

    def _edge_at(self, local_x: float) -> str:
        w = self.rect().width()
        if local_x <= EDGE_GRAB_PX:
            return "trim-left"
        if local_x >= w - EDGE_GRAB_PX:
            return "trim-right"
        return "move"

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            self.setSelected(not self.isSelected())
            if not self.isSelected():
                # Ctrl-click just removed this clip from the selection --
                # arming a drag on it now would move a deselected clip.
                event.accept()
                return
        else:
            self.scene().clearSelection()
            self.setSelected(True)
        self.timeline.clip_selected.emit(self.clip)
        self._drag_mode = self._edge_at(event.pos().x())
        self._drag_anchor_scene_x = event.scenePos().x()
        self._drag_orig_start = self.clip.start_time
        self._drag_orig_in = self.clip.in_point
        self._drag_orig_out = self.clip.out_point
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_mode is None:
            return
        pps = self.timeline.pixels_per_second
        delta_seconds = (event.scenePos().x() - self._drag_anchor_scene_x) / pps

        if self._drag_mode == "move":
            new_start = max(0.0, self._drag_orig_start + delta_seconds)
            self.clip.start_time = self.timeline.snap_time(new_start, self.clip)
        elif self._drag_mode == "trim-left":
            max_in = self._drag_orig_out - MIN_CLIP_SECONDS
            new_in = max(0.0, min(self._drag_orig_in + delta_seconds, max_in))
            self.clip.in_point = new_in
            self.clip.start_time = max(0.0, self._drag_orig_start + (new_in - self._drag_orig_in))
        elif self._drag_mode == "trim-right":
            limit = self.timeline.source_duration_limit(self.clip)
            min_out = self._drag_orig_in + MIN_CLIP_SECONDS
            new_out = max(min_out, self._drag_orig_out + delta_seconds)
            if limit is not None:
                new_out = min(new_out, limit)
            self.clip.out_point = new_out

        self.update_geometry()

    def mouseReleaseEvent(self, event):
        if self._drag_mode is not None:
            self._drag_mode = None
            self.timeline.project_modified.emit()
        super().mouseReleaseEvent(event)

    def hoverMoveEvent(self, event):
        edge = self._edge_at(event.pos().x())
        if edge in ("trim-left", "trim-right"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().hoverMoveEvent(event)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        rect = self.rect()
        color = CLIP_COLORS.get(self.clip.clip_type, QColor("#666"))
        if self.isSelected():
            painter.setBrush(QBrush(color.lighter(130)))
            painter.setPen(QPen(QColor("#fff"), 2))
        else:
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(QColor("#111"), 1))
        painter.drawRoundedRect(rect, 4, 4)

        text_x = rect.x() + 4
        thumb = self.timeline.thumbnail_for(self.clip.source_path)
        if thumb is not None and rect.width() > 30:
            thumb_h = rect.height() - 6
            thumb_w = thumb_h * thumb.width() / max(thumb.height(), 1)
            painter.drawPixmap(int(rect.x() + 3), int(rect.y() + 3), int(thumb_w), int(thumb_h), thumb)
            text_x = rect.x() + 3 + thumb_w + 6

        painter.setPen(QPen(QColor("#fff")))
        label = self.clip.text if self.clip.clip_type == ClipType.TEXT else os.path.basename(self.clip.source_path)
        from PySide6.QtCore import QRectF

        text_rect = QRectF(text_x, rect.y(), rect.right() - text_x - 2, rect.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label or "")

    def contextMenuEvent(self, event):
        menu = QMenu()
        delete_action = menu.addAction("Delete clip")
        chosen = menu.exec(event.screenPos())
        if chosen == delete_action:
            self.timeline.delete_clip(self.clip)


class TimelineGraphicsView(QGraphicsView):
    def __init__(self, timeline: "TimelineWidget"):
        super().__init__(timeline.scene)
        self.timeline = timeline
        self._scrubbing = False
        self.setAcceptDrops(True)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        mime = event.mimeData()
        if not mime.hasText():
            super().dropEvent(event)
            return
        path = mime.text()
        type_bytes = mime.data("application/x-videobuilder-clip-type")
        clip_type = ClipType(bytes(type_bytes).decode()) if type_bytes else ClipType.VIDEO
        thumbnail = QPixmap.fromImage(mime.imageData()) if mime.hasImage() else None
        scene_pos = self.mapToScene(event.position().toPoint())
        self.timeline.handle_drop(path, clip_type, scene_pos.x(), thumbnail)
        event.acceptProposedAction()

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        scene_pos = self.mapToScene(pos)
        item = self.itemAt(pos)
        is_clip = isinstance(item, ClipItem)
        if scene_pos.y() <= RULER_HEIGHT and not is_clip:
            self.timeline.scrub_to_x(scene_pos.x())
            self._scrubbing = True
            # Don't forward to the scene's default click-handling: it would
            # clear the current clip selection just because the ruler isn't
            # a selectable item, breaking "select clip, scrub playhead, split".
            return
        if not is_clip:
            self.scene().clearSelection()
            self.timeline.clip_selected.emit(None)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._scrubbing:
            scene_pos = self.mapToScene(event.position().toPoint())
            self.timeline.scrub_to_x(scene_pos.x())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._scrubbing = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        pos = event.position().toPoint()
        scene_pos = self.mapToScene(pos)
        item = self.itemAt(pos)
        if isinstance(item, ClipItem) and item.clip.clip_type == ClipType.TEXT:
            self.timeline.edit_title_clip(item.clip)
            return
        if not isinstance(item, ClipItem):
            track_index = self.timeline.track_index_at_y(scene_pos.y())
            if track_index is not None and self.timeline.project.tracks[track_index].kind == TrackKind.TEXT:
                self.timeline.add_title_clip_at(scene_pos.x(), track_index)
                return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_S:
            self.timeline.split_selected_at_playhead()
        elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.timeline.delete_selected()
        elif event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.timeline.select_all_clips()
        else:
            super().keyPressEvent(event)


class TimelineWidget(QWidget):
    clip_selected = Signal(object)  # Clip | None
    playhead_changed = Signal(float)
    project_modified = Signal()

    def __init__(self, project: Project, parent: QWidget | None = None):
        super().__init__(parent)
        self.project = project
        self.pixels_per_second = PIXELS_PER_SECOND_DEFAULT
        self.playhead_time = 0.0
        self._thumbnails: dict[str, QPixmap] = {}
        self._duration_cache: dict[str, Optional[float]] = {}

        self.scene = QGraphicsScene()
        self.playhead_item = QGraphicsLineItem()
        self.playhead_item.setPen(QPen(QColor("#e74c3c"), 2))
        self.playhead_item.setZValue(10)
        self.scene.addItem(self.playhead_item)

        self.view = TimelineGraphicsView(self)
        self.view.setFixedHeight(RULER_HEIGHT + TRACK_HEIGHT * len(project.tracks) + 4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Zoom:"))
        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setFixedWidth(28)
        zoom_out_btn.clicked.connect(lambda: self.set_zoom(self.pixels_per_second * 0.8))
        toolbar.addWidget(zoom_out_btn)
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedWidth(28)
        zoom_in_btn.clicked.connect(lambda: self.set_zoom(self.pixels_per_second * 1.25))
        toolbar.addWidget(zoom_in_btn)
        toolbar.addSpacing(16)
        split_btn = QPushButton("Split at playhead (S)")
        split_btn.clicked.connect(self.split_selected_at_playhead)
        toolbar.addWidget(split_btn)
        toolbar.addWidget(QLabel("Double-click the Titles row to add a title clip."))
        toolbar.addStretch()
        self._total_duration_label = QLabel()
        self._total_duration_label.setStyleSheet("font-weight: bold;")
        toolbar.addWidget(self._total_duration_label)
        layout.addLayout(toolbar)

        bulk_toolbar = QHBoxLayout()
        bulk_toolbar.addWidget(QLabel("Ctrl/Shift-click clips (or Ctrl+A) to select several, then:"))
        self._bulk_duration_spin = QDoubleSpinBox()
        self._bulk_duration_spin.setRange(0.1, 600.0)
        self._bulk_duration_spin.setSingleStep(0.5)
        self._bulk_duration_spin.setValue(2.0)
        bulk_toolbar.addWidget(self._bulk_duration_spin)
        set_duration_btn = QPushButton("Set Duration for Selected")
        set_duration_btn.setToolTip(
            "Applies to every selected clip. Video/audio clips are clamped to their own source length."
        )
        set_duration_btn.clicked.connect(lambda: self.set_duration_for_selected(self._bulk_duration_spin.value()))
        bulk_toolbar.addWidget(set_duration_btn)
        bulk_toolbar.addSpacing(16)
        remove_gaps_btn = QPushButton("Pack Clips Tight (No Gaps)")
        remove_gaps_btn.setToolTip(
            "Repacks every clip on the Video track back-to-back, in order -- closes gaps left by "
            "shortening clips and resolves overlaps left by lengthening them, so playback is smooth "
            "with no black gaps or accidental crossfades."
        )
        remove_gaps_btn.clicked.connect(lambda: self.remove_gaps(TrackKind.VIDEO))
        bulk_toolbar.addWidget(remove_gaps_btn)
        bulk_toolbar.addStretch()
        layout.addLayout(bulk_toolbar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.addWidget(self._build_track_labels())
        body.addWidget(self.view, stretch=1)
        layout.addLayout(body)

        # A plain clip drag (move) only emits project_modified, it doesn't
        # call rebuild() -- so the total-duration label must listen directly,
        # or it goes stale after every drag that doesn't also trim/split/etc.
        self.project_modified.connect(self._update_total_duration_label)

        # Snapshot-based undo: every project_modified pushes the new state
        # (deduped, so no-op emissions like a click-without-drag don't count).
        self._undo_stack: list[dict] = [self.project.to_dict()]
        self._undo_index = 0
        self._restoring_snapshot = False
        self.project_modified.connect(self._push_undo_snapshot)

        self.rebuild()

    # --- Track label column -----------------------------------------------------

    def _build_track_labels(self) -> QWidget:
        col = QWidget()
        col.setFixedWidth(72)
        v = QVBoxLayout(col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        spacer = QLabel("")
        spacer.setFixedHeight(RULER_HEIGHT)
        v.addWidget(spacer)
        for track in self.project.tracks:
            lbl = QLabel(TRACK_LABELS.get(track.kind, track.kind.value))
            lbl.setFixedHeight(TRACK_HEIGHT)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            color = TRACK_ROW_COLORS.get(track.kind, QColor("#333")).name()
            lbl.setStyleSheet(f"background: {color}; color: white;")
            v.addWidget(lbl)
        v.addStretch()
        return col

    # --- Model lookups -----------------------------------------------------

    def _track_of(self, clip: Clip) -> Optional[Track]:
        for track in self.project.tracks:
            for c in track.clips:
                if c is clip:
                    return track
        return None

    def _remove_clip_from_model(self, clip: Clip) -> None:
        for track in self.project.tracks:
            for i, c in enumerate(track.clips):
                if c is clip:
                    del track.clips[i]
                    return

    def _track_index_for_kind(self, kind: TrackKind) -> Optional[int]:
        for i, track in enumerate(self.project.tracks):
            if track.kind == kind:
                return i
        return None

    def track_index_at_y(self, y: float) -> Optional[int]:
        if y < RULER_HEIGHT:
            return None
        idx = int((y - RULER_HEIGHT) // TRACK_HEIGHT)
        return idx if 0 <= idx < len(self.project.tracks) else None

    def get_source_duration(self, path: str) -> Optional[float]:
        if path not in self._duration_cache:
            try:
                self._duration_cache[path] = probe(path).duration
            except Exception:
                self._duration_cache[path] = None
        return self._duration_cache[path]

    def source_duration_limit(self, clip: Clip) -> Optional[float]:
        if clip.clip_type in (ClipType.IMAGE, ClipType.TEXT):
            return None
        return self.get_source_duration(clip.source_path)

    def thumbnail_for(self, path: str) -> Optional[QPixmap]:
        return self._thumbnails.get(path)

    def snap_time(self, value: float, clip: Clip) -> float:
        track = self._track_of(clip)
        candidates = [0.0, self.playhead_time]
        if track:
            for other in track.clips:
                if other is clip:
                    continue
                candidates.append(other.start_time)
                candidates.append(other.end_time)
        tolerance = SNAP_PX / self.pixels_per_second
        for c in candidates:
            if abs(value - c) <= tolerance:
                return max(0.0, c)
        return value

    # --- Drop / add clips -----------------------------------------------------

    def _default_duration_for(self, path: str, clip_type: ClipType) -> float:
        if clip_type in (ClipType.IMAGE, ClipType.TEXT):
            return DEFAULT_IMAGE_TEXT_SECONDS
        dur = self.get_source_duration(path)
        return max(dur, MIN_CLIP_SECONDS) if dur else DEFAULT_IMAGE_TEXT_SECONDS

    def handle_drop(self, path: str, clip_type: ClipType, scene_x: float, thumbnail: Optional[QPixmap]) -> None:
        target_kind = TrackKind.AUDIO if clip_type == ClipType.AUDIO else TrackKind.VIDEO
        track_index = self._track_index_for_kind(target_kind)
        if track_index is None:
            return
        start_time = max(0.0, scene_x / self.pixels_per_second)
        duration = self._default_duration_for(path, clip_type)
        clip = Clip(source_path=path, clip_type=clip_type, start_time=start_time, in_point=0.0, out_point=duration)
        self.project.tracks[track_index].clips.append(clip)
        clip.start_time = self.snap_time(clip.start_time, clip)
        if thumbnail is not None:
            self._thumbnails[path] = thumbnail
        self.rebuild()
        self.project_modified.emit()

    def add_image_sequence(
        self,
        paths: list[str],
        seconds_per_image: float,
        thumbnail_lookup: Optional[Callable[[str], Optional[QIcon]]] = None,
    ) -> None:
        """Appends a batch of images to the video track, back-to-back, each
        shown for seconds_per_image -- e.g. 10 images at 2s each = a 20s run."""
        self.add_clips_sequence(
            [(path, ClipType.IMAGE) for path in paths], seconds_per_image, thumbnail_lookup
        )

    def add_clips_sequence(
        self,
        entries: list[tuple[str, ClipType]],
        image_duration: float,
        thumbnail_lookup: Optional[Callable[[str], Optional[QIcon]]] = None,
    ) -> None:
        """Appends a batch of clips back-to-back, in the given order. Video and
        image clips go to the video track, audio clips to the audio track --
        each track keeps its own cursor, starting right after that track's
        current last clip (0 if empty). Video/audio clips use their own real
        duration; image_duration only applies to images (e.g. 10 images at 2s
        each = a 20s run).

        thumbnail_lookup lets a caller hand over an already-decoded icon (e.g.
        the media pool's) instead of re-decoding every image from disk here --
        matters for large batches where a second decode pass would itself be
        slow enough to feel like a freeze.
        """
        video_index = self._track_index_for_kind(TrackKind.VIDEO)
        audio_index = self._track_index_for_kind(TrackKind.AUDIO)
        if video_index is None or audio_index is None or not entries:
            return
        video_track = self.project.tracks[video_index]
        audio_track = self.project.tracks[audio_index]
        video_cursor = max((c.end_time for c in video_track.clips), default=0.0)
        audio_cursor = max((c.end_time for c in audio_track.clips), default=0.0)

        for path, clip_type in entries:
            if clip_type == ClipType.AUDIO:
                duration = self.get_source_duration(path) or image_duration
                clip = Clip(source_path=path, clip_type=ClipType.AUDIO, start_time=audio_cursor, in_point=0.0, out_point=duration)
                audio_track.clips.append(clip)
                audio_cursor += duration
                continue

            duration = image_duration if clip_type == ClipType.IMAGE else (self.get_source_duration(path) or image_duration)
            clip = Clip(source_path=path, clip_type=clip_type, start_time=video_cursor, in_point=0.0, out_point=duration)
            video_track.clips.append(clip)
            self._cache_thumbnail_if_missing(path, thumbnail_lookup)
            video_cursor += duration

        self.rebuild()
        self.project_modified.emit()

    def _cache_thumbnail_if_missing(self, path: str, thumbnail_lookup: Optional[Callable[[str], Optional[QIcon]]]) -> None:
        if path in self._thumbnails:
            return
        pixmap = None
        if thumbnail_lookup is not None:
            icon = thumbnail_lookup(path)
            if icon is not None and not icon.isNull():
                pixmap = icon.pixmap(QSize(160, 120))
        if pixmap is None:
            try:
                image = load_scaled_qimage(path, QSize(160, 120))
                pixmap = QPixmap.fromImage(image)
            except Exception:
                pixmap = None
        if pixmap is not None:
            self._thumbnails[path] = pixmap

    def add_title_clip_at(self, scene_x: float, track_index: int) -> None:
        text, ok = QInputDialog.getText(self.view, "Add Title", "Title text:")
        if not ok or not text.strip():
            return
        duration, ok2 = QInputDialog.getDouble(self.view, "Title Duration", "Seconds:", DEFAULT_IMAGE_TEXT_SECONDS, 0.5, 60.0, 1)
        if not ok2:
            return
        start_time = max(0.0, scene_x / self.pixels_per_second)
        clip = Clip(source_path="", clip_type=ClipType.TEXT, start_time=start_time, in_point=0.0, out_point=duration, text=text.strip())
        self.project.tracks[track_index].clips.append(clip)
        clip.start_time = self.snap_time(clip.start_time, clip)
        self.rebuild()
        self.project_modified.emit()

    def edit_title_clip(self, clip: Clip) -> None:
        text, ok = QInputDialog.getText(self.view, "Edit Title", "Title text:", text=clip.text or "")
        if not ok or not text.strip():
            return
        duration, ok2 = QInputDialog.getDouble(self.view, "Title Duration", "Seconds:", clip.duration, 0.5, 60.0, 1)
        if not ok2:
            return
        clip.text = text.strip()
        clip.out_point = clip.in_point + duration
        self.rebuild()
        self.project_modified.emit()

    def delete_clip(self, clip: Clip) -> None:
        self._remove_clip_from_model(clip)
        self.rebuild()
        self.project_modified.emit()

    def delete_selected(self) -> None:
        for item in [it for it in self.scene.selectedItems() if isinstance(it, ClipItem)]:
            self._remove_clip_from_model(item.clip)
        self.rebuild()
        self.project_modified.emit()

    def select_all_clips(self) -> None:
        for item in self.scene.items():
            if isinstance(item, ClipItem):
                item.setSelected(True)

    # --- Undo / redo -----------------------------------------------------

    def _push_undo_snapshot(self) -> None:
        if self._restoring_snapshot:
            return
        snapshot = self.project.to_dict()
        if snapshot == self._undo_stack[self._undo_index]:
            return
        del self._undo_stack[self._undo_index + 1:]
        self._undo_stack.append(snapshot)
        self._undo_index += 1
        if len(self._undo_stack) > 100:
            drop = len(self._undo_stack) - 100
            del self._undo_stack[:drop]
            self._undo_index -= drop

    def undo(self) -> None:
        if self._undo_index == 0:
            return
        self._undo_index -= 1
        self._restore_snapshot(self._undo_stack[self._undo_index])

    def redo(self) -> None:
        if self._undo_index >= len(self._undo_stack) - 1:
            return
        self._undo_index += 1
        self._restore_snapshot(self._undo_stack[self._undo_index])

    def _restore_snapshot(self, snapshot: dict) -> None:
        restored = Project.from_dict(snapshot)
        # Swap contents in place: MainWindow and this widget share the same
        # Project instance, so the object identity must not change.
        self.project.tracks = restored.tracks
        self.project.name = restored.name
        self.project.width = restored.width
        self.project.height = restored.height
        self.project.fps = restored.fps
        self._restoring_snapshot = True
        try:
            self.rebuild()
            self.project_modified.emit()
        finally:
            self._restoring_snapshot = False

    def selected_clips(self) -> list[Clip]:
        return [it.clip for it in self.scene.selectedItems() if isinstance(it, ClipItem)]

    def set_duration_for_selected(self, seconds: float) -> None:
        """Bulk-sets the shown duration for every selected clip (e.g. several
        images at once). Video/audio clips are clamped to their own source
        length; images/titles can be set to any positive duration. Existing
        gaps/overlaps elsewhere on the track are left alone -- use
        remove_gaps() afterwards to close any resulting empty space."""
        clips = self.selected_clips()
        if not clips:
            QMessageBox.information(
                self, "No clips selected",
                "Click clips on the timeline first (Ctrl/Shift-click or Ctrl+A to select several), then set the duration.",
            )
            return
        for clip in clips:
            limit = self.source_duration_limit(clip)
            if limit is not None:
                max_duration = max(MIN_CLIP_SECONDS, limit - clip.in_point)
                seconds_for_clip = min(seconds, max_duration)
            else:
                seconds_for_clip = seconds
            clip.out_point = clip.in_point + max(MIN_CLIP_SECONDS, seconds_for_clip)
        self.rebuild()
        self.project_modified.emit()

    def remove_gaps(self, track_kind: TrackKind = TrackKind.VIDEO) -> None:
        """Repacks every clip on a track back-to-back in their current order
        -- closes gaps (e.g. after shortening several clips) and resolves
        overlaps (e.g. after lengthening them), so the result always plays
        with no black gaps and no accidental crossfades. Since any overlap
        now auto-crossfades, "smooth" for a plain slideshow means zero gaps
        *and* zero overlaps unless you deliberately drag clips back together
        afterwards."""
        track_index = self._track_index_for_kind(track_kind)
        if track_index is None:
            return
        track = self.project.tracks[track_index]
        clips_sorted = sorted(track.clips, key=lambda c: c.start_time)
        cursor = 0.0
        for clip in clips_sorted:
            clip.start_time = cursor
            cursor += clip.duration
        self.rebuild()
        self.project_modified.emit()

    def split_selected_at_playhead(self) -> None:
        selected = [it for it in self.scene.selectedItems() if isinstance(it, ClipItem)]
        if not selected:
            return
        clip = selected[0].clip
        t = self.playhead_time
        if not (clip.start_time + MIN_CLIP_SECONDS < t < clip.end_time - MIN_CLIP_SECONDS):
            return
        track = self._track_of(clip)
        if track is None:
            return
        elapsed = t - clip.start_time
        split_point = clip.in_point + elapsed
        second = Clip(
            source_path=clip.source_path,
            clip_type=clip.clip_type,
            start_time=t,
            in_point=split_point,
            out_point=clip.out_point,
            text=clip.text,
        )
        clip.out_point = split_point
        idx = next(i for i, c in enumerate(track.clips) if c is clip)
        track.clips.insert(idx + 1, second)
        self.rebuild()
        self.project_modified.emit()

    # --- Zoom / scrub -----------------------------------------------------

    def set_zoom(self, new_pps: float) -> None:
        low, high = PIXELS_PER_SECOND_RANGE
        self.pixels_per_second = max(low, min(high, new_pps))
        self.rebuild()

    def scrub_to_x(self, scene_x: float) -> None:
        self.playhead_time = max(0.0, scene_x / self.pixels_per_second)
        self._update_playhead_item()
        self.playhead_changed.emit(self.playhead_time)

    def _update_playhead_item(self) -> None:
        x = self.playhead_time * self.pixels_per_second
        height = RULER_HEIGHT + TRACK_HEIGHT * len(self.project.tracks)
        self.playhead_item.setLine(x, 0, x, height)

    # --- Rebuild / draw -----------------------------------------------------

    def rebuild(self) -> None:
        # ClipItems are recreated below; without carrying the selection over,
        # any action that rebuilds (Set Duration, split, ...) silently clears
        # it -- so e.g. adjusting the duration twice in a row would no-op.
        selected_clip_ids = {
            id(it.clip) for it in self.scene.selectedItems() if isinstance(it, ClipItem)
        }
        for item in list(self.scene.items()):
            if item is not self.playhead_item:
                self.scene.removeItem(item)

        total_seconds = max(self.project.total_duration(), 30.0) + 10.0
        total_width = total_seconds * self.pixels_per_second
        height = RULER_HEIGHT + TRACK_HEIGHT * len(self.project.tracks)

        for track_index, track in enumerate(self.project.tracks):
            bg = QGraphicsRectItem(0, RULER_HEIGHT + track_index * TRACK_HEIGHT, total_width, TRACK_HEIGHT)
            shade = TRACK_ROW_COLORS.get(track.kind, QColor("#333")).darker(160 if track_index % 2 else 140)
            bg.setBrush(QBrush(shade))
            bg.setPen(QPen(Qt.PenStyle.NoPen))
            bg.setZValue(-2)
            self.scene.addItem(bg)

        interval = TICK_INTERVALS[-1]
        for candidate in TICK_INTERVALS:
            if candidate * self.pixels_per_second >= 50:
                interval = candidate
                break
        t = 0
        while t <= total_seconds:
            x = t * self.pixels_per_second
            tick = QGraphicsLineItem(x, 0, x, height)
            tick.setPen(QPen(QColor("#444"), 1))
            tick.setZValue(-1)
            self.scene.addItem(tick)
            label = QGraphicsSimpleTextItem(_format_seconds(t))
            label.setBrush(QBrush(QColor("#ccc")))
            label.setPos(x + 2, 2)
            label.setZValue(0)
            self.scene.addItem(label)
            t += interval

        for track_index, track in enumerate(self.project.tracks):
            for clip in track.clips:
                item = ClipItem(clip, track_index, self)
                self.scene.addItem(item)
                if id(clip) in selected_clip_ids:
                    item.setSelected(True)

        self.scene.setSceneRect(0, 0, total_width, height)
        self._update_playhead_item()
        self._update_total_duration_label()

    def _estimated_export_duration(self) -> float:
        """Mirrors _TimelineGraphBuilder's duration logic: governed by the
        video track when it has clips, falling back to the audio track
        otherwise. Audio extending past the video gets trimmed at export
        (standard editor behavior) -- this is what the label should show,
        not the longest-of-all-tracks max."""
        video_index = self._track_index_for_kind(TrackKind.VIDEO)
        video_track = self.project.tracks[video_index] if video_index is not None else None
        if video_track and video_track.clips:
            return max(c.end_time for c in video_track.clips)
        audio_index = self._track_index_for_kind(TrackKind.AUDIO)
        audio_track = self.project.tracks[audio_index] if audio_index is not None else None
        if audio_track and audio_track.clips:
            return max(c.end_time for c in audio_track.clips)
        return 0.0

    def _update_total_duration_label(self) -> None:
        duration = self._estimated_export_duration()
        self._total_duration_label.setText(f"Total: {_format_seconds(duration)}")
        self._total_duration_label.setToolTip(
            "This is what Export will produce. Audio extending past the video track is trimmed to match."
        )
