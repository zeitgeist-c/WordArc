import getpass
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from brand import BRAND, brand_asset
import trayicon
import verbatim
import wordarc


_QT_APP = None


def _app():
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


def test_brand_identity_and_legacy_entry_point():
    assert BRAND.name == "WordArc"
    assert BRAND.version == wordarc.__version__ == "0.4.24"
    assert BRAND.executable == "wordarc.exe"
    assert wordarc.SERVER_NAME == f"wordarc-{getpass.getuser()}"
    assert wordarc.LEGACY_SERVER_NAME == f"verbatim-{getpass.getuser()}"
    assert verbatim.Verbatim is wordarc.WordArc


def test_svg_renders_at_all_supported_sizes():
    _app()
    icon = QIcon(str(brand_asset("wordarc-app.svg")))
    for size in (16, 20, 24, 32, 48, 64, 128, 256):
        pixmap = icon.pixmap(size, size)
        assert not pixmap.isNull()
        assert pixmap.toImage().pixelColor(0, 0).alpha() == 0


def test_ico_contains_required_sizes_and_tray_states_render():
    _app()
    with Image.open(brand_asset("wordarc.ico")) as image:
        assert set(image.ico.sizes()) >= {
            (16, 16), (20, 20), (24, 24), (32, 32),
            (48, 48), (64, 64), (128, 128), (256, 256),
        }
    for state in ("audio-input-microphone", "media-record", "view-refresh"):
        assert not trayicon.icon(state).isNull()
