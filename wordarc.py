#!/usr/bin/env python3
"""WordArc: press Ctrl+Space, talk, press again to transcribe, clean up and paste.

Usage:
  wordarc.py             open Settings and keep the tray service running
  wordarc.py background  run in the background (Windows startup)
  wordarc.py toggle      start / stop recording
  wordarc.py cancel      discard the current recording
  wordarc.py meeting     start / end a meeting recording
  wordarc.py meeting-cancel  discard the meeting being recorded
  wordarc.py settings    open the settings window
  wordarc.py restart     reload the running instance
  wordarc.py quit        shut the application down
"""

import ctypes
import getpass
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

from brand import BRAND, set_windows_app_id

__version__ = BRAND.version

from PyQt6.QtCore import QObject, QTimer, QElapsedTimer, Qt, QRectF, pyqtSignal  # noqa: E402
from PyQt6.QtGui import (QAction, QBrush, QColor, QFont, QIcon,  # noqa: E402
                         QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                         QRadialGradient)
from PyQt6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PyQt6.QtWidgets import (QApplication, QMenu, QSplashScreen,
                             QSystemTrayIcon)  # noqa: E402

import audio  # noqa: E402
import config as cfg  # noqa: E402
import diagnostics  # noqa: E402
import hotkey  # noqa: E402
import meeting  # noqa: E402
import localspeech  # noqa: E402
from cuda_recovery import CudaRecovery  # noqa: E402
import operation  # noqa: E402
import brand_migration  # noqa: E402
import theme  # noqa: E402
import startup  # noqa: E402
from brand import brand_asset  # noqa: E402
import i18n  # noqa: E402
from i18n import t  # noqa: E402
import livespeech  # noqa: E402
import screenshot_capture  # noqa: E402
from meeting import MeetingPipeline  # noqa: E402
import overlay  # noqa: E402
from overlay import Overlay  # noqa: E402
from settings_ui import SettingsWindow, WindowView, install_qt_translator  # noqa: E402
from worker import Pipeline  # noqa: E402

SERVER_NAME = BRAND.ipc_name(getpass.getuser())
LEGACY_SERVER_NAME = BRAND.legacy_ipc_name(getpass.getuser())
SERVER_NAMES = (SERVER_NAME, LEGACY_SERVER_NAME)

# Flag the replacement process carries after an in-app restart. The old
# instance is still quitting while the child boots, so the child must not
# hand a command to it (it would talk to the dying instance and exit,
# leaving nothing running) and must not replay the launch command either.
RESTART_FLAG = "--restarted"

# One-shot commands a restarted child must never replay: booting straight
# into one would make the fresh instance act on a stale request — or exit
# outright, which is what a restart looked like when it silently killed
# the app instead of reloading it.
_ONE_SHOT_COMMANDS = frozenset((
    "toggle", "cancel", "settings", "restart", "quit", "start", "stop",
    "background", "ask", "ask-reset", "ask-cancel", "meeting",
    "meeting-cancel",
))


def _restart_args(argv):
    """Argv for the replacement process: flags kept, commands dropped."""
    kept = [a for a in argv[1:]
            if a.startswith("-") and a != RESTART_FLAG]
    return kept + [RESTART_FLAG]

# The socket check in main() loses a race when two launches land in the same
# instant: neither finds the other's socket, and both go on to serve. A named
# mutex decides the owner instead. "Local\" keeps it to this logon session, the
# same reach the sockets have.
SINGLETON_MUTEX = f"Local\\{BRAND.slug}-single-instance"
ERROR_ALREADY_EXISTS = 183
_instance_mutex = None


def _acquire_instance_mutex(name=None):
    """True when this process owns the instance; False when another one does.

    Any failure to create the mutex counts as "mine", so a mutex problem can
    never stop the app from starting.
    """
    global _instance_mutex
    if os.name != "nt":
        return True
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                          ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel32.CreateMutexW(None, 0, name or SINGLETON_MUTEX)
    except OSError:
        return True
    if not handle:
        return True
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _instance_mutex = (kernel32, handle)
    return True


def _release_instance_mutex():
    """Hand the instance over, so a restarted copy can take it."""
    global _instance_mutex
    if _instance_mutex is None:
        return
    kernel32, handle = _instance_mutex
    _instance_mutex = None
    try:
        kernel32.CloseHandle(handle)
    except OSError:
        pass
IDLE, RECORDING, BUSY = "idle", "recording", "busy"
# A meeting runs alongside dictation rather than through it: writing up an hour
# of audio takes minutes, and dictation should not be held hostage to it.
M_IDLE, M_RECORDING, M_WORKING = "idle", "recording", "working"


class _LiveOpener(QObject):
    """Open a live session off the GUI thread; report back through signals."""

    opened = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, keys, mode, parent=None):
        super().__init__(parent)
        self._keys = list(keys)
        self._mode = mode

    def run(self):
        try:
            session = livespeech.LiveSession.open_with_keys(
                self._keys, self._mode)
        except livespeech.LiveError as exc:
            self.failed.emit(str(exc))
            return
        self.opened.emit(session)


class _LiveFinisher(QObject):
    """Finish a live session off the GUI thread; hand over the transcript."""

    ready = pyqtSignal(str, float, object, str)
    failed = pyqtSignal(str, str)

    def __init__(self, session, duration, rms_values, operation_id,
                 parent=None):
        super().__init__(parent)
        self._session = session
        self._duration = duration
        self._rms = list(rms_values)
        self._operation_id = operation_id

    def run(self):
        try:
            text = self._session.finish()
        except livespeech.LiveError as exc:
            self.failed.emit(str(exc), self._operation_id)
            return
        self.ready.emit(text, self._duration, self._rms, self._operation_id)


class _UpdateWorker(QObject):
    """Ask the public release repo off the GUI thread; report via signals."""

    checked = pyqtSignal(object)        # UpdateInfo or None (already latest)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int)     # bytes done, bytes total
    installed = pyqtSignal(str, str)    # version, new exe path

    def __init__(self, current, parent=None):
        super().__init__(parent)
        self._current = current
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def run(self):
        import update as update_mod
        try:
            info = update_mod.check_for_update(self._current)
        except update_mod.UpdateError as exc:
            self.failed.emit(str(exc))
            return
        self.checked.emit(info)

    def install(self, info):
        import update as update_mod
        dest = update_mod.install_path(Path(sys.executable), info.version)
        try:
            update_mod.download(info, dest, progress=self._progress,
                                cancel=self._cancel)
        except update_mod.UpdateError as exc:
            if str(exc) == "cancelled":
                logging.getLogger("wordarc.update").info(
                    "update download cancelled")
                return
            self.failed.emit(str(exc))
            return
        self.installed.emit(info.version, str(dest))

    def _progress(self, done, total):
        # Coalesce: one emit per megabyte keeps the GUI thread free.
        if done % (1024 * 1024) < 256 * 1024 or done == total:
            self.progress.emit(done, total)


class WordArc:
    def __init__(self, app, conf=None):
        self.app = app
        self.conf = conf or cfg.Config()
        self.cuda_recovery = CudaRecovery(self.conf)
        self.state = IDLE
        self.dictation_operation = operation.OperationController()
        self.meeting_operation = operation.OperationController()
        self.meeting_state = M_IDLE
        self.meeting_base = ""
        self.meeting_message = ""
        self.settings_window = None
        self._settings_view = None
        self._last_dictation = ""
        self._quitting = False

        overlay.set_meter(self.conf.get("overlay_meter") or "spectrum")
        self.overlay = Overlay(self.conf["overlay_corner"])
        self.recorder = audio.Recorder()
        self.pipeline = Pipeline(self.conf)
        self.meeting_recorder = audio.MeetingRecorder()
        self.meetings = MeetingPipeline(self.conf)
        self.evdev = hotkey.EvdevHotkey()
        self.cancel_hotkey = hotkey.EvdevHotkey()

        self.recorder.level.connect(self._on_level)
        self.recorder.stopped.connect(self._on_recorded)
        self.recorder.failed.connect(self._on_recorder_error)
        self.live_streamer = audio.LiveStreamer()
        self.live_streamer.chunk.connect(
            self._on_live_chunk, Qt.ConnectionType.QueuedConnection)
        # The meter: without this the ribbon sits flat through a whole live
        # dictation — the capture was reading levels and nobody was listening.
        self.live_streamer.level.connect(
            self._on_level, Qt.ConnectionType.QueuedConnection)
        self.live_streamer.failed.connect(self._on_live_stream_error)
        self.live_session = None
        self.live_keys = []
        self.live_start_slot = 0
        self._live_opener = None
        self._live_finisher = None
        self._finishing_session = None
        self.live_timer = QTimer()
        self.live_timer.setInterval(200)
        self.live_timer.timeout.connect(self._live_poll)
        self.pipeline.stage.connect(self._on_dictation_stage)
        self.pipeline.finished.connect(self._on_finished)
        self.pipeline.failed.connect(self._on_error)
        self.meeting_recorder.levels.connect(self._on_meeting_levels)
        self.meeting_recorder.stopped.connect(self._on_meeting_recorded)
        self.meeting_recorder.died.connect(self._on_meeting_died)
        self.meeting_recorder.limit_reached.connect(self.stop_meeting)
        self.meeting_recorder.failed.connect(self._on_meeting_error)
        self.meetings.progress.connect(self._on_meeting_progress)
        self.meetings.finished.connect(self._on_meeting_finished)
        self.meetings.failed.connect(self._on_meeting_failed)
        self.evdev.triggered.connect(self._on_hotkey)
        self.evdev.failed.connect(self._on_error)
        self.cancel_hotkey.triggered.connect(self._on_cancel_key)

        self.elapsed = QElapsedTimer()
        self.meeting_elapsed = QElapsedTimer()
        self.last_toggle = QElapsedTimer()
        self.ticker = QTimer()
        self.ticker.setInterval(100)
        self.ticker.timeout.connect(self._tick)
        self.meeting_ticker = QTimer()
        self.meeting_ticker.setInterval(500)
        self.meeting_ticker.timeout.connect(self._meeting_tick)

        self.tray = QSystemTrayIcon()
        self.tray.activated.connect(self._tray_clicked)
        # Once a day, quietly: a frozen install asks the public release repo
        # for the newest tag and only then knocks on the tray. The timer fires
        # the check on its own thread, so a slow network never slows boot.
        self._update_thread = None
        self._update_cancel = threading.Event()
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._update_startup_check)
        self._update_timer.start(30_000)
        self.screenshot_controller = screenshot_capture.ScreenshotController(
            self.conf, self.settings_window)
        self.screenshot_controller.failed.connect(self._on_screenshot_failed)
        self.screenshot_controller.preferences_saved.connect(
            self._on_screenshot_preferences_saved)
        self.screenshot_controller.ocr_done.connect(self._on_screenshot_ocr)
        self._apply_settings()
        self.tray.show()

    # ---- tray ----------------------------------------------------------

    def _build_tray(self):
        # Keep menu and actions on self: PyQt does not take ownership when they
        # are only passed to addAction(), and garbage collection eats them.
        self.menu = QMenu()
        self.toggle_action = QAction(t("Start recording"), self.menu)
        self.toggle_action.triggered.connect(self._toggle)
        self.menu.addAction(self.toggle_action)

        self.cancel_action = QAction(t("Cancel recording"), self.menu)
        self.cancel_action.triggered.connect(self.cancel)
        self.cancel_action.setEnabled(False)
        self.menu.addAction(self.cancel_action)
        self.menu.addSeparator()

        self.meeting_action = QAction(t("Record a meeting"), self.menu)
        self.meeting_action.triggered.connect(self._toggle_meeting)
        self.menu.addAction(self.meeting_action)

        self.meeting_cancel_action = QAction(t("Discard the meeting"), self.menu)
        self.meeting_cancel_action.triggered.connect(self.cancel_meeting)
        self.meeting_cancel_action.setEnabled(False)
        self.menu.addAction(self.meeting_cancel_action)
        self.menu.addSeparator()

        self.screenshot_action = QAction(t("Capture screenshot"), self.menu)
        self.screenshot_action.triggered.connect(self._take_screenshot)
        self.menu.addAction(self.screenshot_action)
        self.menu.addSeparator()

        self.settings_action = QAction(t("Settings…"), self.menu)
        self.settings_action.triggered.connect(self.open_settings)
        self.menu.addAction(self.settings_action)

        self.restart_action = QAction(t("Restart"), self.menu)
        self.restart_action.triggered.connect(self.restart)
        self.menu.addAction(self.restart_action)
        self.menu.addSeparator()

        self.quit_action = QAction(t("Quit"), self.menu)
        self.quit_action.triggered.connect(self.app.quit)
        self.menu.addAction(self.quit_action)

        self.tray.setContextMenu(self.menu)
        self.tray.setToolTip(t("WordArc: ready"))
        self._set_icon("audio-input-microphone")

    def _tray_clicked(self, reason):
        # A left click opens the window; recording starts from the hotkey or
        # the right-click menu. Booting a take on a stray click surprised the
        # user more often than it helped.
        if reason != QSystemTrayIcon.ActivationReason.Trigger:
            return
        self.open_settings()

    def _set_icon(self, name):
        import trayicon
        self.tray.setIcon(trayicon.icon(name if name else "audio-input-microphone"))

    # ---- state ----------------------------------------------------------

    @property
    def recording(self):
        return self.state == RECORDING

    def _set_state(self, state):
        self.state = state
        self._sync_workspace()
        self._refresh_cancel_hotkey()
        self._refresh_tray()

    def _refresh_cancel_hotkey(self):
        # Escape must only be global while something is recording. Keeping it
        # registered while idle would swallow Escape in every other program.
        if self.state == RECORDING or self.meeting_state == M_RECORDING:
            self.cancel_hotkey.start({"cancel": "Escape"})
        else:
            self.cancel_hotkey.stop()

    def _on_cancel_key(self, _name):
        if self.recording:
            self.cancel()
        elif self.meeting_state == M_RECORDING:
            self.cancel_meeting()

    def _set_meeting_state(self, state):
        self.meeting_state = state
        if state != M_WORKING:
            self.meeting_message = ""
        self._sync_workspace()
        self._refresh_cancel_hotkey()
        self._refresh_tray()

    def _refresh_tray(self):
        labels = {
            IDLE: ("Start recording", "audio-input-microphone", "WordArc: ready"),
            RECORDING: ("Stop and transcribe", "media-record", "WordArc: recording"),
            BUSY: ("Working…", "view-refresh", "WordArc: working"),
        }
        label, icon, tip = labels[self.state]
        self.toggle_action.setText(t(label))
        self.toggle_action.setEnabled(self.state != BUSY)
        self.cancel_action.setEnabled(self.recording)

        meeting_labels = {
            M_IDLE: "Record a meeting",
            M_RECORDING: "End the meeting and write it up",
            M_WORKING: "Writing the meeting up…",
        }
        self.meeting_action.setText(t(meeting_labels[self.meeting_state]))
        self.meeting_action.setEnabled(self.meeting_state != M_WORKING)
        self.meeting_cancel_action.setEnabled(self.meeting_state == M_RECORDING)

        # A meeting speaks last: it runs for an hour and then works for minutes,
        # so it would otherwise own the icon for most of the day.
        if self.state == IDLE and self.meeting_state != M_IDLE:
            if self.meeting_state == M_RECORDING:
                icon, tip = "media-record", t("WordArc: in a meeting")
            else:
                icon = "view-refresh"
                tip = self.meeting_message or t("WordArc: writing the meeting up")
            self._set_icon(icon)
            self.tray.setToolTip(tip)
            return
        self._set_icon(icon)
        self.tray.setToolTip(t(tip))

    # ---- actions ---------------------------------------------------------

    def toggle(self):
        """A toggle from outside this process: the KDE shortcut, or the CLI."""
        self._external("toggle", self._toggle)

    def toggle_meeting(self):
        self._external("meeting", self._toggle_meeting)

    def _external(self, name, handler):
        # RegisterHotKey is the single shortcut path on Windows and never echoes.
        handler()

    def _on_hotkey(self, name):
        handlers = {
            "meeting": self._toggle_meeting,
            "screenshot": self._take_screenshot,
        }
        handlers.get(name, self._toggle)()

    def _take_screenshot(self, *_):
        self.screenshot_controller.start("region", self.settings_window)

    def _on_screenshot_failed(self, message):
        logging.getLogger("wordarc.screenshot").warning("capture failed: %s", message)
        if self.tray.isVisible():
            self.tray.showMessage(BRAND.name, message,
                                  QSystemTrayIcon.MessageIcon.Warning, 5000)

    def _on_screenshot_ocr(self, text):
        # Queued in from the OCR worker thread; safe on the GUI thread.
        if not text:
            self._on_screenshot_failed(t("No readable text found in the capture."))
            return
        QApplication.clipboard().setText(text)
        if self.tray.isVisible():
            self.tray.showMessage(BRAND.name, t("Text extracted — copied to the clipboard."),
                                  QSystemTrayIcon.MessageIcon.Information, 4000)

    def _on_screenshot_preferences_saved(self, directory, image_format):
        window = self.settings_window
        if window is not None:
            window.screenshot_directory.setText(directory)
            window._select_data(window.screenshot_format, image_format)

    def _toggle(self):
        # Two /dev/input nodes can carry the same keyboard, and a menu click can
        # land on top of a key press; swallow the immediate repeat.
        if self._repeated():
            return
        if self.state == RECORDING:
            self.stop()
        elif self.state == IDLE:
            self.start()
        # a request during its own BUSY is ignored; nothing queues up

    def _repeated(self):
        if self.last_toggle.isValid() and self.last_toggle.elapsed() < 400:
            return True
        self.last_toggle.restart()
        return False

    def start(self):
        if self.state != IDLE:
            return
        self.dictation_operation.begin()
        if self._live_engine():
            self._start_live()
            return
        self.overlay.show_recording()
        if not self._begin_recording():
            if self.dictation_operation.state == operation.State.RECORDING:
                self.dictation_operation.transition(operation.State.FAILED)
                self.dictation_operation.transition(operation.State.IDLE)
            return
        self._set_state(RECORDING)

    def _live_engine(self):
        """Whether dictation streams through Gemini Live right now."""
        try:
            return self.conf.get("transcribe_engine", "cloud") == "live"
        except Exception:
            return False

    def _start_live(self):
        """Open the live session off the GUI thread, then stream the mic."""
        self.overlay.show_recording()
        self.elapsed.restart()
        self.ticker.start()
        keys = self.conf.gemini_keys()
        start = self.conf.claim_api_slot(len(keys))
        ordered = keys[start:] + keys[:start] if keys else []
        self.live_keys = list(keys)
        self.live_start_slot = start
        mode = self.conf.get("live_transcription_mode", "smart") or "smart"
        self._live_opener = _LiveOpener(ordered, mode)
        self._live_opener.opened.connect(self._on_live_opened)
        self._live_opener.failed.connect(self._on_live_open_failed)
        self._set_state(RECORDING)
        threading.Thread(target=self._live_opener.run, daemon=True).start()

    def _on_live_opened(self, session):
        if self.state != RECORDING:
            session.cancel()
            return
        self.live_session = session
        self.live_streamer.start(self.conf["mic_target"],
                                 self.conf["max_seconds"])
        if not self.live_streamer.active:
            return  # start() has already said what went wrong
        self.live_timer.start(200)

    def _on_live_open_failed(self, message):
        self._live_opener = None
        self.ticker.stop()
        self._on_error(message, self.dictation_operation.operation_id)

    def _on_live_chunk(self, pcm):
        session = self.live_session
        if session is not None:
            session.push(pcm)

    def _on_live_stream_error(self, message):
        session, self.live_session = self.live_session, None
        if session is not None:
            session.cancel()
        self.live_timer.stop()
        self.ticker.stop()
        self._on_error(message, self.dictation_operation.operation_id)

    def _live_poll(self):
        session = self.live_session
        if session is None or self.state != RECORDING:
            return
        self.overlay.show_live_text(session.preview())
        if session.limit_hit.is_set():
            self.stop()

    def _begin_recording(self):
        self.elapsed.restart()
        self.ticker.start()
        self.recorder.start(self.conf["mic_target"], self.conf["max_seconds"])
        return self.recorder.active

    def stop(self):
        if self.state != RECORDING:
            return
        if self._live_engine():
            self._stop_live()
            return
        self.ticker.stop()
        self.dictation_operation.transition(operation.State.PROCESSING)
        self._set_state(BUSY)
        self.overlay.show_busy(t("Transcribing…"))
        self.recorder.stop()

    def _live_slot(self, session):
        """Absolute rotation slot the live session spoke with."""
        total = len(self.live_keys)
        if total <= 0:
            return 0, 0
        index = getattr(session, "key_index", 0) or 0
        return (self.live_start_slot + index) % total, total

    def _stop_live(self):
        self.ticker.stop()
        self.live_timer.stop()
        self.dictation_operation.transition(operation.State.PROCESSING)
        self._set_state(BUSY)
        session, self.live_session = self.live_session, None
        self._live_opener = None
        operation_id = self.dictation_operation.operation_id
        if session is None:
            # Still connecting, or nothing captured: a late opener lands in
            # _on_live_opened, sees no RECORDING and cancels the session.
            self.dictation_operation.transition(operation.State.CANCELLED)
            self.dictation_operation.transition(operation.State.IDLE)
            self.overlay.dismiss()
            self._set_state(IDLE)
            return
        self.overlay.show_busy(t("Finishing live transcription…"))
        result = self.live_streamer.stop()
        if result is None:
            # Too short or already cancelled: the streamer has said so
            # through its failed signal; only settle the API rotation here.
            session.cancel()
            slot, total = self._live_slot(session)
            if total:
                self.conf.record_api_attempt(slot, total)
            return
        duration, rms_values = result
        self._finishing_session = session
        self._live_finisher = _LiveFinisher(session, duration, rms_values,
                                           operation_id)
        self._live_finisher.ready.connect(self._on_live_ready)
        self._live_finisher.failed.connect(self._on_live_failed)
        threading.Thread(target=self._live_finisher.run, daemon=True).start()

    def _on_live_ready(self, text, duration, rms_values, operation_id):
        self._live_finisher = None
        session, self._finishing_session = self._finishing_session, None
        slot, total = self._live_slot(session)
        if total:
            self.conf.record_api_success(slot, total)
        self.pipeline.run_transcript(text, duration, rms_values, operation_id,
                                     start_slot=self.live_start_slot)

    def _on_live_failed(self, message, operation_id):
        self._live_finisher = None
        session, self._finishing_session = self._finishing_session, None
        slot, total = self._live_slot(session)
        if total:
            self.conf.record_api_attempt(slot, total)
        self._on_error(message, operation_id)

    def cancel(self):
        """Throw away the current dictation recording."""
        if not self.recording:
            return
        if self._live_engine():
            self._cancel_live()
            return
        self.ticker.stop()
        self.recorder.cancel()
        self.dictation_operation.transition(operation.State.CANCELLED)
        self.dictation_operation.transition(operation.State.IDLE)
        self.overlay.dismiss()
        self._set_state(IDLE)

    def _cancel_live(self):
        """Abort a live dictation: session, capture and timers all go."""
        self.ticker.stop()
        self.live_timer.stop()
        self._live_opener = None
        self._live_finisher = None
        session, self.live_session = self.live_session, None
        if session is not None:
            session.cancel()
        self.live_streamer.cancel()
        self._finishing_session = None
        self.dictation_operation.transition(operation.State.CANCELLED)
        self.dictation_operation.transition(operation.State.IDLE)
        self.overlay.dismiss()
        self._set_state(IDLE)

    def _on_level(self, level):
        self.overlay.push_level(level)

    def _tick(self):
        seconds = self.elapsed.elapsed() / 1000.0
        self.overlay.set_seconds(seconds)
        if self.live_session is not None and self.live_session.limit_hit.is_set():
            self.stop()
            return
        if seconds >= self.conf["max_seconds"]:
            self.stop()

    # ---- meetings ---------------------------------------------------------

    def _toggle_meeting(self):
        if self.meeting_state == M_IDLE:
            self.start_meeting()
        elif self.meeting_state == M_RECORDING:
            self.stop_meeting()

    def start_meeting(self):
        if self.meeting_state != M_IDLE:
            return
        self.meeting_operation.begin()
        base = meeting.new_base()
        _, wav_path = cfg.meeting_paths(base)
        self.meeting_recorder.start(
            str(wav_path),
            self.conf["meeting_mic_target"] or self.conf["mic_target"],
            self.conf["meeting_system_target"],
            self.conf["meeting_max_seconds"],
        )
        if not self.meeting_recorder.active:
            if self.meeting_operation.state == operation.State.RECORDING:
                self.meeting_operation.transition(operation.State.FAILED)
                self.meeting_operation.transition(operation.State.IDLE)
            return  # start() has already said what went wrong
        self.meeting_base = base
        self.meeting_elapsed.restart()
        self.meeting_ticker.start()
        self.overlay.show_meeting()
        self._set_meeting_state(M_RECORDING)

    def stop_meeting(self):
        if self.meeting_state != M_RECORDING:
            return
        self.meeting_ticker.stop()
        self.meeting_operation.transition(operation.State.PROCESSING)
        self._set_meeting_state(M_WORKING)
        self.overlay.show_busy(t("Ending the meeting…"))
        self.meeting_recorder.stop()

    def cancel_meeting(self):
        if self.meeting_state != M_RECORDING:
            return
        self.meeting_ticker.stop()
        self.meeting_recorder.cancel()
        self.meeting_operation.transition(operation.State.CANCELLED)
        self.meeting_operation.transition(operation.State.IDLE)
        if self.overlay.state == "meeting":
            self.overlay.dismiss()
        self._set_meeting_state(M_IDLE)

    def _on_meeting_levels(self, mine, theirs):
        self.overlay.push_levels(mine, theirs)

    def _meeting_tick(self):
        seconds = self.meeting_elapsed.elapsed() / 1000.0
        if self.overlay.state == "meeting":
            self.overlay.set_seconds(seconds)
        if self.state == IDLE:
            self.tray.setToolTip(
                t("WordArc: in a meeting ({time})", time=_clock(seconds))
            )
        if seconds >= self.conf["meeting_max_seconds"]:
            self.stop_meeting()

    def _on_meeting_recorded(self, path, duration):
        entry = meeting.new_entry(self.meeting_base, duration)
        try:
            cfg.save_meeting(entry)
        except OSError as exc:
            self._on_meeting_failed(entry["base"], str(exc))
            return
        # On the way out there is no time to write anything up; the recording is
        # on disk and listed, and the Meeting tab can pick it up next time.
        if self._quitting:
            return
        if not self.meetings.run(entry):
            self.meeting_operation.transition(operation.State.FAILED)
            self.meeting_operation.transition(operation.State.IDLE)
            self._set_meeting_state(M_IDLE)
            self.tray.showMessage(
                "WordArc",
                t("Recording saved. The previous meeting is still being written "
                  "up, so start this one from Settings → Meeting when it is done."),
                QSystemTrayIcon.MessageIcon.Information, 10000,
            )
            return
        self.overlay.show_done(t("Meeting recorded, writing it up…"), 4000)

    def _on_meeting_progress(self, _base, message):
        if (self.meeting_operation.state in (operation.State.RECORDING,
                                              operation.State.PROCESSING)
                and _base != self.meeting_base):
            return
        self.meeting_message = message
        self._sync_workspace()
        if self.state == IDLE and self.meeting_state == M_WORKING:
            self.tray.setToolTip(message)

    def _on_meeting_finished(self, base, title):
        if (self.meeting_operation.state in (operation.State.RECORDING,
                                              operation.State.PROCESSING)
                and base != self.meeting_base):
            return
        if self.meeting_operation.state == operation.State.PROCESSING:
            self.meeting_operation.transition(operation.State.COMPLETED)
            self.meeting_operation.transition(operation.State.IDLE)
        self._set_meeting_state(M_IDLE)
        doc_path, _ = cfg.meeting_paths(base)
        self.overlay.show_done(t("Meeting written up: {title}", title=title), 5000)
        self.tray.showMessage(
            t("WordArc: the meeting is written up"), f"{title}\n{doc_path}",
            QSystemTrayIcon.MessageIcon.Information, 10000,
        )

    def _on_meeting_failed(self, base, error):
        if (self.meeting_operation.state in (operation.State.RECORDING,
                                              operation.State.PROCESSING)
                and base != self.meeting_base):
            return
        if self.meeting_operation.state == operation.State.PROCESSING:
            self.meeting_operation.transition(operation.State.FAILED)
            self.meeting_operation.transition(operation.State.IDLE)
        self._set_meeting_state(M_IDLE)
        if self.settings_window is not None:
            self.settings_window.set_recording_state("meeting", M_IDLE, error)
        first_line = error.strip().splitlines()[0]
        self.overlay.show_error(t("Meeting failed: {error}", error=first_line))
        self.tray.showMessage(
            t("WordArc: the meeting could not be written up"),
            t("{error}\n\nThe recording has been kept. Settings → Meeting can "
              "try again.", error=error),
            QSystemTrayIcon.MessageIcon.Warning, 12000,
        )

    def _on_meeting_error(self, message):
        """The recorder itself could not run."""
        if self.meeting_operation.state in (operation.State.RECORDING,
                                             operation.State.PROCESSING):
            self.meeting_operation.transition(operation.State.FAILED)
            self.meeting_operation.transition(operation.State.IDLE)
        self.meeting_ticker.stop()
        if self.overlay.state == "meeting":
            self.overlay.dismiss()
        self._set_meeting_state(M_IDLE)
        self._report(message, self.overlay)

    def _on_meeting_died(self):
        if self.meeting_state != M_RECORDING:
            return
        self.tray.showMessage(
            "WordArc",
            t("The recording stopped on its own; the sound device may have gone "
              "away. Keeping what was captured."),
            QSystemTrayIcon.MessageIcon.Warning, 10000,
        )
        self.stop_meeting()

    def _on_recorded(self, wav_path, duration, rms_values):
        self.pipeline.run(
            wav_path, duration, rms_values,
            operation_id=self.dictation_operation.operation_id)

    def _on_dictation_stage(self, message, operation_id):
        if self.dictation_operation.accepts(operation_id):
            self.overlay.show_busy(message)
            if self.settings_window is not None:
                self.settings_window.set_recording_state("dictation", self.state, message)

    def _on_finished(self, _raw, text, warning, operation_id):
        if (self.dictation_operation.state != operation.State.PROCESSING
                or not self.dictation_operation.accepts(operation_id)):
            return
        self._last_dictation = text
        if self.settings_window is not None:
            self.settings_window.set_dictation_result(text)
        self.dictation_operation.transition(operation.State.COMPLETED)
        self.dictation_operation.transition(operation.State.IDLE)
        if warning:
            # The text was still pasted, but cleanup did not run. Say so loudly:
            # a rejected key otherwise looks exactly like working dictation.
            message = t("Copied raw, cleanup failed: {error}", error=warning.splitlines()[0]) if not self.conf["auto_paste"] else t("Pasted raw, cleanup failed: {error}", error=warning.splitlines()[0])
            self.overlay.show_warning(message)
            self.tray.showMessage(
                t("WordArc: cleanup failed"), warning,
                QSystemTrayIcon.MessageIcon.Warning, 10000,
            )
        else:
            action = t("Pasted") if self.conf["auto_paste"] else t("Copied")
            self.overlay.show_done(
                t("{action}: {preview}", action=action, preview=_preview(text))
            )
        self._set_state(IDLE)

    def _on_recorder_error(self, message):
        """Report a microphone failure through the dictation operation."""
        self.ticker.stop()
        self.recorder.cancel()
        self._on_error(message)

    def _on_error(self, message, operation_id=""):
        if operation_id and not self.dictation_operation.accepts(operation_id):
            return
        if self.dictation_operation.state in (operation.State.RECORDING,
                                               operation.State.PROCESSING):
            self.dictation_operation.transition(operation.State.FAILED)
            self.dictation_operation.transition(operation.State.IDLE)
        self._report(message, self.overlay)
        self._set_state(IDLE)
        if self.settings_window is not None:
            self.settings_window.set_recording_state("dictation", IDLE, message)

    def _report(self, message, overlay):
        logging.getLogger("wordarc.ui").warning("operation error: %s", message)
        first_line = message.strip().splitlines()[0]
        overlay.show_error(first_line)
        if len(message) > len(first_line):
            self.tray.showMessage("WordArc", message, QSystemTrayIcon.MessageIcon.Warning, 8000)

    # ---- settings ---------------------------------------------------------

    def _sync_workspace(self):
        window = getattr(self, "settings_window", None)
        if window is not None:
            window.set_recording_state("dictation", self.state)
            window.set_recording_state("meeting", self.meeting_state,
                                       getattr(self, "meeting_message", ""))

    def _window_record(self, kind):
        if kind == "dictation":
            if self.state == IDLE:
                self.start()
            elif self.state == RECORDING:
                self.stop()
        else:
            self._toggle_meeting()

    def _window_cancel(self, kind):
        if kind == "dictation":
            self.cancel()
        else:
            self.cancel_meeting()

    # ---- updates ---------------------------------------------------------

    def _updates_possible(self):
        """Update flow needs a real installed exe, not a source checkout."""
        return bool(getattr(sys, "frozen", False))

    def _update_startup_check(self):
        # The first silent check runs 30 s after boot; after that only once
        # per day, and never from a source checkout.
        if not self._updates_possible():
            return
        import update as update_mod
        stamp = str(self.conf.get("update_last_check", "") or "")
        if not update_mod.last_check_is_old(stamp):
            return
        self._run_update_check(tray=True)

    def _update_check(self):
        self._run_update_check(tray=False)

    def _run_update_check(self, tray):
        import update as update_mod
        if self._update_thread is not None and self._update_thread.is_alive():
            return
        if not self._updates_possible():
            if not tray and self.settings_window is not None:
                self.settings_window.show_update_error(
                    t("Updates are only available in the installed program."))
            return
        self._update_manual = not tray
        if not tray and self.settings_window is not None:
            self.settings_window.show_update_checking()
        worker = _UpdateWorker(BRAND.version)
        worker.checked.connect(self._update_checked)
        worker.failed.connect(self._update_failed)
        self._update_worker = worker
        self._update_thread = threading.Thread(target=worker.run, daemon=True)
        self._update_thread.start()

    def _update_checked(self, info):
        import update as update_mod
        self.conf["update_last_check"] = update_mod.now_stamp()
        try:
            self.conf.save()
        except OSError:
            pass
        manual = getattr(self, "_update_manual", False)
        window = self.settings_window
        if info is None:
            if manual and window is not None:
                window.show_update_latest()
            return
        if window is not None:
            window.show_update_available(info)
        elif self.tray.isVisible():
            self.tray.showMessage(
                BRAND.name,
                t("Version {version} is out. Check it from Settings ▸ Updates."
                  ).format(version=info.version),
                QSystemTrayIcon.MessageIcon.Information, 10000)

    def _update_failed(self, message):
        window = self.settings_window
        translated = t(message)
        if window is not None:
            window.show_update_error(translated)
        elif getattr(self, "_update_manual", False) and self.tray.isVisible():
            self.tray.showMessage(BRAND.name, translated,
                                  QSystemTrayIcon.MessageIcon.Warning, 8000)

    def _update_install(self):
        window = self.settings_window
        info = getattr(window, "_update_info", None) if window else None
        if info is None or not self._updates_possible():
            return
        worker = _UpdateWorker(BRAND.version)
        worker.progress.connect(self._update_progress)
        worker.failed.connect(self._update_failed)
        worker.installed.connect(self._update_installed)
        self._update_worker = worker
        self._update_thread = threading.Thread(target=worker.install,
                                               args=(info,), daemon=True)
        self._update_thread.start()
        if window is not None:
            window.show_update_installing()

    def _update_cancel_download(self):
        worker = getattr(self, "_update_worker", None)
        if worker is not None:
            worker.cancel()
        if self.settings_window is not None:
            self.settings_window.show_update_current()

    def _update_progress(self, done, total):
        if self.settings_window is not None:
            self.settings_window.show_update_progress(done, total)

    def _update_installed(self, version, new_exe):
        import update as update_mod
        if self.tray.isVisible():
            self.tray.showMessage(
                BRAND.name,
                t("Version {version} downloaded. WordArc is restarting.").format(
                    version=version),
                QSystemTrayIcon.MessageIcon.Information, 5000)
        update_mod.spawn_swap(os.getpid(), Path(new_exe))
        self.restart()

    def open_settings(self):
        if self.settings_window is None:
            self.settings_window = SettingsWindow(
                self.conf, launch_command(), meeting_command(), self.meetings,
            )
            self.settings_window.recording_requested.connect(self._window_record)
            self.settings_window.screenshot_requested.connect(
                lambda mode: self.screenshot_controller.start(
                    mode, self.settings_window))
            self.screenshot_controller.failed.connect(
                self.settings_window.screenshot_failed)
            self.settings_window.cancel_requested.connect(self._window_cancel)
            self.settings_window.shortcut_capture.connect(
                self._on_shortcut_capture)
            self.settings_window.set_dictation_result(self._last_dictation)
            self._sync_workspace()
            self.settings_window.applied.connect(self._apply_settings)
            self.settings_window.language_changed.connect(self._reopen_settings)
            self.settings_window.finished.connect(self._settings_closed)
            self.settings_window.update_check_requested.connect(
                self._update_check)
            self.settings_window.update_install_requested.connect(
                self._update_install)
            self.settings_window.update_cancel_requested.connect(
                self._update_cancel_download)
        # The language change rebuilds the window and hands over where the old
        # one was; it is applied before show(), so the window never appears at
        # its opening size first. It travels on the instance rather than in the
        # signature because the tray action hands this method its own
        # `checked` flag.
        view, self._settings_view = getattr(self, "_settings_view", None), None
        if view is not None:
            view.apply(self.settings_window)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def _reopen_settings(self):
        """Rebuild the settings window so the new language applies at once.

        The replacement is built before the old window goes away. Building one
        reaches PortAudio, and a build that fails — a device rescan in a bad
        library state, for one — used to leave a closed window and no new one:
        nothing on screen at all. When the rebuild does fail, the window the
        user already had stays up, and the new language arrives with the next
        open.
        """
        # Qt's own strings — the context menus of text fields, the buttons of
        # standard dialogs — come from its translator, which only the header
        # button used to install: a language saved from the Settings tab left
        # them in the old language. Every path goes through here.
        install_qt_translator(self.app, i18n.language())
        # The tray menu is drawn from the same string table, and nothing else
        # rebuilds it: without this it kept speaking the old language until the
        # next save.
        self._build_tray()
        self._refresh_tray()
        old = self.settings_window
        if old is None:
            # A language saved from the Settings tab arrives here a turn later,
            # and by then the window may already be closed: there is nothing to
            # rebuild, and opening one here would put back on screen a window
            # the user has just dismissed.
            return
        try:
            view = WindowView(old)
        except Exception:
            logging.getLogger("wordarc.ui").exception(
                "could not read the settings window state")
            view = None
        self._settings_view = view
        self.settings_window = None
        try:
            self.open_settings()
        except Exception:
            logging.getLogger("wordarc.ui").exception(
                "could not rebuild the settings window for the language change")
            self._settings_view = None
            self.settings_window = old
            self._sync_workspace()
            old.show()
            old.raise_()
            old.activateWindow()
            return
        # Blocked so close() does not trip _settings_closed (which would drop
        # the fresh window and could quit the app); closeEvent still stops a
        # running file transcription directly. The old window is freed a turn
        # later, because this runs inside its own signal.
        old.blockSignals(True)
        old.close()
        QTimer.singleShot(0, old.deleteLater)

    def _settings_closed(self, *_):
        # Don't drop the object while its own signal is still being delivered.
        window = self.settings_window

        def finish_close():
            # A window opened in between — a language change, the tray — is not
            # the one that closed: dropping the reference would lose it, and
            # the quit below would take the app down from under it.
            if self.settings_window is not window:
                return
            self.settings_window = None
            if not self._quitting:
                self._apply_hotkeys()
            if (not self._quitting
                    and (not self.conf["close_to_tray"]
                         or not QSystemTrayIcon.isSystemTrayAvailable())):
                self.app.quit()
        QTimer.singleShot(0, finish_close)

    def _on_shortcut_capture(self, active):
        """Park the global shortcuts while a shortcut field listens for keys.

        RegisterHotKey swallows its combinations everywhere, our own settings
        window included: without this, a field could never capture a
        combination that already belongs to an action. The shortcuts come
        back as soon as the field stops listening.
        """
        evdev = getattr(self, "evdev", None)
        if evdev is None:
            return
        if active:
            evdev.stop()
            cancel_hotkey = getattr(self, "cancel_hotkey", None)
            if cancel_hotkey is not None:
                cancel_hotkey.stop()
        else:
            self._apply_hotkeys()
            if getattr(self, "cancel_hotkey", None) is not None:
                self._refresh_cancel_hotkey()

    def _apply_hotkeys(self):
        evdev = getattr(self, "evdev", None)
        if evdev is None:
            return
        evdev.stop()
        evdev.start({"toggle": self.conf["shortcut"],
                          "meeting": self.conf["meeting_shortcut"],
                          "screenshot": self.conf.get("screenshot_shortcut", "")})

    def _apply_settings(self):
        theme.ThemeManager.apply(self.conf["theme_mode"], self.app)
        self.overlay.corner = self.conf["overlay_corner"]
        overlay.set_meter(self.conf.get("overlay_meter") or "spectrum")
        self._build_tray()
        self._refresh_tray()
        self._apply_hotkeys()

    def restart(self):
        """Replace this process with a fresh one, picking up code and settings.

        The child boots with no launch command: replaying the parent's
        (e.g. "restart" itself) made the replacement hand the command to the
        still-quitting old instance and exit, so the restart closed the app
        instead of reloading it.
        """
        if self.settings_window is not None:
            self.settings_window.close()
        self.shutdown()
        for name in SERVER_NAMES:
            QLocalServer.removeServer(name)
        # Hand the instance over before the replacement starts.
        _release_instance_mutex()
        child_args = _restart_args(sys.argv)
        if getattr(sys, "frozen", False):
            # Paketlenmiş onefile exe'de __file__ geçici _MEI klasörünü gösterir;
            # yeni süreç yalnız exe + kullanıcı argümanlarıyla başlatılmalı.
            subprocess.Popen([sys.executable] + child_args)
        else:
            subprocess.Popen([sys.executable, os.path.realpath(__file__)]
                             + child_args)
        self.app.quit()

    def shutdown(self):
        self._quitting = True
        self.screenshot_controller.shutdown()
        self.evdev.stop()
        self.cancel_hotkey.stop()
        self.pipeline.cancel()
        self.meetings.stop()
        if self.recording:
            self.recorder.cancel()
            if getattr(self, "_live_opener", None) is not None or \
                    getattr(self, "live_session", None) is not None:
                self._live_opener = None
                session, self.live_session = self.live_session, None
                if session is not None:
                    session.cancel()
                self.live_streamer.cancel()
                self.live_timer.stop()
        # A meeting in progress is closed properly rather than thrown away: the
        # WAV ends up valid and listed, ready to be written up after the restart.
        if self.meeting_state == M_RECORDING:
            self.meeting_ticker.stop()
            self.meeting_recorder.stop()
        self.overlay.dismiss()
        self.tray.hide()


def _preview(text):
    line = text.replace("\n", " ")
    return line[:48] + ("…" if len(line) > 48 else "")


def _clock(seconds):
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return (f"{hours}:{minutes:02d}:{secs:02d}" if hours
            else f"{minutes}:{secs:02d}")


def launch_command():
    """The command the global shortcut would run (kept for settings display)."""
    return f'"{sys.executable}" "{os.path.realpath(__file__)}" toggle'


def meeting_command():
    return f'"{sys.executable}" "{os.path.realpath(__file__)}" meeting'


SPLASH_WIDTH, SPLASH_HEIGHT = 460, 268


def _splash_pixmap(dpr):
    """Modern launch card painted from vector assets, HiDPI-crisp.

    Everything is drawn in logical pixels on a dpr-scaled pixmap, so a
    125/150% display gets a sharp card instead of an upscaled 256 px icon.
    Raises on missing assets; the caller degrades to no splash.
    """
    width, height = SPLASH_WIDTH, SPLASH_HEIGHT
    pixmap = QPixmap(round(width * dpr), round(height * dpr))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    paint = QPainter(pixmap)
    try:
        paint.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform)
        _paint_splash_card(paint, width, height)
    finally:
        paint.end()
    return pixmap


def _paint_splash_card(paint, width, height):
    from PyQt6.QtSvg import QSvgRenderer

    card = QPainterPath()
    card.addRoundedRect(QRectF(1, 1, width - 2, height - 2), 24, 24)
    paint.setClipPath(card)
    background = QLinearGradient(22, height - 28, width - 20, 20)
    background.setColorAt(0, QColor("#161C2E"))
    background.setColorAt(1, QColor("#090C12"))
    paint.setPen(QPen(QColor(255, 255, 255, 33), 1))
    paint.setBrush(QBrush(background))
    paint.drawRoundedRect(1, 1, width - 2, height - 2, 24, 24)
    glow = QRadialGradient(width - 90, 20, 150)
    glow.setColorAt(0, QColor(139, 92, 246, 89))
    glow.setColorAt(0.45, QColor(34, 211, 238, 31))
    glow.setColorAt(1, QColor(34, 211, 238, 0))
    paint.setPen(Qt.PenStyle.NoPen)
    paint.setBrush(QBrush(glow))
    paint.drawRect(0, 0, width, height)
    mark = QSvgRenderer(str(brand_asset("wordarc-mark.svg")))
    mark.render(paint, QRectF(36, (height - 104) / 2, 104, 104))
    name_font = QFont("Segoe UI")
    name_font.setWeight(QFont.Weight.Bold)
    name_font.setPixelSize(42)
    paint.setFont(name_font)
    paint.setPen(QColor("#F3F6FC"))
    paint.drawText(QRectF(164, 92, 270, 64),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   "WordArc")
    version_font = QFont("Segoe UI")
    version_font.setPixelSize(13)
    paint.setFont(version_font)
    paint.setPen(QColor("#8B93A7"))
    paint.drawText(QRectF(164, 158, 270, 24),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                   BRAND.version)


def _startup_splash(app):
    """A first pixel while the windowed app finishes starting.

    The onefile bundle spends most of its start unpacking before any Python
    runs, so this only covers the tail: imports are done, the tray and the
    settings window are not yet up. It still answers the question a second
    double-click asks — did the first one land? — next to the launcher guard
    that keeps that click from unpacking the bundle all over again. The card
    is painted from vector assets at the screen's native pixel ratio, so it
    stays sharp on scaled displays; any failure degrades to no splash.
    """
    try:
        screen = app.primaryScreen()
        dpr = screen.devicePixelRatio() if screen is not None else 1.0
        pixmap = _splash_pixmap(dpr)
    except Exception:
        return None
    splash = QSplashScreen(pixmap, Qt.WindowType.WindowStaysOnTopHint)
    splash.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    splash.showMessage(
        t("Starting WordArc…"),
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        QColor("white"))
    splash.show()
    app.processEvents()
    return splash


def send_command(command, timeout=800):
    """Hand a command to the running instance; False when there is none."""
    for name in SERVER_NAMES:
        socket = QLocalSocket()
        socket.connectToServer(name)
        if not socket.waitForConnected(timeout):
            continue
        socket.write(command.encode("utf-8"))
        socket.flush()
        socket.waitForBytesWritten(timeout)
        socket.disconnectFromServer()
        return True
    return False


def _should_open_settings(command, has_api_keys, tray_available):
    return (command in ("", "settings") or not has_api_keys
            or not tray_available)


def ensure_startup_registration(conf):
    """Create the Windows Run entry once when the setting says 'on'.

    Schema 5 made "start with Windows" the default, so an install that joined
    it through the migration must also register itself: the version just
    installed has to boot with the next sign-in. A box the user left off reads
    False and is never re-registered, and an existing entry is left untouched.
    """
    if not conf["start_with_windows"]:
        return False
    try:
        if startup.is_enabled():
            return False
        startup.set_enabled(True)
    except startup.StartupError as exc:
        logging.getLogger("wordarc.startup").warning(
            "Windows startup registration failed: %s", exc)
        return False
    return True


def main():
    if "--local-stt-check" in sys.argv:
        from local_stt_diagnostic import run
        return run(sys.argv[sys.argv.index("--local-stt-check") + 1:])
    startup_timer = QElapsedTimer()
    startup_timer.start()
    # Windows otherwise labels source-mode launches as pythonw.exe and shows
    # Python's icon in the taskbar even though Qt has a WordArc window icon.
    set_windows_app_id()
    try:
        migration = brand_migration.migrate(
            cfg.LEGACY_CONFIG_DIR, cfg.CONFIG_DIR,
            cfg.LEGACY_DATA_DIR, cfg.DATA_DIR,
        )
    except Exception as exc:
        # This runs before diagnostics.setup(), so anything that gets past the
        # migration leaves a start with no window and no log to say why. The
        # warning travels with the result and is logged below.
        migration = brand_migration.MigrationResult(
            warnings=(f"migration failed: {type(exc).__name__}",))
    diagnostics.setup()
    logging.getLogger("wordarc.startup").info(
        "starting WordArc v%s (%s) argv=%r", BRAND.version,
        "frozen" if getattr(sys, "frozen", False) else "source",
        sys.argv[1:])
    try:
        startup.ensure_current_command()
    except startup.StartupError as exc:
        logging.getLogger("wordarc.startup").warning("%s", exc)
    migration_log = logging.getLogger("wordarc.migration")
    if migration.copied_files or migration.credential_migrated:
        migration_log.info("legacy migration completed: files=%d credential=%s",
                           migration.copied_files, migration.credential_migrated)
    for warning in migration.warnings:
        migration_log.warning("legacy migration: %s", warning)
    # Support quick version check
    if "--version" in sys.argv:
        print(f"WordArc version {BRAND.version}")
        return 0
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    command = args[0] if args else ""
    restarted = RESTART_FLAG in sys.argv
    if restarted:
        # A replacement booting while the old instance quits: never hand a
        # command to it, and never replay a stale launch command — boot
        # normally instead.
        command = ""


    if command and command not in ("toggle", "cancel", "settings", "restart",
                                   "quit", "start", "stop", "background",
                                   "ask", "ask-reset",
                                   "ask-cancel", "meeting", "meeting-cancel"):
        print(__doc__)
        return 2

    app = QApplication(sys.argv)
    app.setApplicationName(BRAND.name)
    app.setApplicationDisplayName(BRAND.name)
    app.setOrganizationName(BRAND.name)
    app.setDesktopFileName(BRAND.slug)
    app.setWindowIcon(QIcon(str(brand_asset("wordarc.ico"))))
    app.setQuitOnLastWindowClosed(False)

    # No command and an instance already running: bring its settings forward.
    # A restarted replacement skips this: the old instance is still quitting,
    # and handing it a command would make the child exit instead of booting.
    if not restarted and send_command(command or "settings"):
        return 0

    if command in ("cancel", "quit", "stop", "restart", "meeting-cancel",
                   "ask", "ask-reset", "ask-cancel"):
        return 0

    # Losing the mutex means another launch got here first, so stand down.
    if not _acquire_instance_mutex():
        return 0

    splash = _startup_splash(app)

    tray_available = QSystemTrayIcon.isSystemTrayAvailable()
    if not tray_available:
        print("wordarc: no system tray found, running anyway")

    conf = cfg.Config()
    ensure_startup_registration(conf)
    # Device discovery can wait on a GPU driver for tens of seconds. Settings
    # resolves it in a worker; startup must not probe on the GUI thread.
    logging.getLogger("wordarc.startup").info(
        "speech engine=%s device preference=%s (discovery deferred)",
        conf.get("transcribe_engine"), conf.get("local_stt_device") or "auto")
    install_qt_translator(app, i18n.language())
    theme.ThemeManager.apply(conf["theme_mode"], app)
    wordarc = WordArc(app, conf)

    servers = []
    for server_name in SERVER_NAMES:
        server = QLocalServer()
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        QLocalServer.removeServer(server_name)
        if server.listen(server_name):
            servers.append(server)
        else:
            print(f"wordarc: could not open the IPC socket: {server.errorString()}")

    def on_connection(server):
        conn = server.nextPendingConnection()
        if conn is None:
            return

        def read():
            payload = bytes(conn.readAll()).decode("utf-8", "replace").strip()
            handler = {
                "toggle": wordarc.toggle,
                "start": wordarc.start,
                "stop": wordarc.stop,
                "cancel": wordarc.cancel,
                "meeting": wordarc.toggle_meeting,
                "meeting-cancel": wordarc.cancel_meeting,
                "settings": wordarc.open_settings,
                "restart": wordarc.restart,
                "quit": app.quit,
            }.get(payload)
            if handler:
                handler()
            conn.disconnectFromServer()

        conn.readyRead.connect(read)

    for server in servers:
        server.newConnection.connect(lambda server=server: on_connection(server))
    app.aboutToQuit.connect(wordarc.shutdown)

    # No key for the chosen transcription provider means nothing can work yet,
    # so the settings window is the only useful thing to open.
    if _should_open_settings(command, bool(wordarc.conf.gemini_keys()),
                             tray_available):
        wordarc.open_settings()
    elif command == "toggle":
        QTimer.singleShot(0, wordarc.toggle)
    elif command == "meeting":
        QTimer.singleShot(0, wordarc.toggle_meeting)

    if splash is not None:
        splash.close()
    logging.getLogger("wordarc.startup").info(
        "UI ready in %d ms (excludes bundle extraction and imports)",
        startup_timer.elapsed())
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())


# Import compatibility for integrations that still reference verbatim.Verbatim.
Verbatim = WordArc
