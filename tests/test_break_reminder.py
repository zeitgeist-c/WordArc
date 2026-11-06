"""Break reminder: deterministic engine tests (fake clock) + offscreen UI tests."""

import ctypes
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PyQt6.QtCore import Qt, QByteArray
from PyQt6.QtWidgets import QApplication

import break_reminder as br
import config as cfg
import i18n

_APP = QApplication.instance() or QApplication([])


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make_engine(work_min=25, break_min=5):
    clock = FakeClock()
    engine = br.BreakEngine(clock=clock)
    engine.work_s = work_min * 60
    engine.break_s = break_min * 60
    return engine, clock


class TestClamp(unittest.TestCase):
    def test_bad_values_fall_back(self):
        self.assertEqual(br.clamp_minutes("xx", 5, 180, 25), 25)
        self.assertEqual(br.clamp_minutes(None, 5, 180, 25), 25)
        self.assertEqual(br.clamp_minutes(0, 5, 180, 25), 25)
        self.assertEqual(br.clamp_minutes(999, 5, 180, 25), 25)
        self.assertEqual(br.clamp_minutes(30, 5, 180, 25), 30)


class TestEngine(unittest.TestCase):
    def test_enable_starts_fresh_work_period(self):
        engine, clock = make_engine()
        self.assertTrue(engine.set_enabled(True, clock()))
        self.assertEqual(engine.phase, br.BreakPhase.WORKING)
        self.assertEqual(engine.remaining(clock()), 25 * 60)
        self.assertFalse(engine.set_enabled(True, clock()))

    def test_work_expiry_fires_reminder_once(self):
        engine, clock = make_engine()
        engine.set_enabled(True, clock())
        clock.advance(25 * 60 - 1)
        self.assertEqual(engine.refresh(clock()), [])
        clock.advance(1)
        self.assertEqual(engine.refresh(clock()), ["reminder"])
        self.assertEqual(engine.phase, br.BreakPhase.REMINDER)
        # Late or repeated ticks never replay the reminder.
        clock.advance(3600)
        self.assertEqual(engine.refresh(clock()), [])

    def test_long_delay_single_event(self):
        """Hours pass (sleep without events): still one reminder, then normal."""
        engine, clock = make_engine()
        engine.set_enabled(True, clock())
        clock.advance(4 * 3600)
        self.assertEqual(engine.refresh(clock()), ["reminder"])
        self.assertTrue(engine.start_break(clock()))
        self.assertEqual(engine.phase, br.BreakPhase.BREAK)
        clock.advance(5 * 60)
        self.assertEqual(engine.refresh(clock()), ["break_finished"])
        self.assertEqual(engine.phase, br.BreakPhase.BREAK_DONE)
        self.assertEqual(engine.remaining(clock()), 0)
        clock.advance(br.BREAK_DONE_S)
        self.assertEqual(engine.refresh(clock()), ["work_started"])
        self.assertEqual(engine.phase, br.BreakPhase.WORKING)
        self.assertEqual(engine.remaining(clock()), 25 * 60)

    def test_break_lifecycle(self):
        engine, clock = make_engine()
        engine.set_enabled(True, clock())
        clock.advance(25 * 60)
        engine.refresh(clock())
        self.assertTrue(engine.start_break(clock()))
        self.assertEqual(engine.remaining(clock()), 5 * 60)
        # Break starts only from the reminder, never from working.
        engine2, clock2 = make_engine()
        engine2.set_enabled(True, clock2())
        self.assertFalse(engine2.start_break(clock2()))
        clock.advance(5 * 60)
        self.assertEqual(engine.refresh(clock()), ["break_finished"])
        self.assertEqual(engine.phase, br.BreakPhase.BREAK_DONE)

    def test_break_done_holds_zero_then_starts_fresh_work(self):
        """00:00 shows for 2 s; those 2 s never count as work."""
        engine, clock = make_engine()
        engine.set_enabled(True, clock())
        clock.advance(25 * 60)
        engine.refresh(clock())
        engine.start_break(clock())
        clock.advance(5 * 60)
        engine.refresh(clock())
        done_at = clock()
        self.assertEqual(engine.phase, br.BreakPhase.BREAK_DONE)
        self.assertEqual(engine.remaining(clock()), 0)
        clock.advance(1)
        self.assertEqual(engine.refresh(clock()), [])
        self.assertEqual(engine.phase, br.BreakPhase.BREAK_DONE)
        clock.advance(1)
        self.assertEqual(engine.refresh(clock()), ["work_started"])
        self.assertEqual(engine.phase, br.BreakPhase.WORKING)
        # Fresh deadline starts at the hide moment, not at the break end.
        self.assertEqual(engine._deadline, done_at + br.BREAK_DONE_S + 25 * 60)

    def test_snooze_choices_each_reopen_the_reminder(self):
        for minutes in br.SNOOZE_CHOICES:
            engine, clock = make_engine()
            engine.set_enabled(True, clock())
            clock.advance(25 * 60)
            engine.refresh(clock())
            self.assertTrue(engine.snooze(minutes * 60, clock()))
            self.assertEqual(engine.phase, br.BreakPhase.WORKING)
            self.assertEqual(engine.remaining(clock()), minutes * 60)
            # No auto break while snoozed: only the reminder returns.
            clock.advance(minutes * 60)
            self.assertEqual(engine.refresh(clock()), ["reminder"])
            self.assertEqual(engine.phase, br.BreakPhase.REMINDER)

    def test_snooze_rejected_outside_reminder(self):
        engine, clock = make_engine()
        engine.set_enabled(True, clock())
        self.assertFalse(engine.snooze(60, clock()))
        engine.pause(clock())
        self.assertFalse(engine.snooze(60, clock()))

    def test_cancel_starts_fresh_work_and_stays_enabled(self):
        engine, clock = make_engine()
        engine.set_enabled(True, clock())
        clock.advance(25 * 60)
        engine.refresh(clock())
        self.assertTrue(engine.cancel(clock()))
        self.assertEqual(engine.phase, br.BreakPhase.WORKING)
        self.assertEqual(engine.remaining(clock()), 25 * 60)
        # Cancelling is not disabling: the next cycle still reminds.
        clock.advance(25 * 60)
        self.assertEqual(engine.refresh(clock()), ["reminder"])

    def test_cancel_rejected_outside_reminder(self):
        engine, clock = make_engine()
        engine.set_enabled(True, clock())
        self.assertFalse(engine.cancel(clock()))

    def test_pause_resume_keeps_remaining(self):
        engine, clock = make_engine()
        engine.set_enabled(True, clock())
        clock.advance(60)
        self.assertTrue(engine.pause(clock()))
        frozen = engine.remaining(clock())
        clock.advance(3600)
        self.assertEqual(engine.remaining(clock()), frozen)
        self.assertTrue(engine.resume(clock()))
        self.assertEqual(engine.phase, br.BreakPhase.WORKING)
        self.assertEqual(engine.remaining(clock()), frozen)

    def test_pause_from_reminder_returns_to_reminder(self):
        engine, clock = make_engine()
        engine.set_enabled(True, clock())
        clock.advance(25 * 60)
        engine.refresh(clock())
        self.assertTrue(engine.pause(clock()))
        self.assertTrue(engine.resume(clock()))
        self.assertEqual(engine.phase, br.BreakPhase.REMINDER)

    def test_suspend_resume_keeps_remaining(self):
        engine, clock = make_engine()
        engine.set_enabled(True, clock())
        clock.advance(120)
        self.assertTrue(engine.on_suspend(clock()))
        self.assertEqual(engine.phase, br.BreakPhase.PAUSED)
        frozen = engine.remaining(clock())
        clock.advance(8 * 3600)  # a night of sleep
        self.assertTrue(engine.on_resume(clock()))
        self.assertEqual(engine.phase, br.BreakPhase.WORKING)
        self.assertEqual(engine.remaining(clock()), frozen)

    def test_manual_pause_survives_resume_event(self):
        engine, clock = make_engine()
        engine.set_enabled(True, clock())
        engine.pause(clock())
        clock.advance(100)
        self.assertFalse(engine.on_resume(clock()))
        self.assertEqual(engine.phase, br.BreakPhase.PAUSED)

    def test_suspend_when_off_is_noop(self):
        engine, clock = make_engine()
        self.assertFalse(engine.on_suspend(clock()))
        self.assertFalse(engine.on_resume(clock()))

    def test_disable_and_reenable_is_fresh(self):
        """Reopening never stacks old reminders: a fresh work period starts."""
        engine, clock = make_engine()
        engine.set_enabled(True, clock())
        clock.advance(25 * 60)
        engine.refresh(clock())
        self.assertEqual(engine.phase, br.BreakPhase.REMINDER)
        self.assertTrue(engine.set_enabled(False, clock()))
        self.assertEqual(engine.phase, br.BreakPhase.OFF)
        self.assertTrue(engine.set_enabled(True, clock()))
        self.assertEqual(engine.phase, br.BreakPhase.WORKING)
        self.assertEqual(engine.remaining(clock()), 25 * 60)

    def test_pause_during_break_and_done(self):
        engine, clock = make_engine()
        engine.set_enabled(True, clock())
        clock.advance(25 * 60)
        engine.refresh(clock())
        engine.start_break(clock())
        clock.advance(60)
        self.assertTrue(engine.pause(clock()))
        frozen = engine.remaining(clock())
        clock.advance(600)
        self.assertEqual(engine.remaining(clock()), frozen)
        self.assertTrue(engine.resume(clock()))
        self.assertEqual(engine.phase, br.BreakPhase.BREAK)

    def test_apply_durations_keeps_progress(self):
        engine, clock = make_engine()
        engine.set_enabled(True, clock())
        clock.advance(60)
        engine.apply_durations(30 * 60, 5 * 60, clock())
        self.assertEqual(engine.remaining(clock()), 30 * 60 - 60)


class FakeConf(dict):
    def get(self, key, default=None):
        return self[key] if key in self else cfg.DEFAULTS.get(key, default)

    def save(self):
        pass


class TestController(unittest.TestCase):
    def setUp(self):
        i18n.set_language("en")
        self.conf = FakeConf()
        self.controller = br.BreakController(self.conf)

    def tearDown(self):
        self.controller.shutdown()
        self.controller.window.deleteLater()
        self.controller.deleteLater()
        i18n.set_language("en")

    def test_off_by_default_window_hidden(self):
        self.controller.sync_from_conf()
        self.assertEqual(self.controller.engine.phase, br.BreakPhase.OFF)
        self.assertFalse(self.controller.window.isVisible())
        self.assertFalse(self.controller._waker.isActive())

    def test_double_sync_single_timer_filter_window(self):
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        waker, filt, window = (self.controller._waker,
                               self.controller._power_filter,
                               self.controller.window)
        self.controller.sync_from_conf()
        self.assertIs(self.controller._waker, waker)
        self.assertIs(self.controller.window, window)
        self.assertIs(self.controller._power_filter, filt)
        self.assertTrue(waker.isActive())

    def test_enable_hides_working_disable_hides(self):
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        self.assertEqual(self.controller.engine.phase, br.BreakPhase.WORKING)
        # Background counting: no window while working.
        self.assertFalse(self.controller.window.isVisible())
        self.conf["break_enabled"] = False
        self.controller.sync_from_conf()
        self.assertEqual(self.controller.engine.phase, br.BreakPhase.OFF)
        self.assertFalse(self.controller.window.isVisible())

    def test_reminder_face_and_buttons(self):
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        engine = self.controller.engine
        engine._deadline = engine._clock() - 1
        self.controller._wake()
        self.assertEqual(engine.phase, br.BreakPhase.REMINDER)
        window = self.controller.window
        self.assertTrue(window.isVisible())
        self.assertEqual(window._stack.currentIndex(), 1)
        window._start_button.click()
        self.assertEqual(engine.phase, br.BreakPhase.BREAK)
        self.assertEqual(window._stack.currentIndex(), 0)

    def test_snooze_buttons_hide_and_cancel_restarts(self):
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        engine = self.controller.engine
        window = self.controller.window
        engine._deadline = engine._clock() - 1
        self.controller._wake()
        window._snooze_buttons[10].click()
        self.assertEqual(engine.phase, br.BreakPhase.WORKING)
        self.assertFalse(window.isVisible())
        engine._deadline = engine._clock() - 1
        self.controller._wake()
        self.assertTrue(window.isVisible())
        window._cancel_button.click()
        self.assertEqual(engine.phase, br.BreakPhase.WORKING)
        self.assertEqual(engine.remaining(), engine.work_s)
        self.assertFalse(window.isVisible())

    def test_break_done_shows_zero_then_hides(self):
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        engine = self.controller.engine
        window = self.controller.window
        engine._deadline = engine._clock() - 1
        self.controller._wake()
        window._start_button.click()
        engine._deadline = engine._clock() - 1
        self.controller._wake()
        self.assertEqual(engine.phase, br.BreakPhase.BREAK_DONE)
        self.assertTrue(window.isVisible())
        self.assertEqual(window._time_label.text(), "00:00")
        engine._done_until = engine._clock() - 1
        self.controller._wake()
        self.assertEqual(engine.phase, br.BreakPhase.WORKING)
        self.assertFalse(window.isVisible())

    def test_pause_never_pops_the_panel(self):
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        engine = self.controller.engine
        window = self.controller.window
        self.controller.set_paused(True)
        self.assertEqual(engine.phase, br.BreakPhase.PAUSED)
        self.assertFalse(window.isVisible())
        self.controller.set_paused(False)
        self.assertEqual(engine.phase, br.BreakPhase.WORKING)
        self.assertFalse(window.isVisible())
        # Pausing the reminder hides it; resuming brings it back.
        engine._deadline = engine._clock() - 1
        self.controller._wake()
        self.assertTrue(window.isVisible())
        self.controller.set_paused(True)
        self.assertFalse(window.isVisible())
        self.controller.set_paused(False)
        self.assertEqual(engine.phase, br.BreakPhase.REMINDER)
        self.assertTrue(window.isVisible())

    def test_window_never_takes_focus(self):
        window = self.controller.window
        self.assertTrue(window.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus)
        self.assertTrue(window.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))
        self.assertEqual(window.focusPolicy(), Qt.FocusPolicy.NoFocus)

    def test_screenshot_hide_restore(self):
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        engine = self.controller.engine
        window = self.controller.window
        # Hidden background work: nothing to park, hold still set.
        self.assertFalse(self.controller.hide_for_capture())
        engine._deadline = engine._clock() - 1
        self.controller._wake()
        # The reminder was reached mid-capture: phase moves, panel stays down.
        self.assertEqual(engine.phase, br.BreakPhase.REMINDER)
        self.assertFalse(window.isVisible())
        self.controller.restore_after_capture(True)
        self.assertTrue(window.isVisible())
        # Disabled: hiding is a no-op and restores nothing.
        self.conf["break_enabled"] = False
        self.controller.sync_from_conf()
        self.assertFalse(self.controller.hide_for_capture())
        self.controller.restore_after_capture(False)
        self.assertFalse(self.controller.window.isVisible())

    def test_capture_hold_blocks_tick_transition_and_resync(self):
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        engine = self.controller.engine
        window = self.controller.window
        engine._deadline = engine._clock() - 1
        self.controller._wake()
        self.assertTrue(window.isVisible())
        self.assertTrue(self.controller.hide_for_capture())
        # A transition reached mid-capture must not re-show the panel.
        engine.snooze(600)
        engine._deadline = engine._clock() - 1
        self.controller._wake()
        self.assertEqual(engine.phase, br.BreakPhase.REMINDER)
        self.assertFalse(window.isVisible(), "tick re-showed during capture")
        self.controller.sync_from_conf()
        self.assertFalse(window.isVisible(), "resync re-showed during capture")
        self.controller.restore_after_capture(True)
        self.assertTrue(window.isVisible())
        self.assertEqual(window._stack.currentIndex(), 1)

    def test_avoids_recording_overlay(self):
        import overlay as rec_overlay_mod
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        rec = rec_overlay_mod.Overlay("bottom-left")
        rec.show_recording()
        rec.move(100, 100)
        rec.show()
        try:
            window = self.controller.window
            window._record_overlay = rec
            window.set_phase(br.BreakPhase.REMINDER, 0)
            window.move(100, 100)
            window._avoid_record_overlay()
            self.assertFalse(window.frameGeometry().intersects(rec.frameGeometry()))
        finally:
            rec.hide()
            rec.deleteLater()

    def test_window_paints_without_errors(self):
        import logging
        from PyQt6.QtGui import QImage, QPainter
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        window = self.controller.window
        records = []

        class Handler(logging.Handler):
            def emit(self, record):
                records.append(record)

        logger = logging.getLogger("wordarc.breaks")
        handler = Handler()
        logger.addHandler(handler)
        try:
            image = QImage(window.width(), window.height(),
                           QImage.Format.Format_ARGB32)
            image.fill(0)
            painter = QPainter(image)
            window.render(painter)
            painter.end()
        finally:
            logger.removeHandler(handler)
        errors = [r for r in records if r.levelno >= logging.ERROR]
        self.assertEqual(errors, [])
        opaque = sum(1 for x in range(0, image.width(), 7)
                     for y in range(0, image.height(), 7)
                     if image.pixelColor(x, y).alpha() > 40)
        self.assertGreater(opaque, 0, "break window painted nothing")

    def test_tr_translation(self):
        i18n.set_language("tr")
        self.controller.retranslate()
        self.assertEqual(self.controller.window._start_button.text(), "Molayı başlat")


def _native_msg(wparam):
    """A real WM_... message buffer; its address is what Qt hands over."""
    from ctypes import wintypes

    class _MSG(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND),
                    ("message", wintypes.UINT),
                    ("wParam", wintypes.WPARAM),
                    ("lParam", wintypes.LPARAM),
                    ("time", wintypes.DWORD),
                    ("pt", wintypes.POINT)]

    return _MSG(0, 0, wparam, 0, 0, wintypes.POINT(0, 0))


class TestReviewFindings(unittest.TestCase):
    """Codex review gaps: each test fails before its fix."""

    def setUp(self):
        i18n.set_language("en")
        self.conf = FakeConf()
        self.controller = br.BreakController(self.conf)

    def tearDown(self):
        self.controller.shutdown()
        self.controller.window.deleteLater()
        self.controller.deleteLater()
        i18n.set_language("en")

    # -- 1: pause lives in the tray and never pops the panel --
    def test_tray_pause_hides_and_resume_restores(self):
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        window = self.controller.window
        engine = self.controller.engine
        self.controller.set_paused(True)
        self.assertEqual(engine.phase, br.BreakPhase.PAUSED)
        self.assertFalse(window.isVisible())
        self.controller.set_paused(False)
        self.assertEqual(engine.phase, br.BreakPhase.WORKING)
        self.assertFalse(window.isVisible())

    # -- 2: capture hold (covered in TestController with the new flow) --
    def test_capture_hold_blocks_tick_transition_and_resync(self):
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        engine = self.controller.engine
        window = self.controller.window
        engine._deadline = engine._clock() - 1
        self.controller._wake()
        self.assertTrue(window.isVisible())
        self.assertTrue(self.controller.hide_for_capture())
        engine.snooze(600)
        engine._deadline = engine._clock() - 1
        self.controller._wake()
        self.assertEqual(engine.phase, br.BreakPhase.REMINDER)
        self.assertFalse(window.isVisible(), "tick re-showed during capture")
        self.controller.sync_from_conf()
        self.assertFalse(window.isVisible(), "resync re-showed during capture")
        self.controller.restore_after_capture(True)
        self.assertTrue(window.isVisible())
        self.assertEqual(window._stack.currentIndex(), 1)

    def test_capture_restore_after_disable_stays_hidden(self):
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        engine = self.controller.engine
        engine._deadline = engine._clock() - 1
        self.controller._wake()
        self.assertTrue(self.controller.hide_for_capture())
        self.conf["break_enabled"] = False
        self.controller.sync_from_conf()
        self.controller.restore_after_capture(True)
        self.assertFalse(self.controller.window.isVisible())

    # -- 3: placement across resizes, corners and saved positions --
    def test_growth_near_edge_stays_on_monitor(self):
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        window = self.controller.window
        area = _APP.primaryScreen().availableGeometry()
        window.move(area.right() - window.width() - 1,
                    area.bottom() - window.height() - 1)
        window.set_phase(br.BreakPhase.REMINDER, 0)
        frame = window.frameGeometry()
        self.assertTrue(area.contains(frame), f"{frame.getRect()} vs {area.getRect()}")

    def test_corner_change_moves_visible_window_and_clears_drag_pos(self):
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        engine = self.controller.engine
        window = self.controller.window
        engine._deadline = engine._clock() - 1
        self.controller._wake()
        self.assertTrue(window.isVisible())
        area = _APP.primaryScreen().availableGeometry()
        self.assertGreaterEqual(window.x(), area.right() - window.width() - 60)
        self.conf["break_corner"] = "bottom-left"
        self.controller.sync_from_conf()
        self.assertEqual(self.conf.get("break_pos"), [])
        self.assertTrue(window.isVisible())
        self.assertLess(window.x(), area.left() + 120)

    def test_saved_pos_beats_corner_until_corner_changes(self):
        area = _APP.primaryScreen().availableGeometry()
        saved = [area.left() + 200, area.top() + 200]
        self.conf["break_enabled"] = True
        self.conf["break_corner"] = "bottom-right"
        self.conf["break_pos"] = list(saved)
        self.controller.sync_from_conf()
        engine = self.controller.engine
        window = self.controller.window
        engine._deadline = engine._clock() - 1
        self.controller._wake()
        self.assertEqual([window.x(), window.y()], saved)

    # -- 4: native filter with the real PyQt6 event type --
    def _send_native(self, kind=None, **kwargs):
        filt = self.controller._power_filter
        self.assertIsNotNone(filt)
        if kind == "lock":
            msg, wparam = filt.WM_WTSSESSION_CHANGE, filt.WTS_SESSION_LOCK
        elif kind == "unlock":
            msg, wparam = filt.WM_WTSSESSION_CHANGE, filt.WTS_SESSION_UNLOCK
        elif kind == "suspend":
            msg, wparam = filt.WM_POWERBROADCAST, filt.PBT_APMSUSPEND
        elif kind == "resume":
            msg, wparam = filt.WM_POWERBROADCAST, filt.PBT_APMRESUMESUSPEND
        buf = _native_msg(wparam)
        buf.message = msg
        accepted, _ = filt.nativeEventFilter(
            QByteArray(b"windows_generic_MSG"), ctypes.addressof(buf))
        self.assertFalse(accepted)

    def test_native_filter_drives_controller_suspend_resume(self):
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        engine = self.controller.engine
        self._send_native("suspend")
        self.assertEqual(engine.phase, br.BreakPhase.PAUSED)
        self.assertTrue(self.controller._suspended)
        self._send_native("resume")
        self.assertEqual(engine.phase, br.BreakPhase.WORKING)
        self.assertFalse(self.controller._suspended)

    def test_lock_sleep_wake_unlock_runs_only_after_unlock(self):
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        engine = self.controller.engine
        before = engine.remaining()
        self._send_native("lock")
        self._send_native("suspend")
        self._send_native("resume")  # system woke, screen still locked
        self.assertEqual(engine.phase, br.BreakPhase.PAUSED,
                         "counter ran while the screen was still locked")
        self._send_native("unlock")
        self.assertEqual(engine.phase, br.BreakPhase.WORKING)
        self.assertGreaterEqual(engine.remaining(), before - 2)

    def test_manual_pause_survives_lock_cycle(self):
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        engine = self.controller.engine
        engine.pause()
        frozen = engine.remaining()
        self._send_native("lock")
        self._send_native("unlock")
        self.assertEqual(engine.phase, br.BreakPhase.PAUSED)
        self.assertEqual(engine.remaining(), frozen)

    # -- 5: corrupt config never breaks settings; paused durations stay sane --
    def test_paused_duration_change_keeps_progress(self):
        clock = FakeClock()
        engine = br.BreakEngine(clock=clock)
        engine.set_enabled(True, clock())
        clock.advance(60)
        engine.pause(clock())
        frozen = engine.remaining(clock())
        engine.apply_durations(30 * 60, 5 * 60, clock())
        self.assertEqual(engine.remaining(clock()), frozen + 5 * 60)
        engine.resume(clock())
        self.assertEqual(engine.phase, br.BreakPhase.WORKING)


class TestBreakSettingsLocation(unittest.TestCase):
    """Finding 6: break controls live inside the Settings tab, not a new tab."""

    def test_no_separate_break_tab(self):
        import settings_ui
        import inspect
        nav = inspect.getsource(settings_ui.SettingsWindow._build_navigation)
        self.assertNotIn("break_reminder", nav)
        general = inspect.getsource(settings_ui.SettingsWindow._general_tab)
        self.assertIn("break_enabled", general)


class TestBreakSettingsHardening(unittest.TestCase):
    """Finding 5 end to end: corrupt break values never break the window."""

    def setUp(self):
        import json
        import pathlib
        import tempfile
        from unittest import mock
        import settings_ui
        import localspeech
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        (root / "cfg").mkdir(parents=True, exist_ok=True)
        (root / "cfg" / "config.json").write_text(json.dumps({
            "break_enabled": True,
            "break_work_minutes": "soon",
            "break_break_minutes": -3,
            "break_snooze_minutes": [5],
            "break_corner": "top-left",
            "break_pos": "nowhere",
        }), encoding="utf-8")
        self.patchers = [
            mock.patch.object(cfg, "CONFIG_DIR", root / "cfg"),
            mock.patch.object(cfg, "CONFIG_FILE", root / "cfg" / "config.json"),
            mock.patch.object(cfg, "DATA_DIR", root / "data"),
            mock.patch.object(cfg, "HISTORY_FILE", root / "data" / "history.jsonl"),
            mock.patch.object(cfg, "MEETINGS_DIR", root / "data" / "meetings"),
            mock.patch.object(cfg, "MEETINGS_FILE", root / "data" / "meetings.jsonl"),
            mock.patch.object(cfg.credential_store, "read", return_value=""),
            mock.patch.object(cfg.credential_store, "read_all", return_value=[]),
            mock.patch.object(cfg.credential_store, "write_all"),
            mock.patch.object(settings_ui.audio, "list_sources", return_value=[]),
            mock.patch.object(settings_ui.audio, "refresh_devices"),
            mock.patch.object(settings_ui.audio, "list_monitors", return_value=[]),
            mock.patch.object(settings_ui.startup, "is_enabled", return_value=True),
            mock.patch.object(settings_ui.startup, "set_enabled"),
            mock.patch.object(localspeech.vulkan_speech, "available", return_value=False),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.addCleanup(self._stop)
        import settings_ui as sui
        self.window = sui.SettingsWindow(cfg.Config(), "wordarc toggle")

    def _stop(self):
        for patcher in self.patchers:
            patcher.stop()

    def test_corrupt_values_fall_back_to_safe_defaults(self):
        window = self.window
        self.assertTrue(window.break_enabled.isChecked())
        self.assertEqual(window.break_work.value(), 25)
        self.assertEqual(window.break_break.value(), 5)
        self.assertFalse(hasattr(window, "break_snooze"))
        self.assertEqual(window.break_corner.currentData(), "bottom-right")

    def test_break_card_saves_and_reloads(self):
        window = self.window
        self.assertIn("settings", window._tab_index)
        window.break_work.setValue(45)
        window.break_corner.setCurrentIndex(
            window.break_corner.findData("bottom-left"))
        self.assertTrue(window._save(quiet=True))
        self.assertEqual(window.conf["break_work_minutes"], 45)
        self.assertEqual(window.conf["break_corner"], "bottom-left")


class TestTraySettingsConsistency(unittest.TestCase):
    """Tray toggles while the settings window is open must stick.

    Real SettingsWindow + real BreakController + the real
    ``WordArc._toggle_break``; only the WordArc shell itself is a stub.
    """

    def setUp(self):
        import pathlib
        import tempfile
        from unittest import mock
        import settings_ui
        import localspeech
        import wordarc
        self._wordarc = wordarc
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = pathlib.Path(self.tmp.name)
        self.patchers = [
            mock.patch.object(cfg, "CONFIG_DIR", root / "cfg"),
            mock.patch.object(cfg, "CONFIG_FILE", root / "cfg" / "config.json"),
            mock.patch.object(cfg, "DATA_DIR", root / "data"),
            mock.patch.object(cfg, "HISTORY_FILE", root / "data" / "history.jsonl"),
            mock.patch.object(cfg, "MEETINGS_DIR", root / "data" / "meetings"),
            mock.patch.object(cfg, "MEETINGS_FILE", root / "data" / "meetings.jsonl"),
            mock.patch.object(cfg.credential_store, "read", return_value=""),
            mock.patch.object(cfg.credential_store, "read_all", return_value=[]),
            mock.patch.object(cfg.credential_store, "write_all"),
            mock.patch.object(settings_ui.audio, "list_sources", return_value=[]),
            mock.patch.object(settings_ui.audio, "refresh_devices"),
            mock.patch.object(settings_ui.audio, "list_monitors", return_value=[]),
            mock.patch.object(settings_ui.startup, "is_enabled", return_value=True),
            mock.patch.object(settings_ui.startup, "set_enabled"),
            mock.patch.object(localspeech.vulkan_speech, "available", return_value=False),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.addCleanup(self._stop)
        self.conf = cfg.Config()
        self.conf["break_enabled"] = True
        self.window = settings_ui.SettingsWindow(self.conf, "wordarc toggle")
        self.controller = wordarc.WordArc.__new__(wordarc.WordArc)
        self.controller.conf = self.conf
        self.controller.app = mock.Mock()
        self.controller.tray = mock.Mock()
        self.controller.tts = mock.Mock()
        self.controller.tts.busy = False
        self.controller.state = wordarc.IDLE
        self.controller.meeting_state = wordarc.M_IDLE
        self.controller.meeting_message = ""
        for name in ("_toggle", "cancel", "_toggle_meeting", "cancel_meeting",
                     "_take_screenshot", "open_settings", "restart"):
            setattr(self.controller, name, mock.Mock())
        self.controller.breaks = br.BreakController(self.conf)
        self.controller.breaks.sync_from_conf()
        self.controller.settings_window = self.window
        self.controller._build_tray()
        self.controller._refresh_tray()
        self.addCleanup(self._teardown_widgets)

    def _stop(self):
        for patcher in self.patchers:
            patcher.stop()

    def _teardown_widgets(self):
        self.controller.breaks.shutdown()
        self.controller.breaks.window.deleteLater()
        self.controller.breaks.deleteLater()
        self.window.deleteLater()

    def test_tray_off_then_save_keeps_it_off(self):
        self.assertTrue(self.window.break_enabled.isChecked())
        self.controller._toggle_break(False)
        self.assertFalse(self.window.break_enabled.isChecked())
        self.assertFalse(self.controller.break_action.isChecked())
        # An unrelated change, then Save: the tray's choice must survive.
        self.window.close_to_tray.setChecked(
            not self.window.close_to_tray.isChecked())
        self.assertTrue(self.window._save(quiet=True))
        self.assertIs(self.conf["break_enabled"], False)
        self.controller.breaks.sync_from_conf()
        self.assertEqual(self.controller.breaks.engine.phase, br.BreakPhase.OFF)

    def test_tray_on_then_save_keeps_it_on(self):
        self.conf["break_enabled"] = False
        self.controller.breaks.sync_from_conf()
        self.window.break_enabled.setChecked(False)
        self.controller._toggle_break(True)
        self.assertTrue(self.window.break_enabled.isChecked())
        self.assertTrue(self.controller.break_action.isChecked())
        self.window.close_to_tray.setChecked(
            not self.window.close_to_tray.isChecked())
        self.assertTrue(self.window._save(quiet=True))
        self.assertIs(self.conf["break_enabled"], True)
        self.controller.breaks.sync_from_conf()
        self.assertEqual(self.controller.breaks.engine.phase, br.BreakPhase.WORKING)

    def test_tray_pause_switch_hides_and_resumes(self):
        breaks = self.controller.breaks
        self.controller._toggle_break_pause(True)
        self.assertEqual(breaks.engine.phase, br.BreakPhase.PAUSED)
        self.assertFalse(breaks.window.isVisible())
        self.assertTrue(self.controller.break_pause_action.isChecked())
        self.controller._toggle_break_pause(False)
        self.assertEqual(breaks.engine.phase, br.BreakPhase.WORKING)
        self.assertFalse(self.controller.break_pause_action.isChecked())


class TestConfigDefaults(unittest.TestCase):
    def test_break_defaults(self):
        self.assertIs(cfg.DEFAULTS["break_enabled"], False)
        self.assertEqual(cfg.DEFAULTS["break_work_minutes"], 25)
        self.assertEqual(cfg.DEFAULTS["break_break_minutes"], 5)
        self.assertEqual(cfg.DEFAULTS["break_corner"], "bottom-right")
        self.assertEqual(cfg.DEFAULTS["break_pos"], [])

    def test_tr_covers_new_strings(self):
        table = i18n.TABLES["tr"]
        for key in ("Break reminder", "Time for a break", "Start the break",
                    "Snooze 1 min", "Snooze 5 min", "Snooze 10 min",
                    "Cancel", "Pause break timer", "Remind me to stand up",
                    "Work minutes", "Break minutes", "Corner"):
            self.assertIn(key, table, key)


if __name__ == "__main__":
    unittest.main()
