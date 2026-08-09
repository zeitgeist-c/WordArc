import os
import queue
import tempfile
import unittest
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

    def test_stable_targets_distinguish_duplicate_host_apis(self):
        with mock.patch.object(audio.sd, "query_devices", return_value=self.DEVICES), \
             mock.patch.object(audio.sd, "query_hostapis", return_value=[
                 {"name": "MME"}, {"name": "WASAPI"}]):
            self.assertEqual(audio.list_sources(), [
                ("sd:0:USB Mic", "USB Mic (MME)"),
                ("sd:1:USB Mic", "USB Mic (WASAPI)"),
            ])

    def test_stable_and_legacy_targets_are_both_accepted(self):
        with mock.patch.object(audio.sd, "query_devices", return_value=self.DEVICES):
            self.assertEqual(audio._match_input_device("sd:1:USB Mic"), 1)
            self.assertEqual(audio._match_input_device("USB Mic"), 0)


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


if __name__ == "__main__":
    unittest.main()
