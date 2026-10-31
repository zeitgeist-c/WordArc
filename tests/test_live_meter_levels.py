"""Live dictation waveform: is the level signal connected?

A user reported in 0.7.2 that the waveform never moved during live dictation.
Root cause: LiveStreamer.level was never connected to anything, so the
overlay's level list stayed at 0.0 and the bars were drawn at their shortest.
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
    """Stands in for the real LiveStreamer: carries signals, opens no device."""

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
    """The real contract: a level from the live capture must reach the overlay."""
    controller = _controller()
    # Wire it the way production does (__init__ does not run in this test).
    controller.live_streamer.level.connect(controller._on_level)
    controller.overlay.levels = [0.0] * overlay.BARS
    controller.live_streamer.level.emit(0.85)
    _QT_APP.processEvents()
    assert max(controller.overlay.levels) > 0.5, "level did not reach the overlay"


def test_production_init_connects_the_streamer_level():
    """Does __init__ really connect it: a source-level check."""
    import inspect
    source = inspect.getsource(wordarc.WordArc.__init__)
    assert "live_streamer.level.connect" in source, \
        "the live capture's level signal is not connected"


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
    """The waveform must really change as levels arrive (pixel measurement)."""
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
    """Does audio.LiveStreamer._callback really emit a level."""
    streamer = audio.LiveStreamer()
    seen = []
    streamer.level.connect(seen.append)
    streamer._stream = mock.Mock()
    indata = mock.Mock()
    indata.tobytes.return_value = b"\xff\x7f" * audio.CHUNK_FRAMES
    streamer._callback(indata, audio.CHUNK_FRAMES, None, None)
    assert seen and seen[0] > 0.1, seen
