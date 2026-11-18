"""Temporarily lower the Windows speaker/headphone volume while dictating.

Only the *render* (output) endpoint's master volume scalar is touched, and
only while a dictation recording runs. The microphone/capture level and the
permanent Windows Communications ducking setting are never modified.

Lifecycle contract (see ``wordarc.WordArc``):
- ``start()`` when dictation capture begins; ``stop()`` the moment dictation
  ends (before transcription runs), on cancel, on recorder/connection errors
  and on application shutdown. Meeting recording takes precedence: dictation
  never ducks while a meeting records, and starting a meeting restores first.
- Every public method is idempotent and never raises: an audio-control
  failure is logged and dictation continues at full volume.
- All reads and writes are bound to one device id captured at ``start()``.
  If the default output changes mid-recording, the new default is never
  written; the original device is re-read (user edits there still win) and
  restored by id. A device that is temporarily unreachable keeps the saved
  state: the next ``stop()`` retries the restore, so replugging the device
  still brings the old level back.
- Hard process termination (kill -9 / TerminateProcess style) cannot run
  in-process cleanup, so the lowered level persists in that one case until
  the user moves the volume slider. The endpoint-volume API offers no
  auto-revert flag and per-app session volumes cannot lower other apps'
  output, so there is no OS self-healing path for the master scalar.
"""

from __future__ import annotations

import logging
import threading

_log = logging.getLogger("wordarc.duck")

# Two consecutive reads of an untouched device return the same scalar, so
# this only needs to cover float/read noise. The duck target itself is the
# level read back right after lowering (the slider quantises), which means
# any deliberate move — even a small one like 0.12 -> 0.14 — lands outside
# this band and is kept as the user's choice.
USER_CHANGED_TOLERANCE = 0.005

MIN_REDUCTION = 5
MAX_REDUCTION = 95
DEFAULT_REDUCTION = 80


def clamp_reduction(value, default=DEFAULT_REDUCTION):
    """Coerce a configured reduction percent into a sane range."""
    try:
        percent = float(value)
    except (TypeError, ValueError):
        return default
    if percent != percent:  # NaN
        return default
    return min(MAX_REDUCTION, max(MIN_REDUCTION, percent))


def ducked_level(original, reduction_percent):
    """The target output level for an original level and a reduction."""
    reduction = clamp_reduction(reduction_percent)
    return min(1.0, max(0.0, float(original) * (1.0 - reduction / 100.0)))


class _WindowsEndpoint:
    """Raw master-volume access to render endpoints (ctypes/COM).

    Each call opens and releases its own COM objects with its own
    CoInitialize/CoUninitialize pair, so calls are safe from any thread and
    never leak an interface pointer.

    ``get``/``set`` address the current default output; ``read``/``write``
    address one device by id. The ducker always pairs them on the id
    captured at ``start()``, so a mid-recording default change can neither
    misread nor miswrite another device.
    """

    def _open_default(self, ole32, guid):
        import uuid
        from ctypes import wintypes, WINFUNCTYPE
        import ctypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD),
                        ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD),
                        ("Data4", wintypes.BYTE * 8)]

        def _guid(text):
            parsed = uuid.UUID(text)
            value = GUID()
            value.Data1 = parsed.time_low
            value.Data2 = parsed.time_mid
            value.Data3 = parsed.time_hi_version
            value.Data4 = (wintypes.BYTE * 8)(*parsed.bytes[8:])
            return value

        CLSID_MMDE = _guid("BCDE0395-E52F-467C-8E3D-C4579291692E")
        IID_ENUM = _guid("A95664D2-9614-4F35-A746-DE8DB63617E6")
        IID_EPV = _guid("5CDF2C82-841E-4546-9722-0CF74078229A")

        ole32.CoCreateInstance.argtypes = [
            ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
        ole32.CoCreateInstance.restype = ctypes.HRESULT
        enumerator = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(ctypes.byref(CLSID_MMDE), None, 0x17,
                                   ctypes.byref(IID_ENUM),
                                   ctypes.byref(enumerator))
        if hr != 0 or not enumerator.value:
            raise OSError("no audio endpoint enumerator (hr=%08x)" % (hr & 0xFFFFFFFF))

        def _vtable(ptr, index, restype, *argtypes):
            table = ctypes.cast(
                ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            return WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(table[index])

        get_default = _vtable(enumerator.value, 4, ctypes.HRESULT,
                              ctypes.c_int, ctypes.c_int,
                              ctypes.POINTER(ctypes.c_void_p))
        device = ctypes.c_void_p()
        # eRender=0, eMultimedia=1: the speakers/headphones Windows mixes to.
        hr = get_default(enumerator.value, 0, 1, ctypes.byref(device))
        _vtable(enumerator.value, 2, ctypes.c_ulong)(enumerator.value)
        if hr != 0 or not device.value:
            raise OSError("no default render endpoint (hr=%08x)" % (hr & 0xFFFFFFFF))

        device_table = ctypes.cast(
            device.value,
            ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents

        def _device_fn(index, restype, *argtypes):
            return WINFUNCTYPE(restype, ctypes.c_void_p,
                              *argtypes)(device_table[index])

        activate = _device_fn(3, ctypes.HRESULT, ctypes.POINTER(GUID),
                              wintypes.DWORD, ctypes.c_void_p,
                              ctypes.POINTER(ctypes.c_void_p))
        endpoint = ctypes.c_void_p()
        hr = activate(device.value, ctypes.byref(IID_EPV), 0x17, None,
                      ctypes.byref(endpoint))
        # The endpoint id belongs to the device, so read it before releasing.
        device_id = ""
        try:
            get_id = _device_fn(5, ctypes.HRESULT,
                               ctypes.POINTER(ctypes.c_void_p))
            raw = ctypes.c_void_p()
            if get_id(device.value, ctypes.byref(raw)) == 0 and raw.value:
                device_id = ctypes.wstring_at(raw.value)
                ole32.CoTaskMemFree(raw)
        except Exception:  # noqa: BLE001 - id is best-effort tracking only
            device_id = ""
        _device_fn(2, ctypes.c_ulong)(device.value)
        if hr != 0 or not endpoint.value:
            raise OSError("could not open the volume control (hr=%08x)"
                          % (hr & 0xFFFFFFFF))
        return endpoint.value, device_id

    @staticmethod
    def _release(endpoint):
        import ctypes
        table = ctypes.cast(
            endpoint,
            ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(table[2])
        release(endpoint)

    def _call(self, func):
        import ctypes
        if ctypes.windll is None:
            raise OSError("audio ducking needs Windows")
        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)
        try:
            endpoint, device_id = self._open_default(ole32, None)
            try:
                return func(endpoint) + (device_id,)
            finally:
                self._release(endpoint)
        finally:
            ole32.CoUninitialize()

    def get(self):
        """(level 0..1, device_id) for the current default output."""
        import ctypes
        from ctypes import WINFUNCTYPE

        def _read(endpoint):
            table = ctypes.cast(
                endpoint,
                ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            getter = WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p,
                                ctypes.POINTER(ctypes.c_float))(table[9])
            level = ctypes.c_float()
            hr = getter(endpoint, ctypes.byref(level))
            if hr != 0:
                raise OSError("could not read the volume (hr=%08x)"
                              % (hr & 0xFFFFFFFF))
            return (float(level.value),)

        return self._call(_read)

    def set(self, level):
        """Set the default output master scalar; returns (device_id)."""
        import ctypes
        from ctypes import WINFUNCTYPE

        target = min(1.0, max(0.0, float(level)))

        def _write(endpoint):
            table = ctypes.cast(
                endpoint,
                ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            setter = WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p,
                                ctypes.c_float, ctypes.c_void_p)(table[7])
            hr = setter(endpoint, ctypes.c_float(target), None)
            if hr != 0:
                raise OSError("could not set the volume (hr=%08x)"
                              % (hr & 0xFFFFFFFF))
            return ()

        return self._call(_write)[-1]

    def _open_by_id(self, ole32, device_id):
        """Open the endpoint-volume control of one device by id.

        Returns ``(endpoint, release_all)`` where calling ``release_all()``
        frees the endpoint, its device and the enumerator. Raises OSError
        when the device is missing or temporarily unreachable (unplugged).
        """
        import ctypes
        import uuid
        from ctypes import wintypes, WINFUNCTYPE

        if not device_id:
            raise OSError("no device id")

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD),
                        ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD),
                        ("Data4", wintypes.BYTE * 8)]

        def _guid(text):
            parsed = uuid.UUID(text)
            value = GUID()
            value.Data1 = parsed.time_low
            value.Data2 = parsed.time_mid
            value.Data3 = parsed.time_hi_version
            value.Data4 = (wintypes.BYTE * 8)(*parsed.bytes[8:])
            return value

        CLSID_MMDE = _guid("BCDE0395-E52F-467C-8E3D-C4579291692E")
        IID_ENUM = _guid("A95664D2-9614-4F35-A746-DE8DB63617E6")
        IID_EPV = _guid("5CDF2C82-841E-4546-9722-0CF74078229A")
        ole32.CoCreateInstance.argtypes = [
            ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
        ole32.CoCreateInstance.restype = ctypes.HRESULT
        enumerator = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(ctypes.byref(CLSID_MMDE), None, 0x17,
                                   ctypes.byref(IID_ENUM),
                                   ctypes.byref(enumerator))
        if hr != 0 or not enumerator.value:
            raise OSError("no audio endpoint enumerator")

        # Flat from here on: every failure path frees exactly what it owns.
        enum_table = ctypes.cast(
            enumerator.value,
            ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        get_device = WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.c_wchar_p,
            ctypes.POINTER(ctypes.c_void_p))(enum_table[5])
        release_enum = WINFUNCTYPE(ctypes.c_ulong,
                                  ctypes.c_void_p)(enum_table[2])
        device = ctypes.c_void_p()
        hr = get_device(enumerator.value, device_id, ctypes.byref(device))
        if hr != 0 or not device.value:
            release_enum(enumerator.value)
            raise OSError("audio device is gone or unreachable (hr=%08x)"
                          % (hr & 0xFFFFFFFF))
        dev_table = ctypes.cast(
            device.value,
            ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        release_dev = WINFUNCTYPE(ctypes.c_ulong,
                                  ctypes.c_void_p)(dev_table[2])
        activate = WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p,
            ctypes.POINTER(GUID), wintypes.DWORD, ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p))(dev_table[3])
        endpoint = ctypes.c_void_p()
        hr = activate(device.value, ctypes.byref(IID_EPV), 0x17,
                      None, ctypes.byref(endpoint))
        if hr != 0 or not endpoint.value:
            release_dev(device.value)
            release_enum(enumerator.value)
            raise OSError("could not reopen the audio device (hr=%08x)"
                          % (hr & 0xFFFFFFFF))

        def _release_all():
            _WindowsEndpoint._release(endpoint.value)
            release_dev(device.value)
            release_enum(enumerator.value)

        return endpoint.value, _release_all

    @staticmethod
    def _read_scalar(endpoint):
        import ctypes
        from ctypes import WINFUNCTYPE
        table = ctypes.cast(
            endpoint,
            ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        getter = WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p,
                             ctypes.POINTER(ctypes.c_float))(table[9])
        level = ctypes.c_float()
        hr = getter(endpoint, ctypes.byref(level))
        if hr != 0:
            raise OSError("could not read the volume (hr=%08x)"
                          % (hr & 0xFFFFFFFF))
        return float(level.value)

    @staticmethod
    def _write_scalar(endpoint, level):
        import ctypes
        from ctypes import WINFUNCTYPE
        table = ctypes.cast(
            endpoint,
            ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        setter = WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p,
                             ctypes.c_float, ctypes.c_void_p)(table[7])
        hr = setter(endpoint, ctypes.c_float(level), None)
        if hr != 0:
            raise OSError("could not set the volume (hr=%08x)"
                          % (hr & 0xFFFFFFFF))

    def _call_on_id(self, device_id, func):
        import ctypes
        if ctypes.windll is None:
            raise OSError("audio ducking needs Windows")
        ole32 = ctypes.windll.ole32
        ole32.CoInitialize(None)
        try:
            endpoint, release_all = self._open_by_id(ole32, device_id)
            try:
                return func(endpoint)
            finally:
                release_all()
        finally:
            ole32.CoUninitialize()

    def read(self, device_id):
        """Current master level of one device, addressed by id."""
        return self._call_on_id(device_id,
                                lambda endpoint: _WindowsEndpoint._read_scalar(
                                    endpoint))

    def write(self, device_id, level):
        """Set the master level of one device, addressed by id.

        Raises OSError when the device is missing or unreachable, so the
        caller can keep the saved level and retry after a replug.
        """
        target = min(1.0, max(0.0, float(level)))
        self._call_on_id(
            device_id,
            lambda endpoint: _WindowsEndpoint._write_scalar(endpoint,
                                                            target))


class AudioDucker:
    """Lower-then-restore guard for dictation recording, per output device.

    ``start(reduction_percent)`` remembers the current output level and lowers
    it on the *same* device, then reads the level back: the read-back value
    — not the computed one — is the baseline, so slider quantisation can
    never look like a user edit, while even a small deliberate move does.
    ``stop()`` re-reads every ducked device (so a manual edit still wins)
    and brings the remembered level back. Both are safe to call when already
    in that state, from any thread, and neither ever raises.

    Without a reliable device id ducking is skipped outright: an unbound
    write could land on the wrong output. Entries are tracked per device,
    so a pending restore on an unplugged output never blocks ducking a new
    one; every ``stop()`` retries the unreachable entries without
    overwriting manual edits.

    ``stop()`` returns True when no lowered level of ours remains. It
    returns False — keeping the saved levels — only while a ducked device
    is unreachable or its write fails, so a later ``stop()`` (e.g. after
    a replug, or at shutdown) can still restore.
    """

    def __init__(self, backend=None):
        self._backend = backend if backend is not None else _WindowsEndpoint()
        self._lock = threading.Lock()
        # device_id -> (original, target); target is the read-back level.
        self._ducked = {}

    @property
    def active(self):
        with self._lock:
            return bool(self._ducked)

    def start(self, reduction_percent=DEFAULT_REDUCTION):
        """Lower the output; True when ducked, False when left untouched."""
        with self._lock:
            try:
                level, device_id = self._backend.get()
            except Exception as exc:  # noqa: BLE001 - dictation must continue
                _log.warning("background duck: could not read volume (%s)", exc)
                return False
            if not device_id:
                # No id to bind the write to: lowering the default blind
                # could hit whatever output appears next. Skip instead.
                _log.warning("background duck: no device id, skipping")
                return False
            if device_id in self._ducked:
                return True
            target = ducked_level(level, reduction_percent)
            try:
                # Bound to the device just read: a default change in between
                # can no longer lower some other output.
                self._backend.write(device_id, target)
            except Exception as exc:  # noqa: BLE001 - dictation must continue
                _log.warning("background duck: could not lower volume (%s)", exc)
                return False
            try:
                actual = self._backend.read(device_id)
            except Exception as exc:  # noqa: BLE001 - undo, then skip
                _log.warning("background duck: could not verify level (%s)",
                             exc)
                try:
                    self._backend.write(device_id, float(level))
                except Exception:
                    # Undo failed too: keep the computed target so a later
                    # stop() can still restore instead of leaking.
                    self._ducked[device_id] = (float(level), float(target))
                return True
            self._ducked[device_id] = (float(level), float(actual))
            _log.info("background duck: %.2f -> %.2f (reduction %s%%)",
                      level, actual, clamp_reduction(reduction_percent))
            return True

    def stop(self):
        """Restore the remembered levels; never raises.

        Reads and writes only the ducked devices: a new default is never
        touched. A device that cannot be reached keeps its saved level and
        the call reports False so the next one can retry.
        """
        with self._lock:
            if not self._ducked:
                return True
            for device_id in list(self._ducked):
                original, target = self._ducked[device_id]
                try:
                    level = self._backend.read(device_id)
                except Exception as exc:  # noqa: BLE001 - device may be back later
                    _log.warning("background duck: device unreachable, "
                                 "keeping %.2f for a later restore (%s)",
                                 original, exc)
                    continue
                if abs(level - target) > USER_CHANGED_TOLERANCE:
                    # The user moved the slider on the ducked device itself
                    # (even after it stopped being the default): their
                    # choice wins.
                    _log.info("background duck: volume changed by user "
                              "(%.2f), keeping it", level)
                    del self._ducked[device_id]
                    continue
                try:
                    self._backend.write(device_id, original)
                    _log.info("background duck: restored %.2f on saved "
                              "device", original)
                except Exception as exc:  # noqa: BLE001 - retry after a replug
                    _log.warning("background duck: restore failed, keeping "
                                 "%.2f for a later restore (%s)", original, exc)
                    continue
                del self._ducked[device_id]
            return not self._ducked

    # Shut down via the same path: quit/cancel while recording restores.
    shutdown = stop
