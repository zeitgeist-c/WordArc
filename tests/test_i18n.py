import unittest, os
import i18n

class TestI18n(unittest.TestCase):
    def test_resolve_auto_en(self):
        os.environ["LANG"] = "C"
        self.assertEqual(i18n.resolve("auto"), "en")
    def test_resolve_auto_tr(self):
        os.environ["LANG"] = "tr_TR.UTF-8"
        self.assertEqual(i18n.resolve("auto"), "tr")
    def test_t_en_passthrough(self):
        i18n.set_language("en")
        self.assertEqual(i18n.t("Start recording"), "Start recording")
    def test_t_tr_translates(self):
        i18n.set_language("tr")
        self.assertEqual(i18n.t("Start recording"), "Kaydı başlat")
    def test_t_formats_kwargs(self):
        i18n.set_language("en")
        self.assertEqual(i18n.t("{action}: {preview}", action="Pasted", preview="hi"), "Pasted: hi")
    def test_name_dative_tr(self):
        i18n.set_language("tr")
        self.assertEqual(i18n.name("Claude", "dative"), "Claude'a")
    def test_name_en_passthrough(self):
        i18n.set_language("en")
        self.assertEqual(i18n.name("Claude", "dative"), "Claude")
    def test_no_linux_strings_remain(self):
        i18n.set_language("en")
        src = open("i18n.py", encoding="utf-8").read()
        for banned in ("pw-record", "wl-copy", "wl-paste", "ydotool", "kdotoold",
                       "/dev/input", "kglobalshortcutsrc", "KDE shortcut is live"):
            self.assertNotIn(banned, src, f"Linux-specific string remains: {banned}")

if __name__ == "__main__":
    unittest.main()