import unittest
from unittest import mock
import hotkey

class TestParseShortcut(unittest.TestCase):
    def test_ctrl_space(self):
        mods, vk = hotkey.parse_shortcut("Ctrl+Space")
        self.assertTrue(mods & hotkey.MOD_CONTROL)
        self.assertTrue(mods & hotkey.MOD_NOREPEAT)
        self.assertEqual(vk, 0x20)
    def test_case_insensitive(self):
        m1, v1 = hotkey.parse_shortcut("ctrl+space")
        m2, v2 = hotkey.parse_shortcut("CTRL+SPACE")
        self.assertEqual((m1, v1), (m2, v2))
    def test_escape_without_modifier(self):
        mods, vk = hotkey.parse_shortcut("Escape")
        self.assertTrue(mods & hotkey.MOD_NOREPEAT)
        self.assertEqual(vk, hotkey.KEYS["escape"])
    def test_letter(self):
        mods, vk = hotkey.parse_shortcut("Ctrl+V")
        self.assertEqual(vk, ord("V"))
        self.assertTrue(mods & hotkey.MOD_CONTROL)
    def test_digit(self):
        mods, vk = hotkey.parse_shortcut("Alt+1")
        self.assertEqual(vk, ord("1"))
        self.assertTrue(mods & hotkey.MOD_ALT)
    def test_super(self):
        mods, vk = hotkey.parse_shortcut("Meta+P")
        self.assertTrue(mods & hotkey.MOD_WIN)
    def test_meta_alt_super(self):
        mods, vk = hotkey.parse_shortcut("Ctrl+Alt+Shift+F1")
        self.assertTrue(mods & hotkey.MOD_CONTROL)
        self.assertTrue(mods & hotkey.MOD_ALT)
        self.assertTrue(mods & hotkey.MOD_SHIFT)
        self.assertEqual(vk, hotkey.KEYS["f1"])
    def test_empty(self):
        self.assertEqual(hotkey.parse_shortcut(""), (0, 0))
        self.assertEqual(hotkey.parse_shortcut("   "), (0, 0))
    def test_unparsable(self):
        self.assertEqual(hotkey.parse_shortcut("ctrl+"), (0, 0))
        self.assertEqual(hotkey.parse_shortcut("banana"), (0, 0))
        self.assertEqual(hotkey.parse_shortcut("Ctrl+A+B"), (0, 0))
    def test_ctrl_and_control_alias(self):
        m1, _ = hotkey.parse_shortcut("control+V")
        m2, _ = hotkey.parse_shortcut("ctrl+V")
        self.assertEqual(m1, m2)
    def test_printscreen_aliases(self):
        for name in ("PrintScreen", "print", "Prtsc", "snapshot"):
            mods, vk = hotkey.parse_shortcut(name)
            self.assertEqual(vk, hotkey.KEYS["printscreen"])
            self.assertTrue(mods & hotkey.MOD_NOREPEAT)
    def test_qt_special_key_names(self):
        self.assertEqual(hotkey.parse_shortcut("Ctrl+Del")[1], 0x2E)
        self.assertEqual(hotkey.parse_shortcut("Ctrl+Ins")[1], 0x2D)
        self.assertEqual(hotkey.parse_shortcut("Ctrl+Alt+Pause")[1], 0x13)
        self.assertEqual(hotkey.parse_shortcut("Ctrl+NumLock")[1], 0x90)
        self.assertEqual(hotkey.parse_shortcut("Ctrl+ScrollLock")[1], 0x91)
    def test_media_and_extended_function_keys(self):
        for name, expected in (("Pause", 0x13), ("Volume Up", 0xAF),
                               ("Media Next", 0xB0), ("F24", 0x87),
                               ("NumPlus", 0x6B), ("Num9", 0x69)):
            self.assertEqual(hotkey.parse_shortcut(name)[1], expected)

    def test_plus_key_is_not_discarded_as_a_separator(self):
        with mock.patch.object(hotkey, "_char_vk", return_value=0xBB) as resolve:
            self.assertEqual(hotkey.parse_shortcut("Ctrl+Shift++")[1], 0xBB)
        resolve.assert_called_once_with("+", hotkey.MOD_CONTROL | hotkey.MOD_SHIFT)
    def test_non_ascii_letter_resolves_through_layout(self):
        import sys
        if not sys.platform.startswith("win"):
            self.skipTest("VkKeyScanW is Windows-only")
        mods, vk = hotkey.parse_shortcut("Ctrl+Alt+ş")
        self.assertTrue(vk and vk <= 0xFF)
    def test_more_than_one_character_is_rejected(self):
        self.assertEqual(hotkey.parse_shortcut("Ctrl+;+V"), (0, 0))

class TestAlias(unittest.TestCase):
    def test_evdev_alias_exists(self):
        self.assertTrue(hasattr(hotkey, "EvdevHotkey"))
        self.assertIs(hotkey.EvdevHotkey, hotkey.WindowsHotkey)


class TestRegistration(unittest.TestCase):
    def test_all_conflicts_leave_listener_stopped(self):
        widget = mock.Mock(hwnd=1)
        listener = hotkey.WindowsHotkey()
        with mock.patch.object(hotkey, "_HotkeyWindow", return_value=widget), \
             mock.patch.object(hotkey.QCoreApplication, "processEvents"), \
             mock.patch.object(hotkey.user32, "RegisterHotKey", return_value=0):
            self.assertFalse(listener.start({"toggle": "Ctrl+Space"}))
        self.assertFalse(listener.running)
        widget.close.assert_called_once()

if __name__ == "__main__":
    unittest.main()
