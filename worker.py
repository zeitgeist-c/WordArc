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

    def run_transcript(self, raw, duration, rms_values=(), operation_id="",
                       auto_paste=None, start_slot=None):
        """Deliver already-transcribed text through cleanup → paste → history.

        The live engine hands over text, not a recording, so transcription
        is skipped; everything after it runs exactly as for a file job.
        ``start_slot`` lets the caller keep one rotation claim across the
        live session and the cleanup that follows it.
        """
        if self.busy:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._work_text,
            args=(raw, duration, list(rms_values), operation_id, auto_paste,
                  start_slot),
            daemon=True,
        )
        self._thread.start()

    def _work_text(self, raw, duration, rms_values, operation_id,
                   auto_paste=None, start_slot=None):
        client, keys, uses_cloud = None, [], False
        try:
            client, keys, uses_cloud, started = self._begin_job(
                operation_id, t("Cleaning up…"), start_slot=start_slot)
            self._deliver(raw, None, duration, rms_values, operation_id,
                          auto_paste, client, keys, uses_cloud, started)
        except Exception as exc:
            self._fail(exc, uses_cloud, client, keys, operation_id)

    def _begin_job(self, operation_id, stage_message, start_slot=None):
        """Claim an API slot and build the failover client for one job."""
        conf = self.conf
        started = time.monotonic()
        self.stage.emit(stage_message, operation_id)
        keys = conf.gemini_keys()
        # The order advances when the job really uses the cloud API: local
        # transcription spends no API, but cleanup/translation still go to Gemini.
        uses_cloud = (conf.get("transcribe_engine") != "local"
                      or conf["cleanup_enabled"]
                      or conf.get("translate_enabled"))
        if start_slot is None and uses_cloud:
            start = conf.claim_api_slot(len(keys))
        else:
            start = start_slot or 0
        client = api.GeminiClient(
            keys,
            should_stop=self._stop.is_set,
            on_fallback=lambda slot, _exc, failed=0: self.stage.emit(
                t("API {used} did not respond; trying API {number}...",
                  used=failed, number=slot), operation_id),
            start_slot=start,
        )
        return client, keys, uses_cloud, started

    def _fail(self, exc, uses_cloud, client, keys, operation_id):
        conf = self.conf
        if isinstance(exc, (api.Cancelled, localspeech.Cancelled)):
            self.cancelled.emit(operation_id)
        elif isinstance(exc, (api.ApiError, localspeech.LocalSpeechError,
                              paste.PasteError)):
            _log.warning("pipeline failed (%s)", type(exc).__name__)
            print(f"wordarc: {exc}", file=sys.stderr)
            # Only an API error advances the order: a clipboard or local engine
            # failure is not another API's fault. A cancellation is kept in a
            # separate branch above and never touches the order.
            if (uses_cloud and client is not None
                    and isinstance(exc, api.ApiError)):
                conf.record_api_attempt(client.active_slot, len(keys))
            self.failed.emit(str(exc), operation_id)
        else:  # never fail silently
            _log.exception("unexpected pipeline error")
            traceback.print_exc()
            self.failed.emit(t("Unexpected error: {error}", error=exc), operation_id)

    def _work(self, wav_path, duration, rms_values, operation_id, auto_paste=None):
        client, keys, uses_cloud = None, [], False
        try:
            client, keys, uses_cloud, started = self._begin_job(
                operation_id, t("Transcribing…"))
            transcribe_started = time.monotonic()
            raw = localspeech.transcribe_for(
                self.conf, wav_path,
                language=self.conf["language"],
                prompt=self.conf["transcribe_prompt"],
                should_stop=self._stop.is_set,
                client=client,
            )
            _log.info("transcribe took %.1fs for %.1fs of audio",
                      time.monotonic() - transcribe_started, duration)
            self._deliver(raw, wav_path, duration, rms_values, operation_id,
                          auto_paste, client, keys, uses_cloud, started)
        except Exception as exc:
            self._fail(exc, uses_cloud, client, keys, operation_id)
        finally:
            self._discard(wav_path)

    def _deliver(self, raw, wav_path, duration, rms_values, operation_id,
                 auto_paste, client, keys, uses_cloud, started):
        """The shared queue after transcription: silence -> cleanup -> paste.

        ``wav_path`` may be None (live engine): then there is no recording to
        delete and the text is delivered directly.
        """
        conf = self.conf
        should_paste = conf["auto_paste"] if auto_paste is None else auto_paste

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
        translate_on = bool(conf.get("translate_enabled"))
        if translate_on or conf["cleanup_enabled"]:
            self.stage.emit(
                t("Translating…" if translate_on else "Cleaning up…"),
                operation_id)
            cleanup_started = time.monotonic()
            try:
                if translate_on:
                    text = client.translate(
                        raw,
                        conf["gemini_translate_model"],
                        cfg.translate_prompt(conf.get("translate_mode", "academic")),
                    )
                else:
                    text = client.cleanup(
                        raw,
                        conf["cleanup_model"],
                        conf.cleanup_prompt(),
                        reasoning=conf["cleanup_reasoning"],
                        allow_empty=True,
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
            _log.info("cleanup took %.1fs for %d chars",
                      time.monotonic() - cleanup_started, len(raw))

        if not text.strip():
            self._discard(wav_path)
            self.failed.emit(t("No speech content remains after cleanup."), operation_id)
            return

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
        if uses_cloud:
            conf.record_api_success(client.active_slot, len(keys))
        self.finished.emit(raw, text, warning, operation_id)

    def _discard(self, wav_path):
        """Delete the temporary recording, or file it away when keep_audio is on."""
        if not wav_path or not os.path.exists(wav_path):
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
