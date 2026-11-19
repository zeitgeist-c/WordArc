"""Behavior contracts for the redesigned workspace."""
from unittest import mock
import pytest
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QDialog, QLineEdit, QListWidget, QApplication
from tests import test_settings_smoke as smoke
import settings_ui
import wordarc
import worker
import config as cfg

@pytest.fixture
def window():
    smoke.TestSettingsSmoke.setUpClass()
    fixture = smoke.TestSettingsSmoke()
    fixture.setUp()
    yield fixture.window
    fixture.tearDown()


def test_record_start_requires_successful_save_but_stop_does_not(window):
    calls = mock.Mock()
    window.recording_requested.connect(calls)
    with mock.patch.object(window, "_save", return_value=None):
        window._request_recording("dictation")
    calls.assert_not_called()
    with mock.patch.object(window, "_save", return_value=True) as save:
        window._request_recording("dictation")
        save.assert_called_once()
    calls.assert_called_once_with("dictation")
    calls.reset_mock()
    window.set_recording_state("dictation", "recording")
    with mock.patch.object(window, "_save") as save:
        window._request_recording("dictation")
        save.assert_not_called()
    calls.assert_called_once_with("dictation")


def test_record_start_saves_quietly_but_the_save_button_confirms(window):
    """The "saved" banner belongs to the Save button, not to record-start."""
    calls = mock.Mock()
    window.recording_requested.connect(calls)
    with mock.patch.object(settings_ui.startup, "set_enabled"), \
         mock.patch.object(settings_ui.sounds, "play") as chime, \
         mock.patch.object(window, "_save",
                           wraps=window._save) as save, \
         mock.patch.object(window.save_banner, "show_saved") as banner:
        window._request_recording("dictation")
    save.assert_called_once_with(quiet=True)
    banner.assert_not_called()
    chime.assert_not_called()
    calls.assert_called_once_with("dictation")


def test_busy_recording_cannot_be_started_again(window):
    calls = mock.Mock()
    window.recording_requested.connect(calls)
    window.set_recording_state("dictation", "busy", "stage")
    assert not window.dictation_record_button.isEnabled()
    assert window.dictation_record_status.text() == "stage"
    window._request_recording("dictation")
    calls.assert_not_called()


def test_controller_routes_buttons_to_existing_recorders():
    controller = wordarc.WordArc.__new__(wordarc.WordArc)
    controller.state = wordarc.IDLE
    controller.start = mock.Mock()
    controller.stop = mock.Mock()
    controller._toggle_meeting = mock.Mock()
    controller._window_record("dictation")
    controller.start.assert_called_once_with()
    controller.state = wordarc.RECORDING
    controller._window_record("dictation")
    controller.stop.assert_called_once()
    controller._window_record("meeting")
    controller._toggle_meeting.assert_called_once()


def test_open_workspace_receives_current_recording_state(window):
    controller = wordarc.WordArc.__new__(wordarc.WordArc)
    controller.settings_window = window
    controller.state = wordarc.RECORDING
    controller.meeting_state = wordarc.M_WORKING
    controller.meeting_message = "minutes stage"
    controller._sync_workspace()
    assert window.dictation_runtime_state == "recording"
    assert window.meeting_runtime_state == "working"
    assert window.meeting_record_status.text() == "minutes stage"


@pytest.mark.parametrize("override,expected", [(None, True), (False, False)])
def test_pipeline_window_override_does_not_modify_paste_preference(override, expected):
    conf = cfg.Config()
    conf["skip_silent"] = False
    conf["cleanup_enabled"] = False
    conf["translate_enabled"] = False
    conf["filter_hallucinations"] = False
    conf["history_enabled"] = False
    conf["auto_paste"] = True
    conf["restore_clipboard"] = True
    pipeline = worker.Pipeline(conf)
    with mock.patch.object(worker.localspeech, "transcribe_for", return_value="hello"), \
         mock.patch.object(worker.api, "GeminiClient"), \
         mock.patch.object(worker.paste, "copy") as copy, \
         mock.patch.object(worker.paste, "press") as press, \
         mock.patch.object(worker.paste, "read_clipboard", return_value=None), \
         mock.patch.object(pipeline, "_discard"), \
         mock.patch.object(worker.cfg, "append_history") as history:
        pipeline._work("isolated.wav", 1, [], "test-operation", override)
    copy.assert_called_once_with("hello")
    assert bool(press.call_count) == expected
    assert conf["auto_paste"] is True
    history.assert_not_called()


def test_searchable_device_picker_filters_and_keeps_device_identifier(window):
    combo = window.mic
    combo.clear()
    combo.addItem("First long microphone", "one")
    combo.addItem("Second long microphone", "two")
    for index in range(3):
        combo.addItem(f"Other microphone {index}", f"other-{index}")
    combo._cards_if_long([(1, "USB")])
    window.show()
    combo.setProperty("searchable", True)
    combo.showPopup()
    dialog = combo._picker
    assert dialog.windowModality() == Qt.WindowModality.NonModal
    def select():
        dialog.findChild(QLineEdit).setText("Second")
        rows = dialog.findChild(QListWidget)
        assert isinstance(rows.itemDelegate(), settings_ui.DeviceCardDelegate)
        assert rows.itemDelegate().connection_text(1) == "USB"
        dialog.findChild(QLineEdit).setText("USB")
        assert rows.item(0).isHidden()
        assert not rows.item(1).isHidden()
        rows.itemDoubleClicked.emit(rows.item(1))
    select()
    QApplication.processEvents()
    assert combo.currentData() == "two"


def test_workspace_reflows_and_settings_remain_accessible(window):
    window.show()
    window.resize(1040, 760)
    QApplication.processEvents()
    assert window.navigate_to("dictation")
    workspace = window.pages.currentWidget().findChild(settings_ui.Workspace)
    assert workspace.columns.direction() == settings_ui.QBoxLayout.Direction.LeftToRight
    window.resize(520, 400)
    QApplication.processEvents()
    assert workspace.selector.isVisibleTo(window)
    assert workspace.panes[0].isVisibleTo(window)
    assert not workspace.panes[1].isVisibleTo(window)
    workspace.selector.setCurrentIndex(1)
    assert workspace.panes[1].isVisibleTo(window)
    assert not workspace.panes[0].isVisibleTo(window)
    assert window.navigate_to("settings")
    QApplication.processEvents()
    assert window.settings_sections.isVisibleTo(window)
    assert window.select_section("application")
    assert window.current_section() == "application"


def test_last_result_is_not_persisted_when_history_is_disabled(window):
    window.set_dictation_result("session-only")
    assert window.dictation_output.toPlainText() == "session-only"
    assert not cfg.HISTORY_FILE.exists()


def test_file_cleanup_prompt_lives_in_audio_file_section(window):
    window.show()
    assert window.navigate_to("settings", "audio_file")
    QApplication.processEvents()
    assert window.file_cleanup_prompt.isVisibleTo(window)
    assert window.file_timestamps.isVisibleTo(window)
    assert window.file_cleanup.isVisibleTo(window)
    # Not on the tool page anymore: pick, start and read stay there.
    assert window.navigate_to("audio_file")
    QApplication.processEvents()
    assert window.file_label.isVisibleTo(window)
    assert window.file_run.isVisibleTo(window)


def _fully_on_screen(window, widget):
    """Viewport containment, not just the visible flag: every ancestor
    scroller viewport must hold the widget's whole rectangle."""
    from PyQt6.QtCore import QPoint, QRect
    if not widget.isVisibleTo(window):
        return False
    box = QRect(window.mapFrom(widget, QPoint(0, 0)), widget.size())
    node = widget.parentWidget()
    while node is not None and node is not window:
        if isinstance(node, settings_ui.QScrollArea):
            view = node.viewport()
            seen = QRect(window.mapFrom(view, QPoint(0, 0)), view.size())
            if not seen.contains(box):
                return False
        node = node.parentWidget()
    return True


def test_tool_first_view_needs_no_scrolling(window):
    """Action, status and result read at first glance at desktop size."""
    from PyQt6.QtGui import QFontDatabase
    for filename in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + filename)
    window.resize(1040, 760)
    window.show()
    cases = [
        ("dictation", None, ["dictation_record_button",
                             "dictation_record_status", "dictation_output",
                             "history", "mic"]),
        ("meeting", None, ["meeting_record_button", "meeting_record_status",
                           "minutes_list"]),
        ("audio_file", None, ["file_run", "file_label", "file_output",
                              "file_status"]),
        ("speak", None, ["speak_read", "speak_input", "speak_status"]),
    ]
    for page, section, attrs in cases:
        assert window.navigate_to(page, section)
        for _ in range(4):
            QApplication.processEvents()
        for attr in attrs:
            widget = getattr(window, attr)
            assert _fully_on_screen(window, widget), (page, attr)


def test_tool_first_view_at_high_scale_size(window):
    """1366x768 with high Windows scaling shows ~910x512 logical pixels:
    the same first glance must hold there."""
    window.resize(910, 512)
    window.show()
    for page, section, attrs in [
            ("dictation", None, ["dictation_record_button",
                                 "dictation_output"]),
            ("audio_file", None, ["file_run", "file_output"])]:
        assert window.navigate_to(page, section)
        for _ in range(4):
            QApplication.processEvents()
        for attr in attrs:
            assert _fully_on_screen(window, getattr(window, attr)), (page, attr)


def test_narrow_tool_rail_needs_no_scroll(window):
    """All five tools plus settings stay one tap away at minimum size."""
    from PyQt6.QtGui import QFontDatabase
    import theme
    for filename in ("segoeui.ttf", "segoeuib.ttf"):
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + filename)
    old_sheet = QApplication.instance().styleSheet()
    theme.ThemeManager.apply("dark", QApplication.instance())
    try:
        window.resize(520, 400)
        window.show()
        for page_id, _title, _desc in settings_ui.SettingsWindow.TOOL_PAGES:
            assert window.navigate_to(page_id)
            for _ in range(2):
                QApplication.processEvents()
        for _ in range(4):
            QApplication.processEvents()
        rail = window.nav
        assert rail.verticalScrollBar().maximum() == 0
        bad = []
        for index in range(rail.count()):
            rect = rail.visualItemRect(rail.item(index))
            if not rail.viewport().rect().contains(rect):
                bad.append((rail.item(index).text(), rect.x(), rect.y(),
                            rect.width(), rect.height()))
        assert not bad, (rail.viewport().rect(), bad)
    finally:
        QApplication.instance().setStyleSheet(old_sheet)


def test_action_buttons_fit_at_compact_sizes(window):
    """Neighbouring buttons reflow instead of squeezing at compact sizes.

    The probe that caught this: at 940x620 and 620x540 the dictation,
    meeting and screenshot action rows squeezed buttons below their text
    width. Grids give each button its column now; nothing may clip.
    """
    from PyQt6.QtGui import QFontDatabase
    from PyQt6.QtWidgets import QPushButton, QScrollArea, QStyle, QStyleOptionButton
    import theme
    for filename in ("segoeui.ttf", "segoeuib.ttf"):
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + filename)
    old_sheet = QApplication.instance().styleSheet()
    saved_cache = (theme.ThemeManager._applied_app,
                   theme.ThemeManager._applied_mode)
    theme.ThemeManager.apply("dark", QApplication.instance())
    try:
        for width, height in ((940, 620), (620, 540)):
            window.resize(width, height)
            window.show()
            for page in ("dictation", "meeting", "screenshot"):
                assert window.navigate_to(page)
                for _ in range(4):
                    QApplication.processEvents()
                node = window.pages.currentWidget()
                bad = []
                for button in node.findChildren(QPushButton):
                    if not button.isVisibleTo(node) or not button.text().strip():
                        continue
                    option = QStyleOptionButton()
                    option.initFrom(button)
                    content = button.style().subElementRect(
                        QStyle.SubElement.SE_PushButtonContents, option, button)
                    text_width = button.fontMetrics().size(
                        Qt.TextFlag.TextShowMnemonic, button.text()).width()
                    if text_width > content.width() + 1:
                        bad.append((page, button.text(),
                                    text_width, content.width()))
                for area in node.findChildren(QScrollArea):
                    if area.isVisibleTo(node):
                        assert area.horizontalScrollBar().maximum() == 0, (
                            width, height, page,
                            area.objectName() or type(area).__name__)
                assert not bad, (width, height, bad)
    finally:
        QApplication.instance().setStyleSheet(old_sheet)
        (theme.ThemeManager._applied_app,
         theme.ThemeManager._applied_mode) = saved_cache


def test_narrow_settings_use_a_section_picker(window):
    """No room for the section rail at minimum width: a picker stands in."""
    window.resize(520, 600)
    window.show()
    assert window.navigate_to("settings")
    for _ in range(4):
        QApplication.processEvents()
    assert not window.settings_section_list.isVisibleTo(window)
    assert window.settings_section_combo.isVisibleTo(window)
    seen = set()
    for index in range(window.settings_section_combo.count()):
        window.settings_section_combo.setCurrentIndex(index)
        for _ in range(2):
            QApplication.processEvents()
        seen.add(window.current_section())
    assert seen == {sid for sid, _title in
                    settings_ui.SettingsWindow.SETTINGS_SECTIONS}
    window.resize(1040, 760)
    for _ in range(4):
        QApplication.processEvents()
    assert window.settings_section_list.isVisibleTo(window)
    assert not window.settings_section_combo.isVisibleTo(window)


def test_narrow_audio_file_run_reaches_transcriber(window):
    """Start and result path work at narrow width through the Details pane."""
    import wave
    import struct
    # Narrow width, workable height: the 400 px floor is covered by the
    # rail test; content checks get room to breathe.
    window.resize(520, 600)
    window.show()
    assert window.navigate_to("audio_file")
    for _ in range(4):
        QApplication.processEvents()
    workspace = window.pages.currentWidget().findChild(settings_ui.Workspace)
    workspace.selector.setCurrentIndex(1)
    for _ in range(4):
        QApplication.processEvents()
    assert window.file_run.isVisibleTo(window)
    assert _fully_on_screen(window, window.file_run)
    # The 200 px transcript cannot fit a 400 px window next to the rail:
    # it must be reachable by scrolling inside its own pane instead.
    pane = window.file_output.parentWidget()
    while pane is not None and not isinstance(pane, settings_ui.QScrollArea):
        pane = pane.parentWidget()
    assert pane is not None
    assert window.file_output.isVisibleTo(window)
    assert (_fully_on_screen(window, window.file_output)
            or pane.verticalScrollBar().maximum() > 0)
    path = cfg.DATA_DIR / "probe.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(struct.pack("<4h", 0, 0, 0, 0))
    window.file_path = str(path)
    window.file_label.setText(str(path))
    with mock.patch.object(window.transcriber, "start") as start:
        window.file_run.click()
    start.assert_called_once_with(str(path),
                                  window.file_timestamps.isChecked(),
                                  window.file_cleanup.isChecked())


def test_combo_uses_compact_choices_or_search_according_to_content(window):
    combos = window.findChildren(settings_ui.QComboBox)
    assert len(combos) >= 15
    for combo in combos:
        assert isinstance(combo, settings_ui.FitsOnScreenCombo)
        with mock.patch.object(combo, "_search_picker") as picker, \
             mock.patch.object(combo, "_menu_popup") as menu, \
             mock.patch.object(settings_ui.QComboBox, "showPopup") as native:
            combo.showPopup()
        if combo.count() == 0:
            assert picker.call_count == 0
            assert menu.call_count == 0
        elif combo._menu_serves():
            assert menu.call_count == 1
            assert picker.call_count == 0
        else:
            assert picker.call_count == 1
            assert menu.call_count == 0
        assert native.call_count == 0


def test_picker_supports_keyboard_selection_custom_models_and_cancel(window):
    from PyQt6.QtTest import QTest
    window.show()
    window.navigate_to("settings")
    combo = window.cleanup_model
    original = combo.currentText()
    combo.showPopup()
    popup = combo._picker
    search = popup.findChild(QLineEdit)
    search.setText("private-model-custom")
    QTest.keyClick(search, Qt.Key.Key_Escape)
    assert combo.currentText() == original
    combo.showPopup()
    search = combo._picker.findChild(QLineEdit)
    search.setText("private-model-custom")
    QTest.keyClick(search, Qt.Key.Key_Return)
    assert combo.currentText() == "private-model-custom"
    combo.showPopup()
    search = combo._picker.findChild(QLineEdit)
    search.setText(combo.itemText(0))
    QTest.keyClick(search, Qt.Key.Key_Down)
    QTest.keyClick(combo._picker.findChild(QListWidget), Qt.Key.Key_Return)
    assert combo.currentIndex() == 0


def test_editable_model_text_is_a_picker_target(window):
    from PyQt6.QtTest import QTest
    window.show()
    window.navigate_to("settings")
    window.transcribe_engine.setCurrentIndex(window.transcribe_engine.findData("gemini"))
    QApplication.processEvents()
    with mock.patch.object(window.transcribe_model, "_search_picker") as picker:
        QTest.mouseClick(window.transcribe_model.lineEdit(), Qt.MouseButton.LeftButton)
        QApplication.processEvents()
    picker.assert_called_once()


def select_editor(window, page, section, target):
    window.navigate_to(page, section)
    for _ in range(4):
        QApplication.processEvents()
    editor = getattr(window, target)
    workspace = window.pages.currentWidget().findChild(settings_ui.Workspace)
    if workspace is not None and not editor.isVisibleTo(window):
        workspace.selector.setCurrentIndex(1)
        for _ in range(4):
            QApplication.processEvents()
    return editor


@pytest.mark.parametrize("page,section,target",
                         [("dictation", None, "history_limit"),
                          ("settings", "meeting", "meeting_prompt"),
                          ("settings", "audio_file", "file_cleanup_prompt")])
@pytest.mark.parametrize("size", [(1040, 760), (520, 400)])
def test_every_advanced_editor_is_reachable_at_large_and_small_sizes(window, page, section, target, size):
    window.resize(*size)
    window.show()
    editor = select_editor(window, page, section, target)
    # One page per tab now: scroll inside the pane until the editor shows.
    scroll = editor.parentWidget()
    while scroll and not isinstance(scroll, settings_ui.QScrollArea):
        scroll = scroll.parentWidget()
    assert scroll is not None
    point = editor.mapTo(scroll.widget(), editor.rect().center())
    scroll.ensureVisible(point.x(), point.y(), 0, 0)
    QApplication.processEvents()
    center = editor.mapTo(scroll.viewport(), editor.rect().center())
    assert 0 <= center.y() <= scroll.viewport().height()
    assert editor.isVisibleTo(window)
    assert scroll.horizontalScrollBar().maximum() == 0


def test_language_rebuild_preserves_selected_pages(window):
    assert window.navigate_to("audio_file")
    window.model_setup.setCurrentIndex(0)
    view = settings_ui.WindowView(window)
    fresh = settings_ui.SettingsWindow(window.conf, "wordarc toggle")
    try:
        view.apply(fresh)
        assert fresh.current_page() == "audio_file"
        assert fresh.model_setup.currentIndex() == 0
    finally:
        fresh.close()


@pytest.mark.parametrize("size", [(1040, 760), (920, 700)])
@pytest.mark.parametrize("language", ["tr", "en"])
def test_selected_desktop_forms_fit_without_horizontal_scrolling(window, size, language):
    from PyQt6.QtGui import QFontDatabase
    import i18n
    import theme
    # Offscreen Qt has no system-font discovery. Use the actual Windows font
    # so the check measures realistic label widths and heights.
    for filename in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + filename)
    old_language = i18n.language()
    old_style = QApplication.instance().styleSheet()
    old_ui = window.conf["ui_language"]
    i18n.set_language(language)
    window.conf["ui_language"] = language
    fresh = settings_ui.SettingsWindow(window.conf, "isolated toggle")
    try:
        fresh.resize(*size)
        fresh.show()
        for mode in ("dark", "light"):
            theme.ThemeManager.apply(mode, QApplication.instance())
            for page_id, _title, _desc in settings_ui.SettingsWindow.TOOL_PAGES:
                fresh.navigate_to(page_id)
                for _ in range(4):
                    QApplication.processEvents()
                for scroll in fresh.pages.currentWidget().findChildren(settings_ui.QScrollArea):
                    if scroll.isVisibleTo(fresh):
                        assert scroll.horizontalScrollBar().maximum() == 0, (size, language, page_id)
            fresh.navigate_to("settings", "audio_models")
            fresh.transcribe_engine.setCurrentIndex(fresh.transcribe_engine.findData("local"))
            fresh.model_setup.setCurrentIndex(0)
            for _ in range(4):
                QApplication.processEvents()
            for scroll in fresh.pages.currentWidget().findChildren(settings_ui.QScrollArea):
                if scroll.isVisibleTo(fresh):
                    assert scroll.verticalScrollBar().maximum() == 0, (size, language, "local")
    finally:
        fresh.close()
        window.conf["ui_language"] = old_ui
        i18n.set_language(old_language)
        QApplication.instance().setStyleSheet(old_style)
