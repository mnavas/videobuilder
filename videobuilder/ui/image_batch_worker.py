"""Decodes thumbnails for a batch of images off the UI thread.

Used whenever many images might be added at once (a whole folder, a large
multi-select) so the UI never blocks regardless of batch size.
"""
from __future__ import annotations

from PySide6.QtCore import QSize, QThread, Signal
from PySide6.QtGui import QImage

from .thumbnail_utils import load_scaled_qimage


class ImageBatchWorker(QThread):
    item_ready = Signal(str, QImage)  # path, thumbnail image
    progress = Signal(int, int)  # current, total
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, paths: list[str], thumbnail_size: QSize):
        super().__init__()
        self.paths = paths
        self.thumbnail_size = thumbnail_size

    def run(self) -> None:
        try:
            total = len(self.paths)
            for i, path in enumerate(self.paths):
                image = load_scaled_qimage(path, self.thumbnail_size)
                self.item_ready.emit(path, image)
                self.progress.emit(i + 1, total)
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
