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
    controller.start.assert_called_once_with(from_window=True)
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
    def select():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QDialog)
        dialog.findChild(QLineEdit).setText("Second")
        rows = dialog.findChild(QListWidget)
        assert rows.item(0).isHidden()
        assert not rows.item(1).isHidden()
        rows.itemDoubleClicked.emit(rows.item(1))
    QTimer.singleShot(0, select)
    combo.showPopup()
    assert combo.currentData() == "two"


def test_workspace_reflows_and_settings_remain_accessible(window):
    window.show()
    window.resize(1040, 760)
    QApplication.processEvents()
    workspace = window.tabs.widget(0).findChild(settings_ui.Workspace)
    assert workspace.columns.direction() == settings_ui.QBoxLayout.Direction.LeftToRight
    window.resize(520, 400)
    QApplication.processEvents()
    assert workspace.columns.direction() == settings_ui.QBoxLayout.Direction.TopToBottom
    window.tabs.setCurrentIndex(3)
    QApplication.processEvents()
    assert window.settings_section_selector.isVisibleTo(window)
    window.settings_section_selector.setCurrentIndex(4)
    assert window.settings_section_stack.currentIndex() == 4


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
    window.tabs.widget(2).findChild(settings_ui.Disclosure).toggle.click()
    assert window.file_cleanup_prompt.isVisibleTo(window)


def test_every_combo_opens_the_search_picker(window):
    # Includes short lists, editable models, languages and the narrow menu.
    combos = window.findChildren(settings_ui.QComboBox)
    assert len(combos) >= 15
    for combo in combos:
        assert isinstance(combo, settings_ui.FitsOnScreenCombo)
        with mock.patch.object(combo, "_search_picker") as picker:
            combo.showPopup()
        picker.assert_called_once()


def test_editable_model_text_is_a_picker_target(window):
    from PyQt6.QtTest import QTest
    window.show()
    window.navigate_to("settings")
    QApplication.processEvents()
    with mock.patch.object(window.transcribe_model, "_search_picker") as picker:
        QTest.mouseClick(window.transcribe_model.lineEdit(), Qt.MouseButton.LeftButton)
    picker.assert_called_once()


def test_expanded_dictation_can_scroll_to_its_last_control(window):
    window.show()
    window.resize(920, 700)
    window.navigate_to("dictation")
    QApplication.processEvents()
    disclosure = window.tabs.widget(0).findChild(settings_ui.Disclosure)
    disclosure.toggle.click()
    for _ in range(3):
        QApplication.processEvents()
    scroll = window.tabs.widget(0).findChild(settings_ui.QScrollArea)
    scroll.ensureWidgetVisible(window.history_limit)
    QApplication.processEvents()
    rect = window.history_limit.rect()
    bottom = window.history_limit.mapTo(scroll.viewport(), rect.bottomLeft())
    top = window.history_limit.mapTo(scroll.viewport(), rect.topLeft())
    assert top.y() >= 0
    assert bottom.y() <= scroll.viewport().height()
    assert scroll.verticalScrollBar().maximum() > 0


@pytest.mark.parametrize("tab,target", [(0, "history_limit"), (1, "meeting_prompt"), (2, "file_cleanup_prompt")])
@pytest.mark.parametrize("size", [(1040, 760), (520, 400)])
def test_every_advanced_editor_is_reachable_at_large_and_small_sizes(window, tab, target, size):
    window.show()
    window.resize(*size)
    window.tabs.setCurrentIndex(tab)
    QApplication.processEvents()
    disclosure = window.tabs.widget(tab).findChild(settings_ui.Disclosure)
    disclosure.toggle.click()
    for _ in range(3):
        QApplication.processEvents()
    scroll = window.tabs.widget(tab).findChild(settings_ui.QScrollArea)
    editor = getattr(window, target)
    center = editor.mapTo(scroll.widget(), editor.rect().center())
    scroll.ensureVisible(center.x(), center.y(), 0, 0)
    QApplication.processEvents()
    visible = editor.mapTo(scroll.viewport(), editor.rect().center())
    assert 0 <= visible.y() <= scroll.viewport().height()
    assert editor.isVisibleTo(window)
    disclosure.toggle.click()
    for _ in range(3):
        QApplication.processEvents()
    assert not editor.isVisibleTo(window)
