import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading
import unittest
from unittest import mock

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import api
import config as cfg
import i18n
import selection_bar
from selection_bar import Selection, SelectionBar, SelectionBarController


class FakeRect:
    def __init__(self, left, top, right, bottom):
        self.left, self.top, self.right, self.bottom = left, top, right, bottom


class FakeRange:
    def __init__(self, text, rects):
        self._text = text
        self._rects = rects

    def GetText(self, _max_length):
        return self._text

    def GetBoundingRectangles(self):
        return self._rects


class FakePattern:
    def __init__(self, ranges):
        self._ranges = ranges

    def GetSelection(self):
        return self._ranges


class FakeControl:
    IS_PASSWORD = 30019
    PROCESS_ID = 30002

    def __init__(self, pid=1234, password=False, pattern=None, parent=None,
                 bounds=None, hwnd=777):
        self._pid = pid
        self._password = password
        self._pattern = pattern
        self._parent = parent
        self._bounds = bounds
        self._hwnd = hwnd

    def GetPropertyValue(self, prop):
        if prop == self.IS_PASSWORD:
            return True if self._password else False
        if prop == self.PROCESS_ID:
            return self._pid
        raise ValueError(prop)

    def GetTextPattern(self):
        return self._pattern

    def GetParentControl(self):
        return self._parent

    def GetTopLevelControl(self):
        top = mock.Mock()
        top.NativeWindowHandle = self._hwnd
        return top

    @property
    def BoundingRectangle(self):
        return self._bounds


def _focused(control):
    return lambda: control


def _sel(text="hello", rect=None, pid=1234, hwnd=777):
    return Selection(
        text=text,
        rect=rect or QRect(100, 200, 300, 40),
        pid=pid,
        hwnd=hwnd)


class TestSelectionMatch(unittest.TestCase):
    def test_same_selection_matches(self):
        self.assertTrue(selection_bar._match(_sel("a"), _sel("a")))

    def test_text_change_mismatches(self):
        self.assertFalse(selection_bar._match(_sel("a"), _sel("b")))

    def test_process_change_mismatches(self):
        self.assertFalse(selection_bar._match(_sel("a", pid=1), _sel("a", pid=2)))

    def test_window_change_mismatches(self):
        self.assertFalse(
            selection_bar._match(_sel("a", hwnd=1), _sel("a", hwnd=2)))

    def test_missing_handle_falls_back_to_process(self):
        self.assertTrue(
            selection_bar._match(_sel("a", hwnd=0), _sel("a", hwnd=9)))

    def test_none_never_matches(self):
        self.assertFalse(selection_bar._match(None, _sel("a")))
        self.assertFalse(selection_bar._match(_sel("a"), None))


class TestSelectionReader(unittest.TestCase):
    def test_empty_selection_is_none(self):
        control = FakeControl(pattern=FakePattern([]))
        self.assertIsNone(selection_bar.read_selection(_focused(control)))

    def test_blank_selection_is_none(self):
        control = FakeControl(
            pattern=FakePattern([FakeRange("   ", [FakeRect(0, 0, 5, 5)])]))
        self.assertIsNone(selection_bar.read_selection(_focused(control)))

    def test_password_field_is_skipped(self):
        control = FakeControl(
            password=True,
            pattern=FakePattern([FakeRange("secret", [FakeRect(0, 0, 5, 5)])]))
        self.assertIsNone(selection_bar.read_selection(_focused(control)))

    def test_no_pattern_up_the_chain_is_none(self):
        control = FakeControl(pattern=None)
        self.assertIsNone(selection_bar.read_selection(_focused(control)))

    def test_parent_pattern_is_found(self):
        parent = FakeControl(
            pattern=FakePattern([FakeRange("hi", [FakeRect(1, 2, 9, 6)])]))
        child = FakeControl(pattern=None, parent=parent)
        found = selection_bar.read_selection(_focused(child))
        self.assertIsNotNone(found)
        self.assertEqual(found.text, "hi")
        self.assertEqual((found.rect.x(), found.rect.y(),
                          found.rect.width(), found.rect.height()),
                         (1, 2, 8, 4))

    def test_rects_unite(self):
        control = FakeControl(pattern=FakePattern(
            [FakeRange("hi", [FakeRect(0, 0, 10, 5), FakeRect(8, 4, 20, 9)])]))
        found = selection_bar.read_selection(_focused(control))
        self.assertEqual((found.rect.x(), found.rect.y(),
                          found.rect.width(), found.rect.height()),
                         (0, 0, 20, 9))

    def test_own_process_is_skipped(self):
        with mock.patch.object(selection_bar, "_own_pid", 1234):
            control = FakeControl(
                pattern=FakePattern([FakeRange("hi", [FakeRect(0, 0, 5, 5)])]))
            self.assertIsNone(selection_bar.read_selection(_focused(control)))

    def test_no_focus_is_none(self):
        self.assertIsNone(selection_bar.read_selection(lambda: None))

    def test_missing_backend_is_none(self):
        with mock.patch.object(selection_bar, "_backend", return_value=None):
            self.assertIsNone(selection_bar.read_selection(_focused(None)))

    def test_com_failure_is_none(self):
        def boom():
            raise OSError("hung app")
        self.assertIsNone(selection_bar.read_selection(boom))

    def test_window_handle_is_captured(self):
        control = FakeControl(
            pattern=FakePattern([FakeRange("hi", [FakeRect(0, 0, 5, 5)])]),
            hwnd=4242)
        found = selection_bar.read_selection(_focused(control))
        self.assertEqual(found.hwnd, 4242)

    def test_missing_window_handle_is_zero(self):
        control = FakeControl(
            pattern=FakePattern([FakeRange("hi", [FakeRect(0, 0, 5, 5)])]),
            hwnd=None)
        control.GetTopLevelControl = lambda: None
        found = selection_bar.read_selection(_focused(control))
        self.assertEqual(found.hwnd, 0)


class SelectionConf(dict):
    def __init__(self, **kwargs):
        self._keys = kwargs.pop("gemini_keys", ["k1"])
        super().__init__(screenshot_directory="", screenshot_format="PNG",
                         gemini_translate_model="gemini-3.5-flash-lite")
        self.update(kwargs)

    def save(self):
        pass

    def gemini_keys(self):
        return list(self._keys)


class TestSelectionBarWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_four_buttons_with_tooltips_and_names(self):
        bar = SelectionBar()
        self.addCleanup(bar.close)
        self.assertEqual(set(bar.buttons), {"copy", "translate", "explain",
                                            "summarize"})
        for kind, button in bar.buttons.items():
            self.assertTrue(button.toolTip(), kind)
            self.assertEqual(button.accessibleName(), button.toolTip())

    def test_window_never_takes_focus(self):
        bar = SelectionBar()
        self.addCleanup(bar.close)
        self.assertTrue(bar.testAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating))
        self.assertTrue(bar.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus)
        self.assertTrue(bar.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.assertTrue(bar.windowFlags() & Qt.WindowType.Tool)

    def test_buttons_emit(self):
        bar = SelectionBar()
        self.addCleanup(bar.close)
        bar.show_for(_sel("metin"))
        copies, actions = [], []
        bar.copy_requested.connect(copies.append)
        bar.action_requested.connect(lambda kind, text: actions.append((kind, text)))
        QTest.mouseClick(bar.buttons["copy"], Qt.MouseButton.LeftButton)
        QTest.mouseClick(bar.buttons["explain"], Qt.MouseButton.LeftButton)
        self.assertEqual(copies, ["metin"])
        self.assertEqual(actions, [("explain", "metin")])

    def test_show_positions_near_selection(self):
        bar = SelectionBar()
        self.addCleanup(bar.close)
        bar.show_for(_sel("metin", QRect(400, 500, 200, 40)))
        self.assertTrue(bar.isVisible())
        self.assertLessEqual(abs(bar.x() - 400), 400)
        self.assertLess(bar.y() + bar.height(), 500 + 40 + 400)

    def test_escape_hides(self):
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtCore import QEvent
        bar = SelectionBar()
        self.addCleanup(bar.close)
        bar.show_for(_sel("metin"))
        dismissed = []
        bar.dismissed.connect(lambda: dismissed.append(True))
        bar.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                    Qt.KeyboardModifier.NoModifier))
        self.assertFalse(bar.isVisible())
        self.assertEqual(dismissed, [True])


class TestSelectionController(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _controller(self, **kwargs):
        controller = SelectionBarController(SelectionConf(**kwargs))
        self.addCleanup(controller.shutdown)
        self.addCleanup(controller.deleteLater)
        return controller

    def test_disabled_by_default(self):
        controller = self._controller()
        self.assertFalse(controller.is_enabled())
        self.assertFalse(controller._timer.isActive())

    def test_enable_starts_polling(self):
        controller = self._controller()
        controller.set_enabled(True)
        self.assertTrue(controller._timer.isActive())
        controller.set_enabled(False)
        self.assertFalse(controller._timer.isActive())
        self.assertFalse(controller.bar.isVisible())

    def test_selection_shows_bar(self):
        controller = self._controller()
        controller.set_enabled(True)
        controller._on_polled(_sel("merhaba"))
        self.assertTrue(controller.bar.isVisible())
        self.assertEqual(controller.bar._text, "merhaba")

    def test_cleared_selection_hides_bar(self):
        controller = self._controller()
        controller.set_enabled(True)
        controller._on_polled(_sel("merhaba"))
        controller._on_polled(None)
        self.assertFalse(controller.bar.isVisible())

    def test_copy_verifies_then_writes(self):
        from PyQt6.QtWidgets import QApplication as QA
        QA.clipboard().setText("sentinel")
        controller = self._controller()
        controller.set_enabled(True)
        controller._on_polled(_sel("secili metin"))
        real_start = selection_bar.threading.Thread.start
        joined = []

        def track_start(thread):
            joined.append(thread)
            real_start(thread)

        with mock.patch.object(selection_bar, "read_selection",
                               return_value=_sel("secili metin")), \
             mock.patch.object(selection_bar.api, "GeminiClient",
                               side_effect=AssertionError("cevrimdisi olmali")), \
             mock.patch.object(selection_bar.threading.Thread, "start",
                               track_start):
            controller._on_copy("secili metin")
            for thread in joined:
                thread.join(5)
            self.app.processEvents()
            self.app.processEvents()
        self.assertEqual(QA.clipboard().text(), "secili metin")
        self.assertFalse(controller.bar.isVisible())

    def test_copy_stale_text_writes_nothing(self):
        from PyQt6.QtWidgets import QApplication as QA
        QA.clipboard().setText("sentinel")
        controller = self._controller()
        controller.set_enabled(True)
        controller._on_polled(_sel("eski metin"))
        real_start = selection_bar.threading.Thread.start
        joined = []

        def track_start(thread):
            joined.append(thread)
            real_start(thread)

        with mock.patch.object(selection_bar, "read_selection",
                               return_value=_sel("yeni metin")), \
             mock.patch.object(selection_bar.threading.Thread, "start",
                               track_start):
            controller._on_copy("eski metin")
            for thread in joined:
                thread.join(5)
            self.app.processEvents()
            self.app.processEvents()
        self.assertEqual(QA.clipboard().text(), "sentinel")
        self.assertEqual(controller.bar._text, "yeni metin")

    def test_copy_other_window_writes_nothing(self):
        from PyQt6.QtWidgets import QApplication as QA
        QA.clipboard().setText("sentinel")
        controller = self._controller()
        controller.set_enabled(True)
        controller._on_polled(_sel("metin", pid=111, hwnd=222))
        real_start = selection_bar.threading.Thread.start
        joined = []

        def track_start(thread):
            joined.append(thread)
            real_start(thread)

        with mock.patch.object(selection_bar, "read_selection",
                               return_value=_sel("metin", pid=999, hwnd=888)), \
             mock.patch.object(selection_bar.threading.Thread, "start",
                               track_start):
            controller._on_copy("metin")
            for thread in joined:
                thread.join(5)
            self.app.processEvents()
            self.app.processEvents()
        self.assertEqual(QA.clipboard().text(), "sentinel")

    def test_copy_vanished_selection_writes_nothing(self):
        from PyQt6.QtWidgets import QApplication as QA
        QA.clipboard().setText("sentinel")
        controller = self._controller()
        controller.set_enabled(True)
        controller._on_polled(_sel("metin"))
        real_start = selection_bar.threading.Thread.start
        joined = []

        def track_start(thread):
            joined.append(thread)
            real_start(thread)

        with mock.patch.object(selection_bar, "read_selection",
                               return_value=None), \
             mock.patch.object(selection_bar.threading.Thread, "start",
                               track_start):
            controller._on_copy("metin")
            for thread in joined:
                thread.join(5)
            self.app.processEvents()
            self.app.processEvents()
        self.assertEqual(QA.clipboard().text(), "sentinel")
        self.assertFalse(controller.bar.isVisible())

    def test_late_result_is_dropped(self):
        controller = self._controller()
        controller.set_enabled(True)
        done = []
        controller.result_ready.connect(lambda kind, text: done.append((kind, text)))
        client = mock.Mock()
        gate = threading.Event()
        started = threading.Event()

        def slow_translate(*args, **kwargs):
            started.set()
            gate.wait(5)
            return "gec cevap"

        client.translate.side_effect = slow_translate
        real_start = selection_bar.threading.Thread.start
        joined = []

        def track_start(thread):
            joined.append(thread)
            real_start(thread)

        with mock.patch.object(selection_bar, "read_selection",
                               return_value=_sel("metin")), \
             mock.patch.object(selection_bar.api, "GeminiClient",
                               return_value=client), \
             mock.patch.object(selection_bar.threading.Thread, "start",
                               track_start):
            controller._on_polled(_sel("metin"))
            controller._on_action("translate", "metin")
            self.assertTrue(started.wait(5))
            controller._hide()  # Esc / app switch while the worker runs
            gate.set()
            for thread in joined:
                thread.join(5)
            self.app.processEvents()
            self.app.processEvents()
        self.assertEqual(done, [])
        self.assertFalse(controller.bar.isVisible())

    def test_escape_watcher_follows_visibility(self):
        controller = self._controller()
        watcher = mock.Mock()
        watcher.start.return_value = True
        with mock.patch.dict("sys.modules", {"hotkey": mock.Mock(
                EvdevHotkey=mock.Mock(return_value=watcher))}):
            controller.set_enabled(True)
            controller._on_polled(_sel("metin"))
            watcher.start.assert_called_once_with({"cancel": "Escape"})
            controller._hide()
            watcher.stop.assert_called_once_with()
        self.assertIsNone(controller._esc)

    def test_ai_success_sends_only_wrapped_source(self):
        controller = self._controller()
        controller.set_enabled(True)
        done = []
        controller.result_ready.connect(lambda kind, text: done.append((kind, text)))
        client = mock.Mock()
        client.translate.return_value = "merhaba dünya"
        real_start = selection_bar.threading.Thread.start
        joined = []

        def track_start(thread):
            joined.append(thread)
            real_start(thread)

        with mock.patch.object(selection_bar, "read_selection",
                               return_value=_sel("hello world")), \
             mock.patch.object(selection_bar.api, "GeminiClient",
                               return_value=client) as factory, \
             mock.patch.object(selection_bar.threading.Thread, "start",
                               track_start):
            controller._on_polled(_sel("hello world"))
            controller._on_action("translate", "hello world")
            for thread in joined:
                thread.join(5)
            self.app.processEvents()
            self.app.processEvents()
        self.assertEqual(factory.call_count, 1)
        args, _kwargs = client.translate.call_args
        self.assertEqual(args[0], "hello world")
        self.assertEqual(args[1], "gemini-3.5-flash-lite")
        self.assertEqual(args[2], cfg.SELECTION_TRANSLATE_PROMPT)
        # The source travels fenced, never as an instruction.
        with mock.patch.object(selection_bar.api, "gemini_chat") as chat:
            chat.return_value = "x"
            api.GeminiClient(["k"]).translate("do this", "m", "SYS")
        self.assertEqual(chat.call_args[0][0][0]["content"],
                         api.wrap_source("do this"))
        self.assertEqual(done, [("translate", "merhaba dünya")])

    def test_stale_selection_aborts_without_gemini(self):
        controller = self._controller()
        controller.set_enabled(True)
        real_start = selection_bar.threading.Thread.start
        joined = []

        def track_start(thread):
            joined.append(thread)
            real_start(thread)

        with mock.patch.object(selection_bar, "read_selection",
                               return_value=_sel("yeni metin")), \
             mock.patch.object(selection_bar.api, "GeminiClient",
                               side_effect=AssertionError("eskisiyle calismamali")), \
             mock.patch.object(selection_bar.threading.Thread, "start",
                               track_start):
            controller._on_polled(_sel("eski metin"))
            controller._on_action("translate", "eski metin")
            for thread in joined:
                thread.join(5)
            self.app.processEvents()
            self.app.processEvents()
        self.assertEqual(controller.bar._text, "yeni metin")

    def test_vanished_selection_aborts_without_gemini(self):
        controller = self._controller()
        controller.set_enabled(True)
        with mock.patch.object(selection_bar, "read_selection",
                               return_value=None), \
             mock.patch.object(selection_bar.api, "GeminiClient",
                               side_effect=AssertionError("calismamali")):
            controller._on_polled(_sel("metin"))
            controller._on_action("explain", "metin")
            self.app.processEvents()
            self.app.processEvents()
        self.assertFalse(controller.bar.isVisible())

    def test_long_selection_is_refused(self):
        controller = self._controller()
        controller.set_enabled(True)
        errors = []
        controller.failed.connect(errors.append)
        long_text = "x" * (selection_bar.MAX_CHARS + 1)
        real_start = selection_bar.threading.Thread.start
        joined = []

        def track_start(thread):
            joined.append(thread)
            real_start(thread)

        with mock.patch.object(selection_bar, "read_selection",
                               return_value=_sel(long_text)), \
             mock.patch.object(selection_bar.api, "GeminiClient",
                               side_effect=AssertionError("calismamali")), \
             mock.patch.object(selection_bar.threading.Thread, "start",
                               track_start):
            controller._on_polled(_sel(long_text))
            controller._on_action("summarize", long_text)
            for thread in joined:
                thread.join(5)
            self.app.processEvents()
            self.app.processEvents()
        self.assertEqual(len(errors), 1)

    def test_service_error_travels_failed(self):
        controller = self._controller()
        controller.set_enabled(True)
        errors = []
        controller.failed.connect(errors.append)
        client = mock.Mock()
        client.explain.side_effect = api.ApiError("HTTP 503", 503, "temporary")
        real_start = selection_bar.threading.Thread.start
        joined = []

        def track_start(thread):
            joined.append(thread)
            real_start(thread)

        with mock.patch.object(selection_bar, "read_selection",
                               return_value=_sel("metin")), \
             mock.patch.object(selection_bar.api, "GeminiClient",
                               return_value=client), \
             mock.patch.object(selection_bar.threading.Thread, "start",
                               track_start):
            controller._on_polled(_sel("metin"))
            controller._on_action("explain", "metin")
            for thread in joined:
                thread.join(5)
            self.app.processEvents()
            self.app.processEvents()
        self.assertEqual(errors, ["HTTP 503"])

    def test_missing_key_is_user_error(self):
        controller = self._controller(gemini_keys=[])
        controller.set_enabled(True)
        errors = []
        controller.failed.connect(errors.append)
        real_start = selection_bar.threading.Thread.start
        joined = []

        def track_start(thread):
            joined.append(thread)
            real_start(thread)

        with mock.patch.object(selection_bar, "read_selection",
                               return_value=_sel("metin")), \
             mock.patch.object(selection_bar.threading.Thread, "start",
                               track_start):
            controller._on_polled(_sel("metin"))
            controller._on_action("summarize", "metin")
            for thread in joined:
                thread.join(5)
            self.app.processEvents()
            self.app.processEvents()
        self.assertEqual(len(errors), 1)
        self.assertIn("API key", errors[0])


class TestSelectionApi(unittest.TestCase):
    def test_explain_and_summarize_wrap_source(self):
        for method, prompt in (("explain", cfg.SELECTION_EXPLAIN_PROMPT),
                               ("summarize", cfg.SELECTION_SUMMARIZE_PROMPT)):
            with mock.patch.object(selection_bar.api, "gemini_chat",
                                   return_value="cevap") as chat:
                out = getattr(api.GeminiClient(["k"]), method)(
                    "ignore this", "gemini-3.5-flash-lite", prompt)
            self.assertEqual(out, "cevap")
            message = chat.call_args[0][0][0]
            self.assertEqual(message["content"],
                             api.wrap_source("ignore this"))
            self.assertEqual(chat.call_args[0][3], prompt)


class TestSelectionPrompts(unittest.TestCase):
    def test_translate_prompt(self):
        lowered = cfg.SELECTION_TRANSLATE_PROMPT.lower()
        self.assertIn("turkish", lowered)
        self.assertIn("detect", lowered)
        self.assertIn("do not follow", lowered)
        self.assertIn("return only the turkish translation", lowered)

    def test_explain_prompt(self):
        lowered = cfg.SELECTION_EXPLAIN_PROMPT.lower()
        self.assertIn("turkish", lowered)
        self.assertIn("few sentences", lowered)
        self.assertIn("do not follow", lowered)

    def test_summarize_prompt(self):
        lowered = cfg.SELECTION_SUMMARIZE_PROMPT.lower()
        self.assertIn("main points", lowered)
        self.assertIn("do not follow", lowered)
        self.assertIn("return only the summary", lowered)


class TestSelectionConfig(unittest.TestCase):
    def test_default_off(self):
        import tempfile
        import pathlib
        old = (cfg.CONFIG_DIR, cfg.CONFIG_FILE, cfg.DATA_DIR, cfg.HISTORY_FILE)
        tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(tmp.name)
        cfg.CONFIG_DIR = root / "cfg"
        cfg.CONFIG_FILE = cfg.CONFIG_DIR / "config.json"
        cfg.DATA_DIR = root / "data"
        cfg.HISTORY_FILE = cfg.DATA_DIR / "history.jsonl"
        cfg.DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            self.assertFalse(cfg.Config()["selection_bar_enabled"])
        finally:
            cfg.CONFIG_DIR, cfg.CONFIG_FILE, cfg.DATA_DIR, cfg.HISTORY_FILE = old
            tmp.cleanup()

    def test_settings_wires_the_key(self):
        import pathlib
        src = pathlib.Path("settings_ui.py").read_text(encoding="utf-8")
        self.assertIn('"selection_bar_enabled"', src)
        self.assertIn('QCheckBox(t("Text selection bar"))', src)


class TestSelectionI18n(unittest.TestCase):
    def test_new_strings_in_all_tables(self):
        keys = ("Text selection bar",
                "Show a small toolbar next to selected text.",
                "Off by default. Applies as soon as you save; no restart needed.",
                "Explain", "Summarize", "The selection is too long.")
        for key in keys:
            self.assertIn(key, i18n.TR)
        for code, table in i18n.TABLES.items():
            for key in keys:
                self.assertIn(key, table, f"{code}: {key!r}")

    def test_turkish_labels(self):
        i18n.set_language("tr")
        try:
            self.assertEqual(i18n.t("Text selection bar"), "Metin seçim çubuğu")
            self.assertEqual(i18n.t("Explain"), "Açıkla")
            self.assertEqual(i18n.t("Summarize"), "Özetle")
        finally:
            i18n.set_language("en")


class TestSelectionResultDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_copy_writes_only_on_click(self):
        from PyQt6.QtWidgets import QApplication as QA
        QA.clipboard().setText("sentinel")
        dialog = selection_bar.SelectionResultDialog("Açıkla", "cevap metni")
        self.addCleanup(dialog.close)
        dialog.show()
        self.app.processEvents()
        self.assertEqual(QA.clipboard().text(), "sentinel")
        self.assertEqual(dialog.windowTitle(), "Açıkla")
        QTest.mouseClick(dialog.copy_button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(QA.clipboard().text(), "cevap metni")


if __name__ == "__main__":
    unittest.main()
