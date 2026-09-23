import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QApplication

import theme


_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def test_theme_normalization_and_all_modes_apply():
    app = _app()
    assert theme.normalize("broken") == theme.ThemeMode.DARK
    assert theme.ThemeManager.apply("dark", app) == theme.ThemeMode.DARK
    assert app.property("wordarcTheme") == "dark"
    assert app.property("wordarcBaseStyle") == "Fusion"
    assert "QMenu" in app.styleSheet()
    assert (app.palette().color(QPalette.ColorRole.Window)
            != app.palette().color(QPalette.ColorRole.WindowText))
    assert theme.ThemeManager.apply("light", app) == theme.ThemeMode.LIGHT
    assert app.property("wordarcTheme") == "light"
    resolved = theme.ThemeManager.apply("system", app)
    assert resolved in (theme.ThemeMode.DARK, theme.ThemeMode.LIGHT)
    assert app.styleSheet()


def test_scrollbar_cards_and_button_variants_are_styled():
    css = theme.stylesheet(theme.palette("dark"))
    assert "QScrollBar::handle:vertical:hover" in css
    assert "width: 12px" in css
    assert "min-height: 36px" in css
    assert "QScrollBar::add-page, QScrollBar::sub-page" in css
    assert "QPushButton#accentButton" in css
    assert "QPushButton#dangerButton" in css
    assert "border-radius: 14px" in css
    assert "QLabel#pageTitle" not in css
