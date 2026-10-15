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
    workspace = window.tabs.widget(0).findChild(settings_ui.Workspace)
    assert workspace.columns.direction() == settings_ui.QBoxLayout.Direction.LeftToRight
    window.resize(520, 400)
    QApplication.processEvents()
    assert workspace.selector.isVisibleTo(window)
    assert workspace.panes[0].isVisibleTo(window)
    assert not workspace.panes[1].isVisibleTo(window)
    workspace.selector.setCurrentIndex(1)
    assert workspace.panes[1].isVisibleTo(window)
    assert not workspace.panes[0].isVisibleTo(window)
    window.tabs.setCurrentIndex(window._tab_index["settings"])
    QApplication.processEvents()
    assert window.settings_section_stack.isVisibleTo(window)
    window.settings_section_stack.setCurrentIndex(3)
    assert window.settings_section_menu.currentRow() == 3


def test_last_result_is_not_persisted_when_history_is_disabled(window):
    window.set_dictation_result("session-only")
    assert window.dictation_output.toPlainText() == "session-only"
    assert not cfg.HISTORY_FILE.exists()


def test_file_options_stay_visible_while_instruction_is_collapsed(window):
    window.show()
    window.tabs.setCurrentIndex(2)
    QApplication.processEvents()
    assert window.file_timestamps.isVisibleTo(window)
    assert window.file_cleanup.isVisibleTo(window)
    assert not window.file_cleanup_prompt.isVisibleTo(window)
    window.file_options.setCurrentIndex(1)
    assert window.file_cleanup_prompt.isVisibleTo(window)


def test_combo_uses_compact_choices_or_search_according_to_content(window):
    combos = window.findChildren(settings_ui.QComboBox)
    assert len(combos) >= 15
    for combo in combos:
        assert isinstance(combo, settings_ui.FitsOnScreenCombo)
        searchable = combo.isEditable() or combo.property("searchable") or combo.count() > 8
        with mock.patch.object(combo, "_search_picker") as picker, \
             mock.patch.object(settings_ui.QComboBox, "showPopup") as native:
            combo.showPopup()
        assert picker.call_count == int(combo.count() > 0)
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


def select_editor(window, tab, target):
    window.tabs.setCurrentIndex(tab)
    workspace = window.tabs.widget(tab).findChild(settings_ui.Workspace)
    workspace.selector.setCurrentIndex(1 if tab < 2 else 0)
    if tab == 0:
        window.dictation_details.setCurrentIndex(2)
    elif tab == 1:
        window.meeting_details.setCurrentIndex(1)
        window.meeting_advanced.setCurrentIndex(3)
    else:
        window.file_options.setCurrentIndex(1)
    for _ in range(4):
        QApplication.processEvents()
    return getattr(window, target)


@pytest.mark.parametrize("tab,target", [(0, "history_limit"), (1, "meeting_prompt"), (2, "file_cleanup_prompt")])
@pytest.mark.parametrize("size", [(1040, 760), (520, 400)])
def test_every_advanced_editor_is_reachable_at_large_and_small_sizes(window, tab, target, size):
    window.resize(*size)
    window.show()
    editor = select_editor(window, tab, target)
    # Scroll only inside the selected panel at small screen heights.
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
    if size == (1040, 760):
        assert scroll.verticalScrollBar().maximum() == 0


def test_language_rebuild_preserves_selected_detail_pages(window):
    window.dictation_details.setCurrentIndex(0)
    window.dictation_advanced.setCurrentIndex(2)
    window.meeting_details.setCurrentIndex(1)
    window.meeting_advanced.setCurrentIndex(3)
    window.file_options.setCurrentIndex(1)
    view = settings_ui.WindowView(window)
    fresh = settings_ui.SettingsWindow(window.conf, "wordarc toggle")
    try:
        view.apply(fresh)
        assert fresh.dictation_details.currentIndex() == 0
        assert fresh.dictation_advanced.currentIndex() == 2
        assert fresh.meeting_details.currentIndex() == 1
        assert fresh.meeting_advanced.currentIndex() == 3
        assert fresh.file_options.currentIndex() == 1
    finally:
        fresh.close()


@pytest.mark.parametrize("size", [(1040, 760), (920, 700)])
@pytest.mark.parametrize("language", ["tr", "en"])
def test_selected_desktop_forms_fit_without_page_scrolling(window, size, language):
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
            for tab, name in enumerate(("dictation_details", "meeting_details", "file_options", "settings_section_stack")):
                fresh.tabs.setCurrentIndex(tab)
                panels = getattr(fresh, name)
                for index in range(panels.count()):
                    panels.setCurrentIndex(index)
                    inner = fresh.dictation_advanced if tab == 0 and index == 0 else fresh.meeting_advanced if tab == 1 and index == 1 else None
                    for detail in range(inner.count() if inner else 1):
                        if inner:
                            inner.setCurrentIndex(detail)
                        for _ in range(4):
                            QApplication.processEvents()
                        for scroll in fresh.tabs.widget(tab).findChildren(settings_ui.QScrollArea):
                            if scroll.isVisibleTo(fresh):
                                if scroll.verticalScrollBar().maximum():
                                    fresh.grab().save(f"build/layout-failure-{language}-{size[0]}.png")
                                assert scroll.verticalScrollBar().maximum() == 0, (size, language, mode, tab, index, detail)
                                assert scroll.horizontalScrollBar().maximum() == 0
            fresh.tabs.setCurrentIndex(3)
            fresh.settings_section_stack.setCurrentIndex(0)
            fresh.transcribe_engine.setCurrentIndex(fresh.transcribe_engine.findData("local"))
            fresh.model_setup.setCurrentIndex(0)
            for _ in range(4):
                QApplication.processEvents()
            for scroll in fresh.tabs.widget(
                    fresh._tab_index["settings"]).findChildren(settings_ui.QScrollArea):
                if scroll.isVisibleTo(fresh):
                    assert scroll.verticalScrollBar().maximum() == 0, (size, language, "local")
    finally:
        fresh.close()
        window.conf["ui_language"] = old_ui
        i18n.set_language(old_language)
        QApplication.instance().setStyleSheet(old_style)
