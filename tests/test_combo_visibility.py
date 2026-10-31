"""Actual styled popup choices and selection, rather than routing mocks.

Short lists open as a native menu (like the language menu); the menu is
swapped for a script double here so the modal loop never blocks the suite.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from unittest import mock

import pytest
from PyQt6.QtWidgets import QApplication
import settings_ui
import theme


class _Menu:
    instances = []
    script = None

    def __init__(self, *args):
        self.actions = []
        self.instances.append(self)

    def addAction(self, text):
        action = mock.Mock()
        action.text.return_value = text
        action.data.return_value = len(self.actions)
        self.actions.append(action)
        return action

    def exec(self, *args):
        return self.script


@pytest.mark.parametrize('mode', [theme.ThemeMode.DARK, theme.ThemeMode.LIGHT])
@pytest.mark.parametrize('count', [2, 4, 7])
def test_styled_choices_are_visible_and_clickable(mode, count):
    app = QApplication.instance() or QApplication([])
    combo = settings_ui.FitsOnScreenCombo()
    combo.setStyleSheet(theme.stylesheet(theme.palette(mode)))
    combo.addItems(['Türkçe', 'English', 'Oyun İngilizcesi', 'Akademik İngilizce',
                    'Français', 'Deutsch', 'Español'][:count])
    combo.resize(460, 38)
    combo.show()
    try:
        _Menu.instances.clear()
        _Menu.script = None
        with mock.patch.object(settings_ui, "QMenu", _Menu):
            combo.showPopup()
        menu = _Menu.instances[-1]
        assert [a.text() for a in menu.actions] == \
            ['Türkçe', 'English', 'Oyun İngilizcesi', 'Akademik İngilizce',
             'Français', 'Deutsch', 'Español'][:count]
        _Menu.script = menu.actions[1]
        with mock.patch.object(settings_ui, "QMenu", _Menu):
            combo.showPopup()
        app.processEvents()
        assert combo.currentIndex() == 1
        assert combo.currentText() == 'English'
    finally:
        combo.hidePopup()
        combo.close()
        combo.deleteLater()
