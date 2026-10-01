"""Reproduce real model-field clicks, not only direct showPopup calls."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QPushButton
import settings_ui
import theme
from tests.test_workspace import window


@pytest.mark.parametrize('mode', [theme.ThemeMode.DARK, theme.ThemeMode.LIGHT])
@pytest.mark.parametrize('target', ['text', 'arrow'])
def test_44_models_open_by_mouse_and_last_model_can_be_selected(mode, target):
    app = QApplication.instance() or QApplication([])
    combo = settings_ui.FitsOnScreenCombo()
    combo.setStyleSheet(theme.stylesheet(theme.palette(mode)))
    combo.setEditable(True)
    combo.addItems([f'gemini-test-{index:02}' for index in range(44)])
    combo.resize(460, 48)
    combo.show()
    try:
        surface = combo.lineEdit() if target == 'text' else combo
        position = surface.rect().center() if target == 'text' else QPoint(combo.width() - 12, combo.height() // 2)
        QTest.mousePress(surface, Qt.MouseButton.LeftButton, pos=position)
        assert getattr(combo, '_picker', None) is None
        QTest.mouseRelease(surface, Qt.MouseButton.LeftButton, pos=position)
        app.processEvents()
        QTest.qWait(40)
        popup = combo._picker
        assert popup.isVisible()
        assert combo._picker_rows.count() == 44
        assert not combo._picker_search.isWindow()
        assert all(not button.isWindow() for button in popup.findChildren(QPushButton))
        combo._picker_search.setText('gemini-test-43')
        app.processEvents()
        rows = combo._picker_rows
        item = rows.item(43)
        assert not item.isHidden()
        QTest.mouseClick(rows.viewport(), Qt.MouseButton.LeftButton, pos=rows.visualItemRect(item).center())
        app.processEvents()
        assert combo.currentText() == 'gemini-test-43'
        assert getattr(combo, '_picker', None) is None or not combo._picker.isVisible()
    finally:
        combo.hidePopup()
        combo.close()


def test_fetched_models_fill_all_ai_selectors_and_keep_custom_value(window):
    models = [f'gemini-test-{index:02}' for index in range(44)]
    for combo in (window.transcribe_model, window.cleanup_model, window.meeting_model):
        combo.setCurrentText('private-custom-model')
    window._on_transcribe_models_loaded(models, '')
    window._on_models_loaded(models, '')
    for combo in (window.transcribe_model, window.cleanup_model, window.meeting_model):
        assert combo.count() == 44
        assert [combo.itemText(i) for i in range(44)] == models
        assert combo.currentText() == 'private-custom-model'
