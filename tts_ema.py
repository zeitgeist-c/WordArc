"""Turkish text-to-speech through EMA Lightning ONNX graphs (no PyTorch).

The 8.6M-parameter EMA Lightning model speaks Turkish from a ~34 MB weight
set. This module runs the community ONNX conversion
(``ozcancelik/ema-lightning-onnx``) with the onnxruntime copy the app already
ships for OCR and local speech, so the frozen package grows by megabytes,
not by a PyTorch install.

Pipeline ports (Apache-2.0, same behavior, NumPy instead of torch):
chunking/finish from ``ema_lightning.chunker``, the text frontend from
``ema_lightning.frontend`` (normalizer-tr), and the plan/decode math the
upstream ``export/verify.py`` uses to prove ONNX==torch to float precision.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
import unicodedata
import wave

import numpy as np

import config as cfg
import ffmpeg_path
from i18n import t

try:
    import normalizer_tr
except ModuleNotFoundError:  # pragma: no cover - missing optional dependency
    normalizer_tr = None

try:
    import onnxruntime as ort
except ModuleNotFoundError:  # pragma: no cover - missing optional dependency
    ort = None

try:
    from huggingface_hub import snapshot_download
except ModuleNotFoundError:  # pragma: no cover - missing optional dependency
    snapshot_download = None

_log = logging.getLogger("wordarc.tts_ema")

REPO = "ozcancelik/ema-lightning-onnx"
FILES = ("text.onnx", "sound.onnx", "decoder.onnx", "meta.json")
SAMPLE_RATE = 48000
FRAMES_PER_SECOND = 25
HOP = 1920  # decoder samples per latent frame
WINDOW = 100  # decoder frames per window after the first
FIRST_WINDOW = 25
CONTEXT = 8
MAX_FRAMES = 3000
SEED = 0

# --- chunking (behavior port of ema_lightning.chunker) -----------------------
LETTERS_PER_SECOND = 18.0
MAX_SECONDS = 10.0
MAX_LETTERS = 250
SENTENCE_PAUSE = 0.25
CLAUSE_PAUSE = 0.12
_CUTS = ((re.compile(r"[.!?]+[\"']*(?= )"), SENTENCE_PAUSE),
         (re.compile(r"[,;:](?= )"), CLAUSE_PAUSE),
         (re.compile(r"\S(?= )"), CLAUSE_PAUSE))
_LETTER = re.compile(r"[^\W\d_]")


def chunk(text, speed=1.0):
    """[(piece, seconds of silence after it)], each ending in punctuation."""
    limit = int(min(MAX_LETTERS, LETTERS_PER_SECOND * MAX_SECONDS * speed))
    pieces, rest = [], text.strip()
    while rest:
        cut, pause = len(rest), 0.0
        if len(rest) > limit:
            cut = limit
            for pattern, gap in _CUTS:
                ends = [m.end() for m in pattern.finditer(rest, 0, limit + 1)]
                if ends:
                    cut, pause = ends[-1], gap
                    break
        piece, rest = rest[:cut].strip(), rest[cut:].strip()
        if _LETTER.search(piece):
            pieces.append((_finish(piece), pause))
    if pieces:
        pieces[-1] = (pieces[-1][0], 0.0)
    return pieces


def _finish(piece):
    if piece.rstrip("\"')")[-1:] in (".", "!", "?"):
        return piece
    return piece.rstrip(",;:- ") + "."


# --- frontend (behavior port of ema_lightning.frontend) ----------------------
_UNSAFE = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u061c\u200e\u200f"
                     "\u202a-\u202e\u2066-\u2069]")
_TYPOGRAPHY = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "´": "'",
                             "`": "'", "“": '"', "”": '"', "„": '"',
                             "«": '"', "»": '"', "–": "-", "—": "-",
                             "−": "-", "…": "..."})
_TURKISH = frozenset("çğıöşüÇĞİÖŞÜ")


class Frontend:
    """Any written Turkish in, text in the model's own alphabet out."""

    def __init__(self, vocab):
        self.vocab = frozenset(vocab)
        self.normalizer = normalizer_tr.Normalizer() if normalizer_tr else None

    def __call__(self, text):
        text = _UNSAFE.sub(" ", text.encode("utf-8", "ignore").decode("utf-8"))
        if not text.strip():
            return ""
        spoken = ([self._spoken(block) for block in _blocks(text)])
        return self.alphabet(" ".join(spoken))

    def _spoken(self, text):
        if self.normalizer is None:
            return text
        try:
            return self.normalizer.normalize(
                text, ambiguity_policy="fallback").normalized_text
        except Exception:  # keep the words rather than lose the sentence
            return text

    def alphabet(self, text):
        text = text.translate(_TYPOGRAPHY).replace("İ", "i").replace("I", "ı")
        text = text.lower()
        out = []
        for ch in text:
            if ch not in _TURKISH:
                ch = "".join(c for c in unicodedata.normalize("NFKD", ch)
                             if not unicodedata.combining(c))
            out.append(ch if ch and all(c in self.vocab for c in ch) else " ")
        return re.sub(r"\s+", " ", "".join(out)).strip()


def _blocks(text, size=8 * 1024):
    words, block, used = text.split(), [], 0
    for word in words:
        n = len(word.encode("utf-8")) + 1
        if block and used + n > size:
            yield " ".join(block)
            block, used = [], 0
        block.append(word)
        used += n
    if block:
        yield " ".join(block)


# --- frame planning (port of upstream export/verify.py plan()) --------------
def plan(ids, cw, wstart, dur, speed=1.0):
    """Frame timeline and letter/frame positions for one piece."""
    dur = np.asarray(dur, dtype=np.float32) / speed
    length = len(ids)
    n_words = int(cw[-1]) + 1
    counts = np.zeros(n_words)
    np.add.at(counts, cw, dur)
    counts = np.clip(np.round(counts), 1, 250).astype(np.int64)
    frames = min(int(counts.sum()), MAX_FRAMES)
    fw = np.repeat(np.arange(n_words), counts)[:frames]
    starts = np.cumsum(counts) - counts
    fp = ((np.arange(frames) - starts[fw]) / counts[fw]).astype(np.float32)
    c = np.maximum(dur, 1e-4).astype(np.float32)
    done = np.cumsum(c)
    before = done - c
    total = np.zeros(n_words, np.float32)
    np.add.at(total, cw, c)
    cp = np.clip((done - before[wstart] - 0.5 * c)
                 / np.maximum(total[cw], 1e-8), 0, 1)
    wlen = np.maximum(np.bincount(cw, minlength=n_words).astype(np.float32), 1)
    woff = np.cumsum(wlen) - wlen
    cg = woff[cw] + cp * wlen[cw]
    fg = woff[fw] + fp * wlen[fw]
    return fw, cg.astype(np.float32), fg.astype(np.float32), length


def windows(frames, first=WINDOW):
    spans, s = [], 0
    while s < frames:
        e = min(frames, s + (first if s == 0 else WINDOW))
        spans.append((s, e))
        s = e
    return spans


# --- engine ------------------------------------------------------------------
def models_dir():
    return cfg.DATA_DIR / "models" / "ema-onnx"


def bundled_models_dir():
    """The weight set shipped inside the frozen package, if present."""
    from brand import resource_path
    return resource_path("models", "ema-onnx")


def resolve_models():
    """Bundled weights win; the user download dir is the fallback."""
    bundled = bundled_models_dir()
    if models_ready(bundled):
        return bundled
    return models_dir()


def models_ready(where=None):
    root = where or models_dir()
    return all((root / name).is_file() for name in FILES)


def ensure_models(progress=None):
    """Return the ONNX weight dir, downloading to DATA_DIR only as fallback."""
    root = resolve_models()
    if models_ready(root):
        return root
    if snapshot_download is None:
        raise RuntimeError(t("Model download needs huggingface_hub: {error}",
                             error="huggingface_hub"))
    root.mkdir(parents=True, exist_ok=True)
    if progress:
        progress(t("Downloading the Turkish voice model (~34 MB)…"))
    snapshot_download(repo_id=REPO, local_dir=str(root),
                      allow_patterns=list(FILES),
                      tqdm_class=_SilentProgress)
    if not models_ready(root):
        raise RuntimeError(t("Voice model download failed."))
    return root


class _SilentProgress:
    """tqdm stand-in that never touches the terminal.

    Windowed builds have no stderr; a real bar dies with
    "'NoneType' object has no attribute 'write'". huggingface_hub only
    needs a context manager with update().
    """

    def __init__(self, *args, **kwargs):
        self.total = kwargs.get("total")
        self.n = kwargs.get("initial", 0) or 0

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self

    def __getattr__(self, name):
        # Future huggingface_hub calls (set_description_str, …) stay silent.
        # Numeric counters (n, total) are real attributes above so getattr
        # defaults in the caller keep working.
        def silent(*args, **kwargs):
            pass
        return silent

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def update(self, n=1):
        try:
            self.n += n or 0
        except TypeError:
            pass

    def close(self):
        pass


class Engine:
    """Lazy ONNX sessions; synthesize() turns Turkish text into audio."""

    def __init__(self, where=None):
        self.where = where
        self._sessions = None
        self._meta = None
        self._frontend = None

    def load(self, progress=None):
        if self._sessions is not None:
            return self
        if ort is None:
            raise RuntimeError(t("Voice engine needs onnxruntime: {error}",
                                 error="onnxruntime"))
        root = ensure_models(progress)
        with open(root / "meta.json", encoding="utf-8") as fh:
            self._meta = json.load(fh)
        opts = ort.SessionOptions()
        self._sessions = {
            name: ort.InferenceSession(str(root / f"{name}.onnx"), opts,
                                       providers=["CPUExecutionProvider"])
            for name in ("text", "sound", "decoder")
        }
        self._frontend = Frontend(self._meta["vocab"])
        return self

    @property
    def ready(self):
        return self._sessions is not None

    def synthesize(self, text, speed=1.0, seed=SEED, stop=None, progress=None):
        """Float32 mono audio at 48 kHz for the whole text."""
        self.load(progress)
        pieces = chunk(self._frontend(text), speed)
        if not pieces:
            raise ValueError(t("There is no readable text."))
        stoi = {ch: i for i, ch in enumerate(self._meta["vocab"])}
        out = []
        for index, (piece_text, pause) in enumerate(pieces):
            if stop is not None and stop.is_set():
                raise InterruptedError(t("Reading stopped."))
            if progress:
                progress(t("Reading part {done} of {total}…",
                           done=index + 1, total=len(pieces)))
            out.append(self._piece(piece_text, stoi, speed,
                                   (seed * 1_000_003 + index) % 2 ** 63))
            if pause > 0:
                out.append(np.zeros(int(pause * SAMPLE_RATE),
                                    dtype=np.float32))
        return np.concatenate(out) if out else np.zeros(0, dtype=np.float32)

    def _piece(self, text, stoi, speed, seed):
        ids = np.array([stoi.get(ch, 1) for ch in text], dtype=np.int64)
        starts = [i for i, ch in enumerate(text)
                  if ch != " " and (i == 0 or text[i - 1] == " ")] or [0]
        bounds = [0] + starts[1:] + [len(text)]
        cw, wstart = [], []
        for w, (a, b) in enumerate(zip(bounds, bounds[1:])):
            cw += [w] * (b - a)
            wstart += [a] * (b - a)
        cw = np.array(cw, dtype=np.int64)
        wstart = np.array(wstart, dtype=np.int64)
        h, dur = self._sessions["text"].run(None, {"ids": ids[None]})
        fw, cg, fg, _length = plan(ids, cw, wstart, dur[0], speed)
        rng = np.random.RandomState(seed % (2 ** 32))
        noise = rng.randn(4, len(fw), 64).astype(np.float32)[None]
        (lat,) = self._sessions["sound"].run(
            None, {"h": h, "cg": cg[None], "fg": fg[None],
                   "cw": cw[None], "fw": fw[None].astype(np.int64),
                   "noise": noise})
        parts = []
        for s, e in windows(len(fw)):
            a, b = max(0, s - CONTEXT), min(len(fw), e + CONTEXT)
            (audio,) = self._sessions["decoder"].run(
                None, {"z": np.ascontiguousarray(
                    lat[:, a:b].transpose(0, 2, 1))})
            parts.append(audio[0, (s - a) * HOP:(e - a) * HOP])
        return np.concatenate(parts)


def save_wav(audio, path):
    import pathlib
    path = pathlib.Path(path)
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(SAMPLE_RATE)
        fh.writeframes(pcm.tobytes())
    return path


def save_compressed(audio, path, fmt="opus"):
    """WAV through the bundled ffmpeg: opus (~32k) or mp3 (128k)."""
    import pathlib
    import tempfile
    path = pathlib.Path(path)
    exe = ffmpeg_path.ffmpeg()
    if fmt == "wav":
        return save_wav(audio, path)
    args = {"opus": ["-c:a", "libopus", "-b:a", "32k"],
            "mp3": ["-c:a", "libmp3lame", "-b:a", "128k"]}[fmt]
    with tempfile.TemporaryDirectory() as tmp:
        wav = pathlib.Path(tmp) / "speech.wav"
        save_wav(audio, wav)
        cmd = [str(exe), "-y", "-i", str(wav), *args, str(path)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not path.is_file():
        raise RuntimeError(t("Audio export failed: {error}",
                             error=proc.stderr.strip().splitlines()[-1:]
                             and proc.stderr.strip().splitlines()[-1]
                             or fmt))
    return path


# --- file reading (Speak tab: PDF/MD/TXT to speech) ---------------------------
READABLE_SUFFIXES = (".txt", ".md", ".markdown", ".pdf")


def read_text_file(path):
    """Plain readable text from a .txt/.md/.pdf file."""
    import pathlib
    path = pathlib.Path(path)
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md", ".markdown"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if suffix != ".txt":
            text = _strip_markdown(text)
    elif suffix == ".pdf":
        try:
            import fitz
        except ModuleNotFoundError:
            raise ValueError(t("PDF reading needs pymupdf."))
        with fitz.open(path) as doc:
            text = "\n".join(page.get_text() for page in doc)
    else:
        raise ValueError(t("Unsupported file type: {suffix}", suffix=suffix))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise ValueError(t("There is no readable text."))
    return text


def _strip_markdown(text):
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
        line = re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", line)
        line = line.replace("`", "")
        lines.append(line)
    return "\n".join(lines)


# --- background worker (UI stays responsive while reading) -------------------
# Playback is exclusive across every worker in the process: the tab and the
# global hotkey each own a worker, and the second one waits its turn loudly
# instead of talking over the first.
_PLAY_LOCK = threading.Lock()


def _play_pcm(audio, stop, timeout=None):
    """Play mono float32 audio without ever hanging the worker thread.

    The old blocking-write loop could stall forever inside PortAudio
    (no error, no sound, busy stuck, Durdur useless). This version feeds
    a callback stream and watches a deadline: stop aborts within a
    buffer, a stalled device aborts as a timeout error.
    """
    import time

    import sounddevice as sd
    expected = len(audio) / SAMPLE_RATE
    deadline = expected + 20.0 if timeout is None else float(timeout)
    pos = 0

    def callback(outdata, frames, _time_info, _status):
        nonlocal pos
        if stop is not None and stop.is_set():
            raise sd.CallbackStop()
        chunk = audio[pos:pos + frames]
        pos += len(chunk)
        outdata[:len(chunk), 0] = chunk
        if len(chunk) < frames:
            outdata[len(chunk):, 0] = 0
            raise sd.CallbackStop()

    stream = sd.OutputStream(samplerate=SAMPLE_RATE, channels=1,
                             dtype="float32", callback=callback)
    stream.start()
    start = time.monotonic()
    try:
        while stream.active:
            if stop is not None and stop.is_set():
                stream.abort()
                raise InterruptedError(t("Reading stopped."))
            if time.monotonic() - start > deadline:
                stream.abort()
                raise TimeoutError(t("Audio output timed out."))
            time.sleep(0.05)
    finally:
        try:
            stream.stop()
        except Exception:  # noqa: BLE001 - abort path may already be stopped
            pass
        stream.close()
    if stop is not None and stop.is_set():
        raise InterruptedError(t("Reading stopped."))
try:
    from PyQt6.QtCore import QObject, pyqtSignal

    class TtsWorker(QObject):
        progress = pyqtSignal(str)
        finished = pyqtSignal(str, float)  # saved path ("" when only played), seconds
        failed = pyqtSignal(str)

        def __init__(self, engine=None, parent=None):
            super().__init__(parent)
            self.engine = engine or Engine()
            self._thread = None
            self._stop = threading.Event()
            self.last_audio = None
            self.last_seconds = 0.0

        @property
        def busy(self):
            return self._thread is not None and self._thread.is_alive()

        def speak(self, text, speed=1.0):
            self._start(self._speak, text, speed, "")

        def save(self, text, path, fmt="opus", speed=1.0):
            self._start(self._save, text, speed, path, fmt)

        def convert_files(self, paths, out_dir, fmt="opus", speed=1.0):
            """One audio file per text file, in order, stopping between files."""
            self._start(self._convert_files, list(paths), str(out_dir), fmt,
                        speed)

        def stop(self):
            self._stop.set()

        def _start(self, target, *args):
            if self.busy:
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._guarded,
                                            args=(target,) + args,
                                            daemon=True)
            self._thread.start()

        def _guarded(self, target, *args):
            try:
                target(*args)
            except InterruptedError as exc:
                self.failed.emit(str(exc))
            except Exception as exc:  # noqa: BLE001 - surfaced to the UI
                _log.exception("tts failed")
                self.failed.emit(str(exc))

        def _emit_progress(self, message):
            self.progress.emit(message)

        def _speak(self, text, speed, _path):
            audio = self.engine.synthesize(text, speed, stop=self._stop,
                                           progress=self._emit_progress)
            self.last_audio = audio
            self.last_seconds = len(audio) / SAMPLE_RATE
            if not _PLAY_LOCK.acquire(blocking=False):
                raise InterruptedError(t("Already reading…"))
            try:
                _play_pcm(audio, self._stop)
            finally:
                _PLAY_LOCK.release()
            self.finished.emit("", self.last_seconds)

        def play_last(self):
            """Replay the most recent synthesis (autoplay after a save)."""
            if self.busy or self.last_audio is None:
                return
            self._stop.clear()
            audio = self.last_audio
            self._thread = threading.Thread(
                target=self._guarded, args=(self._play_last, audio),
                daemon=True)
            self._thread.start()

        def _play_last(self, audio):
            if not _PLAY_LOCK.acquire(blocking=False):
                raise InterruptedError(t("Already reading…"))
            try:
                _play_pcm(audio, self._stop)
            finally:
                _PLAY_LOCK.release()
            self.finished.emit("", self.last_seconds)

        def _save(self, text, speed, path, fmt):
            audio = self.engine.synthesize(text, speed, stop=self._stop,
                                           progress=self._emit_progress)
            if self._stop.is_set():
                raise InterruptedError(t("Reading stopped."))
            self.last_audio = audio
            self.last_seconds = len(audio) / SAMPLE_RATE
            save_compressed(audio, path, fmt)
            self.finished.emit(str(path), self.last_seconds)

        def _convert_files(self, paths, out_dir, fmt, speed):
            import pathlib
            out_dir = pathlib.Path(out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            total = len(paths)
            for index, raw in enumerate(paths):
                if self._stop.is_set():
                    raise InterruptedError(t("Reading stopped."))
                path = pathlib.Path(raw)
                self._emit_progress(
                    t("Reading file {done} of {total}: {name}",
                      done=index + 1, total=total, name=path.name))
                try:
                    text = read_text_file(path)
                except (OSError, ValueError) as exc:
                    self.failed.emit(f"{path.name}: {exc}")
                    continue
                target = out_dir / f"{path.stem}.{fmt}"
                audio = self.engine.synthesize(
                    text, speed, stop=self._stop,
                    progress=self._emit_progress)
                if self._stop.is_set():
                    raise InterruptedError(t("Reading stopped."))
                save_compressed(audio, target, fmt)
                self.finished.emit(str(target), len(audio) / SAMPLE_RATE)

except ModuleNotFoundError:  # pragma: no cover - Qt unavailable in some tests
    pass
