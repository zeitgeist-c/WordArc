"""Speech to text on this computer, with faster-whisper.

The cloud path in api.py is one way to turn speech into text; this is the other.
Both answer the same question and are called the same way, so the caller picks
one and never asks which it got.

Why a separate module rather than a second client inside api.py: everything this
needs is optional. The cloud client is four stdlib modules and an API key; this
one pulls in ctranslate2, onnxruntime and a 1.6 GB model file, and every one of
those is a reason an installation can fail on a machine that does not want it.
So nothing heavy is imported until it is asked for, and every failure to reach
this engine is reported as a plain, actionable message instead of an import
error at start-up.

The audio the app records is already 16 kHz mono s16 WAV, which is exactly what
Whisper wants, so decoding is the stdlib wave module and a float32 array — PyAV
is a faster-whisper dependency but is never called for a WAV we produced
ourselves.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import threading
import wave
from dataclasses import dataclass

from i18n import t

_log = logging.getLogger("wordarc.localspeech")

RATE = 16000           # what the app records, and what Whisper is trained on
COMPUTE_TYPE = "int8"  # float32 is several times slower for no accuracy gain here
THREADS = 8

# The three sizes, and what each is for. Measured on the machine this was
# written on (16 threads, no GPU) on Turkish dictation: base read a noisy take
# without a single error, small added an invented closing sentence,
# large-v3-turbo read it cleanly and invented nothing. The smallest Whisper size
# is not offered because it breaks words apart ("WordArc" -> "4.projesinin"), and
# a dictation the user has to read and fix is worse than no dictation at all.
MODEL_CHOICES = (
    ("base", "Systran/faster-whisper-base"),
    ("small", "Systran/faster-whisper-small"),
    ("large-v3-turbo", "mobiuslabsgmbh/faster-whisper-large-v3-turbo"),
)

# Only these make a model usable. The repository also carries the original
# float16 weights and a PyTorch export, several times the size of the
# CTranslate2 model, and this engine never loads them. The tokenizer comes as
# vocabulary.txt in the Systran repositories and as vocabulary.json in the turbo
# one, so either satisfies the check; listing only one is how a download finishes
# and then reports itself incomplete.
REQUIRED_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
ALSO_ACCEPTED = ("vocabulary.json", "preprocessor_config.json")
REQUIRED_ANY = ("vocabulary.txt", "vocabulary.json")

# One engine per process, shared. Loading a model is seconds of work (measured:
# 2.8 s for large-v3-turbo, 0.9 s for small) and the dictation hotkey can be
# pressed twice in a row, so a per-call load would be felt as a stall on the
# second take. Switching model replaces it and the old one is dropped.
_lock = threading.Lock()
_model = None
_model_name = ""


class LocalSpeechError(Exception):
    """Anything that keeps the local engine from answering."""


class Cancelled(LocalSpeechError):
    """The user asked to stop; the caller treats it as a stop, not a failure."""


def human_size(num_bytes):
    """A download size as the user would say it: 142 MB, 1,6 GB.

    Rounded to a size anyone can act on — a file count rounded to the megabyte
    reads as false precision next to a figure like "1,6 GB", and this string
    goes in front of a button that starts the download.
    """
    if num_bytes >= 1024 ** 3:
        value = num_bytes / 1024 ** 3
        text = f"{value:.1f}".rstrip("0").rstrip(".")
        return f"{text.replace('.', ',')} GB"
    if num_bytes >= 1024 ** 2:
        return f"{round(num_bytes / 1024 ** 2)} MB"
    if num_bytes:
        return f"{round(num_bytes / 1024)} KB"
    return ""


@dataclass(frozen=True)
class ModelState:
    name: str
    installed: bool
    size: int          # bytes on disk, 0 when absent
    expected: int = 0  # roughly the download, for the label
    path: str = ""


def default_model():
    return "large-v3-turbo"


# The two ways a take can be read. The label is the user's own phrasing: where
# the work happens, not which library does it.
ENGINES = (
    ("Cloud (Gemini)", "cloud"),
    ("Local (this computer)", "local"),
)

# What each size costs to download, measured from the files actually fetched.
# The box and the status line quote the same number, so a user who reads
# "1,6 GB" in the list and "1,5 GB" underneath does not stop to wonder which is
# right.
EXPECTED_SIZES = {
    "base": 147_882_941,          # 141 MB
    "small": 486_391_123,         # 464 MB
    "large-v3-turbo": 1_620_000_000,  # 1,5 GB
}

# The same figures as the box writes them, in the interface language's decimal
# comma, so the two places cannot drift apart. The note is what the extra
# megabytes actually buy, measured on one hard Turkish take (50 words: a
# product name, two acronyms, a number spelled in words, a closing question):
#   base 43/50 at 18x realtime, small 42/50 at 9x, large-v3-turbo 43/50 at 4x
# turbo is the safest pick on the hardest audio, not on every take — it is the
# one that never mangled a product name into two words or added a closing
# sentence. base is listed as quick, not as wrong: it scored the same here.
MODEL_NOTES = {
    "base": "quick, 141 MB",
    "small": "middle, 464 MB",
    "large-v3-turbo": "hardest audio, 1,5 GB",
}


def model_label(name):
    """(label, note) for the model box: the name and what it costs."""
    return f"Whisper {name}", MODEL_NOTES.get(name, "")


def model_names():
    return [name for name, _repo in MODEL_CHOICES]


def _repo(name):
    return dict(MODEL_CHOICES).get(name)


def models_dir():
    import config
    return config.DATA_DIR / "whisper"


def _root(name, where=None):
    repo = _repo(name)
    if repo is None:
        return ""
    return os.path.join(str(where or models_dir()), repo.replace("/", "--"))


def _is_installed(name, where=None):
    root = _root(name, where)
    if not root:
        return False
    if not all(os.path.exists(os.path.join(root, part)) for part in REQUIRED_FILES
               if part not in REQUIRED_ANY):
        return False
    # One tokenizer file is enough; which one depends on the repository.
    return any(os.path.exists(os.path.join(root, part)) for part in REQUIRED_ANY)


def _dir_size(path):
    total = 0
    with contextlib.suppress(OSError):
        for entry in os.scandir(path):
            with contextlib.suppress(OSError):
                total += entry.stat().st_size
    return total


def _expected_size(name):
    return EXPECTED_SIZES.get(name, 0)


def state(name, where=None):
    """What Settings shows: on disk or not, and how much room it takes."""
    if _repo(name) is None:
        return ModelState(name, False, 0)
    if not _is_installed(name, where):
        return ModelState(name, False, 0, _expected_size(name))
    return ModelState(name, True, _dir_size(_root(name, where)),
                      _expected_size(name), _root(name, where))


def installed_size(where=None):
    """Bytes the installed models take, for the settings summary."""
    return sum(state(name, where).size for name in model_names())


def _fail(message, **kwargs):
    raise LocalSpeechError(t(message, **kwargs) if kwargs else t(message))


def download(name, where=None, should_stop=None, on_progress=None):
    """Fetch one model into place. Blocking — call it off the UI thread."""
    if _repo(name) is None:
        _fail("Unknown local model: {name}", name=name)
    if _is_installed(name, where):
        return 0
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        _fail("The download helper is missing. Reinstall WordArc to get it "
              "back.")
    root = _root(name, where)
    os.makedirs(root, exist_ok=True)
    try:
        snapshot_download(
            repo_id=_repo(name),
            local_dir=root,
            # The tokenizer and the config are what this engine reads; the rest
            # of the repository is another framework's copy of the same weights.
            allow_patterns=[*REQUIRED_FILES, *ALSO_ACCEPTED],
            max_workers=4,
        )
    except Exception as exc:
        # A half-written model is worse than none: it would pass the file check
        # and then fail at load with a message nobody can act on.
        shutil.rmtree(root, ignore_errors=True)
        _fail("Could not download the local model: {error}", error=exc)
    if not _is_installed(name, where):
        shutil.rmtree(root, ignore_errors=True)
        _fail("The local model downloaded incompletely. Try again.")
    with contextlib.suppress(Exception):
        if on_progress is not None:
            on_progress(1.0)
    return _dir_size(root)


def remove(name, where=None):
    """Delete a model from disk. True when something was there."""
    root = _root(name, where)
    if not root or not os.path.isdir(root):
        return False
    shutil.rmtree(root, ignore_errors=True)
    return True


def _check_cancelled(should_stop):
    if should_stop is not None and should_stop():
        raise Cancelled(t("Stopped."))


def engine(name, where=None):
    """The loaded model, or an error saying what the user should do.

    ``where`` is where the models live; the app always uses the default, and a
    test passes its own directory so a run never touches the real one.
    """
    global _model, _model_name
    name = name or default_model()
    if _repo(name) is None:
        _fail("Unknown local model: {name}", name=name)
    cache = where or models_dir()
    with _lock:
        if _model is not None and _model_name == name:
            return _model
        if not _is_installed(name, cache):
            _fail("The local model {name} is not installed yet. Download it "
                  "in Settings.", name=name)
        try:
            from faster_whisper import WhisperModel
            # faster-whisper's own downloader is deliberately bypassed. It
            # would look the model up by name in the huggingface cache, which
            # is a different layout from the one download() writes, so the
            # engine went looking for a snapshot the app never created. Handing
            # it the directory we filled is the whole point of doing the
            # download ourselves.
            _model = WhisperModel(_root(name, cache), device="cpu",
                                  compute_type=COMPUTE_TYPE,
                                  cpu_threads=THREADS)
        except ImportError:
            _model, _model_name = None, ""
            _fail("The local speech engine is missing. Reinstall WordArc to "
                  "get it back.")
        except Exception as exc:  # ctranslate2 raises bare RuntimeError
            _model, _model_name = None, ""
            _fail("Could not load the local model: {error}", error=exc)
        _model_name = name
        return _model


def transcribe(name, wav_path, language="", prompt="", should_stop=None,
               with_segments=False, where=None):
    """The transcript of one WAV file.

    Same arguments as the cloud call, so a caller that already speaks to a
    transcriber can be pointed here by changing one name. ``with_segments``
    asks for [(start, end, text)] instead of a single string, which the callers
    that lay out a timeline need and the dictation path does not.
    """
    model = engine(name, where)
    audio = _read_wav(wav_path)
    # A zero-length take makes Whisper answer with something invented, which is
    # the one failure the app's own silence check exists to prevent; fail here
    # rather than hand back a sentence nobody said.
    if not len(audio):
        _fail("The recording was empty.")
    _check_cancelled(should_stop)
    options = dict(beam_size=5,
                   # Whisper feeds its own output back in as context for the
                   # next window, and on a stream of dictation that is how one
                   # take turns into the same closing sentence twice. Nothing
                   # here needs the previous window.
                   condition_on_previous_text=False,
                   initial_prompt=prompt or None)
    if with_segments:
        options["word_timestamps"] = True
    language = None if language in ("", "auto", None) else language
    try:
        # A generator, not a list: only the first window is decoded at this
        # point, and the rest happens as it is walked.
        segments, _info = model.transcribe(audio, language=language, **options)
        if with_segments:
            out = []
            for seg in segments:
                _check_cancelled(should_stop)
                out.append((seg.start, seg.end, seg.text.strip()))
            return out
        return " ".join(seg.text.strip() for seg in segments).strip()
    except LocalSpeechError:
        raise
    except Exception as exc:
        _fail("Local transcription failed: {error}", error=exc)


def _read_wav(path):
    """The file as float32 in -1..1, which is the array Whisper takes."""
    import numpy
    with contextlib.closing(wave.open(path, "rb")) as wav:
        rate = wav.getframerate()
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        raw = wav.readframes(wav.getnframes())
    if width != 2:
        _fail("The local model reads 16-bit audio.")
    if rate != RATE:
        _fail("The local model reads {rate} kHz audio, but this recording is "
              "{actual} kHz.", rate=16, actual=round(rate / 1000))
    samples = numpy.frombuffer(raw, dtype=numpy.int16)
    if channels > 1:
        samples = samples.reshape(-1, channels)[:, 0]
    return samples.astype(numpy.float32) / 32768.0


# --- the bridge the app calls ---------------------------------------------

def transcribe_for(conf, wav_path, language="", prompt="", should_stop=None,
                   with_segments=False, client=None):
    """Transcribe with whichever engine the settings ask for.

    The cloud and the local engine answer the same question, so every caller
    goes through this and switching engines in Settings changes all of them at
    once.

    A local failure never falls through to the cloud. Choosing the local engine
    is the user saying the audio does not leave this computer; quietly
    uploading it after a local error would break that promise without telling
    them, so the error is surfaced instead and the settings say what to do.

    ``client`` is the caller's own GeminiClient, carrying its failover
    callbacks; one is built here when the caller has none.
    """
    if conf.get("transcribe_engine", "cloud") != "local":
        return _cloud(conf, wav_path, language, prompt, should_stop,
                      with_segments, client)
    name = conf.get("local_stt_model") or default_model()
    try:
        return transcribe(name, wav_path, language, prompt, should_stop,
                          with_segments)
    except Cancelled:
        raise
    except LocalSpeechError as exc:
        _log.warning("local engine could not answer (%s); not sending the "
                     "audio to the cloud, because local was chosen", exc)
        raise


def _cloud(conf, wav_path, language, prompt, should_stop, with_segments,
           client=None):
    if client is None:
        import api
        client = api.GeminiClient(conf.gemini_keys(), should_stop=should_stop)
    text = client.transcribe(conf["gemini_transcribe_model"], wav_path,
                             language=language, prompt=prompt)
    if not with_segments:
        return text
    # The cloud engine reports no timings, and a caller that needs a timeline
    # chunks the audio itself and places each chunk at its own offset, so one
    # entry carrying the whole chunk is exactly what it expects.
    return [(0.0, 0.0, text.strip())]
