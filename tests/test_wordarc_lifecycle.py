from unittest import mock

import os
import uuid
import pytest

import wordarc


def test_singleton_mutex_allows_one_owner_and_can_be_handed_over():
    if os.name != "nt":
        return  # the mutex is a Windows singleton guard
    name = f"Local\\wordarc-test-{os.getpid()}-{uuid.uuid4().hex}"
    assert wordarc._acquire_instance_mutex(name)
    assert not wordarc._acquire_instance_mutex(name), "a second owner must not get it"
    wordarc._release_instance_mutex()
    assert wordarc._acquire_instance_mutex(name), "a released lock must be reacquirable"
    wordarc._release_instance_mutex()


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


def test_tray_left_click_opens_window_instead_of_recording():
    from PyQt6.QtWidgets import QSystemTrayIcon

    controller = _controller(True)
    controller._toggle = mock.Mock()
    controller.open_settings = mock.Mock()

    controller._tray_clicked(QSystemTrayIcon.ActivationReason.Trigger)

    controller.open_settings.assert_called_once_with()
    controller._toggle.assert_not_called()


def test_other_tray_reasons_stay_inert():
    from PyQt6.QtWidgets import QSystemTrayIcon

    controller = _controller(True)
    controller._toggle = mock.Mock()
    controller.open_settings = mock.Mock()

    controller._tray_clicked(QSystemTrayIcon.ActivationReason.MiddleClick)

    controller.open_settings.assert_not_called()
    controller._toggle.assert_not_called()


def test_hotkey_failure_names_the_action():
    controller = _controller(True)
    controller.conf = {"shortcut": "ScrollLock", "meeting_shortcut": "",
                       "screenshot_shortcut": "Ctrl+Alt+S",
                       "tts_shortcut": "", "tts_stop_shortcut": ""}
    messages = []
    controller.tray = mock.Mock()
    controller.tray.isVisible.return_value = True
    controller.tray.showMessage.side_effect = \
        lambda *_a, **_k: messages.append(_a[1])
    controller._on_hotkey_failed("...kullanıyor olabilir: Ctrl+Alt+S")
    assert len(messages) == 1
    assert messages[0].endswith("(Screenshot)")


def test_hotkey_failure_without_match_passes_through():
    controller = _controller(True)
    controller.conf = {"shortcut": "ScrollLock", "meeting_shortcut": "",
                       "screenshot_shortcut": "Ctrl+Alt+S",
                       "tts_shortcut": "", "tts_stop_shortcut": ""}
    messages = []
    controller.tray = mock.Mock()
    controller.tray.isVisible.return_value = True
    controller.tray.showMessage.side_effect = \
        lambda *_a, **_k: messages.append(_a[1])
    controller._on_hotkey_failed("...kullanıyor olabilir: Ctrl+F9")
    assert messages == ["...kullanıyor olabilir: Ctrl+F9"]


def test_tray_stop_action_follows_speaking_state():
    app = wordarc.QApplication.instance() or wordarc.QApplication([])
    controller = _controller(True)
    controller.tts = mock.Mock()
    controller.tts.busy = False
    controller.tray = mock.Mock()
    controller._build_tray()
    assert controller.speak_stop_action.isEnabled() is False
    controller.tts.busy = True
    controller._refresh_stop_action()
    assert controller.speak_stop_action.isEnabled() is True


def test_ocr_result_lands_in_the_clipboard_or_the_warning_tray():
    from PyQt6.QtWidgets import QApplication

    controller = _controller(True)
    messages = []
    controller.tray = mock.Mock()
    controller.tray.isVisible.return_value = True
    controller.tray.showMessage.side_effect = \
        lambda *_a, **_k: messages.append(_a[1])
    clipboard = mock.Mock()
    with mock.patch.object(wordarc.QApplication, "clipboard",
                           return_value=clipboard):
        controller._on_screenshot_ocr("ayıklanan metin")
    clipboard.setText.assert_called_once_with("ayıklanan metin")
    assert len(messages) == 1

    clipboard.reset_mock()
    messages.clear()
    with mock.patch.object(wordarc.QApplication, "clipboard",
                           return_value=clipboard):
        controller._on_screenshot_ocr("")
    clipboard.setText.assert_not_called()
    assert len(messages) == 1, "an empty result must be reported as a warning"


def test_startup_registration_runs_once_and_respects_the_switch():
    with mock.patch.object(wordarc.startup, "is_enabled", return_value=False), \
         mock.patch.object(wordarc.startup, "set_enabled") as set_enabled:
        assert wordarc.ensure_startup_registration({"start_with_windows": True})
    set_enabled.assert_called_once_with(True)

    with mock.patch.object(wordarc.startup, "is_enabled", return_value=True), \
         mock.patch.object(wordarc.startup, "set_enabled") as set_enabled:
        assert not wordarc.ensure_startup_registration({"start_with_windows": True})
    set_enabled.assert_not_called()

    with mock.patch.object(wordarc.startup, "is_enabled") as is_enabled, \
         mock.patch.object(wordarc.startup, "set_enabled") as set_enabled:
        assert not wordarc.ensure_startup_registration({"start_with_windows": False})
    is_enabled.assert_not_called()
    set_enabled.assert_not_called()


def test_startup_registration_failure_never_blocks_boot():
    with mock.patch.object(wordarc.startup, "is_enabled",
                           side_effect=wordarc.startup.StartupError("locked")), \
         mock.patch.object(wordarc.startup, "set_enabled"):
        assert not wordarc.ensure_startup_registration({"start_with_windows": True})


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
    controller.screenshot_controller = mock.Mock()
    controller.evdev = mock.Mock()
    controller.cancel_hotkey = mock.Mock()
    controller.pipeline = mock.Mock()
    controller.meetings = mock.Mock(spec=["stop"])
    controller.state = wordarc.IDLE
    controller.meeting_state = wordarc.M_IDLE
    controller.overlay = mock.Mock()
    controller.tray = mock.Mock()

    controller.shutdown()

    controller.screenshot_controller.shutdown.assert_called_once_with()
    controller.meetings.stop.assert_called_once_with()
    controller.cancel_hotkey.stop.assert_called_once_with()


def test_shortcut_capture_parks_and_returns_the_global_hotkeys():
    controller = wordarc.WordArc.__new__(wordarc.WordArc)
    controller.evdev = mock.Mock()
    controller.cancel_hotkey = mock.Mock()
    controller._refresh_cancel_hotkey = mock.Mock()
    controller.conf = {"shortcut": "Ctrl+Space", "meeting_shortcut": "",
                       "screenshot_shortcut": "Ctrl+Alt+S",
                       "tts_shortcut": "Ctrl+Shift+O",
                       "tts_stop_shortcut": "Ctrl+Shift+X"}

    controller._on_shortcut_capture(True)
    controller.evdev.stop.assert_called_once_with()
    controller.cancel_hotkey.stop.assert_called_once_with()

    controller._on_shortcut_capture(False)
    controller.evdev.start.assert_called_once_with({
        "toggle": "Ctrl+Space", "meeting": "",
        "screenshot": "Ctrl+Alt+S",
        "speak": "Ctrl+Shift+O", "speak_stop": "Ctrl+Shift+X"})
    controller._refresh_cancel_hotkey.assert_called_once_with()


def test_escape_is_global_only_while_recording():
    controller = wordarc.WordArc.__new__(wordarc.WordArc)
    controller.cancel_hotkey = mock.Mock()
    controller._refresh_tray = mock.Mock()
    controller.meeting_state = wordarc.M_IDLE

    controller._set_state(wordarc.RECORDING)
    controller.cancel_hotkey.start.assert_called_once_with({"cancel": "Escape"})

    controller._set_state(wordarc.BUSY)
    controller.cancel_hotkey.stop.assert_called_once_with()


def test_escape_arms_for_meeting_and_cancels_it():
    controller = wordarc.WordArc.__new__(wordarc.WordArc)
    controller.cancel_hotkey = mock.Mock()
    controller._refresh_tray = mock.Mock()
    controller.state = wordarc.IDLE
    controller.meeting_state = wordarc.M_IDLE
    controller.meeting_message = ""

    controller._set_meeting_state(wordarc.M_RECORDING)
    controller.cancel_hotkey.start.assert_called_once_with({"cancel": "Escape"})

    controller.cancel = mock.Mock()
    controller.cancel_meeting = mock.Mock()
    controller._on_cancel_key("cancel")
    controller.cancel.assert_not_called()
    controller.cancel_meeting.assert_called_once_with()

    controller._set_meeting_state(wordarc.M_IDLE)
    controller.cancel_hotkey.stop.assert_called_once_with()


def test_escape_prefers_dictation_over_meeting():
    controller = wordarc.WordArc.__new__(wordarc.WordArc)
    controller.state = wordarc.RECORDING
    controller.meeting_state = wordarc.M_RECORDING
    controller.cancel = mock.Mock()
    controller.cancel_meeting = mock.Mock()
    controller._on_cancel_key("cancel")
    controller.cancel.assert_called_once_with()
    controller.cancel_meeting.assert_not_called()


def test_language_change_keeps_the_window_when_the_rebuild_fails():
    """The rebuild closes the old window only after the new one is up.

    Closing first left the user with nothing on screen when the build threw
    (a device rescan in a bad PortAudio state is enough), which is what a
    language change looked like: the window gone.
    """
    controller = wordarc.WordArc.__new__(wordarc.WordArc)
    old = mock.Mock()
    controller.app = mock.Mock()
    controller.settings_window = old
    controller._settings_view = None
    controller._sync_workspace = mock.Mock()
    controller._build_tray = mock.Mock()
    controller._refresh_tray = mock.Mock()

    with mock.patch.object(wordarc, "install_qt_translator"), \
         mock.patch.object(wordarc.WordArc, "open_settings",
                           side_effect=RuntimeError("no window")):
        controller._reopen_settings()

    assert controller.settings_window is old
    old.close.assert_not_called()
    old.show.assert_called_once_with()
    old.activateWindow.assert_called_once_with()
    # The tray menu speaks the new language either way.
    controller._build_tray.assert_called_once_with()


def test_language_change_swaps_the_window_and_frees_the_old_one():
    controller = wordarc.WordArc.__new__(wordarc.WordArc)
    old = mock.Mock()
    fresh = mock.Mock()
    controller.app = mock.Mock()
    controller.settings_window = old
    controller._settings_view = None
    controller._build_tray = mock.Mock()
    controller._refresh_tray = mock.Mock()

    def rebuild():
        controller.settings_window = fresh

    with mock.patch.object(wordarc, "install_qt_translator"), \
         mock.patch.object(wordarc.WordArc, "open_settings",
                           side_effect=rebuild), \
         mock.patch.object(wordarc.QTimer, "singleShot") as later:
        controller._reopen_settings()

    assert controller.settings_window is fresh
    old.blockSignals.assert_called_once_with(True)
    old.close.assert_called_once_with()
    # Deleted on the next turn of the loop, not inside the window's own signal.
    later.assert_called_once()
    assert later.call_args[0][1] == old.deleteLater


def test_language_change_hands_the_window_state_to_the_rebuild():
    controller = wordarc.WordArc.__new__(wordarc.WordArc)
    old = mock.Mock()
    controller.app = mock.Mock()
    controller.settings_window = old
    controller._settings_view = None
    controller._build_tray = mock.Mock()
    controller._refresh_tray = mock.Mock()
    view = mock.Mock()
    fresh = mock.Mock()
    handed = []

    def rebuild():
        handed.append(controller._settings_view)
        controller.settings_window = fresh

    with mock.patch.object(wordarc, "install_qt_translator"), \
         mock.patch.object(wordarc, "WindowView", return_value=view), \
         mock.patch.object(wordarc.WordArc, "open_settings",
                           side_effect=rebuild), \
         mock.patch.object(wordarc.QTimer, "singleShot"):
        controller._reopen_settings()

    assert handed == [view]


def test_a_window_opened_before_the_close_lands_is_not_dropped():
    """The 0 ms timer drops the window it was queued for, not whatever is on
    screen when it fires: a window opened in between used to be lost (and the
    quit below took the app with it)."""
    controller = wordarc.WordArc.__new__(wordarc.WordArc)
    closed = mock.Mock()
    fresh = mock.Mock()
    controller.app = mock.Mock()
    controller.settings_window = closed
    controller._quitting = False
    controller.conf = {"close_to_tray": True}
    timers = []

    with mock.patch.object(wordarc.QTimer, "singleShot",
                           side_effect=lambda _ms, fn: timers.append(fn)):
        controller._settings_closed()
    controller.settings_window = fresh
    for fn in timers:
        fn()

    assert controller.settings_window is fresh
    controller.app.quit.assert_not_called()


def test_a_late_language_change_does_not_reopen_a_closed_window():
    """A language saved from the Settings tab rebuilds the window a turn later.

    By then the window may already be closed, and opening one here would put
    back on screen a window the user has just dismissed.
    """
    controller = wordarc.WordArc.__new__(wordarc.WordArc)
    controller.app = mock.Mock()
    controller.settings_window = None
    controller._settings_view = None
    controller._build_tray = mock.Mock()
    controller._refresh_tray = mock.Mock()

    with mock.patch.object(wordarc, "install_qt_translator"), \
         mock.patch.object(wordarc.WordArc, "open_settings") as open_settings:
        controller._reopen_settings()

    open_settings.assert_not_called()
    assert controller.settings_window is None
    # The tray menu speaks the new language either way.
    controller._build_tray.assert_called_once_with()


def test_open_settings_puts_the_window_back_where_it_was_before_showing():
    """The rebuild's state is applied by open_settings, before show(), so the
    window never appears at its opening size first."""
    controller = wordarc.WordArc.__new__(wordarc.WordArc)
    controller.conf = mock.Mock()
    controller.meetings = None
    controller._last_dictation = ""
    controller.settings_window = None
    controller.screenshot_controller = mock.Mock()
    controller._sync_workspace = mock.Mock()
    controller._window_record = mock.Mock()
    controller._window_cancel = mock.Mock()
    controller._apply_settings = mock.Mock()
    controller._reopen_settings = mock.Mock()
    controller._settings_closed = mock.Mock()
    window = mock.Mock()
    view = mock.Mock()
    controller._settings_view = view

    with mock.patch.object(wordarc, "SettingsWindow", return_value=window):
        controller.open_settings()

    view.apply.assert_called_once_with(window)
    assert controller._settings_view is None, "the state outlived the open"
    window.show.assert_called_once_with()


def test_restart_args_drop_one_shot_commands_and_mark_the_child():
    assert wordarc._restart_args(["wordarc.py", "toggle"]) == ["--restarted"]
    assert wordarc._restart_args(["wordarc.py", "restart"]) == ["--restarted"]
    assert wordarc._restart_args(["wordarc.py"]) == ["--restarted"]
    assert wordarc._restart_args(["wordarc.py", "--local-stt-check", "x"]) == [
        "--local-stt-check", "--restarted"]
    # An old flag never piles up over several restarts.
    assert wordarc._restart_args(["wordarc.py", "--restarted"]) == [
        "--restarted"]


def _restart_controller():
    controller = wordarc.WordArc.__new__(wordarc.WordArc)
    controller.settings_window = None
    controller.shutdown = mock.Mock()
    controller.app = mock.Mock()
    return controller


def test_restart_boots_the_child_without_a_launch_command():
    """Replaying the parent's command made the child talk to the dying
    instance and exit, so a restart closed the app instead of reloading it."""
    controller = _restart_controller()
    with mock.patch.object(wordarc, "_release_instance_mutex"), \
         mock.patch.object(wordarc, "QLocalServer"), \
         mock.patch.object(wordarc.subprocess, "Popen") as popen, \
         mock.patch.object(wordarc.sys, "argv", ["wordarc.py", "toggle"]):
        controller.restart()
    popen.assert_called_once()
    cmd = popen.call_args[0][0]
    assert cmd[0] == wordarc.sys.executable
    assert "toggle" not in cmd
    assert cmd[-1] == wordarc.RESTART_FLAG
    controller.app.quit.assert_called_once_with()


def test_restart_uses_the_exe_itself_when_frozen():
    controller = _restart_controller()
    with mock.patch.object(wordarc, "_release_instance_mutex"), \
         mock.patch.object(wordarc, "QLocalServer"), \
         mock.patch.object(wordarc.subprocess, "Popen") as popen, \
         mock.patch.object(wordarc.sys, "argv", ["WordArc.exe"]), \
         mock.patch.object(wordarc.sys, "frozen", True, create=True):
        controller.restart()
    popen.assert_called_once()
    cmd = popen.call_args[0][0]
    assert cmd[0] == wordarc.sys.executable
    assert len(cmd) == 2 and cmd[1] == wordarc.RESTART_FLAG


def test_startup_splash_renders_vector_card():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = wordarc.QApplication.instance() or wordarc.QApplication([])
    splash = wordarc._startup_splash(app)
    assert splash is not None
    pixmap = splash.pixmap()
    assert not pixmap.isNull()
    assert (pixmap.width(), pixmap.height()) == (
        wordarc.SPLASH_WIDTH, wordarc.SPLASH_HEIGHT)
    image = pixmap.toImage()
    assert image.pixelColor(4, 4).alpha() < 50  # rounded corner stays clear
    card = image.pixelColor(300, 210)
    assert card.alpha() > 200 and card.lightness() < 120  # dark card body
    splash.close()


@pytest.mark.parametrize("dpr", [1.0, 1.25, 1.5, 2.0])
def test_splash_keeps_all_four_corners_clear_at_display_scale(dpr):
    app = wordarc.QApplication.instance() or wordarc.QApplication([])
    pixmap = wordarc._splash_pixmap(dpr)
    assert pixmap.deviceIndependentSize().width() == wordarc.SPLASH_WIDTH
    image = pixmap.toImage()
    width, height = image.width(), image.height()
    for x, y in [(2, 2), (width - 3, 2), (2, height - 3),
                 (width - 3, height - 3)]:
        assert image.pixelColor(x, y).alpha() == 0
    # The right and bottom edges must exist inside the canvas, not be cropped
    # away by a second application of the display scale.
    assert image.pixelColor(width - round(4 * dpr), height // 2).alpha() > 200
    assert image.pixelColor(width // 2, height - round(4 * dpr)).alpha() > 200


def test_setup_language_arg_accepts_only_known_codes():
    assert wordarc._setup_language_arg(
        ["WordArc.exe", "--setup-language", "tr"]) == "tr"
    assert wordarc._setup_language_arg(
        ["WordArc.exe", "--setup-language", "pt-BR"]) == "pt-BR"
    assert wordarc._setup_language_arg(
        ["WordArc.exe", "--setup-language", "ptBR"]) == "pt-BR"
    assert wordarc._setup_language_arg(
        ["WordArc.exe", "--setup-language", "zhCN"]) == "zh-CN"
    assert wordarc._setup_language_arg(["WordArc.exe"]) == ""
    assert wordarc._setup_language_arg(
        ["WordArc.exe", "--setup-language", "xx"]) == ""
    assert wordarc._setup_language_arg(
        ["WordArc.exe", "--setup-language"]) == ""


def test_first_run_applies_setup_language_once():
    import i18n
    conf = mock.MagicMock()
    conf.fresh = True
    try:
        wordarc._apply_first_run_language(conf, "de")
    finally:
        i18n.set_language("en")
    conf.__setitem__.assert_called_once_with("ui_language", "de")


def test_first_run_leaves_existing_install_alone():
    conf = mock.MagicMock()
    conf.fresh = False
    with mock.patch.object(wordarc, "_ask_first_run_language") as ask:
        wordarc._apply_first_run_language(conf, "tr")
        ask.assert_not_called()
    conf.__setitem__.assert_not_called()
