"""Batch image import: pick several photos at once (individually or a whole
folder), set a uniform display duration, and optionally lay them out
back-to-back on the timeline -- e.g. 10 images at 2s each becomes a 20s run."""
from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

IMAGE_FILE_FILTER = "Images (*.jpg *.jpeg *.png *.bmp *.gif *.tif *.tiff)"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff"}


class AddImagesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Images")
        self.setMinimumWidth(400)

        self.image_paths: list[str] = []

        layout = QVBoxLayout(self)

        choose_row = QHBoxLayout()
        choose_btn = QPushButton("Choose Images…")
        choose_btn.clicked.connect(self._choose_images)
        choose_row.addWidget(choose_btn)
        choose_folder_btn = QPushButton("Choose Folder…")
        choose_folder_btn.clicked.connect(self._choose_folder)
        choose_row.addWidget(choose_folder_btn)
        layout.addLayout(choose_row)

        self._summary_label = QLabel("No images selected")
        layout.addWidget(self._summary_label)

        duration_row = QHBoxLayout()
        duration_row.addWidget(QLabel("Seconds per image:"))
        self._duration_spin = QDoubleSpinBox()
        self._duration_spin.setRange(0.1, 60.0)
        self._duration_spin.setSingleStep(0.5)
        self._duration_spin.setValue(2.0)
        self._duration_spin.valueChanged.connect(self._update_summary)
        duration_row.addWidget(self._duration_spin)
        layout.addLayout(duration_row)

        self._sequential_checkbox = QCheckBox(
            "Arrange one after another on the timeline (auto-adjust)"
        )
        self._sequential_checkbox.setChecked(True)
        layout.addWidget(self._sequential_checkbox)

        self._total_label = QLabel()
        layout.addWidget(self._total_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_summary()

    def _choose_images(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose Images", "", IMAGE_FILE_FILTER)
        if paths:
            self.image_paths = paths
            names = ", ".join(os.path.basename(p) for p in paths[:3])
            if len(paths) > 3:
                names += f", +{len(paths) - 3} more"
            self._summary_label.setText(f"{len(paths)} images: {names}")
        self._update_summary()

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose Folder of Images")
        if not folder:
            return
        # Just listing filenames -- no image decoding happens here, so this
        # stays instant even for a folder with hundreds of photos.
        names = sorted(
            name for name in os.listdir(folder) if os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS
        )
        if not names:
            QMessageBox.warning(self, "No images found", "That folder has no supported image files.")
            return
        self.image_paths = [os.path.join(folder, name) for name in names]
        self._summary_label.setText(f"{len(names)} images from folder: {os.path.basename(folder)}")
        self._update_summary()

    def _update_summary(self) -> None:
        count = len(self.image_paths)
        total = count * self._duration_spin.value()
        self._total_label.setText(f"{count} image(s) x {self._duration_spin.value():.1f}s = {total:.1f}s total")

    @property
    def seconds_per_image(self) -> float:
        return self._duration_spin.value()

    @property
    def arrange_sequentially(self) -> bool:
        return self._sequential_checkbox.isChecked()
