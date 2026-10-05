import os
import queue
import shutil
import tempfile
import unittest
import weakref
from unittest import mock

import audio
import audio_capture


class _FakeInput:
    def __init__(self, *args, **kwargs):
        self.callback = kwargs.get("callback")

    def start(self):
        pass

    def stop(self):
        pass


class TestRecorderLimit(unittest.TestCase):
    def test_callback_does_not_close_stream_before_owner_can_stop_it(self):
        recorder = audio.Recorder()
        recorder._stream = _FakeInput()
        recorder._max_bytes = 1
        indata = mock.Mock()
        indata.tobytes.return_value = b"\x00\x00" * audio.CHUNK_FRAMES

        recorder._callback(indata, audio.CHUNK_FRAMES, None, None)

        self.assertIsNotNone(recorder._stream)


class TestAudioDeviceEnumeration(unittest.TestCase):
    DEVICES = [
        {"name": "USB Mic", "hostapi": 0, "max_input_channels": 1},
        {"name": "USB Mic", "hostapi": 1, "max_input_channels": 2},
        {"name": "Speakers", "hostapi": 1, "max_input_channels": 0},
    ]
    HOSTAPIS = [{"name": "MME"}, {"name": "Windows WASAPI"}]
    # What Windows hands PortAudio for the Bluetooth hands-free endpoint: a raw
    # driver string with the resource placeholders left in and a line break.
    HANDS_FREE = ("Kulaklık (@System32\\drivers\\bthhfenum.sys,#2;%1 "
                  "Hands-Free%0\r\n;(REDMI Buds 8 Lite))")

    def _sources(self, devices, hostapis=None, unopenable=()):
        """`unopenable` lists device indexes that reject the app's settings."""
        def check(device=None, **kwargs):
            if device in unopenable:
                raise RuntimeError("Invalid sample rate")
        with mock.patch.object(audio.sd, "query_devices", return_value=devices), \
             mock.patch.object(audio.sd, "query_hostapis",
                               return_value=hostapis or self.HOSTAPIS), \
             mock.patch.object(audio.sd, "check_input_settings",
                               side_effect=check):
            return audio.list_sources()

    def test_one_row_per_device_points_at_the_best_host_api(self):
        """Windows lists every device once per host API; one row is kept."""
        self.assertEqual(self._sources(self.DEVICES), [
            ("sd:0:USB Mic", "USB Mic"),
        ])

    def test_a_copy_the_app_cannot_open_is_passed_over(self):
        """A WASAPI copy that refuses the rate loses to the MME copy."""
        self.assertEqual(self._sources(self.DEVICES, unopenable={0}), [
            ("sd:1:USB Mic", "USB Mic"),
        ])

    def test_a_device_no_copy_can_open_keeps_its_first_copy(self):
        """Hiding every device would leave the box empty; keep them then."""
        self.assertEqual(self._sources(self.DEVICES, unopenable={0, 1}), [
            ("sd:0:USB Mic", "USB Mic"),
        ])

    def test_wdm_ks_copies_are_not_offered(self):
        """Kernel-streaming copies cannot be trusted to open; leave them out."""
        devices = [
            {"name": "USB Mic", "hostapi": 0, "max_input_channels": 1},
            {"name": "Kernel Only Mic", "hostapi": 3, "max_input_channels": 1},
        ]
        hostapis = [{"name": "MME"}, {"name": "Windows DirectSound"},
                    {"name": "Windows WASAPI"}, {"name": "Windows WDM-KS"}]
        self.assertEqual(self._sources(devices, hostapis), [
            ("sd:0:USB Mic", "USB Mic"),
        ])

    def test_mme_truncated_name_merges_with_the_full_one(self):
        """MME cuts names short; the cut copy is not a second device."""
        full = "Mikrofon (3- USBGH8-Plus-7.1-ENC)"
        devices = [
            {"name": full[:audio.MME_NAME_LIMIT], "hostapi": 0,
             "max_input_channels": 1},
            {"name": full, "hostapi": 1, "max_input_channels": 1},
        ]
        self.assertEqual(self._sources(devices), [
            ("sd:0:" + full[:audio.MME_NAME_LIMIT], full),
        ])

    def test_devices_differing_after_the_cut_stay_apart(self):
        """Two devices may share their first 31 characters; they are not merged."""
        devices = [
            {"name": "Mikrofon (Realtek HD Audio Mic input)", "hostapi": 1,
             "max_input_channels": 1},
            {"name": "Mikrofon (Realtek HD Audio Line input)", "hostapi": 1,
             "max_input_channels": 1},
        ]
        self.assertEqual(self._sources(devices), [
            ("sd:1:Mikrofon (Realtek HD Audio Mic input)",
             "Mikrofon (Realtek HD Audio Mic input)"),
            ("sd:1:Mikrofon (Realtek HD Audio Line input)",
             "Mikrofon (Realtek HD Audio Line input)"),
        ])

    def test_hands_free_driver_string_becomes_a_readable_row(self):
        """The hands-free endpoint is its own device, with a readable name."""
        devices = [
            {"name": "Kulaklık (REDMI Buds 8 Lite)", "hostapi": 2,
             "max_input_channels": 1},
            {"name": self.HANDS_FREE, "hostapi": 2, "max_input_channels": 1},
        ]
        self.assertEqual(self._sources(
            devices, [{"name": "MME"}, {"name": "Windows DirectSound"},
                      {"name": "Windows WASAPI"}]), [
            ("sd:2:Kulaklık (REDMI Buds 8 Lite)",
             "Kulaklık (REDMI Buds 8 Lite)"),
            ("sd:2:" + self.HANDS_FREE,
             "Kulaklık (REDMI Buds 8 Lite) — Hands-Free"),
        ])

    def test_rows_that_would_read_the_same_keep_the_host_api_hint(self):
        """Two devices whose rows would look alike stay tellable apart."""
        devices = [
            {"name": "Kulaklık (REDMI Buds 8 Lite) — Hands-Free", "hostapi": 0,
             "max_input_channels": 1},
            {"name": self.HANDS_FREE, "hostapi": 2, "max_input_channels": 1},
        ]
        self.assertEqual(self._sources(
            devices, [{"name": "MME"}, {"name": "Windows DirectSound"},
                      {"name": "Windows WASAPI"}]), [
            ("sd:0:Kulaklık (REDMI Buds 8 Lite) — Hands-Free",
             "Kulaklık (REDMI Buds 8 Lite) — Hands-Free (MME)"),
            ("sd:2:" + self.HANDS_FREE,
             "Kulaklık (REDMI Buds 8 Lite) — Hands-Free (Windows WASAPI)"),
        ])

    def test_stable_and_legacy_targets_are_both_accepted(self):
        with mock.patch.object(audio.sd, "query_devices", return_value=self.DEVICES):
            self.assertEqual(audio._match_input_device("sd:1:USB Mic"), 1)
            self.assertEqual(audio._match_input_device("USB Mic"), 0)


class TestDeviceRescan(unittest.TestCase):
    """PortAudio caches its device list; a rescan has to restart it."""

    def test_refresh_restarts_portaudio_so_new_devices_appear(self):
        with mock.patch.object(audio.sd, "_terminate") as terminate, \
             mock.patch.object(audio.sd, "_initialize") as initialize:
            self.assertTrue(audio.refresh_devices())
        terminate.assert_called_once_with()
        initialize.assert_called_once_with()

    def test_refresh_never_runs_while_a_stream_is_open(self):
        """Re-initialising PortAudio would end the recording in progress."""
        stream = mock.Mock(active=True)
        audio._streams.add(stream)
        try:
            with mock.patch.object(audio.sd, "_terminate") as terminate:
                self.assertFalse(audio.refresh_devices())
            terminate.assert_not_called()
        finally:
            audio._streams.discard(stream)

    def test_a_stopped_stream_does_not_block_the_rescan(self):
        stream = mock.Mock(active=False)
        audio._streams.add(stream)
        try:
            with mock.patch.object(audio.sd, "_terminate"):
                self.assertTrue(audio.refresh_devices())
        finally:
            audio._streams.discard(stream)

    def test_a_dead_stream_pointer_does_not_take_down_the_rescan(self):
        """A wrapper whose PortAudio pointer died raises on .active.

        Regression guard for the settings-window crash: such an entry is a
        stream that is over, so it is dropped and the rescan proceeds.
        """
        stream = mock.Mock()
        type(stream).active = mock.PropertyMock(
            side_effect=RuntimeError("Invalid stream pointer"))
        audio._streams.add(stream)
        try:
            with mock.patch.object(audio.sd, "_terminate") as terminate, \
                 mock.patch.object(audio.sd, "_initialize"):
                self.assertTrue(audio.refresh_devices())
            terminate.assert_called_once_with()
            self.assertNotIn(stream, audio._streams)
        finally:
            audio._streams.discard(stream)

    def test_streams_are_tracked_for_the_guard(self):
        fake = mock.Mock(active=True)
        with mock.patch.object(audio.sd, "InputStream", return_value=fake):
            stream = audio._open_portaudio_stream(device=None)
        try:
            self.assertIs(stream, fake)
            self.assertTrue(audio.has_active_capture())
        finally:
            audio._streams.discard(fake)


class TestRecorderDeviceFallback(unittest.TestCase):
    """A saved device can go away; the take must survive it."""

    def test_a_dead_saved_microphone_falls_back_to_the_default(self):
        opened = []

        def fake_input_stream(**kwargs):
            opened.append(kwargs["device"])
            stream = mock.Mock()
            if kwargs["device"] is not None:
                stream.start.side_effect = RuntimeError("Invalid device")
            return stream

        recorder = audio.Recorder()
        with mock.patch.object(audio.sd, "query_devices", return_value=[
                {"name": "Dead Mic", "hostapi": 0, "max_input_channels": 1}]), \
             mock.patch.object(audio.sd, "InputStream",
                               side_effect=fake_input_stream), \
             mock.patch.object(audio, "_log") as log:
            recorder.start("sd:0:Dead Mic")
        self.assertEqual(opened, [0, None])
        self.assertTrue(recorder.active)
        log.warning.assert_called_once()

    def test_a_dead_default_microphone_still_reports_failure(self):
        def fake_input_stream(**kwargs):
            stream = mock.Mock()
            stream.start.side_effect = RuntimeError("no device")
            return stream

        recorder = audio.Recorder()
        errors = []
        recorder.failed.connect(errors.append)
        with mock.patch.object(audio.sd, "InputStream",
                               side_effect=fake_input_stream):
            recorder.start("")
        self.assertEqual(len(errors), 1)
        self.assertFalse(recorder.active)


class TestMeetingRecorderReuse(unittest.TestCase):
    def test_start_resets_stop_event_and_queue(self):
        recorder = audio.MeetingRecorder()
        recorder._stopped_evt.set()
        recorder._q.put(("m", b"stale", 0.0))
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        os.unlink(path)

        with mock.patch.object(audio, "_match_input_device", return_value=1), \
             mock.patch.object(audio, "_match_loopback_device", return_value=2), \
             mock.patch.object(audio.sd, "InputStream", _FakeInput):
            recorder.start(path)

        try:
            self.assertFalse(recorder._stopped_evt.is_set())
            with self.assertRaises(queue.Empty):
                recorder._q.get_nowait()
        finally:
            recorder.cancel()

    def test_cancel_removes_partial_recording(self):
        recorder = audio.MeetingRecorder()
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        recorder._path = path
        recorder._cancelled = False

        recorder.cancel()

        self.assertFalse(os.path.exists(path))

    def test_uses_wasapi_fallback_when_portaudio_has_no_loopback(self):
        recorder = audio.MeetingRecorder()
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        os.unlink(path)
        fallback = _FakeInput()
        with mock.patch.object(audio, "_match_input_device", return_value=1), \
             mock.patch.object(audio, "_match_loopback_device", return_value=None), \
             mock.patch.object(audio.sd, "InputStream", _FakeInput), \
             mock.patch.object(audio_capture.AudioCapture, "open_loopback",
                               return_value=fallback) as opened:
            recorder.start(path, system_target="Speakers")
        try:
            self.assertTrue(recorder.active)
            opened.assert_called_once()
        finally:
            recorder.cancel()

    def test_queue_overflow_reports_capture_failure(self):
        recorder = audio.MeetingRecorder()
        recorder._q = queue.Queue(maxsize=1)
        recorder._q.put(("m", b"full", 0.0))
        recorder._enqueue("s", b"more", 0.0)
        self.assertTrue(recorder._error_reported)

    def test_writer_error_reports_capture_failure(self):
        recorder = audio.MeetingRecorder()
        recorder._wav = mock.Mock()
        recorder._wav.writeframes.side_effect = OSError("disk full")
        recorder._q.put(("m", b"\x00\x00", 0.0))
        recorder._q.put(("s", b"\x00\x00", 0.0))
        recorder._writer()
        self.assertTrue(recorder._error_reported)

    def test_writer_reports_one_channel_stalling(self):
        recorder = audio.MeetingRecorder()
        recorder._wav = mock.Mock()
        recorder._q = mock.Mock()
        recorder._q.get.side_effect = [
            ("m", b"\x00\x00", 0.0), queue.Empty(),
        ]
        with mock.patch.object(audio, "CHANNEL_STALL_SECONDS", 0), \
             mock.patch.object(audio.time, "monotonic", side_effect=[10.0, 11.0]):
            recorder._writer()
        self.assertTrue(recorder._error_reported)

    def test_start_creates_missing_parent_directory(self):
        tmp = tempfile.mkdtemp(prefix="wordarc-test-")
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "nope", "sub", "rec.wav")
        recorder = audio.MeetingRecorder()
        with mock.patch.object(audio, "_match_input_device", return_value=None), \
             mock.patch.object(audio, "_match_loopback_device", return_value=2), \
             mock.patch.object(audio.sd, "InputStream", _FakeInput):
            recorder.start(path)
        try:
            self.assertTrue(recorder.active)
            self.assertTrue(os.path.isdir(os.path.dirname(path)))
        finally:
            recorder.cancel()

    def test_saved_mic_falls_back_to_default_when_it_no_longer_opens(self):
        recorder = audio.MeetingRecorder()
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        os.unlink(path)
        calls = []

        def flaky(*args, **kwargs):
            calls.append(kwargs.get("device"))
            if len(calls) == 1:
                raise OSError("device gone")
            return _FakeInput(*args, **kwargs)

        with mock.patch.object(audio, "_match_input_device", return_value=24), \
             mock.patch.object(audio, "_match_loopback_device", return_value=2), \
             mock.patch.object(audio.sd, "InputStream", flaky):
            recorder.start(path, mic_target="sd:3:gone")
        try:
            self.assertTrue(recorder.active)
            self.assertEqual(calls, [24, None])
        finally:
            recorder.cancel()


class TestStaleStreams(unittest.TestCase):
    """A stream that is already over must not answer the rescan with an error.

    PortAudio hands back a stale pointer for it after the library is restarted
    under it (error -9988), and the wrapper outlives the stop for a moment
    because the callback thread is still holding it. That error used to come
    out of the device rescan, and the rescan runs while the settings window is
    being built — so the window came out half-built and the language change
    that asked for it left nothing on screen.
    """

    class _DeadStream:
        """A stopped stream whose pointer PortAudio has already invalidated."""

        @property
        def active(self):
            raise audio.sd.PortAudioError(
                "Invalid stream pointer [PaErrorCode -9988]")

    class _LiveStream:
        active = True

    def _with_streams(self, *streams):
        return mock.patch.object(audio, "_streams", weakref.WeakSet(streams))

    def test_a_dead_stream_counts_as_no_recording(self):
        dead = self._DeadStream()
        with self._with_streams(dead):
            self.assertFalse(audio.has_active_capture())
            # And it is let go, so the next rescan does not meet it again.
            self.assertNotIn(dead, audio._streams)

    def test_a_dead_entry_does_not_hide_a_live_recording(self):
        # Held in a name of its own: the set keeps only weak references, and a
        # temporary would be collected before the call under test.
        dead, live = self._DeadStream(), self._LiveStream()
        with self._with_streams(dead, live):
            self.assertTrue(audio.has_active_capture())

    def test_refresh_devices_survives_a_dead_stream(self):
        dead = self._DeadStream()
        with self._with_streams(dead), \
             mock.patch.object(audio.sd, "_terminate"), \
             mock.patch.object(audio.sd, "_initialize"):
            self.assertTrue(audio.refresh_devices())


class TestMicFailureDiagnostics(unittest.TestCase):
    """A microphone that will not open must say why, not just that it did not.

    The frozen app once reported only "Mikrofon açılamadı." while the log
    stayed silent about the PortAudio reason, so a busy or vanished device
    could not be told apart from a broken one.
    """

    def _start_failing(self, recorder, target, first, second=None):
        errors = []
        recorder.failed.connect(errors.append)
        outcomes = [first] if second is None else [first, second]

        def opener(**kwargs):
            outcome = outcomes.pop(0) if len(outcomes) > 1 else outcomes[0]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        with mock.patch.object(audio, "_match_input_device",
                               return_value=7 if target else None), \
             mock.patch.object(audio, "_open_portaudio_stream",
                               side_effect=opener):
            with self.assertLogs("wordarc.audio", level="WARNING") as logs:
                recorder.start(target)
        return errors, "\n".join(logs.output)

    def test_saved_mic_failure_logs_reason_and_reports_it(self):
        recorder = audio.Recorder()
        errors, logged = self._start_failing(
            recorder, "sd:0:Ghost Mic",
            OSError("Device unavailable"), OSError("Device unavailable"))
        self.assertFalse(recorder.active)
        self.assertTrue(errors)
        self.assertIn("Device unavailable", errors[0])
        self.assertIn("did not open", logged)
        self.assertIn("Device unavailable", logged)

    def test_default_mic_failure_logs_reason(self):
        recorder = audio.Recorder()
        errors, logged = self._start_failing(
            recorder, "", OSError("Invalid sample rate"))
        self.assertFalse(recorder.active)
        self.assertIn("Invalid sample rate", errors[0])
        self.assertIn("Invalid sample rate", logged)

    def test_meeting_mic_failure_logs_reason_and_reports_it(self):
        recorder = audio.MeetingRecorder()
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        os.unlink(path)
        errors = []
        recorder.failed.connect(errors.append)
        with mock.patch.object(audio, "_match_input_device",
                               return_value=7), \
             mock.patch.object(audio, "_match_loopback_device",
                               return_value=None), \
             mock.patch.object(audio, "_open_portaudio_stream",
                               side_effect=[OSError("Device unavailable"),
                                             OSError("Device unavailable")]):
            with self.assertLogs("wordarc.audio", level="WARNING") as logs:
                recorder.start(path, mic_target="sd:0:Ghost Mic")
        try:
            self.assertFalse(recorder.active)
            self.assertTrue(errors)
            self.assertIn("Device unavailable", errors[0])
            self.assertIn("Device unavailable", "\n".join(logs.output))
        finally:
            recorder.cancel()


if __name__ == "__main__":
    unittest.main()
