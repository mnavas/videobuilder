"""A modal progress dialog driving an ExportWorker to completion."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QProgressBar, QVBoxLayout

from .export_worker import ExportWorker


class ExportProgressDialog(QDialog):
    def __init__(self, worker: ExportWorker, title: str = "Exporting…", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(360)

        self._worker = worker
        self._succeeded = False

        layout = QVBoxLayout(self)
        self._label = QLabel("Exporting…")
        layout.addWidget(self._label)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        layout.addWidget(self._bar)

        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_finished)
        worker.failed.connect(self._on_failed)

    def _on_progress(self, fraction: float) -> None:
        self._bar.setValue(int(fraction * 100))

    def _on_finished(self) -> None:
        self._succeeded = True
        self._label.setText("Done.")
        self.accept()

    def _on_failed(self, message: str) -> None:
        self.reject()
        QMessageBox.critical(self.parent(), "Export failed", message)

    def run(self) -> bool:
        """Starts the worker and blocks (via exec) until it finishes or fails."""
        self._worker.start()
        self.exec()
        return self._succeeded
