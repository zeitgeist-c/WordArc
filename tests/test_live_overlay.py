"""Tests for Overlay.show_live_text (live interim display)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

import overlay

_QT_APP = QApplication.instance() or QApplication([])


def test_live_text_keeps_recording_state_and_shows_tail():
    box = overlay.Overlay()
    box.show_recording()
    spoken = "merhaba dünya, bu uzun bir ara metindir " * 10
    box.show_live_text(spoken)
    assert box.state == "recording"
    assert box.message
    assert len(box.message) <= 120
    assert spoken.strip().endswith(box.message)


def test_live_text_empty_clears_message():
    box = overlay.Overlay()
    box.show_recording()
    box.show_live_text("merhaba")
    assert box.message
    box.show_live_text("")
    assert box.message == ""
    assert box.state == "recording"


def test_live_text_short_message_shown_whole():
    box = overlay.Overlay()
    box.show_recording()
    box.show_live_text("merhaba")
    assert box.message == "merhaba"
