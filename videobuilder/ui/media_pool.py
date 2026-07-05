"""Media pool: import video/audio/image files, show thumbnails + duration, drag onto the timeline."""
from __future__ import annotations

import os
import tempfile

from PySide6.QtCore import QMimeData, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ..core.media_probe import MediaInfo, probe
from ..core.models import ClipType
from ..core.thumbnail import generate_video_thumbnail
from .image_batch_worker import ImageBatchWorker
from .thumbnail_utils import load_scaled_qimage

THUMBNAIL_SIZE = QSize(120, 90)

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff"}

MEDIA_PATH_ROLE = Qt.ItemDataRole.UserRole
MEDIA_TYPE_ROLE = Qt.ItemDataRole.UserRole + 1
MEDIA_DURATION_ROLE = Qt.ItemDataRole.UserRole + 2


def classify_extension(path: str) -> ClipType | None:
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXTENSIONS:
        return ClipType.VIDEO
    if ext in AUDIO_EXTENSIONS:
        return ClipType.AUDIO
    if ext in IMAGE_EXTENSIONS:
        return ClipType.IMAGE
    return None


class MediaPool(QListWidget):
    """A list of imported media. Supports drag-out onto the timeline."""

    media_imported = Signal(str, ClipType, float)  # path, type, duration

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._thumb_dir = tempfile.mkdtemp(prefix="videobuilder_thumbs_")
        self._icon_cache: dict[str, QIcon] = {}
        self._batch_worker: ImageBatchWorker | None = None
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(THUMBNAIL_SIZE)
        self.setGridSize(QSize(THUMBNAIL_SIZE.width() + 20, THUMBNAIL_SIZE.height() + 30))
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setAcceptDrops(True)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)

    def icon_for_path(self, path: str) -> QIcon | None:
        return self._icon_cache.get(path)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.count() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(QColor("#999"))
            painter.drawText(
                self.viewport().rect().adjusted(16, 16, -16, -16),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                "Media pool is empty.\n\nClick “Import Media…” or “Add Images…” above,\nor drag files here from your file manager.",
            )
            painter.end()

    # --- Import ---------------------------------------------------------------

    def import_files_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Import Media")
        for path in paths:
            self.import_file(path)

    def import_file(self, path: str) -> None:
        clip_type = classify_extension(path)
        if clip_type is None:
            QMessageBox.warning(self, "Unsupported file", f"Skipping unsupported file type:\n{path}")
            return

        try:
            duration, icon = self._build_entry(path, clip_type)
        except Exception as exc:
            QMessageBox.warning(self, "Could not import file", f"{path}\n\n{exc}")
            return

        item = QListWidgetItem(icon, os.path.basename(path))
        item.setData(MEDIA_PATH_ROLE, path)
        item.setData(MEDIA_TYPE_ROLE, clip_type.value)
        item.setData(MEDIA_DURATION_ROLE, duration)
        item.setToolTip(f"{path}\nDuration: {duration:.2f}s")
        self.addItem(item)
        self._icon_cache[path] = icon
        self.media_imported.emit(path, clip_type, duration)

    def import_images_async(self, paths: list[str], on_finished=None) -> None:
        """Decodes thumbnails for a batch of images off the UI thread, then adds
        them incrementally -- use this instead of looping import_file() for a
        whole folder or a large multi-select, so the UI never blocks."""
        if not paths:
            if on_finished:
                on_finished()
            return

        worker = ImageBatchWorker(paths, THUMBNAIL_SIZE)
        self._batch_worker = worker

        def handle_ready(path: str, image: QImage) -> None:
            icon = QIcon(QPixmap.fromImage(image))
            item = QListWidgetItem(icon, os.path.basename(path))
            item.setData(MEDIA_PATH_ROLE, path)
            item.setData(MEDIA_TYPE_ROLE, ClipType.IMAGE.value)
            item.setData(MEDIA_DURATION_ROLE, 0.0)
            self.addItem(item)
            self._icon_cache[path] = icon
            self.media_imported.emit(path, ClipType.IMAGE, 0.0)

        worker.item_ready.connect(handle_ready)
        if on_finished:
            worker.finished_ok.connect(on_finished)
        worker.start()

    def _build_entry(self, path: str, clip_type: ClipType) -> tuple[float, QIcon]:
        if clip_type == ClipType.VIDEO:
            info: MediaInfo = probe(path)
            thumb_path = os.path.join(self._thumb_dir, os.path.basename(path) + ".png")
            try:
                generate_video_thumbnail(path, thumb_path, at_seconds=min(0.5, info.duration / 2))
                icon = QIcon(QPixmap(thumb_path))
            except Exception:
                icon = QIcon()
            return info.duration, icon

        if clip_type == ClipType.AUDIO:
            info = probe(path)
            return info.duration, QIcon()

        if clip_type == ClipType.IMAGE:
            image = load_scaled_qimage(path, THUMBNAIL_SIZE)
            return 0.0, QIcon(QPixmap.fromImage(image))

        raise ValueError(f"Unhandled clip type: {clip_type}")

    # --- Drag-and-drop import (dropping files onto the pool) -------------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                local_path = url.toLocalFile()
                if local_path:
                    self.import_file(local_path)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    # --- Drag-out (onto the timeline) ------------------------------------------

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if item is None:
            return
        mime = QMimeData()
        mime.setText(item.data(MEDIA_PATH_ROLE))
        mime.setData("application/x-videobuilder-clip-type", item.data(MEDIA_TYPE_ROLE).encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        if item.icon():
            drag.setPixmap(item.icon().pixmap(THUMBNAIL_SIZE))
        drag.exec(Qt.DropAction.CopyAction)
