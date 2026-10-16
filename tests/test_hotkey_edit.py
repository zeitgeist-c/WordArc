import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import hotkey
from i18n import t
from settings_ui import HotkeyEdit


class TestHotkeyEdit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make(self, **kwargs):
        edit = HotkeyEdit(**kwargs)
        edit.show()
        self.app.processEvents()
        self.addCleanup(edit.close)
        self.addCleanup(edit.deleteLater)
        return edit

    def listen(self, edit):
        """A click on the field starts the capture (game-style)."""
        QTest.mouseClick(edit.line, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        return edit._listening

    # ---- the listening model --------------------------------------------

    def test_clicking_starts_listening(self):
        edit = self.make()
        started = []
        edit.capture_started.connect(lambda: started.append(True))
        self.assertTrue(self.listen(edit))
        self.assertEqual(started, [True])
        self.assertEqual(edit.line.placeholderText(), t("Press the keys now…"))
        self.assertTrue(edit.line.isReadOnly())

    def test_leaving_the_field_finishes_the_capture(self):
        edit = self.make()
        finished = []
        edit.capture_finished.connect(lambda: finished.append(True))
        self.listen(edit)
        edit.line.clearFocus()
        self.app.processEvents()
        self.assertEqual(finished, [True])
        self.assertEqual(edit.line.placeholderText(),
                         t("Press shortcut keys…"))

    def test_pressing_while_listening_assigns_and_asks_for_save(self):
        edit = self.make()
        self.listen(edit)
        QTest.keyClick(edit.line, Qt.Key.Key_S,
                       Qt.KeyboardModifier.ControlModifier
                       | Qt.KeyboardModifier.AltModifier)
        self.assertEqual(edit.currentText(), "Ctrl+Alt+S")
        self.assertNotEqual(hotkey.parse_shortcut(edit.currentText()), (0, 0))
        self.assertTrue(edit.hint.isVisible())
        self.assertEqual(edit.hint.text(), t("Press Save to apply."))

    def test_plain_letter_assigns_once_and_stops_listening(self):
        edit = self.make()
        self.listen(edit)
        QTest.keyClicks(edit.line, "abc")
        self.assertEqual(edit.currentText(), "A")
        self.assertFalse(edit._listening)

    def test_pause_and_navigation_keys_assign_without_modifiers(self):
        for key, expected in ((Qt.Key.Key_Pause, "Pause"),
                              (Qt.Key.Key_Home, "Home"),
                              (Qt.Key.Key_Space, "Space"),
                              (Qt.Key.Key_Tab, "Tab"),
                              (Qt.Key.Key_Return, "Return"),
                              (Qt.Key.Key_F24, "F24")):
            with self.subTest(key=expected):
                edit = self.make()
                finished = []
                edit.capture_finished.connect(lambda: finished.append(True))
                self.listen(edit)
                QTest.keyClick(edit.line, key)
                self.assertEqual(edit.currentText(), expected)
                self.assertFalse(edit._listening)
                self.assertEqual(finished, [True])

    def test_focus_loss_without_assignment_restores_original_value(self):
        edit = self.make()
        edit.setCurrentText("Pause")
        self.listen(edit)
        self.assertEqual(edit.line.text(), "")
        edit.line.clearFocus()
        self.app.processEvents()
        self.assertEqual(edit.currentText(), "Pause")

    def test_holding_space_does_not_restart_capture_after_assignment(self):
        edit = self.make()
        self.listen(edit)
        QTest.keyClick(edit.line, Qt.Key.Key_Space)
        QApplication.sendEvent(edit.line, QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Space,
            Qt.KeyboardModifier.NoModifier, " ", True))
        self.assertEqual(edit.currentText(), "Space")
        self.assertFalse(edit._listening)

    def test_keypad_digit_preserves_its_distinct_virtual_key(self):
        edit = self.make()
        self.listen(edit)
        QTest.keyClick(edit.line, Qt.Key.Key_1,
                       Qt.KeyboardModifier.KeypadModifier)
        self.assertEqual(edit.currentText(), "Num1")
        self.assertEqual(hotkey.parse_shortcut(edit.currentText())[1], 0x61)

    # ---- keys -----------------------------------------------------------

    def test_print_screen_assigns_without_modifiers(self):
        edit = self.make()
        self.listen(edit)
        QTest.keyClick(edit.line, Qt.Key.Key_Print)
        self.assertEqual(edit.currentText(), "PrintScreen")
        self.assertNotEqual(hotkey.parse_shortcut(edit.currentText()), (0, 0))

    def test_print_screen_keeps_modifiers(self):
        edit = self.make()
        self.listen(edit)
        QTest.keyClick(edit.line, Qt.Key.Key_Print,
                       Qt.KeyboardModifier.ControlModifier
                       | Qt.KeyboardModifier.AltModifier)
        self.assertEqual(edit.currentText(), "Ctrl+Alt+PrintScreen")

    def test_function_key_assigns_without_modifiers(self):
        edit = self.make()
        self.listen(edit)
        QTest.keyClick(edit.line, Qt.Key.Key_F9)
        self.assertEqual(edit.currentText(), "F9")

    def test_delete_with_modifiers_assigns(self):
        edit = self.make()
        self.listen(edit)
        QTest.keyClick(edit.line, Qt.Key.Key_Delete,
                       Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(edit.currentText(), "Ctrl+Del")

    def test_reserved_combination_shows_a_hint(self):
        edit = self.make()
        self.listen(edit)
        QTest.keyClick(edit.line, Qt.Key.Key_Delete,
                       Qt.KeyboardModifier.ControlModifier
                       | Qt.KeyboardModifier.AltModifier)
        self.assertEqual(edit.currentText(), "")
        self.assertTrue(edit.hint.isVisible())
        self.assertIn("Windows", edit.hint.text())

    def test_media_key_assigns(self):
        edit = self.make()
        self.listen(edit)
        QTest.keyClick(edit.line, Qt.Key.Key_VolumeUp,
                       Qt.KeyboardModifier.ControlModifier
                       | Qt.KeyboardModifier.AltModifier)
        self.assertEqual(edit.currentText(), "Ctrl+Alt+Volume Up")
        self.assertEqual(hotkey.parse_shortcut(edit.currentText())[1], 0xAF)
        self.assertFalse(edit._listening)

    def test_shortcut_override_is_captured_and_accepted(self):
        edit = self.make()
        self.listen(edit)
        event = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_B,
                          Qt.KeyboardModifier.ControlModifier
                          | Qt.KeyboardModifier.AltModifier)
        QApplication.sendEvent(edit.line, event)
        self.assertEqual(edit.currentText(), "")
        self.assertTrue(event.isAccepted())
        QApplication.sendEvent(edit.line, QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_B,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier))
        self.assertEqual(edit.currentText(), "Ctrl+Alt+B")
        self.assertFalse(edit._listening)

    # ---- escape, clearing, round trips ----------------------------------

    def test_escape_puts_back_the_value_from_before_listening(self):
        edit = self.make()
        edit.setCurrentText("Meta+M")
        self.listen(edit)
        QTest.keyClick(edit.line, Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertEqual(edit.currentText(), "Meta+M")
        self.assertFalse(edit._listening)

    def test_backspace_clears_the_value(self):
        edit = self.make()
        edit.setCurrentText("Meta+M")
        self.listen(edit)
        QTest.keyClick(edit.line, Qt.Key.Key_Backspace)
        self.assertEqual(edit.currentText(), "")
        self.assertEqual(edit.hint.text(), t("Press Save to apply."))

    def test_typed_text_round_trips(self):
        edit = self.make()
        edit.setCurrentText("Meta+M")
        self.assertEqual(edit.currentText().strip(), "Meta+M")

    def test_clear_empties(self):
        edit = self.make()
        edit.setCurrentText("Ctrl+Alt+S")
        edit.clear()
        self.assertEqual(edit.currentText(), "")


if __name__ == "__main__":
    unittest.main()
