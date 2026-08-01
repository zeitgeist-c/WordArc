"""Render the canonical WordArc SVG into deterministic Windows icon sizes."""

from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "brand" / "wordarc-app.svg"
OUTPUT = ROOT / "assets" / "brand" / "wordarc.ico"
SIZES = (16, 20, 24, 32, 48, 64, 128, 256)


def render(size):
    renderer = QSvgRenderer(str(SOURCE))
    if not renderer.isValid():
        raise RuntimeError(f"invalid SVG: {SOURCE}")
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    return Image.frombytes("RGBA", (size, size), bytes(rgba.bits().asstring(size * size * 4)))


def main():
    app = QGuiApplication.instance() or QGuiApplication([])
    images = [render(size) for size in SIZES]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    images[-1].save(OUTPUT, format="ICO", append_images=images[:-1], sizes=[(s, s) for s in SIZES])
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
