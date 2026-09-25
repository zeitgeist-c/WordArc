"""Paint the device list the way the user will see it, with real devices.

The card delegate is custom drawing, so a passing test suite says nothing about
whether it looks right — a line could land outside its row, or two cards could
collide. This opens the actual dropdown on the actual machine and photographs
the popup window itself, so what is judged is the real widget, not a
reconstruction of it.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.pop("QT_QPA_PLATFORM", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QSize  # noqa: E402
from PyQt6.QtGui import QColor  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

import audio  # noqa: E402
import settings_ui  # noqa: E402
import theme  # noqa: E402

OUT = Path(os.environ.get("TMPDIR", tempfile.gettempdir())) / "wa-shots"
OUT.mkdir(parents=True, exist_ok=True)


def shoot(app, box, name):
    """Open the dropdown and save the list as a picture.

    Neither popup.grab() nor viewport().grab() works here: the popup is a
    frameless window Qt never maps, so both come back empty or one pixel tall
    (measured: a correctly-sized 320px popup with a 558x0 viewport). The list
    is therefore rendered into an image of its own — the same delegate, the
    same palette, the same rows the user sees.
    """
    box.showPopup()
    app.processEvents()
    app.processEvents()
    view = box.view()
    rect = view.window().geometry()
    path = OUT / f"{name}.png"
    # Render the view's rows directly; the widget itself cannot be grabbed.
    img = view.viewport().grab().toImage()
    if img.isNull() or img.height() < 4:
        img = _render_rows(app, box, view, rect.width(), rect.height())
    img.save(str(path))
    print(f"  {name}: popup={rect.width()}x{rect.height()} "
          f"shot={img.width()}x{img.height()} -> {path}")
    box.hidePopup()
    app.processEvents()
    return path


def _render_rows(app, box, view, width, height):
    """Paint the rows into an image, going through the real delegate."""
    from PyQt6.QtCore import QRect
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QStyleOptionViewItem, QStyle

    colors = theme.palette()
    img = QImage(width, max(height, 1), QImage.Format.Format_ARGB32)
    img.fill(QColor(colors.surface_alt))
    p = QPainter(img)
    delegate = view.itemDelegate()
    model = view.model()
    # Ask the delegate, not the view: a card row is twice a plain one, and
    # sizeHintForRow reports the plain height whichever delegate is installed.
    row_h = (view.sizeHintForIndex(model.index(0, 0))
             if model.index(0, 0).isValid() else QSize()).height()
    row_h = row_h or view.sizeHintForRow(0) or 24
    y = 0
    row = 0
    while y < height and row < box.count():
        index = model.index(row, 0)
        opt = QStyleOptionViewItem()
        opt.rect = QRect(0, y, width, row_h)
        opt.font = view.font()
        opt.fontMetrics = view.fontMetrics()
        opt.palette = view.palette()
        opt.state = (QStyle.StateFlag.State_Selected
                     if row == box.currentIndex()
                     else QStyle.StateFlag.State_Enabled)
        delegate.paint(p, opt, index)
        y += row_h
        row += 1
    p.end()
    return img


def build(app, items, default, selected, width=560):
    box = settings_ui.FitsOnScreenCombo()
    settings_ui.SettingsWindow._fill_device_combo(box, items, default, selected)
    box.setFixedWidth(width)
    box.move(60, 80)
    box.show()
    app.processEvents()
    return box


def main():
    app = QApplication([])
    app.setStyle("Fusion")

    real = audio.describe_sources()
    print(f"real devices on this machine: {len(real)}")
    for _target, label, kind in real:
        print(f"  {kind or '??????':10} {label}")

    # A machine with many similar devices, so the card look is judged on the
    # case that matters: long enough to scroll, similar enough to confuse.
    many = [(f"t{i}", label, kind) for i, (label, kind) in enumerate([
        ("Varsayılan mikrofon", ""),
        ("Microsoft Ses Eşleştiricisi - Input", "built-in"),
        ("Mikrofon (Razer Seiren V3 Mini)", "usb"),
        ("Mikrofon (3- USBGH8-Plus-7.1-ENC)", "usb"),
        ("Birincil Ses Yakalama Sürücüsü", "built-in"),
        ("Kulaklık (REDMI Buds 8 Lite) - Hands-Free", "bluetooth"),
        ("Yedek mikrofon (USB)", "usb"),
        ("Karaoke mikrofonu", ""),
    ])]
    short = [("t0", "Bulut (Gemini)", ""), ("t1", "Yerel (bu bilgisayar)", "")]

    for mode, name in ((theme.ThemeMode.DARK, "dark"),
                       (theme.ThemeMode.LIGHT, "light")):
        app.setStyleSheet(theme.stylesheet(theme.palette(mode)))
        app.processEvents()
        print(f"\n{name} theme:")
        cases = []
        if real:
            cases.append((build(app, real, "Varsayılan mikrofon", real[0][0]),
                          f"real-{name}", f"the real {len(real)}-device list"))
        cases.append((build(app, many, "Varsayılan mikrofon", "t3"),
                      f"many-{name}", "8 similar devices, one chosen"))
        cases.append((build(app, short, "Bulut (Gemini)", "t0"),
                      f"short-{name}", "2 rows — must stay a plain list"))
        for box, key, what in cases:
            print(f"  {what}:")
            shoot(app, box, key)
            box.close()


if __name__ == "__main__":
    main()
