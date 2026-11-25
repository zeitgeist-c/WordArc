import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading
import time
import unittest
from unittest import mock

from PyQt6.QtCore import QPoint, QRect, Qt
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
    TEXT_PATTERN = 10014

    def __init__(self, pid=1234, password=False, pattern=None, parent=None,
                 bounds=None, hwnd=777, children=(), fail_password=False,
                 raise_pattern=False):
        self._pid = pid
        self._password = password
        self._pattern = pattern
        self._parent = parent
        self._bounds = bounds
        self._hwnd = hwnd
        self._children = list(children)
        self._fail_password = fail_password
        self._raise_pattern = raise_pattern

    def GetPropertyValue(self, prop):
        if prop == self.IS_PASSWORD:
            if self._fail_password:
                raise OSError("unreadable wrapper")
            return True if self._password else False
        if prop == self.PROCESS_ID:
            return self._pid
        raise ValueError(prop)

    def GetPattern(self, pattern_id):
        if self._raise_pattern:
            raise AttributeError("no GetPattern on this backend")
        if pattern_id == self.TEXT_PATTERN:
            return self._pattern
        return None

    def GetChildren(self):
        return list(self._children)

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


def _sel(text="hello", rect=None, pid=1234, hwnd=777, lines=(), anchor=None):
    return Selection(
        text=text,
        rect=rect or QRect(100, 200, 300, 40),
        pid=pid,
        hwnd=hwnd,
        lines=tuple(lines),
        anchor=anchor)


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

    def test_broken_pattern_call_climbs_to_parent(self):
        # The real backend answers None for unsupported patterns; an older
        # one raises instead. Either way the walk continues upward.
        parent = FakeControl(
            pattern=FakePattern([FakeRange("hi", [FakeRect(1, 2, 9, 6)])]))
        child = FakeControl(pattern=None, parent=parent, raise_pattern=True)
        found = selection_bar.read_selection(_focused(child))
        self.assertIsNotNone(found)
        self.assertEqual(found.text, "hi")

    def test_unreadable_ancestor_password_does_not_veto(self):
        grand = FakeControl(
            pattern=FakePattern([FakeRange("hi", [FakeRect(1, 2, 9, 6)])]))
        middle = FakeControl(pattern=None, parent=grand,
                             fail_password=True)
        leaf = FakeControl(pattern=None, parent=middle)
        found = selection_bar.read_selection(_focused(leaf))
        self.assertIsNotNone(found)
        self.assertEqual(found.text, "hi")

    def test_focused_password_refusal_is_strict(self):
        leaf = FakeControl(pattern=None, fail_password=True)
        self.assertIsNone(selection_bar.read_selection(_focused(leaf)))

    def test_selection_without_geometry_stays_hidden(self):
        # No line rects and no fallback: the bar must not park on an
        # unrelated spot (the old whole-control fallback is gone).
        control = FakeControl(pattern=FakePattern([FakeRange("hi", [])]))
        self.assertIsNone(selection_bar.read_selection(_focused(control)))

    def test_window_scan_finds_the_document_selection(self):
        doc = FakeControl(
            pattern=FakePattern([FakeRange("pane text",
                                           [FakeRect(10, 10, 100, 30)])]))
        doc_top = FakeControl(pattern=None, children=[doc])
        doc_top.GetTopLevelControl = lambda: doc_top
        # A top level without the document yields nothing, even though the
        # walk itself is empty.
        bare = FakeControl(pattern=None)
        bare.GetTopLevelControl = lambda: bare
        lonely = FakeControl(pattern=None)
        lonely.GetTopLevelControl = bare.GetTopLevelControl
        self.assertIsNone(selection_bar.read_selection(_focused(lonely)))
        gate = FakeControl(pattern=None, parent=None)
        gate.GetTopLevelControl = doc_top.GetTopLevelControl
        found = selection_bar.read_selection(_focused(gate))
        self.assertIsNotNone(found)
        self.assertEqual(found.text, "pane text")

    def test_window_scan_skips_password_fields(self):
        secret = FakeControl(
            password=True,
            pattern=FakePattern([FakeRange("hunter2",
                                           [FakeRect(10, 10, 100, 30)])]))
        plain = FakeControl(
            pattern=FakePattern([FakeRange("open note",
                                           [FakeRect(10, 50, 100, 70)])]))
        top = FakeControl(pattern=None, children=[secret, plain])
        top.GetTopLevelControl = lambda: top
        gate = FakeControl(pattern=None)
        gate.GetTopLevelControl = top.GetTopLevelControl
        found = selection_bar.read_selection(_focused(gate))
        self.assertIsNotNone(found)
        self.assertEqual(found.text, "open note")

    def test_line_rects_are_kept_per_line(self):
        control = FakeControl(pattern=FakePattern(
            [FakeRange("two lines", [FakeRect(0, 0, 90, 12),
                                     FakeRect(0, 12, 70, 24)])]))
        found = selection_bar.read_selection(_focused(control))
        self.assertEqual(len(found.lines), 2)
        self.assertEqual((found.lines[1].x(), found.lines[1].width()),
                         (0, 70))

    def test_deep_document_found_by_window_scan(self):
        inner = FakeControl(pattern=FakePattern(
            [FakeRange("derin satir", [FakeRect(0, 0, 100, 20)])]))
        top = inner
        for _ in range(11):
            top = FakeControl(children=[top])
        found = selection_bar._read_window_selection(top, 7, 8)
        self.assertIsNotNone(found)
        self.assertEqual(found.text, "derin satir")

    def test_window_scan_respects_node_budget(self):
        top = FakeControl(children=[FakeControl() for _ in range(1600)])
        started = time.time()
        found = selection_bar._read_window_selection(top, 7, 8)
        self.assertIsNone(found)
        self.assertLess(time.time() - started, 5.0)

    def test_anchor_prefers_caret_then_cursor(self):
        from PyQt6.QtCore import QPoint
        control = FakeControl(pattern=FakePattern(
            [FakeRange("hi", [FakeRect(100, 100, 300, 140)])]))
        with mock.patch.object(selection_bar, "_caret_pos",
                               return_value=QPoint(150, 120)), \
             mock.patch.object(selection_bar, "_cursor_pos",
                               return_value=QPoint(250, 120)):
            found = selection_bar.read_selection(_focused(control))
        self.assertEqual((found.anchor.x(), found.anchor.y()), (150, 120))
        with mock.patch.object(selection_bar, "_caret_pos",
                               return_value=None), \
             mock.patch.object(selection_bar, "_cursor_pos",
                               return_value=QPoint(250, 120)):
            found = selection_bar.read_selection(_focused(control))
        self.assertEqual((found.anchor.x(), found.anchor.y()), (250, 120))
        with mock.patch.object(selection_bar, "_caret_pos",
                               return_value=QPoint(900, 900)), \
             mock.patch.object(selection_bar, "_cursor_pos",
                               return_value=QPoint(5, 5)):
            found = selection_bar.read_selection(_focused(control))
        self.assertIsNone(found.anchor)

    def test_anchor_forwards_hwnd_to_caret(self):
        from PyQt6.QtCore import QRect
        with mock.patch.object(selection_bar, "_caret_pos",
                               return_value=None) as caret, \
             mock.patch.object(selection_bar, "_cursor_pos",
                               return_value=None):
            selection_bar._anchor_for(QRect(0, 0, 100, 20), 123)
        caret.assert_called_once_with(123)


class TestCaretOwnership(unittest.TestCase):
    """The caret counts only when owned by the source window on screen."""

    def test_no_source_window_means_no_caret(self):
        with mock.patch.object(selection_bar, "_caret_raw",
                               return_value=(500, QPoint(10, 20))):
            self.assertIsNone(selection_bar._caret_pos())
            self.assertIsNone(selection_bar._caret_pos(0))

    def _owned(self, root=700, screen=None, frame=None):
        screen = QPoint(110, 220) if screen is None else screen
        frame = QRect(0, 0, 800, 600) if frame is None else frame
        return (mock.patch.object(selection_bar, "_caret_raw",
                                   return_value=(500, QPoint(10, 20))),
                mock.patch.object(selection_bar, "_root_window",
                                   return_value=root),
                mock.patch.object(selection_bar, "_client_to_screen",
                                   return_value=screen),
                mock.patch.object(selection_bar, "_window_frame",
                                   return_value=frame))

    def test_owned_caret_resolves_to_screen(self):
        patches = self._owned()
        for patch in patches:
            patch.start()
        self.addCleanup(lambda: [patch.stop() for patch in patches])
        self.assertEqual(selection_bar._caret_pos(700), QPoint(110, 220))

    def test_foreign_caret_rejected(self):
        patches = self._owned(root=999)
        for patch in patches:
            patch.start()
        self.addCleanup(lambda: [patch.stop() for patch in patches])
        self.assertIsNone(selection_bar._caret_pos(700))

    def test_caret_outside_frame_rejected(self):
        patches = self._owned(screen=QPoint(5000, 5000))
        for patch in patches:
            patch.start()
        self.addCleanup(lambda: [patch.stop() for patch in patches])
        self.assertIsNone(selection_bar._caret_pos(700))

    def test_unresolvable_caret_rejected(self):
        with mock.patch.object(selection_bar, "_caret_raw",
                               return_value=None):
            self.assertIsNone(selection_bar._caret_pos(700))
        patches = self._owned()
        for patch in patches:
            patch.start()
        self.addCleanup(lambda: [patch.stop() for patch in patches])
        with mock.patch.object(selection_bar, "_client_to_screen",
                               return_value=None):
            self.assertIsNone(selection_bar._caret_pos(700))


class TestLogicalMapping(unittest.TestCase):
    """Physical UIA pixels become Qt logical pixels per owning screen."""

    def test_single_scaled_screen(self):
        from PyQt6.QtCore import QRect
        out = selection_bar._to_logical_on_screens(
            QRect(125, 125, 100, 50), [(QRect(0, 0, 1920, 1080), 1.25)])
        self.assertEqual((out.x(), out.y(), out.width(), out.height()),
                         (100, 100, 80, 40))

    def test_second_monitor_offset_and_scale(self):
        from PyQt6.QtCore import QRect
        screens = [(QRect(0, 0, 1920, 1080), 1.0),
                   (QRect(1920, 0, 1280, 1024), 1.5)]
        out = selection_bar._to_logical_on_screens(
            QRect(3000, 150, 150, 60), screens)
        self.assertEqual((out.x(), out.y(), out.width(), out.height()),
                         (2640, 100, 100, 40))

    def test_left_monitor_negative_origin_scaled(self):
        # Regression: left monitor x=-1920 at 125%; physical x=-1700 must
        # map to Qt x=-1744, not -1360.
        from PyQt6.QtCore import QRect
        screens = [(QRect(-1920, 0, 1536, 864), 1.25),
                   (QRect(0, 0, 1920, 1080), 1.0)]
        out = selection_bar._to_logical_on_screens(
            QRect(-1700, 100, 250, 40), screens)
        self.assertEqual((out.x(), out.y(), out.width(), out.height()),
                         (-1744, 80, 200, 32))

    def test_right_monitor_positive_origin_scaled(self):
        from PyQt6.QtCore import QRect
        screens = [(QRect(0, 0, 1920, 1080), 1.0),
                   (QRect(1920, 0, 800, 600), 1.5)]
        out = selection_bar._to_logical_on_screens(
            QRect(2000, 300, 150, 40), screens)
        self.assertEqual((out.x(), out.y(), out.width(), out.height()),
                         (1973, 200, 100, 27))

    def test_unknown_layout_falls_back_to_first_scale(self):
        from PyQt6.QtCore import QRect
        out = selection_bar._to_logical_on_screens(
            QRect(-5000, -5000, 100, 50),
            [(QRect(0, 0, 1920, 1080), 1.25)])
        self.assertEqual((out.x(), out.y()), (-4000, -4000))


class TestAnchorRow(unittest.TestCase):
    def test_containing_row_wins(self):
        from PyQt6.QtCore import QRect, QPoint
        rows = [QRect(0, 0, 200, 20), QRect(0, 20, 200, 40)]
        self.assertIs(selection_bar.SelectionBar._anchor_row(
            rows, QRect(0, 0, 200, 40), QPoint(50, 30)), rows[1])

    def test_nearest_row_when_outside(self):
        from PyQt6.QtCore import QRect, QPoint
        rows = [QRect(0, 0, 200, 20), QRect(0, 100, 200, 120)]
        self.assertIs(selection_bar.SelectionBar._anchor_row(
            rows, QRect(0, 0, 200, 120), QPoint(50, 90)), rows[1])

    def test_no_anchor_means_first_row(self):
        from PyQt6.QtCore import QRect
        rows = [QRect(0, 0, 200, 20), QRect(0, 20, 200, 40)]
        self.assertIs(selection_bar.SelectionBar._anchor_row(
            rows, QRect(0, 0, 200, 40), None), rows[0])

    def test_no_rows_means_fallback(self):
        from PyQt6.QtCore import QRect
        box = QRect(0, 0, 200, 40)
        self.assertIs(selection_bar.SelectionBar._anchor_row(
            [], box, None), box)


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


class TestSelectionTooltips(unittest.TestCase):
    """Hover hints stay one word in every language."""

    def test_bar_tooltips_are_single_words_everywhere(self):
        import i18n

        previous = i18n.language()
        try:
            for code, _name in i18n.LANGUAGES:
                i18n.set_language(code)
                for kind, label in selection_bar.SelectionBar.ACTIONS:
                    text = i18n.t(label)
                    self.assertTrue(text.strip(), (code, kind))
                    self.assertNotIn(" ", text.strip(), (code, kind, text))
        finally:
            i18n.set_language(previous)

    def test_translate_tooltip_key(self):
        import i18n

        self.assertEqual(
            [label for kind, label in selection_bar.SelectionBar.ACTIONS
             if kind == "translate"], ["Translate"])
        previous = i18n.language()
        try:
            i18n.set_language("tr")
            bar = selection_bar.SelectionBar()
            self.addCleanup(bar.close)
            self.assertEqual(bar.buttons["translate"].toolTip(), "Çevir")
        finally:
            i18n.set_language(previous)


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

    def test_enable_rearms_for_current_selection(self):
        controller = self._controller()
        controller.set_enabled(True)
        controller._on_polled(_sel("metin"))
        self.assertTrue(controller.bar.isVisible())
        controller._consumed = _sel("metin")  # as if just acted on
        controller.bar.hide()
        controller.set_enabled(False)
        controller.set_enabled(True)
        controller._on_polled(_sel("metin"))
        self.assertTrue(controller.bar.isVisible())

    def test_acted_selection_stays_hidden_until_it_changes(self):
        from PyQt6.QtWidgets import QApplication as QA
        QA.clipboard().setText("sentinel")
        controller = self._controller()
        controller.set_enabled(True)
        controller._on_polled(_sel("secili metin"))
        self.assertTrue(controller.bar.isVisible())
        real_start = selection_bar.threading.Thread.start
        joined = []

        def track_start(thread):
            joined.append(thread)
            real_start(thread)

        with mock.patch.object(selection_bar, "read_selection",
                               return_value=_sel("secili metin")), \
             mock.patch.object(selection_bar.threading.Thread, "start",
                               track_start):
            controller._on_copy("secili metin")
            for thread in joined:
                thread.join(5)
            self.app.processEvents()
            self.app.processEvents()
        self.assertEqual(QA.clipboard().text(), "secili metin")
        # Acted on: gone at once, and the same selection must not bring
        # the bar back on the next polls.
        self.assertFalse(controller.bar.isVisible())
        controller._on_polled(_sel("secili metin"))
        self.assertFalse(controller.bar.isVisible())
        # A new selection re-arms the bar; clearing it hides again.
        controller._on_polled(_sel("baska metin"))
        self.assertTrue(controller.bar.isVisible())
        controller._on_polled(None)
        self.assertFalse(controller.bar.isVisible())

    def test_action_answer_leaves_bar_hidden_for_same_selection(self):
        controller = self._controller()
        controller.set_enabled(True)
        done = []
        controller.result_ready.connect(lambda kind, text: done.append((kind, text)))
        client = mock.Mock()
        client.translate.return_value = "ceviri"
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
            self.assertTrue(controller.bar.isVisible())
            controller._on_action("translate", "metin")
            # Stays where it is and says it is waiting until the answer lands.
            self.assertTrue(controller.bar.isVisible())
            self.assertTrue(controller.bar._busy_label.isVisible())
            self.assertIn("…", controller.bar._busy_label.text())
            for thread in joined:
                thread.join(5)
            self.app.processEvents()
            self.app.processEvents()
        self.assertEqual(done, [("translate", "ceviri")])
        self.assertFalse(controller.bar.isVisible())
        controller._on_polled(_sel("metin"))
        self.assertFalse(controller.bar.isVisible())

    def test_action_started_fires_and_popup_rect_is_kept(self):
        controller = self._controller()
        controller.set_enabled(True)
        started = []
        controller.action_started.connect(started.append)
        client = mock.Mock()
        client.translate.return_value = "ceviri"
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
            for thread in joined:
                thread.join(5)
            self.app.processEvents()
        self.assertEqual(started, ["translate"])
        kept = controller.popup_rect()
        self.assertIsNotNone(kept)
        self.assertEqual((kept.x(), kept.y(), kept.width(), kept.height()),
                         (100, 200, 300, 40))

    def test_copy_takes_no_busy_line(self):
        controller = self._controller()
        controller.set_enabled(True)
        started = []
        controller.action_started.connect(started.append)
        with mock.patch.object(selection_bar, "read_selection",
                               return_value=_sel("metin")):
            controller._on_polled(_sel("metin"))
            controller._on_action("copy", "metin")
            self.app.processEvents()
            self.app.processEvents()
        self.assertEqual(started, [])
        self.assertFalse(controller.bar._busy_label.isVisible())


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
        # The layout mirrors the source: lists and paragraphs stay in place.
        self.assertIn("bullet", lowered)
        self.assertIn("numbered", lowered)
        self.assertIn("paragraph", lowered)

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
                "Explain", "Summarize", "Translate",
                "The selection is too long.")
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
            self.assertEqual(i18n.t("Summarize"), "Özet")
            self.assertEqual(i18n.t("Translate"), "Çevir")
            self.assertEqual(i18n.t("Copy"), "Kopyala")
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

    def test_copy_on_the_left_close_on_the_right_same_size(self):
        dialog = selection_bar.SelectionResultDialog("Başlık", "kısa metin")
        self.addCleanup(dialog.close)
        dialog.show()
        self.app.processEvents()
        self.assertLess(dialog.copy_button.x(), 200)
        close_button = [button for button in dialog.findChildren(
            dialog.copy_button.__class__)
            if button is not dialog.copy_button][0]
        self.assertGreater(close_button.x(), dialog.copy_button.x())
        self.assertEqual(dialog.copy_button.width(), close_button.width())

    def test_width_follows_text_height_stays(self):
        short = selection_bar.SelectionResultDialog("B", "kısa")
        long_text = selection_bar.SelectionResultDialog(
            "B", "uzun bir satır " * 20 + "\n" + "ikinci satır " * 10)
        self.addCleanup(short.close)
        self.addCleanup(long_text.close)
        short.show()
        long_text.show()
        self.app.processEvents()
        self.assertGreater(long_text.width(), short.width())
        self.assertEqual(long_text.height(), short.height())

    def test_position_near_parks_below_the_selection(self):
        from PyQt6.QtWidgets import QApplication as QA
        dialog = selection_bar.SelectionResultDialog("B", "metin")
        self.addCleanup(dialog.close)
        dialog.show()
        self.app.processEvents()
        rect = QRect(100, 200, 300, 40)
        dialog.position_near(rect)
        screen = QA.screenAt(QPoint(250, 220)) or QA.primaryScreen()
        area = screen.availableGeometry()
        width, height = dialog.width(), dialog.height()
        below = rect.bottom() + 8
        if below + height <= area.bottom():
            expect_y = below
        else:
            expect_y = max(area.top(), rect.top() - 8 - height)
        expect_x = min(max(100, area.left()),
                       max(area.right() - width, area.left()))
        self.assertEqual((dialog.x(), dialog.y()), (expect_x, expect_y))

    def test_position_near_without_rect_keeps_place(self):
        dialog = selection_bar.SelectionResultDialog("B", "metin")
        self.addCleanup(dialog.close)
        dialog.show()
        self.app.processEvents()
        before = (dialog.x(), dialog.y())
        dialog.position_near(None)
        self.assertEqual((dialog.x(), dialog.y()), before)


class TestBarPlacement(unittest.TestCase):
    """The bar parks by the row the user acted on, inside the screen."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_multi_line_anchor_uses_release_row(self):
        bar = SelectionBar()
        self.addCleanup(bar.close)
        rows = [QRect(400, 200, 200, 20), QRect(400, 220, 200, 20),
                QRect(400, 240, 200, 20)]
        bar.show_for(_sel("üç satır", QRect(400, 200, 200, 60),
                          lines=rows, anchor=QPoint(450, 250)))
        self.app.processEvents()
        # By the last row, above it: not by the first row, not below all.
        self.assertLessEqual(bar.y() + bar.height(), 240 + 8)
        self.assertGreater(bar.y() + bar.height(), 220)

    def test_top_edge_drops_below(self):
        bar = SelectionBar()
        self.addCleanup(bar.close)
        bar.show_for(_sel("üstte", QRect(400, 0, 200, 20)))
        self.app.processEvents()
        self.assertGreaterEqual(bar.y(), 20)

    def test_scaled_screen_uses_logical_pixels(self):
        bar = SelectionBar()
        self.addCleanup(bar.close)
        for ratio in (1.25, 1.5):
            fake = mock.Mock()
            fake.geometry.return_value = QRect(0, 0, 1920, 1080)
            fake.devicePixelRatio.return_value = ratio
            fake.availableGeometry.return_value = QRect(0, 0, 1920, 1040)
            gui = selection_bar.QGuiApplication
            with mock.patch.object(gui, "screens", return_value=[fake]), \
                 mock.patch.object(gui, "screenAt", return_value=fake):
                # Physical (1000 * ratio, 500 * ratio) is logical (1000, 500).
                bar.show_for(_sel("ölçekli", QRect(int(1000 * ratio),
                                                   int(500 * ratio), 250, 50)))
                self.app.processEvents()
            self.assertLess(bar.x() + bar.width(), 1000 * ratio)
            self.assertLessEqual(bar.y() + bar.height(), 500 + 8)

    def test_scrolled_selection_moves_the_bar(self):
        controller = SelectionBarController(SelectionConf())
        self.addCleanup(controller.shutdown)
        self.addCleanup(controller.deleteLater)
        controller.set_enabled(True)
        controller._on_polled(_sel("metin", rect=QRect(100, 200, 300, 40)))
        first = (controller.bar.x(), controller.bar.y())
        self.assertTrue(controller.bar.isVisible())
        controller._on_polled(_sel("metin", rect=QRect(100, 300, 300, 40)))
        second = (controller.bar.x(), controller.bar.y())
        self.assertTrue(controller.bar.isVisible())
        self.assertNotEqual(first, second)
        self.assertEqual(controller.bar._text, "metin")

    def test_window_change_repositions(self):
        controller = SelectionBarController(SelectionConf())
        self.addCleanup(controller.shutdown)
        self.addCleanup(controller.deleteLater)
        controller.set_enabled(True)
        controller._on_polled(_sel("metin", rect=QRect(100, 200, 300, 40),
                                   hwnd=111))
        first = (controller.bar.x(), controller.bar.y())
        controller._on_polled(_sel("metin", rect=QRect(500, 200, 300, 40),
                                   hwnd=222))
        second = (controller.bar.x(), controller.bar.y())
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
