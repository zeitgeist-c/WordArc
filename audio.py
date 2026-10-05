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
import weakref

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
CHUNK_SECONDS = CHUNK_FRAMES / RATE
MIN_FRAMES = int(RATE * 0.25)
CHANNEL_STALL_SECONDS = 5.0
DEVICE_TARGET_PREFIX = "sd:"

# Host APIs, best first, among the copies a device can really be opened on.
# The order is the one this app has always recorded with: MME resamples to the
# app's rate everywhere, DirectSound next; a WASAPI endpoint that refuses the
# rate records nothing at all, so it only wins when nothing else opens.
_HOST_PRIORITY = ("mme", "windows directsound", "windows wasapi")
# MME truncates every device name to this many characters.
MME_NAME_LIMIT = 31

# No default device is forced here. PortAudio's own default host API (MME on
# Windows) resamples to the app's rate, while forcing the WASAPI copies — the
# obvious-looking `sd.default.hostapi` is read-only anyway — hands back "Invalid
# sample rate" for the 16 kHz this app records at.

# Every running PortAudio stream, so a device rescan can tell whether
# re-initialising the library is safe (it would end an open recording).
_streams = weakref.WeakSet()


def _open_portaudio_stream(**kwargs):
    """Create and start an input stream, tracked for the device rescan."""
    stream = sd.InputStream(**kwargs)
    stream.start()
    _streams.add(stream)
    return stream


def has_active_capture():
    """Whether a PortAudio stream is running right now.

    A stream that has been stopped keeps its Python wrapper for a moment —
    the callback thread may still be holding it — and a PortAudio restart
    under it (which refresh_devices() does itself) leaves that wrapper with a
    dead pointer, so asking whether it is active raises instead of answering.
    Such an entry is a stream that is over, not a recording: it is dropped
    here. Letting the error out took the whole settings window down with it,
    because a device rescan runs while the window is built.
    """
    for stream in list(_streams):
        try:
            running = getattr(stream, "active", False)
        except Exception:
            _streams.discard(stream)
            continue
        if running:
            return True
    return False


def refresh_devices():
    """Make the device list live again; True when the library was restarted.

    PortAudio caches what it saw when it started, so a headset reconnected
    after the app opened never shows up in a plain re-query — terminating and
    re-initialising the library is what makes it appear. Nothing happens while
    a stream is open: that would end the recording.
    """
    if has_active_capture():
        return False
    try:
        sd._terminate()
        sd._initialize()
    except Exception:
        return False
    return True


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


def _short_error(exc):
    """One log- and UI-safe line naming a PortAudio failure."""
    detail = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    name = type(exc).__name__
    return f"{name}: {detail}" if detail else name


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
            self._open_stream()
        except Exception as exc:
            self._stream = None
            reason = _short_error(exc)
            if target:
                # The saved microphone is still listed but no longer opens (a
                # disconnected Bluetooth headset keeps a dead entry behind):
                # dictate through the default input instead of failing the take.
                _log.warning("saved microphone %r did not open "
                             "(%s); falling back to the default input",
                             target, reason)
                try:
                    self._device = None
                    self._open_stream()
                except Exception as fallback_exc:
                    self._stream = None
                    reason = _short_error(fallback_exc)
                    _log.warning("default microphone did not open either "
                                 "(%s)", reason)
            else:
                _log.warning("default microphone did not open (%s)", reason)
            if self._stream is None:
                self.failed.emit(
                    t("Could not open the microphone: {error}", error=reason))

    def _open_stream(self):
        self._stream = _open_portaudio_stream(
            samplerate=RATE, channels=CHANNELS, dtype="int16",
            blocksize=CHUNK_FRAMES, device=self._device,
            callback=self._callback)

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
            self._mic_stream = _open_portaudio_stream(
                samplerate=RATE, channels=1, dtype="int16",
                blocksize=CHUNK_FRAMES, device=mic_dev,
                callback=lambda d, f, ti, s: self._mic_cb(d, f, ti, s))
        except Exception as exc:
            self._mic_stream = None
            reason = _short_error(exc)
            if mic_target:
                # The saved microphone is still listed but no longer opens
                # (a disconnected Bluetooth headset): fall back to the default
                # input for this run instead of losing the whole meeting.
                _log.warning("saved meeting microphone %r did not open "
                             "(%s); falling back to the default input",
                             mic_target, reason)
                try:
                    self._mic_stream = _open_portaudio_stream(
                        samplerate=RATE, channels=1, dtype="int16",
                        blocksize=CHUNK_FRAMES, device=None,
                        callback=lambda d, f, ti, s: self._mic_cb(d, f, ti, s))
                except Exception as fallback_exc:
                    self._mic_stream = None
                    reason = _short_error(fallback_exc)
                    _log.warning("default meeting microphone did not open "
                                 "either (%s)", reason)
            else:
                _log.warning("default meeting microphone did not open (%s)",
                             reason)
            if self._mic_stream is None:
                self._cleanup_file()
                self._remove_partial()
                self.failed.emit(
                    t("Could not open the microphone: {error}", error=reason))
                return
        if sys_dev is None:
            try:
                self._sys_stream = AudioCapture(RATE, CHUNK_FRAMES).open_loopback(
                    self._fallback_sys_cb, system_target)
            except Exception:
                pass
        else:
            try:
                self._sys_stream = _open_portaudio_stream(
                    samplerate=RATE, channels=1, dtype="int16",
                    blocksize=CHUNK_FRAMES, device=sys_dev,
                    callback=lambda d, f, ti, s: self._sys_cb(d, f, ti, s))
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


def _strip_placeholders(text):
    """Drop INF resource placeholders ("%1", "%0"), glued to words included."""
    kept = []
    index = 0
    while index < len(text):
        if text[index] == "%":
            index += 1
            while index < len(text) and text[index].isdigit():
                index += 1
            kept.append(" ")
            continue
        kept.append(text[index])
        index += 1
    return " ".join("".join(kept).split())


def _friendly_name(name):
    """One readable line for a device name.

    Windows hands PortAudio the raw driver string for the Bluetooth Hands-Free
    endpoint — "@System32\\drivers\\bthhfenum.sys,#2;%1 Hands-Free%0 ;(REDMI
    Buds 8 Lite)" — with the %1/%0 placeholders it normally fills in itself.
    Rebuild it as "Kulaklık (REDMI Buds 8 Lite) — Hands-Free".
    """
    flat = " ".join((name or "").split())
    if "@" not in flat or "%" not in flat:
        return flat
    base, _, detail = flat.partition("(")
    mode = device = ""
    for chunk in detail.split(";"):
        chunk = chunk.strip().strip("()")
        if not chunk or chunk.startswith("@") or ".sys" in chunk:
            continue
        if "%" in chunk:
            mode = _strip_placeholders(chunk) or mode
        else:
            device = chunk
    parts = [part for part in (base.strip(), device, mode) if part]
    if len(parts) == 3:
        return f"{parts[0]} ({parts[1]}) — {parts[2]}"
    if len(parts) == 2:
        return f"{parts[0]} ({parts[1]})"
    return flat


def same_device_name(left, right):
    """Whether two device names are copies of the same hardware.

    Windows exposes every device once per host API and the names usually match
    across them; MME is the exception, it truncates every name to
    MME_NAME_LIMIT characters, so its copy of a longer name is a prefix of the
    other copies'. The rule is deliberately narrow: only a name sitting exactly
    at the limit may stand in for a longer one.
    """
    left = " ".join((left or "").split()).casefold()
    right = " ".join((right or "").split()).casefold()
    if left == right:
        return True
    short, long = (left, right) if len(left) <= len(right) else (right, left)
    return len(short) == MME_NAME_LIMIT and long.startswith(short)


def _host_rank(hostapi_name):
    """Lower is better: MME, then DirectSound, then WASAPI, then the rest."""
    folded = (hostapi_name or "").strip().casefold()
    if folded in _HOST_PRIORITY:
        return _HOST_PRIORITY.index(folded)
    return len(_HOST_PRIORITY)


CONNECTION_HINTS = (
    # Bluetooth first: a headset name can carry a USB-ish word too, and the
    # bth* ids are the one thing that is never wrong about a Bluetooth device.
    ("bluetooth", "bluetooth", "bth", "bt_", "bthenum", "bthhfenum",
     "hands-free", "handsfree", "a2dp", "wireless", "redmi buds"),
    ("usb", "usb", "usbgh"),
    # The onboard controller shows up under whatever the sound card is called,
    # so this list is the card vendors rather than the word "internal".
    ("built-in", "dahili", "internal", "built in", "integrated", "onboard",
     "realtek", "hda intel", "apple", "mic array", "ses eşleştiricisi",
     "birincil ses", "thx", "amd"),
)


def _connection_kind(name, host_name=""):
    """How a device is plugged in, from what Windows calls it.

    Windows has no field for this, so it has to be read out of the names — which
    is also why a guess is made only when something actually matches: a
    wrong "USB" on a Bluetooth headset is worse than saying nothing. The host
    API is the tie-breaker, because a Bluetooth endpoint is always carried by a
    Bluetooth service and never by MME or DirectSound. The three labels are
    translated where the box is drawn, not here.
    """
    hay = f"{name or ''} {host_name or ''}".casefold()
    for kind, *hints in CONNECTION_HINTS:
        if any(hint in hay for hint in hints):
            return kind
    return ""


def _recordable(index, host_name):
    """Whether a device copy can record at the settings this app uses.

    WDM-KS copies are left out entirely: that API is kernel-exclusive, never
    resamples, and keeps a dead entry behind when its device goes away — a
    disconnected Bluetooth endpoint passes the capability check below and then
    fails to open, so it would sit in the list as a trap.
    """
    if "wdm-ks" in (host_name or "").casefold():
        return False
    try:
        sd.check_input_settings(device=index, samplerate=RATE,
                                channels=CHANNELS, dtype="int16")
        return True
    except Exception:
        return False


def list_sources():
    """Stable targets and readable labels, one row per physical device.

    PortAudio lists the same hardware once per host API (MME, DirectSound,
    WASAPI...), which filled the microphone box with three copies of every
    device; only the copy that can actually record is kept now, named with the
    fullest name any of them reported. Devices a single API exposes — the
    Bluetooth Hands-Free endpoint, for one — keep their own row.
    """
    try:
        devices = list(sd.query_devices())
        hostapis = list(sd.query_hostapis())
    except Exception:
        return []
    groups = []
    for index, d in enumerate(devices):
        if d.get("max_input_channels", 0) <= 0:
            continue
        name = d.get("name") or t("Unnamed audio device")
        host_index = d.get("hostapi", -1)
        try:
            host_name = hostapis[host_index]["name"]
        except (IndexError, KeyError, TypeError):
            host_name = ""
        entry = (_host_rank(host_name), index, host_index, name, host_name)
        for group in groups:
            if same_device_name(group["name"], name):
                group["members"].append(entry)
                break
        else:
            groups.append({"name": name, "members": [entry]})
    out = []
    for group in groups:
        # A copy that cannot record at the app's settings would only fail the
        # take, so the recordable ones win even when they are the older API.
        usable = [m for m in group["members"] if _recordable(m[1], m[4])]
        _, _, host_index, name, host_name = min(usable or group["members"])
        label = _friendly_name(max((m[3] for m in group["members"]), key=len))
        out.append([f"{DEVICE_TARGET_PREFIX}{host_index}:{name}", label,
                    host_name, bool(usable)])
    # A device no copy can record from only fails the take, so it stays out of
    # the box — unless that would empty the list entirely, in which case the
    # devices are still worth offering.
    playable = [row for row in out if row[3]]
    if playable:
        out = playable
    # Two different devices can still carry the same name; keep those apart.
    counts = {}
    for _, label, *_ in out:
        folded = label.casefold()
        counts[folded] = counts.get(folded, 0) + 1
    return [(target, f"{label} ({host_name})"
             if host_name and counts[label.casefold()] > 1 else label)
            for target, label, host_name, _ in out]


def describe_sources():
    """[(target, label, connection)] for the device boxes, with the kind.

    list_sources() answers "which device is this" and stays a flat pair list,
    because the recording code and the tests both read it that way. This adds
    the one extra thing the settings list shows under the name — how the device
    is connected — by asking audio.list_sources() rather than re-walking
    PortAudio, so the two can never disagree about which devices exist.
    """
    out = []
    for target, label in list_sources():
        out.append((target, label, _connection_kind(label)))
    return out


def describe_monitors():
    """[(target, label, connection)] for the system-sound boxes.

    Same shape as describe_sources(), and for the same reason: the card row
    wants one extra line of text, and re-walking PortAudio here would risk
    the two lists naming different outputs.
    """
    return [(target, label, _connection_kind(label))
            for target, label in list_monitors()]


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
