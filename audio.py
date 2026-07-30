"""Raw PCM capture with a live level meter, via sounddevice (WASAPI)."""

import array
import math
import queue
import tempfile
import threading
import wave

import sounddevice as sd

from PyQt6.QtCore import QObject, pyqtSignal

from i18n import t

RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # int16
CHUNK_FRAMES = 1024
CHUNK_BYTES = CHUNK_FRAMES * SAMPLE_WIDTH * CHANNELS
CHUNK_SECONDS = CHUNK_FRAMES / RATE
MIN_FRAMES = int(RATE * 0.25)

# Force WASAPI when present; fall back silently otherwise.
try:
    for i, host in enumerate(sd.query_hostapis()):
        if host["name"].lower() == "wasapi":
            sd.default.hostapi = i
            break
except Exception:
    pass


def _peak_rms(chunk):
    """(peak, rms) in 0..1 for an int16 byte chunk."""
    samples = array.array("h")
    usable = len(chunk) - (len(chunk) % 2)
    if usable <= 0:
        return 0.0, 0.0
    samples.frombytes(chunk[:usable])
    peak = max(abs(min(samples)), abs(max(samples))) / 32768.0
    rms = math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768.0
    return min(1.0, peak), min(1.0, rms)


def chunk_levels(chunk):
    return _peak_rms(chunk)


def stereo_levels(chunk):
    """(left peak, right peak) in 0..1 from interleaved int16 stereo."""
    samples = array.array("h")
    usable = len(chunk) - (len(chunk) % 4)
    if usable <= 0:
        return 0.0, 0.0
    samples.frombytes(chunk[:usable])
    left = samples[0::2]
    right = samples[1::2]
    lp = min(1.0, max(abs(min(left)), abs(max(left))) / 32768.0) if left else 0.0
    rp = min(1.0, max(abs(min(right)), abs(max(right))) / 32768.0) if right else 0.0
    return lp, rp


def write_wav(pcm, rate=RATE, channels=CHANNELS, width=SAMPLE_WIDTH):
    fd, path = tempfile.mkstemp(prefix="verbatim-", suffix=".wav")
    with open(fd, "wb") as raw, wave.open(raw, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return path


class _CaptureBase:
    """Common meter/stop plumbing shared by the two recorders."""
    def __init__(self):
        self._lock = threading.Lock()
        self._buffer = bytearray()
        self._rms = []
        self._cancelled = False
        self._stream = None

    def _on_data(self, indata, frames, time_info, status):
        chunk = indata.tobytes()
        peak, rms = _peak_rms(chunk)
        with self._lock:
            self._buffer.extend(chunk)
            self._rms.append(rms)
        return chunk, peak, rms


class Recorder(QObject, _CaptureBase):
    """Mono capture for dictation, mirroring the Linux Recorder signature."""

    level = pyqtSignal(float)
    stopped = pyqtSignal(str, float, object)
    failed = pyqtSignal(str)
    active = property(lambda self: self._stream is not None)

    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        _CaptureBase.__init__(self)
        self._device = None

    def start(self, target="", max_seconds=300):
        if self.active:
            return
        self._device = _match_input_device(target)
        self._buffer = bytearray()
        self._rms = []
        self._cancelled = False
        self._max_bytes = int(max_seconds * RATE * SAMPLE_WIDTH * CHANNELS)
        try:
            self._stream = sd.InputStream(
                samplerate=RATE, channels=CHANNELS, dtype="int16",
                blocksize=CHUNK_FRAMES, device=self._device,
                callback=self._callback)
            self._stream.start()
        except Exception as exc:
            self._stream = None
            self.failed.emit(t("Could not open the microphone."))

    def _callback(self, indata, frames, time_info, status):
        chunk, peak, _rms = self._on_data(indata, frames, time_info, status)
        self.level.emit(peak)
        with self._lock:
            too_long = len(self._buffer) >= self._max_bytes
        if too_long:
            self._stop_stream()

    def _stop_stream(self):
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
            self._stream = None

    def cancel(self):
        self._cancelled = True
        self._stop_stream()
        with self._lock:
            self._buffer = bytearray()

    def stop(self):
        if self._stream is None:
            return
        self._stop_stream()
        with self._lock:
            pcm = bytes(self._buffer)
            rms = list(self._rms)
            self._buffer = bytearray()
            self._rms = []
        if self._cancelled:
            return
        frames = len(pcm) // (SAMPLE_WIDTH * CHANNELS)
        if frames < MIN_FRAMES:
            self.failed.emit(t("Recording too short, speak for at least 0.3 s"))
            return
        path = write_wav(pcm)
        self.stopped.emit(path, frames / RATE, rms)


class MeetingRecorder(QObject, _CaptureBase):
    """Microphone (left) + system loopback (right) into a stereo WAV."""

    levels = pyqtSignal(float, float)
    stopped = pyqtSignal(str, float)
    died = pyqtSignal()
    failed = pyqtSignal(str)
    active = property(lambda self: self._mic_stream is not None)

    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        _CaptureBase.__init__(self)
        self._wav = None
        self._path = ""
        self._frames = 0
        self._mic_stream = None
        self._sys_stream = None
        self._writer_thread = None
        self._q = queue.Queue()      # tuples (which_channel, bytes)
        self._stopped_evt = threading.Event()

    def start(self, path, mic_target="", system_target="", max_seconds=14400):
        if self.active:
            return
        self._path = path
        self._frames = 0
        self._cancelled = False
        self._max_frames = int(max_seconds * RATE)
        try:
            self._wav = wave.open(path, "wb")
            self._wav.setnchannels(2)
            self._wav.setsampwidth(SAMPLE_WIDTH)
            self._wav.setframerate(RATE)
        except OSError as exc:
            self.failed.emit(t("Could not start recording: {error}", error=exc))
            return
        mic_dev = _match_input_device(mic_target)
        sys_dev = _match_loopback_device(system_target)
        try:
            self._mic_stream = sd.InputStream(
                samplerate=RATE, channels=1, dtype="int16",
                blocksize=CHUNK_FRAMES, device=mic_dev,
                callback=lambda d, f, ti, s: self._mic_cb(d, f, ti, s))
            self._mic_stream.start()
        except Exception:
            self._cleanup_file()
            self.failed.emit(t("Could not open the microphone."))
            return
        if sys_dev is None:
            try:
                import wasapi_loopback
                self._sys_stream = wasapi_loopback.open(RATE)
            except Exception:
                pass
        else:
            try:
                self._sys_stream = sd.InputStream(
                    samplerate=RATE, channels=1, dtype="int16",
                    blocksize=CHUNK_FRAMES, device=sys_dev,
                    callback=lambda d, f, ti, s: self._sys_cb(d, f, ti, s))
                self._sys_stream.start()
            except Exception:
                self._sys_stream = None
                # No system capture is not fatal — record a silent right channel.
        if self._sys_stream is None:
            self._cleanup_file()
            self.failed.emit(t("Could not start the system loopback"))
            self._mic_stream.stop()
            self._mic_stream = None
            return
        self._writer_thread = threading.Thread(target=self._writer, daemon=True)
        self._writer_thread.start()

    def _mic_cb(self, indata, frames, time_info, status):
        b = indata.tobytes()
        peak, _ = _peak_rms(b)
        self._q.put(("m", b, peak))

    def _sys_cb(self, indata, frames, time_info, status):
        b = indata.tobytes()
        peak = _peak_only(b)
        self._q.put(("s", b, peak))

    def _writer(self):
        pending_m, pending_s = b"", b""
        last_m_peak, last_s_peak = 0.0, 0.0
        while not self._stopped_evt.is_set():
            try:
                which, b, peak = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            if which == "m":
                pending_m += b
                last_m_peak = peak
            else:
                pending_s += b
                last_s_peak = peak
            # interleave at the smallest common length
            n = min(len(pending_m), len(pending_s)) & ~3
            if n:
                cm = pending_m[:n]
                cs = pending_s[:n]
                samples = array.array("h")
                samples.frombytes(cm)
                left = samples[:]
                samples2 = array.array("h")
                samples2.frombytes(cs)
                right = samples2[:]
                stereo = array.array("h")
                for l, r in zip(left, right):
                    stereo.append(l)
                    stereo.append(r)
                self._wav.writeframes(stereo.tobytes())
                self._frames += n // 2
                pending_m = pending_m[n:]
                pending_s = pending_s[n:]
                self.levels.emit(last_m_peak, last_s_peak)
                if self._frames >= self._max_frames:
                    self._stopped_evt.set()
                    return

    def _cleanup_file(self):
        if self._wav is not None:
            try:
                self._wav.close()
            except Exception:
                pass
            self._wav = None

    def cancel(self):
        self._cancelled = True
        self.stop()

    def stop(self):
        try:
            if self._mic_stream is not None:
                self._mic_stream.stop()
            if isinstance(self._sys_stream, sd.InputStream) and self._sys_stream is not None:
                self._sys_stream.stop()
        except Exception:
            pass
        self._stopped_evt.set()
        if self._writer_thread is not None:
            self._writer_thread.join(timeout=3)
        self._writer_thread = None
        self._mic_stream = None
        self._sys_stream = None
        self._cleanup_file()
        if self._cancelled:
            return
        if self._frames < MIN_FRAMES:
            self.failed.emit(t("Recording too short, speak for at least 0.3 s"))
            return
        self.stopped.emit(self._path, self._frames / RATE)


def _peak_only(chunk):
    samples = array.array("h")
    usable = len(chunk) - (len(chunk) % 2)
    if usable <= 0:
        return 0.0
    samples.frombytes(chunk[:usable])
    return min(1.0, max(abs(min(samples)), abs(max(samples))) / 32768.0)


def _match_input_device(target):
    """Map a config mic_target substring to a sounddevice device index, else None."""
    if not target:
        return None
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and target.lower() in d["name"].lower():
            return i
    return None


def _match_loopback_device(target):
    """Index of the matching output's WASAPI loopback, or None.

    PortAudio exposes loopback capture devices on Windows under WASAPI. When a
    specific target device name is given, its loopback sibling is looked up.
    Otherwise the default output's loopback is returned. Falls back to None
    (the ctypes path is then attempted by the caller).
    """
    try:
        if target:
            out_name = target.lower()
        else:
            default_out = sd.default.device[1]
            if default_out is None:
                return None
            out_name = sd.query_devices(default_out)["name"].lower()
    except Exception:
        return None
    for i, d in enumerate(sd.query_devices()):
        name = (d.get("name") or "").lower()
        if d["max_input_channels"] > 0 and name == out_name + " (loopback)":
            return i
    # Fallback: any device whose name contains the target + "loopback"
    for i, d in enumerate(sd.query_devices()):
        name = (d.get("name") or "").lower()
        if d["max_input_channels"] > 0 and "loopback" in name and out_name in name:
            return i
    return None


def list_sources():
    """[(name, description)] for every input device."""
    out = []
    for d in sd.query_devices():
        if d["max_input_channels"] > 0:
            out.append((d["name"], d["name"]))
    return out


def list_monitors():
    """[(name, description)] for the loopback of the default output.

    settings_ui already inserts a 'Current output' item with data='', so when
    no real loopback device is visible we return [] rather than duplicating it.
    """
    dev = _match_loopback_device("")
    if dev is None:
        return []
    d = sd.query_devices(dev)
    return [(d["name"], d["name"])]


def default_monitor():
    dev = _match_loopback_device("")
    name = sd.query_devices(dev)["name"] if dev is not None else ""
    return name
