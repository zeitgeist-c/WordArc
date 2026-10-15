import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import hotkey
from settings_ui import HotkeyEdit


class TestHotkeyEdit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make(self, **kwargs):
        edit = HotkeyEdit(**kwargs)
        edit.show()
        self.addCleanup(edit.close)
        self.addCleanup(edit.deleteLater)
        return edit

    def test_pressing_combo_assigns_portable_text(self):
        edit = self.make()
        QTest.keyClick(edit.line, Qt.Key.Key_S,
                       Qt.KeyboardModifier.ControlModifier
                       | Qt.KeyboardModifier.AltModifier)
        self.assertEqual(edit.currentText(), "Ctrl+Alt+S")
        self.assertNotEqual(hotkey.parse_shortcut(edit.currentText()), (0, 0))

    def test_shift_letter_is_not_hijacked_while_typing(self):
        edit = self.make()
        QTest.keyClicks(edit.line, "A")
        self.assertEqual(edit.currentText(), "A")

    def test_function_key_assigns_without_modifiers(self):
        edit = self.make()
        QTest.keyClick(edit.line, Qt.Key.Key_F9)
        self.assertEqual(edit.currentText(), "F9")

    def test_escape_keeps_previous_value(self):
        edit = self.make()
        edit.setCurrentText("Ctrl+Alt+S")
        QTest.keyClick(edit.line, Qt.Key.Key_Escape)
        self.assertEqual(edit.currentText(), "Ctrl+Alt+S")

    def test_clear_button_empties(self):
        edit = self.make()
        edit.setCurrentText("Ctrl+Alt+S")
        QTest.mouseClick(edit.clear_button, Qt.MouseButton.LeftButton)
        self.assertEqual(edit.currentText(), "")

    def test_typed_text_round_trips(self):
        edit = self.make()
        edit.setCurrentText("Meta+M")
        self.assertEqual(edit.currentText().strip(), "Meta+M")


if __name__ == "__main__":
    unittest.main()
