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
    # Switching to a retired value still repolishes once (dark fallback),
    # then re-applying the same resolved mode is a no-op.
    resolved = theme.ThemeManager.apply("system", app)
    assert resolved in (theme.ThemeMode.DARK, theme.ThemeMode.LIGHT)
    assert app.styleSheet()
    before = app.styleSheet()
    theme.ThemeManager.apply(resolved.value, app)
    assert app.styleSheet() == before


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


def _luminance(value):
    value = {"white": "#FFFFFF", "black": "#000000"}.get(value, value)
    red = int(value[1:3], 16) / 255
    green = int(value[3:5], 16) / 255
    blue = int(value[5:7], 16) / 255

    def linear(part):
        return part / 12.92 if part <= 0.04045 else ((part + 0.055) / 1.055) ** 2.4

    return 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)


def _contrast(first, second):
    lighter, darker = sorted((_luminance(first), _luminance(second)),
                             reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _button_pairs(colors):
    return {
        "primary": (colors.primary, "white"),
        "primary hover": (colors.primary_hover, "white"),
        "primary pressed": (colors.primary_pressed, "white"),
        "danger hover": (colors.danger_fill, "white"),
        "muted on window": (colors.muted, colors.window),
        "muted on card input": (colors.muted, colors.surface_alt),
        "text on selected": (colors.text, colors.selected),
        "text on hover": (colors.text, colors.hover),
        "key chip": (colors.violet, colors.chip_bg),
    }


def test_action_text_contrast_in_both_themes():
    for mode in ("dark", "light"):
        colors = theme.palette(mode)
        for name, (foreground, background) in _button_pairs(colors).items():
            assert _contrast(foreground, background) >= 4.5, (mode, name)


def test_keyboard_focus_ring_is_visible_in_both_themes():
    from PyQt6.QtCore import QRect
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QPushButton, QStyle, QStyleOptionButton

    _app()
    state = QStyle.StateFlag

    def render(button, flags):
        option = QStyleOptionButton()
        option.initFrom(button)
        option.state = flags
        option.rect = QRect(0, 0, 180, 36)
        image = QImage(option.rect.size(), QImage.Format.Format_RGB32)
        image.fill(0)
        painter = QPainter(image)
        try:
            button.style().drawControl(QStyle.ControlElement.CE_PushButton,
                                       option, painter, button)
        finally:
            painter.end()
        return image

    for mode in ("dark", "light"):
        colors = theme.palette(mode)
        assert _contrast(colors.violet, colors.surface_alt) >= 3.0, mode
        for role in ("", "primaryButton", "accentButton", "dangerButton"):
            button = QPushButton()
            button.setObjectName(role)
            button.setStyleSheet(theme.stylesheet(colors))
            button.ensurePolished()
            focused_hover = (state.State_Enabled | state.State_HasFocus
                             | state.State_MouseOver)
            for flags in (focused_hover, focused_hover | state.State_Sunken):
                image = render(button, flags)
                assert image.pixelColor(90, 1).name() == colors.violet.lower(), (mode, role)
            disabled = render(button, state.State_None)
            assert disabled.pixelColor(90, 5).name() == colors.window.lower(), (mode, role)
