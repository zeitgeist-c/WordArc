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

from brand import BRAND, set_windows_app_id

__version__ = BRAND.version

from PyQt6.QtCore import QTimer, QElapsedTimer  # noqa: E402
from PyQt6.QtGui import QAction, QIcon  # noqa: E402
from PyQt6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PyQt6.QtWidgets import (QApplication, QMenu,
                             QSystemTrayIcon)  # noqa: E402

import audio  # noqa: E402
import config as cfg  # noqa: E402
import diagnostics  # noqa: E402
import hotkey  # noqa: E402
import meeting  # noqa: E402
import operation  # noqa: E402
import brand_migration  # noqa: E402
import theme  # noqa: E402
import startup  # noqa: E402
from brand import brand_asset  # noqa: E402
import i18n  # noqa: E402
from i18n import t  # noqa: E402
from meeting import MeetingPipeline  # noqa: E402
from overlay import Overlay  # noqa: E402
from settings_ui import SettingsWindow, install_qt_translator  # noqa: E402
from worker import Pipeline  # noqa: E402

SERVER_NAME = BRAND.ipc_name(getpass.getuser())
LEGACY_SERVER_NAME = BRAND.legacy_ipc_name(getpass.getuser())
SERVER_NAMES = (SERVER_NAME, LEGACY_SERVER_NAME)

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


class WordArc:
    def __init__(self, app, conf=None):
        self.app = app
        self.conf = conf or cfg.Config()
        self.state = IDLE
        self.dictation_operation = operation.OperationController()
        self.meeting_operation = operation.OperationController()
        self.meeting_state = M_IDLE
        self.meeting_base = ""
        self.meeting_message = ""
        self.settings_window = None
        self._window_dictation = False
        self._last_dictation = ""
        self._quitting = False

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
        if reason != QSystemTrayIcon.ActivationReason.Trigger:
            return
        self._toggle()

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
        handlers = {"meeting": self._toggle_meeting}
        handlers.get(name, self._toggle)()

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

    def start(self, from_window=False):
        if self.state != IDLE:
            return
        self._window_dictation = from_window
        self.dictation_operation.begin()
        self.overlay.show_recording()
        if not self._begin_recording():
            if self.dictation_operation.state == operation.State.RECORDING:
                self.dictation_operation.transition(operation.State.FAILED)
                self.dictation_operation.transition(operation.State.IDLE)
            return
        self._set_state(RECORDING)

    def _begin_recording(self):
        self.elapsed.restart()
        self.ticker.start()
        self.recorder.start(self.conf["mic_target"], self.conf["max_seconds"])
        return self.recorder.active

    def stop(self):
        if self.state != RECORDING:
            return
        self.ticker.stop()
        self.dictation_operation.transition(operation.State.PROCESSING)
        self._set_state(BUSY)
        self.overlay.show_busy(t("Transcribing…"))
        self.recorder.stop()

    def cancel(self):
        """Throw away the current dictation recording."""
        if not self.recording:
            return
        self.ticker.stop()
        self.recorder.cancel()
        self.dictation_operation.transition(operation.State.CANCELLED)
        self.dictation_operation.transition(operation.State.IDLE)
        self.overlay.dismiss()
        self._set_state(IDLE)

    def _on_level(self, level):
        self.overlay.push_level(level)

    def _tick(self):
        seconds = self.elapsed.elapsed() / 1000.0
        self.overlay.set_seconds(seconds)
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
            operation_id=self.dictation_operation.operation_id,
            auto_paste=False if self._window_dictation else None)

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
            message = t("Copied raw, cleanup failed: {error}", error=warning.splitlines()[0]) if self._window_dictation else t("Pasted raw, cleanup failed: {error}", error=warning.splitlines()[0])
            self.overlay.show_warning(message)
            self.tray.showMessage(
                t("WordArc: cleanup failed"), warning,
                QSystemTrayIcon.MessageIcon.Warning, 10000,
            )
        else:
            action = t("Pasted") if self.conf["auto_paste"] and not self._window_dictation else t("Copied")
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
        logging.getLogger("wordarc.ui").warning("operation reported an error")
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
                self.start(from_window=True)
            elif self.state == RECORDING:
                self.stop()
        else:
            self._toggle_meeting()

    def _window_cancel(self, kind):
        if kind == "dictation":
            self.cancel()
        else:
            self.cancel_meeting()

    def open_settings(self):
        if self.settings_window is None:
            self.settings_window = SettingsWindow(
                self.conf, launch_command(), meeting_command(), self.meetings,
            )
            self.settings_window.recording_requested.connect(self._window_record)
            self.settings_window.cancel_requested.connect(self._window_cancel)
            self.settings_window.set_dictation_result(self._last_dictation)
            self._sync_workspace()
            self.settings_window.applied.connect(self._apply_settings)
            self.settings_window.language_changed.connect(self._reopen_settings)
            self.settings_window.finished.connect(self._settings_closed)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def _reopen_settings(self):
        """Rebuild the settings window so the new language applies at once."""
        if self.settings_window is not None:
            # Blocked so close() does not trip _settings_closed (which would
            # drop the fresh window and could quit the app); closeEvent still
            # stops a running file transcription directly.
            self.settings_window.blockSignals(True)
            self.settings_window.close()
            self.settings_window = None
        self.open_settings()

    def _settings_closed(self, *_):
        # Don't drop the object while its own signal is still being delivered.
        def finish_close():
            self.settings_window = None
            if (not self._quitting
                    and (not self.conf["close_to_tray"]
                         or not QSystemTrayIcon.isSystemTrayAvailable())):
                self.app.quit()
        QTimer.singleShot(0, finish_close)

    def _apply_settings(self):
        theme.ThemeManager.apply(self.conf["theme_mode"], self.app)
        self.overlay.corner = self.conf["overlay_corner"]
        self._build_tray()
        self._refresh_tray()
        self.evdev.stop()
        self.evdev.start({"toggle": self.conf["shortcut"],
                          "meeting": self.conf["meeting_shortcut"]})

    def restart(self):
        """Replace this process with a fresh one, picking up code and settings."""
        if self.settings_window is not None:
            self.settings_window.close()
        self.shutdown()
        for name in SERVER_NAMES:
            QLocalServer.removeServer(name)
        # Hand the instance over before the replacement starts.
        _release_instance_mutex()
        if getattr(sys, "frozen", False):
            # Paketlenmiş onefile exe'de __file__ geçici _MEI klasörünü gösterir;
            # yeni süreç yalnız exe + kullanıcı argümanlarıyla başlatılmalı.
            subprocess.Popen([sys.executable] + sys.argv[1:])
        else:
            subprocess.Popen([sys.executable, os.path.realpath(__file__)] + sys.argv[1:])
        self.app.quit()

    def shutdown(self):
        self._quitting = True
        self.evdev.stop()
        self.cancel_hotkey.stop()
        self.pipeline.cancel()
        self.meetings.stop()
        if self.recording:
            self.recorder.cancel()
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


def main():
    # Windows otherwise labels source-mode launches as pythonw.exe and shows
    # Python's icon in the taskbar even though Qt has a WordArc window icon.
    set_windows_app_id()
    migration = brand_migration.migrate(
        cfg.LEGACY_CONFIG_DIR, cfg.CONFIG_DIR,
        cfg.LEGACY_DATA_DIR, cfg.DATA_DIR,
    )
    diagnostics.setup()
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
    if send_command(command or "settings"):
        return 0

    if command in ("cancel", "quit", "stop", "restart", "meeting-cancel",
                   "ask", "ask-reset", "ask-cancel"):
        return 0

    # Losing the mutex means another launch got here first, so stand down.
    if not _acquire_instance_mutex():
        return 0

    tray_available = QSystemTrayIcon.isSystemTrayAvailable()
    if not tray_available:
        print("wordarc: no system tray found, running anyway")

    conf = cfg.Config()
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

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())


# Import compatibility for integrations that still reference verbatim.Verbatim.
Verbatim = WordArc
