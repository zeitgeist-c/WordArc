"""WordArc's application-wide light/dark theme service."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PyQt6.QtGui import QColor, QPalette


class ThemeMode(str, Enum):
    DARK = "dark"
    LIGHT = "light"


@dataclass(frozen=True)
class Palette:
    mode: str
    window: str
    surface: str
    surface_alt: str
    border: str
    text: str
    muted: str
    violet: str
    cyan: str
    hover: str
    selected: str
    danger: str
    warning: str
    success: str


DARK = Palette(
    "dark", "#0B0E14", "#141925", "#262E3E", "#2B3447", "#F3F6FC",
    "#94A0B5", "#8B5CF6", "#22D3EE", "#20283A", "#292448",
    "#FF6B7A", "#F5B84B", "#48D597",
)
LIGHT = Palette(
    "light", "#F4F6FA", "#FFFFFF", "#EDF1F7", "#D9DFEA", "#18202D",
    "#667085", "#6D4AFF", "#087E99", "#E8ECF4", "#EDE9FE",
    "#D83A52", "#A86600", "#16835B",
)


def normalize(mode) -> ThemeMode:
    if isinstance(mode, ThemeMode):
        return mode
    try:
        return ThemeMode(str(mode or "dark"))
    except ValueError:
        return ThemeMode.DARK


def resolve(mode) -> ThemeMode:
    # Only dark and light exist; anything else (including the retired
    # "system" value in old configs) falls back to dark via normalize.
    return normalize(mode)


def palette(mode=None) -> Palette:
    selected = resolve(mode or ThemeManager.selected_mode)
    return DARK if selected == ThemeMode.DARK else LIGHT


def _mix(base: str, accent: str, ratio: float) -> str:
    """A solid colour part way between two palette entries.

    Qt's stylesheets read an ``rgba()`` alpha as a 0-255 integer, so a tint is
    pre-blended onto whatever actually sits behind it instead.
    """
    first, second = QColor(base), QColor(accent)
    return QColor(
        round(first.red() + (second.red() - first.red()) * ratio),
        round(first.green() + (second.green() - first.green()) * ratio),
        round(first.blue() + (second.blue() - first.blue()) * ratio),
    ).name()


def stylesheet(colors: Palette) -> str:
    return f"""
    * {{
        font-family: "Segoe UI Variable", "Segoe UI";
        font-size: 10pt;
        color: {colors.text};
    }}
    QDialog, QMainWindow, QWidget#settingsRoot {{ background: {colors.window}; }}
    QLabel#brandName {{ font-size: 18pt; font-weight: 700; }}
    QFrame#headerRule {{ background: {colors.border}; border: 0; }}
    QLabel#muted, QLabel#pageDescription, QLabel#cardDescription {{
        color: {colors.muted};
    }}
    QWidget#tabCard, QWidget#pageCard {{
        background: {colors.surface};
        border: 1px solid {colors.border};
        border-radius: 14px;
    }}
    QWidget#page, QScrollArea, QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QGroupBox {{
        background: {colors.surface};
        border: 1px solid {colors.border};
        border-radius: 14px;
        margin-top: 18px;
        padding: 20px 16px 16px 16px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 8px;
        color: {colors.violet};
        background: {colors.surface};
        font-size: 11pt;
        font-weight: 700;
    }}
    QTabWidget#settingsTabs::pane {{ background: transparent; border: 0; }}
    QWidget#sharedAiNote {{
        background: {colors.surface_alt};
        border: 1px solid {colors.border};
        border-radius: 10px;
    }}
    QTabWidget#settingsTabs QTabBar::tab {{
        background: transparent;
        border: 0;
        border-radius: 9px;
        padding: 10px 16px;
        margin: 0 6px 10px 0;
        color: {colors.muted};
        font-weight: 500;
    }}
    QTabWidget#settingsTabs QTabBar::tab:hover {{
        background: {colors.hover}; color: {colors.text};
    }}
    QTabWidget#settingsTabs QTabBar::tab:selected {{
        background: {colors.selected};
        color: {colors.text};
        font-weight: 600;
    }}
    QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget {{
        background: {colors.surface_alt};
        border: 1px solid {colors.border};
        border-radius: 8px;
        padding: 7px 10px;
        selection-background-color: {colors.violet};
        selection-color: white;
    }}
    QLineEdit:hover, QPlainTextEdit:hover, QComboBox:hover,
    QSpinBox:hover, QDoubleSpinBox:hover, QListWidget:hover {{
        background: {colors.selected}; border-color: {colors.violet};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 2px solid {colors.violet}; padding: 6px 9px;
    }}
    QComboBox, QSpinBox, QDoubleSpinBox {{ min-height: 22px; }}
    QComboBox::drop-down {{ border: 0; width: 24px; }}
    QComboBox QAbstractItemView {{
        background: {colors.surface_alt};
        border: 1px solid {colors.border};
        border-radius: 8px;
        outline: 0;
        padding: 4px;
        selection-background-color: {colors.selected};
        selection-color: {colors.text};
    }}
    QComboBox QAbstractItemView::item {{
        padding: 6px 8px; margin: 2px 0; border-radius: 6px;
    }}
    QComboBox QAbstractItemView::item:selected {{
        background: {colors.selected}; color: {colors.text};
    }}
    QComboBox QAbstractItemView::item:hover {{
        background: {colors.hover}; color: {colors.text};
    }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        background: transparent; border: 0; width: 22px;
    }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover,
    QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
        background: {colors.hover}; border-radius: 4px;
    }}
    QListWidget {{ padding: 4px; }}
    QListWidget::item {{ padding: 7px 9px; margin: 2px 0; border-radius: 6px; }}
    QListWidget::item:selected {{ background: {colors.selected}; color: {colors.text}; }}
    QListWidget::item:hover {{ background: {colors.hover}; }}
    QPushButton {{
        min-height: 24px;
        background: {colors.surface_alt};
        border: 1px solid {colors.border};
        border-radius: 8px;
        padding: 7px 12px;
        font-weight: 600;
        color: {colors.text};
    }}
    QPushButton:hover {{ background: {colors.selected}; border-color: {colors.violet}; }}
    QPushButton:pressed {{
        background: {colors.violet}; border-color: {colors.violet}; color: white;
    }}
    QPushButton:disabled {{
        color: {colors.muted}; background: {colors.window}; border-color: {colors.border};
    }}
    QPushButton#primaryButton {{
        color: white;
        background: {colors.violet};
        border: 1px solid {colors.violet};
        padding: 9px 22px;
        font-weight: 700;
    }}
    QPushButton#primaryButton:hover {{
        background: {colors.cyan}; border-color: {colors.cyan};
    }}
    QPushButton#accentButton {{
        background: transparent; border: 1px solid {colors.violet}; color: {colors.text};
    }}
    QPushButton#accentButton:hover {{
        background: {colors.violet}; border-color: {colors.violet}; color: white;
    }}
    QPushButton#dangerButton {{
        background: transparent; border: 1px solid {colors.border}; color: {colors.danger};
    }}
    QPushButton#dangerButton:hover {{
        background: {colors.danger}; border-color: {colors.danger}; color: white;
    }}
    QCheckBox {{ spacing: 10px; padding: 2px 0; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; }}
    QCheckBox::indicator:unchecked {{
        background: {colors.surface_alt}; border: 1px solid {colors.border};
        border-radius: 5px;
    }}
    QCheckBox::indicator:unchecked:hover {{ border-color: {colors.violet}; }}
    QCheckBox::indicator:checked {{
        background: {colors.violet}; border: 1px solid {colors.violet};
        border-radius: 5px;
    }}
    QScrollBar:vertical {{
        background: transparent; width: 12px; margin: 2px 2px 2px 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {colors.border}; border-radius: 4px; min-height: 36px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {colors.violet}; }}
    QScrollBar::handle:vertical:pressed {{ background: {colors.cyan}; }}
    QScrollBar:horizontal {{
        background: transparent; height: 12px; margin: 2px 2px 2px 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {colors.border}; border-radius: 4px; min-width: 36px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {colors.violet}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        background: none; border: 0; width: 0; height: 0;
    }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QToolTip {{
        background: {colors.surface}; color: {colors.text};
        border: 1px solid {colors.border}; padding: 6px;
    }}
    QMenu {{
        background: {colors.surface}; color: {colors.text};
        border: 1px solid {colors.border}; border-radius: 10px; padding: 6px;
    }}
    QMenu::item {{
        background: transparent; color: {colors.text};
        border-radius: 6px; padding: 7px 26px 7px 10px;
    }}
    QMenu::item:selected {{ background: {colors.selected}; color: {colors.text}; }}
    QMenu::item:disabled {{ color: {colors.muted}; }}
    QMenu::separator {{ background: {colors.border}; height: 1px; margin: 5px 8px; }}
    QTabWidget::pane {{ border: 0; background: transparent; top: -1px; }}
    QTabBar {{ qproperty-drawBase: 0; }}
    QTabBar::tab {{
        background: transparent; color: {colors.muted}; border: 0;
        border-bottom: 2px solid transparent; padding: 11px 14px;
        margin-right: 2px; font-weight: 600;
    }}
    QTabBar::tab:hover {{ color: {colors.text}; background: {colors.hover}; }}
    QTabBar::tab:selected {{ color: {colors.text}; border-bottom-color: {colors.violet}; }}
    QMessageBox {{ background: {colors.surface}; }}
    QFrame#saveBanner {{
        background: {_mix(colors.window, colors.success, 0.10)};
        border: 1px solid {_mix(colors.window, colors.success, 0.45)};
        border-radius: 10px;
    }}
    QLabel#saveBannerMark {{
        color: {colors.success};
        background: {_mix(colors.window, colors.success, 0.18)};
        border: 1px solid {_mix(colors.window, colors.success, 0.42)};
        border-radius: 13px;
        font-size: 11pt;
        font-weight: 700;
    }}
    QLabel#saveBannerText {{ color: {colors.text}; font-weight: 600; }}
    """

def qt_palette(colors: Palette) -> QPalette:
    result = QPalette()
    mapping = {
        QPalette.ColorRole.Window: colors.window,
        QPalette.ColorRole.WindowText: colors.text,
        QPalette.ColorRole.Base: colors.surface,
        QPalette.ColorRole.AlternateBase: colors.surface_alt,
        QPalette.ColorRole.ToolTipBase: colors.surface,
        QPalette.ColorRole.ToolTipText: colors.text,
        QPalette.ColorRole.Text: colors.text,
        QPalette.ColorRole.Button: colors.surface_alt,
        QPalette.ColorRole.ButtonText: colors.text,
        QPalette.ColorRole.BrightText: colors.danger,
        QPalette.ColorRole.Highlight: colors.violet,
        QPalette.ColorRole.HighlightedText: "#FFFFFF",
        QPalette.ColorRole.PlaceholderText: colors.muted,
    }
    for role, value in mapping.items():
        result.setColor(role, QColor(value))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText,
                 QPalette.ColorRole.ButtonText):
        result.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors.muted))
    return result


class ThemeManager:
    selected_mode = ThemeMode.DARK
    resolved_mode = ThemeMode.DARK
    _app = None

    @classmethod
    def apply(cls, mode, app=None):
        cls.selected_mode = normalize(mode)
        cls.resolved_mode = resolve(cls.selected_mode)
        cls._app = app or cls._app
        colors = palette(cls.resolved_mode)
        if cls._app is not None:
            cls._app.setStyle("Fusion")
            cls._app.setProperty("wordarcBaseStyle", "Fusion")
            cls._app.setPalette(qt_palette(colors))
            cls._app.setStyleSheet(stylesheet(colors))
            cls._app.setProperty("wordarcTheme", cls.resolved_mode.value)
        try:
            import overlay
            overlay.set_theme(colors)
            import trayicon
            trayicon.set_theme(colors)
        except ImportError:
            pass
        return cls.resolved_mode
