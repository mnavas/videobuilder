"""Fast, EXIF-aware thumbnail decoding shared by the media pool and timeline widget."""
from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage, QImageReader


def load_scaled_qimage(path: str, target_size: QSize) -> QImage:
    """Decode an image directly at (roughly) thumbnail resolution.

    Using QImageReader.setScaledSize lets formats like JPEG downscale during
    decode (libjpeg DCT scaling) instead of decoding at full camera
    resolution and scaling afterwards -- the difference between this being
    fast and it freezing the UI for a folder of full-size photos.
    """
    reader = QImageReader(path)
    reader.setAutoTransform(True)  # honor EXIF orientation
    original = reader.size()
    if original.isValid() and original.width() > 0 and original.height() > 0:
        scale = min(target_size.width() / original.width(), target_size.height() / original.height())
        if scale < 1.0:
            scaled = QSize(max(1, int(original.width() * scale)), max(1, int(original.height() * scale)))
            reader.setScaledSize(scaled)
    image = reader.read()
    if image.isNull():
        image = QImage(path)
    return image
