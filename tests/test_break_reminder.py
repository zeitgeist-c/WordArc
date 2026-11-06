"""Break reminder: deterministic engine tests (fake clock) + offscreen UI tests."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PyQt6.QtCore import Qt
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


def make_engine(work_min=25, break_min=5, snooze_min=5):
    clock = FakeClock()
    engine = br.BreakEngine(clock=clock)
    engine.work_s = work_min * 60
    engine.break_s = break_min * 60
    engine.snooze_s = snooze_min * 60
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

    def test_snooze(self):
        engine, clock = make_engine()
        engine.set_enabled(True, clock())
        clock.advance(25 * 60)
        engine.refresh(clock())
        self.assertTrue(engine.snooze(clock()))
        self.assertEqual(engine.phase, br.BreakPhase.WORKING)
        self.assertEqual(engine.remaining(clock()), 5 * 60)
        clock.advance(5 * 60)
        self.assertEqual(engine.refresh(clock()), ["reminder"])

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

    def test_end_break_starts_fresh_work(self):
        engine, clock = make_engine()
        engine.set_enabled(True, clock())
        clock.advance(25 * 60)
        engine.refresh(clock())
        engine.start_break(clock())
        clock.advance(60)
        self.assertTrue(engine.end_break(clock()))
        self.assertEqual(engine.phase, br.BreakPhase.WORKING)
        self.assertEqual(engine.remaining(clock()), 25 * 60)

    def test_apply_durations_keeps_progress(self):
        engine, clock = make_engine()
        engine.set_enabled(True, clock())
        clock.advance(60)
        engine.apply_durations(30 * 60, 5 * 60, 5 * 60, clock())
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

    def test_enable_shows_timer_disable_hides(self):
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        self.assertEqual(self.controller.engine.phase, br.BreakPhase.WORKING)
        self.assertTrue(self.controller.window.isVisible())
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
        self.assertEqual(window._stack.currentIndex(), 1)
        window._start_button.click()
        self.assertEqual(engine.phase, br.BreakPhase.BREAK)
        self.assertEqual(window._stack.currentIndex(), 0)

    def test_snooze_and_pause_buttons(self):
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        engine = self.controller.engine
        engine._deadline = engine._clock() - 1
        self.controller._wake()
        window = self.controller.window
        window._snooze_button.click()
        self.assertEqual(engine.phase, br.BreakPhase.WORKING)
        engine._deadline = engine._clock() - 1
        self.controller._wake()
        window._pause_button.click()
        self.assertEqual(engine.phase, br.BreakPhase.PAUSED)

    def test_window_never_takes_focus(self):
        window = self.controller.window
        self.assertTrue(window.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus)
        self.assertTrue(window.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))
        self.assertEqual(window.focusPolicy(), Qt.FocusPolicy.NoFocus)

    def test_screenshot_hide_restore(self):
        self.conf["break_enabled"] = True
        self.controller.sync_from_conf()
        self.assertTrue(self.controller.hide_for_capture())
        self.assertFalse(self.controller.window.isVisible())
        self.controller.restore_after_capture(True)
        self.assertTrue(self.controller.window.isVisible())
        # Disabled: hiding is a no-op and restores nothing.
        self.conf["break_enabled"] = False
        self.controller.sync_from_conf()
        self.assertFalse(self.controller.hide_for_capture())
        self.controller.restore_after_capture(False)
        self.assertFalse(self.controller.window.isVisible())

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


class TestConfigDefaults(unittest.TestCase):
    def test_break_defaults(self):
        self.assertIs(cfg.DEFAULTS["break_enabled"], False)
        self.assertEqual(cfg.DEFAULTS["break_work_minutes"], 25)
        self.assertEqual(cfg.DEFAULTS["break_break_minutes"], 5)
        self.assertEqual(cfg.DEFAULTS["break_snooze_minutes"], 5)
        self.assertEqual(cfg.DEFAULTS["break_corner"], "bottom-right")
        self.assertEqual(cfg.DEFAULTS["break_pos"], [])

    def test_tr_covers_new_strings(self):
        table = i18n.TABLES["tr"]
        for key in ("Break reminder", "Time for a break", "Start the break",
                    "Snooze {minutes} min", "Pause", "Remind me to stand up",
                    "Work minutes", "Break minutes", "Snooze minutes", "Corner"):
            self.assertIn(key, table, key)


if __name__ == "__main__":
    unittest.main()
