"""Actual styled popup geometry and selection, rather than routing mocks."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
import settings_ui
import theme


@pytest.mark.parametrize('mode', [theme.ThemeMode.DARK, theme.ThemeMode.LIGHT])
@pytest.mark.parametrize('count', [2, 4, 7])
def test_styled_native_choices_are_visible_and_clickable(mode, count):
    app = QApplication.instance() or QApplication([])
    combo = settings_ui.FitsOnScreenCombo()
    combo.setStyleSheet(theme.stylesheet(theme.palette(mode)))
    combo.addItems(['Türkçe', 'English', 'Oyun İngilizcesi', 'Akademik İngilizce',
                    'Français', 'Deutsch', 'Español'][:count])
    combo.resize(460, 38)
    combo.show()
    try:
        combo.showPopup()
        app.processEvents()
        view = combo.view()
        viewport = view.viewport()
        assert viewport.height() > 0
        for row in range(count):
            rect = view.visualRect(view.model().index(row, 0))
            assert viewport.rect().contains(rect.center()), (row, rect, viewport.rect())
        target = view.visualRect(view.model().index(1, 0)).center()
        QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=target)
        app.processEvents()
        assert combo.currentIndex() == 1
        assert combo.currentText() == 'English'
    finally:
        combo.hidePopup()
        combo.close()
        combo.deleteLater()
