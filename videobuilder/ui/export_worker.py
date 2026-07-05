"""Runs a blocking export function on a background thread so the UI stays responsive."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QThread, Signal


class ExportWorker(QThread):
    progress = Signal(float)
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, export_fn: Callable[..., None], **kwargs):
        super().__init__()
        self._export_fn = export_fn
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            self._export_fn(on_progress=self.progress.emit, **self._kwargs)
            self.finished_ok.emit()
        except Exception as exc:  # surfaced to the UI via the failed signal
            self.failed.emit(str(exc))
