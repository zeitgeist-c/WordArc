import unittest
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
    def test_ctrl_and_control_alias(self):
        m1, _ = hotkey.parse_shortcut("control+V")
        m2, _ = hotkey.parse_shortcut("ctrl+V")
        self.assertEqual(m1, m2)

class TestAlias(unittest.TestCase):
    def test_evdev_alias_exists(self):
        self.assertTrue(hasattr(hotkey, "EvdevHotkey"))
        self.assertIs(hotkey.EvdevHotkey, hotkey.WindowsHotkey)

if __name__ == "__main__":
    unittest.main()
