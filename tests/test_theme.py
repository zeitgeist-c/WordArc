import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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
    assert theme.ThemeManager.apply("light", app) == theme.ThemeMode.LIGHT
    assert app.property("wordarcTheme") == "light"
    resolved = theme.ThemeManager.apply("system", app)
    assert resolved in (theme.ThemeMode.DARK, theme.ThemeMode.LIGHT)
    assert app.styleSheet()
