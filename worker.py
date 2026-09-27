"""The dictation chain: transcribe → clean up → clipboard → paste."""

import os
import logging
import shutil
import sys
import threading
import time
import traceback

from PyQt6.QtCore import QObject, pyqtSignal

import api
import audio
import config as cfg
import localspeech
import paste
import vad
from i18n import t

CHUNK_SECONDS = audio.CHUNK_FRAMES / audio.RATE

# Pasting is not one step but three: read the clipboard, replace it, press the
# shortcut. Keep the lock so future concurrent producers cannot interleave them.
_paste_lock = threading.Lock()
_log = logging.getLogger("wordarc.worker")


class Pipeline(QObject):
    stage = pyqtSignal(str, str)  # progress line, operation id
    finished = pyqtSignal(str, str, str, str)  # raw, final, warning, operation id
    failed = pyqtSignal(str, str)  # message, operation id
    cancelled = pyqtSignal(str)

    def __init__(self, conf, parent=None):
        super().__init__(parent)
        self.conf = conf
        self._thread = None
        self._stop = threading.Event()

    @property
    def busy(self):
        return self._thread is not None and self._thread.is_alive()

    def run(self, wav_path, duration, rms_values=(), operation_id="", auto_paste=None):
        if self.busy:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._work,
            args=(wav_path, duration, list(rms_values), operation_id, auto_paste),
            daemon=True,
        )
        self._thread.start()

    def cancel(self):
        """Give up on a job already under way.

        Only the Claude call can honour this, and it is the only one long enough
        to be worth interrupting: a transcription is over in seconds, a command
        that went looking through the web is not.
        """
        self._stop.set()

    def _work(self, wav_path, duration, rms_values, operation_id, auto_paste=None):
        conf = self.conf
        should_paste = conf["auto_paste"] if auto_paste is None else auto_paste
        started = time.monotonic()
        raw = ""

        # Room tone only: don't spend an API call, and don't invite a
        # hallucinated sentence back.
        if conf["skip_silent"]:
            stats = vad.analyse(rms_values, CHUNK_SECONDS, conf["speech_margin_db"])
            if vad.is_silent(stats, conf["silence_db"], conf["speech_margin_db"],
                             conf["min_voiced_seconds"]):
                self._discard(wav_path)
                self.failed.emit(t("No speech detected ({level} dB)",
                                   level=round(stats["speech_db"])), operation_id)
                return

        try:
            self.stage.emit(t("Transcribing…"), operation_id)
            client = api.GeminiClient(
                conf.gemini_keys(),
                should_stop=self._stop.is_set,
                on_fallback=lambda slot, _exc: self.stage.emit(
                    t("Default API did not respond; trying API {number}...",
                      number=slot), operation_id),
            )
            raw = localspeech.transcribe_for(
                conf, wav_path,
                language=conf["language"],
                prompt=conf["transcribe_prompt"],
                should_stop=self._stop.is_set,
                client=client,
            )

            if conf["filter_hallucinations"] and vad.looks_like_hallucination(raw, duration):
                self._discard(wav_path)
                self.failed.emit(t("Discarded a stock phrase: “{text}”", text=raw[:60]),
                                 operation_id)
                return

            text = raw
            warning = ""
            # Claude reads through “eee” and “hani” without help, so a dictation
            # on its way there is normally sent as it was heard, one API call and
            # a second or two lighter.
            if conf["cleanup_enabled"]:
                self.stage.emit(t("Cleaning up…"), operation_id)
                try:
                    text = client.cleanup(
                        raw,
                        conf["cleanup_model"],
                        conf.cleanup_prompt(),
                        reasoning=conf["cleanup_reasoning"],
                    )
                except api.Cancelled:
                    # A stop that lands while the cleanup request is in flight
                    # is a stop, not a cleanup failure: Cancelled is an
                    # ApiError, so without this it was swallowed here and the
                    # run went on to paste the raw text as if all were well.
                    raise
                except api.ApiError as exc:
                    # Keep the transcript, but never let the failure pass unseen:
                    # a rejected key would otherwise look like working dictation.
                    text = raw
                    warning = str(exc)
                    _log.warning("cleanup request failed (status=%s, category=%s)",
                                 exc.status, exc.category)
                    print(f"wordarc: cleanup failed: {exc}", file=sys.stderr)

            with _paste_lock:
                previous = paste.read_clipboard() if should_paste and conf["restore_clipboard"] else None
                paste.copy(text)

                if should_paste:
                    self.stage.emit(t("Pasting…"), operation_id)
                    pasted = False
                    try:
                        paste.press(conf["paste_shortcut"])
                        pasted = True
                    finally:
                        # The old contents go back whatever happened: when the
                        # keystroke never landed, the clipboard was left holding
                        # the dictation text and the user's own clipboard was
                        # gone for good.
                        if previous is not None:
                            if pasted:
                                # The target reads the clipboard after the
                                # keystroke lands, so the old contents wait.
                                time.sleep(0.35)
                            paste.copy_bytes(previous)

            history_entry = {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "duration": round(duration, 1),
                "elapsed": round(time.monotonic() - started, 1),
                "model": conf.transcribe_name(),
                "cleanup_model": conf["cleanup_model"] if conf["cleanup_enabled"] else "",
                "cleanup_error": warning,
                "raw": raw,
                "text": text,
            }
            if conf["history_enabled"]:
                cfg.append_history(history_entry)
                try:
                    cfg.trim_history(conf["history_limit"])
                except OSError as exc:
                    print(f"wordarc: could not trim the history: {exc}", file=sys.stderr)
            self.finished.emit(raw, text, warning, operation_id)

        except api.Cancelled:
            self.cancelled.emit(operation_id)
        except localspeech.Cancelled:
            self.cancelled.emit(operation_id)
        except (api.ApiError, localspeech.LocalSpeechError,
                paste.PasteError) as exc:
            _log.warning("pipeline failed (%s)", type(exc).__name__)
            print(f"wordarc: {exc}", file=sys.stderr)
            self.failed.emit(str(exc), operation_id)
        except Exception as exc:  # never fail silently
            _log.exception("unexpected pipeline error")
            traceback.print_exc()
            self.failed.emit(t("Unexpected error: {error}", error=exc), operation_id)
        finally:
            self._discard(wav_path)

    def _discard(self, wav_path):
        """Delete the temporary recording, or file it away when keep_audio is on."""
        if not os.path.exists(wav_path):
            return
        if self.conf["keep_audio"]:
            try:
                cfg.RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
                shutil.move(wav_path, cfg.RECORDINGS_DIR / (time.strftime("%Y%m%d-%H%M%S") + ".wav"))
                return
            except OSError as exc:
                # Deleting it instead would throw away the recording the user
                # asked to keep, so leave it where it is and log the path.
                _log.warning("could not file the recording away (%s); kept %s",
                             exc, wav_path)
                return
        try:
            os.unlink(wav_path)
        except OSError:
            pass
