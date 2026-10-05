"""A deleted summary label must not break the settings update.

The log once showed `RuntimeError: wrapped C/C++ object of type QLabel has
been deleted` out of `_refresh_shared_ai_summaries`: a language change swaps
the pages out from under the label list, and the next update died on the
stale entry.
"""
from unittest import mock

from settings_ui import SettingsWindow


def test_deleted_summary_label_is_dropped_silently():
    live = mock.Mock()
    dead = mock.Mock()
    dead.setText.side_effect = RuntimeError(
        "wrapped C/C++ object of type QLabel has been deleted")
    window = mock.Mock()
    window._shared_ai_labels = [live, dead]
    window._engine_summary.return_value = "Whisper large-v3-turbo"
    window.transcribe_model.currentText.return_value = "gemini-x"
    window.cleanup_model.currentText.return_value = "gemini-y"

    SettingsWindow._refresh_shared_ai_summaries(window)

    live.setText.assert_called_once()
    assert window._shared_ai_labels == [live]
