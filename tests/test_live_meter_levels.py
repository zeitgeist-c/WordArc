"""Canlı diktede ses dalgası: seviye sinyali bağlı mı?

Kullanıcı 0.7.2'de canlı diktede dalganın hiç oynamadığını bildirdi.
Kök neden: LiveStreamer.level sinyali hiçbir yere bağlanmamıştı, bu yüzden
overlay'in seviye listesi hep 0.0 kalıyor ve çubuklar en kısa hâlde çiziliyordu.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest import mock

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication

import audio
import operation
import overlay
import wordarc

_QT_APP = QApplication.instance() or QApplication([])


class _FakeStreamer(QObject):
    """Gerçek LiveStreamer yerine: sinyalleri taşır, cihaz açmaz."""

    chunk = pyqtSignal(bytes)
    level = pyqtSignal(float)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.started = None
        self._active = False

    @property
    def active(self):
        return self._active

    def start(self, target="", max_seconds=480):
        self.started = (target, max_seconds)
        self._active = True

    def stop(self):
        return None

    def cancel(self):
        self._active = False


def _controller():
    controller = wordarc.WordArc.__new__(wordarc.WordArc)
    conf = {"transcribe_engine": "live", "mic_target": "", "max_seconds": 300,
            "live_transcription_mode": "smart", "auto_paste": True}
    controller.conf = mock.MagicMock()
    controller.conf.get.side_effect = lambda key, default=None: conf.get(key, default)
    controller.conf.__getitem__.side_effect = lambda key: conf[key]
    controller.conf.gemini_keys.return_value = ["k1"]
    controller.conf.claim_api_slot.return_value = 0
    controller.state = wordarc.RECORDING
    controller.meeting_state = wordarc.M_IDLE
    controller.dictation_operation = operation.OperationController()
    controller.dictation_operation.begin()
    controller.overlay = overlay.Overlay()
    controller.overlay.show_recording()
    controller.elapsed = mock.Mock()
    controller.ticker = mock.Mock()
    controller.pipeline = mock.Mock()
    controller.tray = mock.Mock()
    controller.settings_window = None
    controller.live_streamer = _FakeStreamer()
    controller.live_session = mock.Mock()
    controller.live_session.preview.return_value = ""
    controller.live_timer = mock.Mock()
    controller.live_keys = ["k1"]
    controller.live_start_slot = 0
    controller._finishing_session = None
    return controller


def test_live_level_signal_reaches_the_overlay():
    """Asıl sözleşme: canlı yakalayıcıdan gelen seviye overlay'e ulaşmalı."""
    controller = _controller()
    # Üretimdeki bağlantıyı kur (__init__ bu testte çalışmıyor).
    controller.live_streamer.level.connect(controller._on_level)
    controller.overlay.levels = [0.0] * overlay.BARS
    controller.live_streamer.level.emit(0.85)
    _QT_APP.processEvents()
    assert max(controller.overlay.levels) > 0.5, "seviye overlay'e ulaşmadı"


def test_production_init_connects_the_streamer_level():
    """__init__ gerçekten bağlıyor mu: kaynak düzeyinde kontrol."""
    import inspect
    source = inspect.getsource(wordarc.WordArc.__init__)
    assert "live_streamer.level.connect" in source, \
        "canlı yakalayıcının level sinyali bağlanmamış"


def _ink(box):
    image = QImage(box.width(), box.height(), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    box.render(painter)
    painter.end()
    painted = 0
    for y in range(box.height()):
        for x in range(46, max(47, box.width() - 70)):
            colour = image.pixelColor(x, y)
            if colour.alpha() < 40:
                continue
            spread = (max(colour.red(), colour.green(), colour.blue())
                      - min(colour.red(), colour.green(), colour.blue()))
            if spread > 24:
                painted += 1
    return painted


def test_pushed_levels_move_the_meter():
    """Seviyeler geldikçe dalga gerçekten değişmeli (piksel ölçümü)."""
    for style in ("bars", "spectrum", "wave", "capsule"):
        overlay.set_meter(style)
        box = overlay.Overlay()
        box.show_recording()
        silent = _ink(box)
        for i in range(overlay.BARS):
            box.push_level(0.75)
        loud = _ink(box)
        assert loud > silent, (style, silent, loud)
    overlay.set_meter("spectrum")


def test_streamer_emits_level_from_callback():
    """audio.LiveStreamer._callback gerçekten level yayıyor mu."""
    streamer = audio.LiveStreamer()
    seen = []
    streamer.level.connect(seen.append)
    streamer._stream = mock.Mock()
    indata = mock.Mock()
    indata.tobytes.return_value = b"\xff\x7f" * audio.CHUNK_FRAMES
    streamer._callback(indata, audio.CHUNK_FRAMES, None, None)
    assert seen and seen[0] > 0.1, seen
