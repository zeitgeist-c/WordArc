"""Raw PCM capture with a live level meter, via sounddevice (WASAPI)."""

import array
import logging
import math
import os
import queue
import tempfile
import threading
import time
import wave

try:
    import sounddevice as sd
except ModuleNotFoundError:
    # Minimal stub for tests when sounddevice unavailable.
    class _DummyStream:
        def __init__(self, *args, **kwargs):
            pass
        def start(self):
            pass
        def stop(self):
            pass
        def close(self):
            pass
    class _DummySD:
        InputStream = _DummyStream
        OutputStream = _DummyStream
        def query_devices(self, *args):
            if args:
                return {"name": "", "hostapi": 0,
                        "max_input_channels": 0, "max_output_channels": 0}
            return []
        def query_hostapis(self):
            return []
        default = type('obj', (), {'hostapi': None, 'device': (None, None)})
    sd = _DummySD()


from PyQt6.QtCore import QObject, pyqtSignal

from i18n import t
from audio_capture import AudioCapture

_log = logging.getLogger("wordarc.audio")

RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # int16
CHUNK_FRAMES = 1024
CHUNK_BYTES = CHUNK_FRAMES * SAMPLE_WIDTH * CHANNELS
CHUNK_SECONDS = CHUNK_FRAMES / RATE
MIN_FRAMES = int(RATE * 0.25)
CHANNEL_STALL_SECONDS = 5.0
DEVICE_TARGET_PREFIX = "sd:"

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


def write_wav(pcm, rate=RATE, channels=CHANNELS, width=SAMPLE_WIDTH):
    fd, path = tempfile.mkstemp(prefix="wordarc-", suffix=".wav")
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
        self._error_reported = False

    def start(self, target="", max_seconds=300):
        if self.active:
            return
        self._device = _match_input_device(target)
        self._buffer = bytearray()
        self._rms = []
        self._cancelled = False
        self._error_reported = False
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
        if status and not self._error_reported:
            self._error_reported = True
            self.failed.emit(t("The sound device stopped responding."))
            return
        _chunk, peak, _rms = self._on_data(indata, frames, time_info, status)
        self.level.emit(peak)
        # The GUI timer calls stop() at the configured limit.  Stopping the
        # stream here used to race with that call: stop() would then see a
        # missing stream and never emit ``stopped``, leaving the UI busy
        # forever.  Let the timer own the transition and accept at most one
        # timer interval of extra audio.

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
    limit_reached = pyqtSignal()
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
        self._q = queue.Queue(maxsize=256)  # tuples (which_channel, bytes, peak)
        self._stopped_evt = threading.Event()
        self._error_reported = False
        self._error_lock = threading.Lock()

    def start(self, path, mic_target="", system_target="", max_seconds=14400):
        if self.active:
            return
        self._path = path
        self._frames = 0
        self._cancelled = False
        self._error_reported = False
        # stop() leaves the event set and callbacks can leave queue entries
        # behind.  Both belong to one recording only; reusing them made every
        # meeting after the first end immediately or consume stale audio.
        self._stopped_evt.clear()
        self._q = queue.Queue(maxsize=256)
        self._max_frames = int(max_seconds * RATE)
        try:
            parent = os.path.dirname(os.path.abspath(path))
            os.makedirs(parent, exist_ok=True)
            self._wav = wave.open(path, "wb")
            self._wav.setnchannels(2)
            self._wav.setsampwidth(SAMPLE_WIDTH)
            self._wav.setframerate(RATE)
        except (OSError, wave.Error) as exc:
            self._cleanup_file()
            self._remove_partial()
            self.failed.emit(t("Could not start recording: {error}", error=exc))
            return
        mic_dev = _match_input_device(mic_target)
        sys_dev = _match_loopback_device(system_target) if system_target else None
        try:
            self._mic_stream = sd.InputStream(
                samplerate=RATE, channels=1, dtype="int16",
                blocksize=CHUNK_FRAMES, device=mic_dev,
                callback=lambda d, f, ti, s: self._mic_cb(d, f, ti, s))
            self._mic_stream.start()
        except Exception:
            self._mic_stream = None
            if mic_target:
                # The saved microphone is still listed but no longer opens
                # (a disconnected Bluetooth headset): fall back to the default
                # input for this run instead of losing the whole meeting.
                _log.warning("saved meeting microphone %r did not open; "
                             "falling back to the default input", mic_target)
                try:
                    self._mic_stream = sd.InputStream(
                        samplerate=RATE, channels=1, dtype="int16",
                        blocksize=CHUNK_FRAMES, device=None,
                        callback=lambda d, f, ti, s: self._mic_cb(d, f, ti, s))
                    self._mic_stream.start()
                except Exception:
                    self._mic_stream = None
            if self._mic_stream is None:
                self._cleanup_file()
                self._remove_partial()
                self.failed.emit(t("Could not open the microphone."))
                return
        if sys_dev is None:
            try:
                self._sys_stream = AudioCapture(RATE, CHUNK_FRAMES).open_loopback(
                    self._fallback_sys_cb, system_target)
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
        if self._sys_stream is None and system_target:
            self._cleanup_file()
            self._mic_stream.stop()
            self._mic_stream = None
            self._remove_partial()
            self.failed.emit(t("Could not start the system loopback"))
            return
        self._writer_thread = threading.Thread(target=self._writer, daemon=True)
        self._writer_thread.start()

    def _mic_cb(self, indata, frames, time_info, status):
        if status:
            self._capture_failed()
            return
        b = indata.tobytes()
        peak, _ = _peak_rms(b)
        self._enqueue("m", b, peak)

    def _sys_cb(self, indata, frames, time_info, status):
        if status:
            self._capture_failed()
            return
        b = indata.tobytes()
        peak = _peak_only(b)
        self._enqueue("s", b, peak)

    def _fallback_sys_cb(self, data, error=None):
        if error is not None or data is None:
            self._capture_failed()
            return
        self._enqueue("s", data, _peak_only(data))

    def _enqueue(self, channel, data, peak):
        try:
            self._q.put_nowait((channel, data, peak))
        except queue.Full:
            self._capture_failed()

    def _capture_failed(self):
        with self._error_lock:
            if self._error_reported or self._stopped_evt.is_set():
                return
            self._error_reported = True
        self.died.emit()

    def _writer(self):
        pending_m, pending_s = b"", b""
        last_m_peak, last_s_peak = 0.0, 0.0
        unmatched_since = None
        try:
            while not self._stopped_evt.is_set():
                try:
                    which, b, peak = self._q.get(timeout=0.2)
                except queue.Empty:
                    if (unmatched_since is not None
                            and time.monotonic() - unmatched_since
                            > CHANNEL_STALL_SECONDS):
                        raise OSError("one audio source stopped producing data")
                    continue
                if which == "m":
                    pending_m += b
                    last_m_peak = peak
                else:
                    pending_s += b
                    last_s_peak = peak
                if pending_m and pending_s:
                    unmatched_since = None
                elif pending_m or pending_s:
                    unmatched_since = unmatched_since or time.monotonic()
                    if time.monotonic() - unmatched_since > CHANNEL_STALL_SECONDS:
                        raise OSError("one audio source stopped producing data")
                n = min(len(pending_m), len(pending_s)) & ~1
                if n:
                    left = array.array("h"); left.frombytes(pending_m[:n])
                    right = array.array("h"); right.frombytes(pending_s[:n])
                    stereo = array.array("h")
                    for l, r in zip(left, right):
                        stereo.append(l); stereo.append(r)
                    self._wav.writeframes(stereo.tobytes())
                    self._frames += n // 2
                    pending_m = pending_m[n:]
                    pending_s = pending_s[n:]
                    self.levels.emit(last_m_peak, last_s_peak)
                    if self._frames >= self._max_frames:
                        self.limit_reached.emit()
                        return
        except Exception:
            self._capture_failed()

    def _cleanup_file(self):
        if self._wav is not None:
            try:
                self._wav.close()
            except Exception:
                pass
            self._wav = None

    def _remove_partial(self):
        try:
            os.unlink(self._path)
        except OSError:
            pass

    def cancel(self):
        self._cancelled = True
        self.stop()
        self._remove_partial()

    def stop(self):
        if self._mic_stream is not None:
            try:
                self._mic_stream.stop()
            except Exception:
                pass
        if self._sys_stream is not None:
            try:
                closer = getattr(self._sys_stream, "stop", None) or getattr(
                    self._sys_stream, "close", None)
                if closer:
                    closer()
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
    """Map a stable device target (or a legacy name) to a device index."""
    if not target:
        return None
    target = target.strip()
    devices = list(sd.query_devices())
    if target.startswith(DEVICE_TARGET_PREFIX):
        try:
            host_text, wanted_name = target[len(DEVICE_TARGET_PREFIX):].split(":", 1)
            wanted_host = int(host_text)
        except (TypeError, ValueError):
            return None
        for i, d in enumerate(devices):
            if (d["max_input_channels"] > 0
                    and d.get("hostapi") == wanted_host
                    and d.get("name") == wanted_name):
                return i
        return None
    # Compatibility with settings saved before stable targets were introduced.
    for i, d in enumerate(devices):
        if d["max_input_channels"] > 0 and target.casefold() in d["name"].casefold():
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
    """Return stable targets and useful labels for every PortAudio input."""
    try:
        devices = list(sd.query_devices())
        hostapis = list(sd.query_hostapis())
    except Exception:
        return []
    inputs = [d for d in devices if d.get("max_input_channels", 0) > 0]
    name_counts = {}
    for d in inputs:
        folded = (d.get("name") or "").casefold()
        name_counts[folded] = name_counts.get(folded, 0) + 1
    out = []
    for d in inputs:
        name = d.get("name") or t("Unnamed audio device")
        host_index = d.get("hostapi", -1)
        target = f"{DEVICE_TARGET_PREFIX}{host_index}:{name}"
        label = name
        if name_counts.get(name.casefold(), 0) > 1:
            try:
                label = f"{name} ({hostapis[host_index]['name']})"
            except (IndexError, KeyError, TypeError):
                pass
        out.append((target, label))
    return out


def list_monitors():
    """[(name, description)] for every usable meeting loopback.

    All PortAudio "(loopback)" inputs first (every output, not just the
    default), then the Windows Core Audio speakers as fallback. The UI
    already inserts a 'Current output' item with data='', so an empty
    list simply means "nothing beyond the default was seen".
    """
    seen = set()
    out = []
    try:
        devices = list(sd.query_devices())
    except Exception:
        devices = []
    for d in devices:
        name = d.get("name") or ""
        if d.get("max_input_channels", 0) > 0 and "loopback" in name.lower():
            if name not in seen:
                seen.add(name)
                out.append((name, name))
    for name, label in AudioCapture.output_devices():
        if name not in seen:
            seen.add(name)
            out.append((name, label))
    return out
