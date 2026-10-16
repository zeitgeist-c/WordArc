"""Draft items must paint: the overlay draws them on every mouse move.

The 0.8.4 field log showed a KeyError: 'rect' traceback on each paint while a
rectangle was being dragged — draw_item read the committed-only "rect" key
while a draft still carries start/end.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PyQt6.QtCore import QPoint  # noqa: E402

from screenshot_editor import AnnotationModel  # noqa: E402


def _draft(kind):
    return {"type": kind, "start": QPoint(10, 10), "end": QPoint(80, 60),
            "color": QColor("red"), "width": 3, "fill": kind == "rect"}


class DraftPaintTests(unittest.TestCase):
    def test_shape_and_pixel_drafts_paint_without_committed_rect(self):
        image = QImage(120, 90, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        try:
            for kind in ("rect", "ellipse", "blur", "pixelate"):
                AnnotationModel.draw_item(painter, _draft(kind))
        finally:
            painter.end()

    def test_committed_shapes_still_paint(self):
        from PyQt6.QtCore import QRect
        image = QImage(120, 90, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        try:
            for kind in ("rect", "ellipse"):
                AnnotationModel.draw_item(
                    painter, {"type": kind, "rect": QRect(5, 5, 60, 40),
                              "color": QColor("blue"), "width": 2})
        finally:
            painter.end()


if __name__ == "__main__":
    unittest.main()
