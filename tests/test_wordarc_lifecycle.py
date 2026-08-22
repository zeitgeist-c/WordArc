from unittest import mock

import wordarc


def test_manual_launch_opens_settings_and_background_stays_hidden():
    assert wordarc._should_open_settings("", True, True)
    assert wordarc._should_open_settings("settings", True, True)
    assert not wordarc._should_open_settings("background", True, True)
    assert wordarc._should_open_settings("background", False, True)
    assert wordarc._should_open_settings("background", True, False)


def _controller(close_to_tray):
    controller = wordarc.WordArc.__new__(wordarc.WordArc)
    controller.settings_window = object()
    controller._quitting = False
    controller.conf = {"close_to_tray": close_to_tray}
    controller.app = mock.Mock()
    return controller


def test_window_close_respects_close_to_tray_setting():
    with mock.patch.object(wordarc.QTimer, "singleShot",
                           side_effect=lambda _delay, callback: callback()), \
         mock.patch.object(wordarc.QSystemTrayIcon, "isSystemTrayAvailable",
                           return_value=True):
        tray_controller = _controller(True)
        tray_controller._settings_closed()
        tray_controller.app.quit.assert_not_called()

        quit_controller = _controller(False)
        quit_controller._settings_closed()
        quit_controller.app.quit.assert_called_once_with()


def test_window_close_quits_if_system_tray_is_unavailable():
    controller = _controller(True)
    with mock.patch.object(wordarc.QTimer, "singleShot",
                           side_effect=lambda _delay, callback: callback()), \
         mock.patch.object(wordarc.QSystemTrayIcon, "isSystemTrayAvailable",
                           return_value=False):
        controller._settings_closed()
    controller.app.quit.assert_called_once_with()


def test_shutdown_stops_meeting_pipeline_without_missing_cancel_method():
    controller = wordarc.WordArc.__new__(wordarc.WordArc)
    controller.evdev = mock.Mock()
    controller.cancel_hotkey = mock.Mock()
    controller.pipeline = mock.Mock()
    controller.meetings = mock.Mock(spec=["stop"])
    controller.state = wordarc.IDLE
    controller.meeting_state = wordarc.M_IDLE
    controller.overlay = mock.Mock()
    controller.tray = mock.Mock()

    controller.shutdown()

    controller.meetings.stop.assert_called_once_with()
    controller.cancel_hotkey.stop.assert_called_once_with()


def test_escape_is_global_only_while_recording():
    controller = wordarc.WordArc.__new__(wordarc.WordArc)
    controller.cancel_hotkey = mock.Mock()
    controller._refresh_tray = mock.Mock()

    controller._set_state(wordarc.RECORDING)
    controller.cancel_hotkey.start.assert_called_once_with({"cancel": "Escape"})

    controller._set_state(wordarc.BUSY)
    controller.cancel_hotkey.stop.assert_called_once_with()
