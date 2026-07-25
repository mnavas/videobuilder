"""A modal progress dialog driving an ExportWorker to completion."""
from __future__ import annotations

import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QProgressBar, QVBoxLayout

from .export_worker import ExportWorker


def _format_elapsed(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"


class ExportProgressDialog(QDialog):
    def __init__(self, worker: ExportWorker, title: str = "Exporting…", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(360)

        self._worker = worker
        self._succeeded = False
        self._got_first_progress = False
        self._start_time = time.monotonic()

        layout = QVBoxLayout(self)
        self._label = QLabel("Starting…")
        layout.addWidget(self._label)

        # ffmpeg has to open every input and parse the whole filter graph
        # before it produces a single output frame -- for a long timeline
        # with many clips that can take a real, visible amount of time,
        # especially on older/slower machines. A determinate bar stuck at 0%
        # reads as "frozen"; an indeterminate (busy) bar reads as "working".
        # We switch to determinate the moment the first real progress ticks
        # in from ffmpeg.
        self._bar = QProgressBar()
        self._bar.setRange(0, 0)
        layout.addWidget(self._bar)

        self._elapsed_label = QLabel("Elapsed: 0:00")
        self._elapsed_label.setStyleSheet("color: #888;")
        layout.addWidget(self._elapsed_label)

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)
        self._elapsed_timer.start()

        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_finished)
        worker.failed.connect(self._on_failed)

    def _tick_elapsed(self) -> None:
        elapsed = time.monotonic() - self._start_time
        self._elapsed_label.setText(f"Elapsed: {_format_elapsed(elapsed)}")

    def _on_progress(self, fraction: float) -> None:
        if not self._got_first_progress:
            self._got_first_progress = True
            self._bar.setRange(0, 100)
        self._bar.setValue(int(fraction * 100))
        self._label.setText(f"Rendering… {int(fraction * 100)}%")

    def _on_finished(self) -> None:
        self._succeeded = True
        self._elapsed_timer.stop()
        self._label.setText("Done.")
        self.accept()

    def _on_failed(self, message: str) -> None:
        self._elapsed_timer.stop()
        self.reject()
        QMessageBox.critical(self.parent(), "Export failed", message)

    def run(self) -> bool:
        """Starts the worker and blocks (via exec) until it finishes or fails."""
        self._worker.start()
        self.exec()
        return self._succeeded
