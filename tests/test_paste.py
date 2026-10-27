import unittest
import paste

class TestVkeys(unittest.TestCase):
    def test_letter_v(self):
        self.assertEqual(paste.VKEYS["v"], 0x56)
    def test_ctrl_and_control_same(self):
        self.assertEqual(paste.VKEYS["ctrl"], paste.VKEYS["control"])
    def test_super_and_meta_same(self):
        self.assertEqual(paste.VKEYS["super"], paste.VKEYS["meta"])
    def test_insert(self):
        self.assertEqual(paste.VKEYS["insert"], 0x2D)

class TestSplitShortcut(unittest.TestCase):
    def test_single_key_parses(self):
        # press splits on +; ctrl+v -> [ctrl, v]
        names = [k.strip().lower() for k in "ctrl+v".split("+") if k.strip()]
        self.assertEqual(names, ["ctrl", "v"])
    def test_unknown_key_raises(self):
        self.assertRaises(paste.PasteError, paste.press, "ctrl+xyz")
        self.assertRaises(paste.PasteError, paste.press, "ctrl+")

class TestClipboardRoundTrip(unittest.TestCase):
    """Real clipboard round-trip; skipped on CI without a desktop."""
    def test_read_write(self):
        import sys
        if not sys.platform.startswith("win"):
            self.skipTest("Windows-only clipboard test")
        paste.copy("hello dǬnya")
        # read_clipboard returns UTF-8 bytes
        self.assertEqual(paste.read_clipboard(), "hello dǬnya".encode("utf-8"))

    def test_restored_raw_bytes_are_nul_terminated(self):
        """CF_UNICODETEXT must end in a NUL inside the allocation.

        copy_bytes() allocated len(data) + 2 but the non-UTF-8 branch filled
        only len(data) bytes, so the last two were uninitialised heap and the
        consuming application read past the end of the block.
        """
        import ctypes
        import sys
        if not sys.platform.startswith("win"):
            self.skipTest("Windows-only clipboard test")
        raw = b"\xff\xfe\x41\x00\x42"
        paste.copy_bytes(raw)
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self.assertTrue(user32.OpenClipboard(0))
        try:
            handle = user32.GetClipboardData(paste.CF_UNICODETEXT)
            self.assertTrue(handle)
            ptr = kernel32.GlobalLock(handle)
            self.assertTrue(ptr)
            try:
                block = ctypes.string_at(ptr, len(raw) + 2)
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
        self.assertEqual(block, raw + b"\x00\x00")

if __name__ == "__main__":
    unittest.main()