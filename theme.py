"""WordArc's application-wide light/dark theme service."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication


class ThemeMode(str, Enum):
    DARK = "dark"
    LIGHT = "light"
    SYSTEM = "system"


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
    "dark", "#0B0E14", "#141925", "#1B2230", "#2B3447", "#F3F6FC",
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


def system_mode() -> ThemeMode:
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        return (ThemeMode.DARK if scheme == Qt.ColorScheme.Dark
                else ThemeMode.LIGHT)
    except (AttributeError, RuntimeError):
        return ThemeMode.DARK


def resolve(mode) -> ThemeMode:
    selected = normalize(mode)
    return system_mode() if selected == ThemeMode.SYSTEM else selected


def palette(mode=None) -> Palette:
    selected = resolve(mode or ThemeManager.selected_mode)
    return DARK if selected == ThemeMode.DARK else LIGHT


def stylesheet(colors: Palette) -> str:
    return f"""
    * {{
        font-family: "Segoe UI Variable", "Segoe UI";
        font-size: 10pt;
        color: {colors.text};
    }}
    QDialog, QMainWindow, QWidget#settingsRoot {{ background: {colors.window}; }}
    QWidget#tabCard {{
        background: {colors.surface};
        border: 1px solid {colors.border};
        border-radius: 12px;
    }}
    QWidget#page, QScrollArea, QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QLabel#brandName {{ font-size: 18pt; font-weight: 700; }}
    QLabel#pageTitle {{ font-size: 15pt; font-weight: 650; }}
    QLabel#pageDescription, QLabel#muted {{ color: {colors.muted}; }}
    QGroupBox {{
        background: {colors.surface};
        border: 1px solid {colors.border};
        border-radius: 12px;
        margin-top: 15px;
        padding: 18px 16px 14px 16px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 7px;
        color: {colors.text};
        background: {colors.surface};
    }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit,
    QListWidget {{
        background: {colors.surface_alt};
        border: 1px solid {colors.border};
        border-radius: 9px;
        padding: 7px 10px;
        selection-background-color: {colors.violet};
        selection-color: white;
    }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ min-height: 22px; }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover,
    QPlainTextEdit:hover, QListWidget:hover {{ border-color: {colors.muted}; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
    QPlainTextEdit:focus, QListWidget:focus {{
        border: 2px solid {colors.violet};
        padding: 6px 9px;
    }}
    QComboBox::drop-down {{ border: 0; width: 28px; }}
    QComboBox QAbstractItemView {{
        background: {colors.surface};
        border: 1px solid {colors.border};
        selection-background-color: {colors.selected};
    }}
    QPushButton {{
        min-height: 24px;
        background: {colors.surface_alt};
        border: 1px solid {colors.border};
        border-radius: 9px;
        padding: 6px 14px;
        font-weight: 600;
    }}
    QPushButton:hover {{ background: {colors.hover}; border-color: {colors.violet}; }}
    QPushButton:pressed {{ background: {colors.selected}; }}
    QPushButton:disabled {{ color: {colors.muted}; background: {colors.window}; }}
    QPushButton#primaryButton {{
        color: white;
        border: 0;
        background: {colors.violet};
        padding: 8px 20px;
    }}
    QPushButton#primaryButton:hover {{ background: {colors.cyan}; }}
    QTabWidget::pane {{ border: 0; background: transparent; top: -1px; }}
    QTabBar {{ qproperty-drawBase: 0; }}
    QTabBar::tab {{
        background: transparent;
        color: {colors.muted};
        border: 0;
        border-bottom: 2px solid transparent;
        padding: 11px 14px;
        margin-right: 2px;
        font-weight: 600;
    }}
    QTabBar::tab:hover {{ color: {colors.text}; background: {colors.hover}; }}
    QTabBar::tab:selected {{ color: {colors.text}; border-bottom-color: {colors.violet}; }}
    QCheckBox {{ spacing: 9px; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; }}
    QCheckBox::indicator:unchecked {{
        background: {colors.surface_alt}; border: 1px solid {colors.border};
        border-radius: 5px;
    }}
    QCheckBox::indicator:checked {{
        background: {colors.violet}; border: 1px solid {colors.violet};
        border-radius: 5px;
    }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 3px; }}
    QScrollBar::handle:vertical {{ background: {colors.border}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QToolTip {{
        background: {colors.surface}; color: {colors.text};
        border: 1px solid {colors.border}; padding: 6px;
    }}
    """


class ThemeManager:
    selected_mode = ThemeMode.DARK
    resolved_mode = ThemeMode.DARK
    _app = None
    _connected = False

    @classmethod
    def apply(cls, mode, app=None):
        cls.selected_mode = normalize(mode)
        cls.resolved_mode = resolve(cls.selected_mode)
        cls._app = app or cls._app
        colors = palette(cls.resolved_mode)
        if cls._app is not None:
            cls._app.setStyleSheet(stylesheet(colors))
            cls._app.setProperty("wordarcTheme", cls.resolved_mode.value)
        try:
            import overlay
            overlay.set_theme(colors)
            import trayicon
            trayicon.set_theme(colors)
        except ImportError:
            pass
        if (cls._app is not None and not cls._connected
                and hasattr(QGuiApplication.styleHints(), "colorSchemeChanged")):
            QGuiApplication.styleHints().colorSchemeChanged.connect(
                lambda _scheme: cls.apply(cls.selected_mode)
                if cls.selected_mode == ThemeMode.SYSTEM else None)
            cls._connected = True
        return cls.resolved_mode
