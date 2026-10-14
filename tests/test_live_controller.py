"""Controller tests for the live dictation path (Tasks 10-12)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest import mock

from PyQt6.QtWidgets import QApplication

import operation
import wordarc

_QT_APP = QApplication.instance() or QApplication([])


def _live_controller(**conf_overrides):
    controller = wordarc.WordArc.__new__(wordarc.WordArc)
    conf = {"transcribe_engine": "live", "mic_target": "",
            "max_seconds": 300, "live_transcription_mode": "smart",
            "auto_paste": True}
    conf.update(conf_overrides)
    controller.conf = mock.MagicMock()
    controller.conf.get.side_effect = lambda key, default=None: conf.get(key, default)
    controller.conf.__getitem__.side_effect = lambda key: conf[key]
    controller.conf.gemini_keys.return_value = ["k1", "k2"]
    controller.conf.claim_api_slot.return_value = 0
    controller.state = wordarc.IDLE
    controller.meeting_state = wordarc.M_IDLE
    controller.dictation_operation = operation.OperationController()
    controller.overlay = mock.Mock()
    controller.elapsed = mock.Mock()
    controller.ticker = mock.Mock()
    controller.recorder = mock.Mock()
    controller.live_streamer = mock.Mock()
    controller.pipeline = mock.Mock()
    controller.tray = mock.Mock()
    controller.settings_window = None
    controller.toggle_action = mock.Mock()
    controller.cancel_action = mock.Mock()
    controller.meeting_action = mock.Mock()
    controller.meeting_cancel_action = mock.Mock()
    controller.cancel_hotkey = mock.Mock()
    controller.live_session = None
    controller.live_timer = mock.Mock()
    controller._live_opener = None
    controller._live_finisher = None
    controller.live_keys = []
    controller.live_start_slot = 0
    return controller


class _InlineThread:
    """threading.Thread yerine: run() çağrısını anında, aynı iplikte yapar."""
    def __init__(self, target=None, args=(), daemon=None):
        self._target = target
        self._args = args

    def start(self):
        self._target(*self._args)


def test_live_engine_routes_start_to_live_path():
    controller = _live_controller()
    with mock.patch.object(controller, "_start_live") as start_live, \
         mock.patch.object(controller, "_begin_recording") as begin_old:
        controller.start()
        start_live.assert_called_once_with()
        begin_old.assert_not_called()


def test_cloud_engine_keeps_old_path():
    controller = _live_controller(transcribe_engine="cloud")
    with mock.patch.object(controller, "_start_live") as start_live, \
         mock.patch.object(controller, "_begin_recording",
                           return_value=True) as begin_old:
        controller.start()
        start_live.assert_not_called()
        begin_old.assert_called_once_with()


def test_live_start_opens_session_and_streams():
    import livespeech
    controller = _live_controller()
    session = mock.Mock()
    session.preview.return_value = ""
    session.limit_hit.is_set.return_value = False
    with mock.patch.object(livespeech.LiveSession, "open_with_keys",
                           return_value=session) as opener, \
         mock.patch.object(wordarc.threading, "Thread", _InlineThread), \
         mock.patch.object(wordarc, "_LiveOpener",
                           wraps=wordarc._LiveOpener) as opener_cls:
        controller.start()
        opener.assert_called_once()
    assert controller.live_session is session
    controller.live_streamer.start.assert_called_once_with("", 300)
    controller.live_timer.start.assert_called_once_with(200)
    controller.overlay.show_recording.assert_called_once_with()
    assert controller.state == wordarc.RECORDING


def test_live_open_failure_reports_error_and_idles():
    import livespeech
    controller = _live_controller()
    with mock.patch.object(livespeech.LiveSession, "open_with_keys",
                           side_effect=livespeech.LiveError("no route")), \
         mock.patch.object(wordarc.threading, "Thread", _InlineThread):
        controller.start()
    assert controller.live_session is None
    assert controller.state == wordarc.IDLE
    controller.overlay.show_error.assert_called()


def test_live_poll_shows_preview_and_auto_stops_at_limit():
    controller = _live_controller()
    controller.state = wordarc.RECORDING
    session = mock.Mock()
    session.preview.return_value = "merhaba"
    session.limit_hit.is_set.return_value = False
    controller.live_session = session
    controller._live_poll()
    controller.overlay.show_live_text.assert_called_once_with("merhaba")
    session.limit_hit.is_set.return_value = True
    with mock.patch.object(controller, "stop") as stop:
        controller._live_poll()
        stop.assert_called_once_with()
