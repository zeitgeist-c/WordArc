import unittest, os
import i18n

class TestI18n(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("LC_ALL", "LC_MESSAGES", "LANG")}
        os.environ.pop("LC_ALL", None)
        os.environ.pop("LC_MESSAGES", None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

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
        from pathlib import Path
        src = Path(__file__).resolve().parent.parent.joinpath("i18n.py").read_text(encoding="utf-8")
        for banned in ("pw-record", "wl-copy", "wl-paste", "ydotool", "ydotoold",
                       "/dev/input", "kglobalshortcutsrc", "KDE shortcut is live"):
            self.assertNotIn(banned, src, f"Linux-specific string remains: {banned}")

if __name__ == "__main__":
    unittest.main()