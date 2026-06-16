"""Decode a vless:// link from a QR code, either from an image file or from a
QImage already in memory (e.g. pasted from the clipboard)."""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtGui import QImage


def decode_qr_from_file(path: str) -> str | None:
    image = cv2.imread(path)
    if image is None:
        return None
    return _decode(image)


def decode_qr_from_qimage(qimage: QImage) -> str | None:
    qimage = qimage.convertToFormat(QImage.Format.Format_RGB888)
    width, height = qimage.width(), qimage.height()
    if width == 0 or height == 0:
        return None

    # QImage rows are padded to bytesPerLine(), which can exceed width * 3 -
    # slice each row down before reshaping, or the image comes out skewed.
    stride = qimage.bytesPerLine()
    buffer = qimage.constBits()
    array = np.frombuffer(buffer, dtype=np.uint8, count=height * stride)
    array = array.reshape((height, stride))[:, : width * 3].reshape((height, width, 3))
    return _decode(array)


def _decode(image: np.ndarray) -> str | None:
    """cv2's classic QRCodeDetector is occasionally finicky about a particular
    image's exact pixel pattern - retry with a couple of cheap variations
    before giving up, since each is a near-instant operation."""
    detector = cv2.QRCodeDetector()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image

    candidates = [
        image,
        gray,
        cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC),
        cv2.resize(gray, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA),
    ]
    for candidate in candidates:
        data, _points, _ = detector.detectAndDecode(candidate)
        if data:
            return data
    return None
