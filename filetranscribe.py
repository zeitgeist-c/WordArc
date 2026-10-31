"""Transcribe an existing audio/video file with the same models.

ffmpeg converts whatever comes in to 16 kHz mono WAV; long files are cut into
chunks that stay under the API's size limit, then stitched back together with
their timestamps shifted into place.
"""

import contextlib
import ffmpeg_path
import os
import re
import shutil
import subprocess
import tempfile
import threading
import wave

from PyQt6.QtCore import QObject, pyqtSignal

import api
import localspeech
from i18n import t

CHUNK_SECONDS = 600          # 10 min ≈ 19 MB at 16 kHz mono s16
CLEANUP_CHUNK_CHARS = 12000  # keep each cleanup call comfortably small
RATE = 16000
MIN_SUBTITLE_SECONDS = 1.5   # how long a cue with no end time of its own stays up

# The [mm:ss] or [h:mm:ss] prefix a timestamped line starts with.
STAMP_RE = re.compile(r"^\[(?:(\d+):)?(\d{1,2}):(\d{2})\]\s*")


class Cancelled(Exception):
    pass


class FileTranscriber(QObject):
    progress = pyqtSignal(str)
    finished = pyqtSignal(str, list)   # text, [(start, end, text)] when timestamped
    failed = pyqtSignal(str)

    def __init__(self, conf, parent=None):
        super().__init__(parent)
        self.conf = conf
        self._thread = None
        self._stop = threading.Event()

    @property
    def busy(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, path, timestamps, do_cleanup):
        if self.busy:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._work, args=(path, timestamps, do_cleanup), daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _check(self):
        if self._stop.is_set():
            raise Cancelled

    def _work(self, path, timestamps, do_cleanup):
        conf = self.conf
        workdir = None
        # Bound before the first fallible step: an ffmpeg or WAV failure lands
        # in the handler below, and reading these from there used to raise
        # UnboundLocalError instead of reporting the error, leaving the window
        # on "Working…" until it was closed.
        keys, client, uses_cloud = [], None, False
        try:
            workdir = tempfile.mkdtemp(prefix="wordarc-file-")
            self.progress.emit(t("Converting audio…"))
            wav_path = _to_wav(path, workdir)
            self._check()

            chunks = split_wav(wav_path, workdir)
            if len(chunks) > 1:
                self.progress.emit(t("Splitting into {count} chunks…", count=len(chunks)))

            keys = conf.gemini_keys()
            # If local transcription + cleanup are both off, the cloud is never
            # called; the order does not move in that case.
            uses_cloud = (conf.get("transcribe_engine") != "local"
                          or do_cleanup)
            start = conf.claim_api_slot(len(keys)) if uses_cloud else 0
            client = api.GeminiClient(
                keys,
                should_stop=self._stop.is_set,
                on_fallback=lambda slot, _exc, failed=0: self.progress.emit(t(
                    "API {used} did not respond; trying API {number}...",
                    used=failed, number=slot,
                )),
                start_slot=start,
            )
            pieces = []
            segments = []
            for index, (chunk_path, offset) in enumerate(chunks, start=1):
                self._check()
                self.progress.emit(
                    t("Transcribing chunk {index}/{count}…", index=index, count=len(chunks))
                )
                found = localspeech.transcribe_for(
                    conf, chunk_path,
                    language=conf["language"],
                    prompt=conf["transcribe_prompt"],
                    should_stop=self._stop.is_set,
                    with_segments=True,
                    client=client,
                )
                # The local engine reports when each line was said; the cloud
                # one does not, and hands back the whole chunk as one entry
                # starting at zero. Both are placed on this chunk's own
                # timeline here, so the two engines produce the same shape and
                # the timestamp option works with either.
                length = wav_duration(chunk_path)
                for start, end, body in found:
                    body = body.strip()
                    if not body:
                        continue
                    at = offset + start
                    # An entry the engine gave no end time for runs to the end
                    # of the chunk, which is what the cloud one needs.
                    stop = offset + end if end > start else offset + length
                    segments.append((at, stop, body))
                    if timestamps:
                        pieces.append(f"[{format_timestamp(at)}] {body}")
                    else:
                        pieces.append(body)

            text = "\n".join(pieces) if timestamps else " ".join(pieces)

            if do_cleanup and text:
                self._check()
                self.progress.emit(t("Cleaning up…"))
                text = self._cleanup(client, text, timestamps)

            if uses_cloud:
                conf.record_api_success(client.active_slot, len(keys))
            self.finished.emit(text, segments)

        except (Cancelled, api.Cancelled, localspeech.Cancelled):
            self.progress.emit(t("Stopped."))
        except (api.ApiError, localspeech.LocalSpeechError, OSError,
                subprocess.SubprocessError, wave.Error) as exc:
            # Only an API error advances the order; a cancellation is kept in the
            # branch above and never touches the order.
            if uses_cloud and isinstance(exc, api.ApiError):
                conf.record_api_attempt(client.active_slot, len(keys))
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 — any surprise must unlock the UI
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            if workdir:
                shutil.rmtree(workdir, ignore_errors=True)

    def _cleanup(self, client, text, timestamps):
        conf = self.conf
        prompt = conf.cleanup_prompt(with_timestamps=timestamps, subtitles=True)
        out = []
        for block in split_text(text, timestamps):
            self._check()
            out.append(client.cleanup(
                block,
                conf["cleanup_model"],
                prompt,
                reasoning=conf["cleanup_reasoning"],
            ))
        return ("\n" if timestamps else "\n\n").join(out)


def format_timestamp(seconds):
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def srt_timestamp(seconds):
    millis = int(round(max(seconds, 0.0) * 1000))
    hours, rest = divmod(millis, 3600000)
    minutes, rest = divmod(rest, 60000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def to_srt(text, segments):
    """Turn the timestamped transcript into SRT cues.

    The text is the authority on wording, so cleanup edits survive; the segments
    are the authority on timing. They meet at the [mm:ss] prefix, which cleanup
    is told to leave alone: a line's whole-second stamp finds the segment it came
    from, and with it the fractional start and the end time whisper reported. A
    line whose stamp finds nothing runs until the next line starts.
    """
    cues = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = STAMP_RE.match(line)
        body = line[match.end():].strip() if match else line
        if not match:
            if cues and body:      # a wrapped line belongs to the cue above it
                cues[-1][2] += " " + body
            continue
        if not body:
            continue
        hours, minutes, secs = (int(g or 0) for g in match.groups())
        cues.append([hours * 3600 + minutes * 60 + secs, None, body])

    timing = {}
    for start, end, _ in segments:
        timing.setdefault(int(start), (start, end))
    for cue in cues:
        cue[0], cue[1] = timing.get(cue[0], (float(cue[0]), 0.0))
    for index, cue in enumerate(cues):
        following = cues[index + 1][0] if index + 1 < len(cues) else 0.0
        if following > cue[0]:
            cue[1] = min(cue[1], following) if cue[1] > cue[0] else following
        elif cue[1] <= cue[0]:
            cue[1] = cue[0] + MIN_SUBTITLE_SECONDS

    blocks = [
        f"{number}\n{srt_timestamp(start)} --> {srt_timestamp(end)}\n{body}"
        for number, (start, end, body) in enumerate(cues, start=1)
    ]
    return "\n\n".join(blocks) + "\n" if blocks else ""


def _to_wav(path, workdir):
    out = os.path.join(workdir, "audio.wav")
    try:
        res = subprocess.run(
            [ffmpeg_path.ffmpeg(), "-nostdin", "-y", "-i", path, "-vn",
             "-ac", "1", "-ar", str(RATE), "-c:a", "pcm_s16le", out],
            capture_output=True, text=True, timeout=900,
        )
    except FileNotFoundError:
        raise api.ApiError(t("ffmpeg not found. Install it to transcribe files."))
    except subprocess.TimeoutExpired:
        raise api.ApiError(t("Could not read the file: {error}", error="ffmpeg timeout (900 s)"))
    if res.returncode != 0 or not os.path.exists(out):
        tail = (res.stderr or "").strip().splitlines()
        raise api.ApiError(t("Could not read the file: {error}",
                             error=tail[-1] if tail else res.returncode))
    return out


def wav_duration(path):
    """Length of a WAV file in seconds."""
    with contextlib.closing(wave.open(path, "rb")) as wav:
        rate = wav.getframerate() or 1
        return wav.getnframes() / float(rate)


def split_wav(wav_path, workdir):
    """[(chunk path, offset in seconds)], a single entry for short files."""
    with contextlib.closing(wave.open(wav_path, "rb")) as src:
        rate = src.getframerate()
        total = src.getnframes()
        per_chunk = CHUNK_SECONDS * rate
        if total <= per_chunk:
            return [(wav_path, 0.0)]

        chunks = []
        index = 0
        while True:
            frames = src.readframes(per_chunk)
            if not frames:
                break
            path = os.path.join(workdir, f"chunk-{index:03d}.wav")
            with contextlib.closing(wave.open(path, "wb")) as dst:
                dst.setnchannels(src.getnchannels())
                dst.setsampwidth(src.getsampwidth())
                dst.setframerate(rate)
                dst.writeframes(frames)
            chunks.append((path, index * CHUNK_SECONDS))
            index += 1
        return chunks


def split_text(text, timestamps):
    """Break long text into cleanup-sized blocks, never mid-line."""
    if len(text) <= CLEANUP_CHUNK_CHARS:
        return [text]
    separator = "\n" if timestamps else " "
    blocks, current = [], ""
    for part in text.split(separator):
        candidate = f"{current}{separator}{part}" if current else part
        if len(candidate) > CLEANUP_CHUNK_CHARS and current:
            blocks.append(current)
            current = part
        else:
            current = candidate
    if current:
        blocks.append(current)
    return blocks
