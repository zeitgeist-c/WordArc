import unittest, os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ast
import pathlib

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

# Both languages share these on purpose: product names, model names and the
# format-only strings that carry other text.
UNTRANSLATED = {
    "Gemini", "Model", "Google Gemini", "Claude Code", "Codex",
    "{action}: {preview}", "{name}: {preview}",
    # Model names, the same in both languages.
    "Whisper base", "Whisper small", "Whisper large-v3-turbo",
    # Compute device names, the same in both languages.
    "Nvidia GPU", "CPU",
}

SOURCE_FILES = ("settings_ui.py", "screenshot_capture.py", "wordarc.py", "meeting.py", "worker.py",
                "audio.py", "filetranscribe.py", "paste.py", "api.py",
                "localspeech.py")

# Helpers that run their string arguments through t() themselves, so the
# literal at the call site IS the translation key: {name: argument indexes}
WRAPPING_HELPERS = {
    "_section_card": (0, 1),
    "_label_row": (0,),
    "_wrap_page": (1,),
    "_prompt_gemini_key": (0,),
    "_key_dialog": (0,),
}


def _root():
    return pathlib.Path(__file__).resolve().parent.parent


def _call_name(node):
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _visible_literals(path):
    """(line, text) for every literal that reaches t() somewhere."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name == "t":
            indexes = (0,)
        elif name in WRAPPING_HELPERS:
            indexes = WRAPPING_HELPERS[name]
        else:
            continue
        for index in indexes:
            if len(node.args) > index:
                arg = node.args[index]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    found.append((node.lineno, arg.value))
    return found


class TestTranslationCoverage(unittest.TestCase):
    def test_every_visible_literal_has_a_turkish_entry(self):
        missing = []
        for name in SOURCE_FILES:
            for line, text in _visible_literals(_root() / name):
                if text in UNTRANSLATED or text in i18n.TR:
                    continue
                missing.append(f"{name}:{line}: {text!r}")
        self.assertFalse(missing, "TR karsiligi yok:\n" + "\n".join(missing))

    def test_no_plain_literal_reaches_a_message_box(self):
        plain = []
        for name in SOURCE_FILES:
            tree = ast.parse((_root() / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if _call_name(node) not in ("warn_box", "info_box", "confirm_box"):
                    continue
                for index in (1, 2):
                    if len(node.args) > index:
                        arg = node.args[index]
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            plain.append(f"{name}:{node.lineno}: {arg.value!r}")
        self.assertFalse(plain, "t() icinden gecmeyen kutu metni:\n" + "\n".join(plain))

    def test_turkish_table_has_no_untranslated_duplicates(self):
        leftovers = [key for key, value in i18n.TR.items()
                     if key == value and key not in UNTRANSLATED]
        self.assertFalse(leftovers, f"cevrilmemis TR kaydi: {leftovers}")

    def test_tab_titles_and_descriptions_are_translated(self):
        """The specs list is the one place a literal reaches t() unseen."""
        tree = ast.parse((_root() / "settings_ui.py").read_text(encoding="utf-8"))
        specs = None
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "specs"
                            for target in node.targets)):
                specs = node.value
        self.assertIsNotNone(specs, "specs listesi bulunamadi")
        self.assertEqual(len(specs.elts), 5)
        for element in specs.elts:
            for index in (2, 3):
                text = element.elts[index]
                self.assertIsInstance(text, ast.Constant)
                self.assertIn(text.value, i18n.TR, text.value)

    def test_combo_label_lists_are_translated(self):
        import settings_ui
        for label, _value in (settings_ui.UI_LANGUAGES + settings_ui.LANGUAGES
                              + settings_ui.REASONING_LEVELS):
            self.assertIn(label, i18n.TR)
        for corner in settings_ui.CORNERS:
            self.assertIn(corner, i18n.TR)


if __name__ == "__main__":
    unittest.main()
