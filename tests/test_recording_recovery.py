"""Recording-loss prevention: local rescue WAVs, ordered stop, early errors.

Fast unit tests first; the two long-duration takes (3-minute dictation,
30-minute meeting) run with synthetic audio and report their own runtime.
Accelerated/simulated runs are labelled as such; the only live-microphone
check is done separately and reported, never committed here.
"""

import array
import os
import pathlib
import tempfile
import threading
import time
import unittest
import wave
from unittest import mock

from PyQt6.QtCore import Qt

import audio
import config as cfg
import i18n
import operation
import worker
import wordarc
from tests.test_live_controller import _InlineThread, _live_controller


def _rescue_spy(seen):
    """Record cfg.rescue_recording's real output paths into ``seen``."""
    real = cfg.rescue_recording

    def _wrapper(src, tag="live"):
        dest = real(src, tag)
        seen.append(dest)
        return dest

    return mock.patch.object(cfg, "rescue_recording", side_effect=_wrapper)


class _FakeStream:
    def __init__(self, *args, **kwargs):
        self.callback = kwargs.get("callback")
        self.stopped = False

    def start(self):
        pass

    def stop(self):
        self.stopped = True

    def close(self):
        pass


def _tone(frames=audio.CHUNK_FRAMES, level=1000):
    samples = array.array("h", [level]) * frames
    return samples.tobytes()


def _feed(streamer, n_callbacks):
    indata = mock.Mock()
    indata.tobytes.return_value = _tone()
    for _ in range(n_callbacks):
        streamer._stream.callback(indata, audio.CHUNK_FRAMES, None, None)


def _write_tone_wav(directory, name="take.wav", seconds=0.1):
    """A real readable WAV file for stale/new-take tests."""
    path = pathlib.Path(directory) / name
    frames = int(seconds * audio.RATE)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(audio.RATE)
        wav.writeframes(_tone(frames))
    return str(path)


def _started_live_streamer():
    streamer = audio.LiveStreamer()
    with mock.patch.object(audio, "_match_input_device", return_value=None), \
         mock.patch.object(audio, "_open_portaudio_stream",
                           side_effect=lambda **kw: _FakeStream(**kw)):
        streamer.start("")
    assert streamer.active
    return streamer


class TestLiveLocalWav(unittest.TestCase):
    def test_capture_is_mirrored_to_a_readable_wav(self):
        streamer = _started_live_streamer()
        try:
            _feed(streamer, 10)
            self.assertTrue(streamer.wav_path)
            with wave.open(streamer.wav_path, "rb") as wav:
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getframerate(), audio.RATE)
                self.assertEqual(wav.getnframes(),
                                 10 * audio.CHUNK_FRAMES)
        finally:
            streamer.cancel()
        self.assertFalse(os.path.exists(streamer.wav_path))

    def test_unwritable_wav_prevents_microphone_start(self):
        streamer = audio.LiveStreamer()
        failures = []
        streamer.failed.connect(failures.append)
        with mock.patch.object(audio, "_match_input_device",
                               return_value=None), \
             mock.patch.object(audio, "_open_portaudio_stream") as open_mic, \
             mock.patch.object(audio.wave, "open",
                               side_effect=OSError("disk full")):
            streamer.start("")
        open_mic.assert_not_called()
        self.assertFalse(streamer.active)
        self.assertEqual(streamer.wav_path, "")
        self.assertEqual(len(failures), 1)
        self.assertIn("disk full", failures[0])

    def test_stop_returns_the_tail_instead_of_emitting_it(self):
        streamer = _started_live_streamer()
        try:
            emitted = []
            streamer.chunk.connect(emitted.append)
            _feed(streamer, 4)
            result = streamer.stop()
            self.assertIsNotNone(result)
            duration, _rms, tail = result
            self.assertEqual(duration,
                             4 * audio.CHUNK_FRAMES / audio.RATE)
            self.assertEqual(tail, _tone()[:1792])
            self.assertEqual(sum(len(part) for part in emitted), 2 * 3200)
        finally:
            streamer.cancel()


class TestRescueFiling(unittest.TestCase):
    def test_rescue_moves_and_names_collision_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "recordings"
            src1 = pathlib.Path(tmp) / "a.wav"
            src2 = pathlib.Path(tmp) / "b.wav"
            src1.write_bytes(b"RIFF....")
            src2.write_bytes(b"RIFF....")
            with mock.patch.object(cfg, "RECORDINGS_DIR", target):
                first = cfg.rescue_recording(str(src1), "live")
                second = cfg.rescue_recording(str(src2), "live")
            self.assertTrue(first and second and first != second)
            self.assertTrue(first.endswith(".wav"))
            self.assertFalse(src1.exists())
            self.assertFalse(src2.exists())

    def test_rescue_of_missing_file_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(cfg, "RECORDINGS_DIR",
                                   pathlib.Path(tmp) / "recordings"):
                self.assertIsNone(
                    cfg.rescue_recording(str(pathlib.Path(tmp) / "no.wav")))


class TestPipelineRescue(unittest.TestCase):
    def setUp(self):
        self._saved_lang = i18n.language()
        i18n.set_language("en")
        self.addCleanup(i18n.set_language, self._saved_lang)
    def _conf(self):
        conf = cfg.Config()
        conf.data.update({"skip_silent": False,
                          "filter_hallucinations": False,
                          "cleanup_enabled": True, "translate_enabled": False,
                          "history_enabled": False,
                          "keep_audio": False, "auto_paste": True,
                          "gemini_next_slot": 0, "gemini_last_used": []})
        return conf

    def _real_wav(self, directory, seconds=1.0):
        path = pathlib.Path(directory) / "take.wav"
        frames = int(seconds * audio.RATE)
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(audio.RATE)
            wav.writeframes(_tone(frames))
        return str(path)

    def _run_work(self, conf, wav_path, transcribe_effect, keys=("k1",)):
        pipeline = worker.Pipeline(conf)
        failures = []
        pipeline.failed.connect(lambda message, _op: failures.append(message))
        client = mock.Mock()
        client.active_slot = 0
        client.cleanup.return_value = "clean"
        with mock.patch.object(
                worker.localspeech, "transcribe_for",
                side_effect=transcribe_effect), \
             mock.patch.object(worker.api, "GeminiClient",
                               return_value=client), \
             mock.patch.object(cfg.Config, "gemini_keys",
                               return_value=list(keys)), \
             mock.patch.object(cfg.Config, "save"), \
             mock.patch.object(worker.paste, "copy"), \
             mock.patch.object(worker.paste, "press"), \
             mock.patch.object(worker.paste, "read_clipboard",
                               return_value=None):
            pipeline._work(wav_path, 1.0, [], "op-1", auto_paste=True)
        return failures

    def test_processing_failure_keeps_the_audio_and_names_it(self):
        import api
        conf = self._conf()
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "recordings"
            wav = self._real_wav(tmp)
            seen = []
            with mock.patch.object(cfg, "RECORDINGS_DIR", target), \
                 _rescue_spy(seen):
                failures = self._run_work(
                    conf, wav, api.ApiError("connection reset", status=500))
            self.assertEqual(len(failures), 1)
            self.assertTrue(seen, "rescue produced no output path")
            kept = seen[-1]
            self.assertTrue(kept, "rescue produced no output path")
            self.assertIn(kept, failures[0])
            with wave.open(kept, "rb") as check:
                self.assertGreater(check.getnframes(), 0)
            self.assertFalse(os.path.exists(wav))

    def test_paste_failure_does_not_file_audio_as_rescued(self):
        import paste
        conf = self._conf()
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "recordings"
            wav = self._real_wav(tmp)
            with mock.patch.object(cfg, "RECORDINGS_DIR", target), \
                 mock.patch.object(worker.paste, "copy",
                                   side_effect=paste.PasteError("no clipboard")):
                pipeline = worker.Pipeline(conf)
                failures = []
                pipeline.failed.connect(
                    lambda message, _op: failures.append(message))
                client = mock.Mock()
                client.active_slot = 0
                with mock.patch.object(
                        worker.localspeech, "transcribe_for",
                        return_value="raw"), \
                     mock.patch.object(worker.api, "GeminiClient",
                                       return_value=client), \
                     mock.patch.object(cfg.Config, "gemini_keys",
                                       return_value=["k1"]), \
                     mock.patch.object(cfg.Config, "save"):
                    pipeline._work(wav, 1.0, [], "op-1", auto_paste=True)
            self.assertEqual(len(failures), 1)
            self.assertNotIn("Audio kept:", failures[0])

    def test_rescued_audio_reprocesses_through_the_pipeline_once(self):
        conf = self._conf()
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "recordings"
            with mock.patch.object(cfg, "RECORDINGS_DIR", target):
                rescued = cfg.rescue_recording(self._real_wav(tmp), "live")
                self.assertTrue(rescued)
                pipeline = worker.Pipeline(conf)
                finished = []
                pipeline.finished.connect(
                    lambda *args: finished.append(args))
                copies = []
                client = mock.Mock()
                client.active_slot = 0
                client.cleanup.return_value = "clean words"
                with mock.patch.object(
                        worker.localspeech, "transcribe_for",
                        return_value="raw words"), \
                     mock.patch.object(worker.api, "GeminiClient",
                                       return_value=client), \
                     mock.patch.object(cfg.Config, "gemini_keys",
                                       return_value=["k1"]), \
                     mock.patch.object(cfg.Config, "save"), \
                     mock.patch.object(worker.paste, "copy",
                                       side_effect=lambda text: copies.append(text)), \
                     mock.patch.object(worker.paste, "press",
                                       return_value=True), \
                     mock.patch.object(worker.paste, "read_clipboard",
                                       return_value=None):
                    pipeline._work(rescued, 1.0, [], "op-2", auto_paste=True)
            self.assertEqual(len(finished), 1)
            self.assertEqual(copies, ["clean words"])

    def _run_work_text(self, conf, wav_path, translate_effect):
        """Drive _work_text with a real WAV; return (finished, failures, copies)."""
        pipeline = worker.Pipeline(conf)
        finished = []
        pipeline.finished.connect(lambda *args: finished.append(args))
        failures = []
        pipeline.failed.connect(lambda message, _op: failures.append(message))
        copies = []
        client = mock.Mock()
        client.active_slot = 0
        client.translate.side_effect = translate_effect
        with mock.patch.object(worker.api, "GeminiClient",
                               return_value=client), \
             mock.patch.object(cfg.Config, "gemini_keys",
                               return_value=["k1"]), \
             mock.patch.object(cfg.Config, "save"), \
             mock.patch.object(worker.paste, "copy",
                               side_effect=lambda text: copies.append(text)), \
             mock.patch.object(worker.paste, "press",
                               return_value=True), \
             mock.patch.object(worker.paste, "read_clipboard",
                               return_value=None):
            pipeline._work_text("ham metin", 1.0, [], "op-9",
                                auto_paste=True, wav_path=wav_path)
        return finished, failures, copies

    def _translate_conf(self):
        conf = self._conf()
        conf.data.update({"translate_enabled": True,
                          "cleanup_enabled": False})
        return conf

    def test_translate_failure_delivers_raw_once_with_warning_and_rescue(self):
        import api
        conf = self._translate_conf()
        error = api.ApiError("ceviri servisi yatti", status=500)
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "recordings"
            wav = self._real_wav(tmp)
            seen = []
            with mock.patch.object(cfg, "RECORDINGS_DIR", target), \
                 _rescue_spy(seen):
                finished, failures, copies = self._run_work_text(
                    conf, wav, error)
            self.assertEqual(failures, [])
            self.assertEqual(len(finished), 1)
            _raw, text, warning, _op = finished[0]
            self.assertEqual(text, "ham metin")
            self.assertIn("ceviri servisi yatti", warning)
            self.assertEqual(copies, ["ham metin"])
            self.assertTrue(seen, "rescue produced no output path")
            kept = seen[-1]
            self.assertIn(kept, warning)
            with wave.open(kept, "rb") as check:
                self.assertGreater(check.getnframes(), 0)
            self.assertFalse(os.path.exists(wav))

    def test_translate_failure_with_failed_move_keeps_file_in_place(self):
        import api
        conf = self._translate_conf()
        error = api.ApiError("ceviri servisi yatti", status=500)
        with tempfile.TemporaryDirectory() as tmp:
            wav = self._real_wav(tmp)
            with mock.patch.object(cfg, "rescue_recording",
                                   return_value=None):
                finished, failures, copies = self._run_work_text(
                    conf, wav, error)
            self.assertEqual(failures, [])
            self.assertEqual(len(finished), 1)
            _raw, text, warning, _op = finished[0]
            self.assertEqual(text, "ham metin")
            self.assertEqual(copies, ["ham metin"])
            self.assertIn(wav, warning)
            self.assertTrue(os.path.exists(wav))
            with wave.open(wav, "rb") as check:
                self.assertGreater(check.getnframes(), 0)


class TestLiveControllerRescue(unittest.TestCase):
    def setUp(self):
        self._saved_lang = i18n.language()
        i18n.set_language("en")
        self.addCleanup(i18n.set_language, self._saved_lang)
    def _fed_controller(self, callbacks=6):
        controller = _live_controller()
        streamer = audio.LiveStreamer()
        with mock.patch.object(audio, "_match_input_device",
                               return_value=None), \
             mock.patch.object(audio, "_open_portaudio_stream",
                               side_effect=lambda **kw: _FakeStream(**kw)):
            streamer.start("")
        controller.live_streamer = streamer
        _feed(streamer, callbacks)
        return controller

    def test_stale_opened_session_is_cancelled_and_ignored(self):
        controller = _live_controller()
        controller.state = wordarc.RECORDING
        controller.dictation_operation.begin()
        controller._live_generation = 2
        late = mock.Mock()
        late.generation = 1
        controller._on_live_opened(late)
        late.cancel.assert_called_once_with()
        self.assertIsNone(controller.live_session)

    def test_stale_open_failed_is_ignored(self):
        controller = _live_controller()
        controller.state = wordarc.RECORDING
        controller.dictation_operation.begin()
        controller._live_generation = 2
        controller._live_opener = mock.Mock()
        with mock.patch.object(controller, "_on_error") as error:
            controller._on_live_open_failed("boom", 1)
        error.assert_not_called()
        self.assertIsNotNone(controller._live_opener)

    def test_live_poll_stops_on_session_error(self):
        controller = _live_controller()
        controller.state = wordarc.RECORDING
        controller.dictation_operation.begin()
        session = mock.Mock()
        session.preview.return_value = ""
        session.limit_hit.is_set.return_value = False
        session.error = "connection reset by peer"
        controller.live_session = session
        with mock.patch.object(controller, "stop") as stop:
            controller._live_poll()
            stop.assert_called_once_with()

    def test_repeated_stop_finishes_only_once(self):
        controller = _live_controller()
        controller.state = wordarc.RECORDING
        controller.dictation_operation.begin()
        session = mock.Mock()
        session.finish.return_value = "yazi"
        session.key_index = 0
        controller.live_session = session
        controller.live_keys = ["k1"]
        controller.live_start_slot = 0
        controller.live_streamer.stop.return_value = (2.0, [], b"")
        with mock.patch.object(wordarc.threading, "Thread", _InlineThread):
            controller.stop()
            first = controller._live_finisher
            controller.stop()
        assert controller._live_finisher is first
        session.finish.assert_called_once_with()

    def test_stop_while_connecting_then_new_start_works(self):
        import livespeech
        controller = _live_controller()
        controller.state = wordarc.RECORDING
        controller.dictation_operation.begin()
        controller._live_opener = mock.Mock()
        controller.stop()
        assert controller.state == wordarc.IDLE
        session = mock.Mock()
        session.finish.return_value = "yazi"

        def fake_open(keys, mode):
            session.generation = controller._live_generation
            return session

        with mock.patch.object(livespeech.LiveSession, "open_with_keys",
                               side_effect=fake_open), \
             mock.patch.object(wordarc.threading, "Thread",
                               _InlineThread):
            controller.start()
        assert controller.live_session is session
        assert controller.state == wordarc.RECORDING

    def test_cancel_then_old_opener_is_ignored(self):
        controller = _live_controller()
        controller.state = wordarc.RECORDING
        controller.dictation_operation.begin()
        controller._live_opener = mock.Mock()
        controller.cancel()
        assert controller.state == wordarc.IDLE
        late = mock.Mock()
        controller._on_live_opened(late)
        late.cancel.assert_called_once_with()
        assert controller.live_session is None

    def test_cancel_during_finishing_delivers_nothing(self):
        controller = _live_controller()
        controller.state = wordarc.BUSY
        controller.dictation_operation.begin()
        controller.dictation_operation.transition(operation.State.PROCESSING)
        stale_id = controller.dictation_operation.operation_id
        controller.dictation_operation.transition(operation.State.CANCELLED)
        controller.dictation_operation.transition(operation.State.IDLE)
        controller._finishing_session = mock.Mock()
        with mock.patch.object(controller, "pipeline") as pipeline:
            controller._on_live_ready("dead text", 1.0, [], stale_id)
            pipeline.run_transcript.assert_not_called()

    def _new_take_finishing(self, controller, stale_wav, new_wav):
        """Leave an old take finishing, then a newer take finishing too.

        Returns (stale_op_id, new objects kept for assertions).
        """
        controller.dictation_operation.begin()
        stale_op = controller.dictation_operation.operation_id
        controller.dictation_operation.transition(operation.State.PROCESSING)
        controller._finishing_session = mock.Mock(name="stale-session")
        controller._live_finisher = mock.Mock(name="stale-finisher")
        controller.dictation_operation.transition(operation.State.COMPLETED)
        controller.dictation_operation.transition(operation.State.IDLE)
        controller.dictation_operation.begin()
        controller.dictation_operation.transition(operation.State.PROCESSING)
        new_session = mock.Mock(name="new-session")
        new_finisher = mock.Mock(name="new-finisher")
        controller._finishing_session = new_session
        controller._live_finisher = new_finisher
        return stale_op, new_session, new_finisher

    def test_stale_ready_during_new_finishing_keeps_new_take(self):
        controller = _live_controller()
        controller.state = wordarc.BUSY
        with tempfile.TemporaryDirectory() as tmp:
            stale_wav = _write_tone_wav(tmp, "stale.wav")
            new_wav = _write_tone_wav(tmp, "new.wav")
            stale_op, new_session, new_finisher = \
                self._new_take_finishing(controller, stale_wav, new_wav)
            with mock.patch.object(controller, "pipeline") as pipeline:
                controller._on_live_ready("old text", 1.0, [], stale_op,
                                          stale_wav)
                pipeline.run_transcript.assert_not_called()
            assert controller._live_finisher is new_finisher
            assert controller._finishing_session is new_session
            self.assertFalse(os.path.exists(stale_wav))
            with wave.open(new_wav, "rb") as check:
                self.assertGreater(check.getnframes(), 0)

    def test_stale_failed_during_new_finishing_keeps_new_take(self):
        controller = _live_controller()
        controller.state = wordarc.BUSY
        with tempfile.TemporaryDirectory() as tmp:
            stale_wav = _write_tone_wav(tmp, "stale.wav")
            new_wav = _write_tone_wav(tmp, "new.wav")
            stale_op, new_session, new_finisher = \
                self._new_take_finishing(controller, stale_wav, new_wav)
            controller._on_live_failed("old boom", stale_op, stale_wav)
            assert controller._live_finisher is new_finisher
            assert controller._finishing_session is new_session
            self.assertFalse(os.path.exists(stale_wav))
            with wave.open(new_wav, "rb") as check:
                self.assertGreater(check.getnframes(), 0)
            controller.overlay.show_error.assert_not_called()
            controller.conf.record_api_attempt.assert_not_called()

    def test_stream_error_stops_capture_and_rescues_audio(self):
        controller = self._fed_controller()
        controller.state = wordarc.RECORDING
        controller.dictation_operation.begin()
        session = mock.Mock()
        controller.live_session = session
        messages = []
        controller.tray.showMessage = lambda *args: messages.append(args)
        with tempfile.TemporaryDirectory() as tmp:
            seen = []
            with mock.patch.object(cfg, "RECORDINGS_DIR",
                                   pathlib.Path(tmp) / "recordings"), \
                 _rescue_spy(seen):
                controller._on_live_stream_error("device gone")
            self.assertFalse(controller.live_streamer.active)
            session.cancel.assert_called_once_with()
            self.assertEqual(len(messages), 1)
            _title, body, _icon, _msec = messages[0]
            self.assertTrue(seen, "rescue produced no output path")
            kept = seen[-1]
            self.assertTrue(kept, "rescue produced no output path")
            self.assertIn(kept, body)
            with wave.open(kept, "rb") as check:
                self.assertEqual(check.getnframes(), 6 * audio.CHUNK_FRAMES)
        self.assertEqual(controller.state, wordarc.IDLE)

    def test_live_finish_failure_rescues_audio(self):
        controller = self._fed_controller()
        controller.state = wordarc.BUSY
        controller.dictation_operation.begin()
        controller.dictation_operation.transition(operation.State.PROCESSING)
        op_id = controller.dictation_operation.operation_id
        controller._finishing_session = mock.Mock()
        # Production order: _stop_live ends the capture first (closing the
        # WAV so it can be moved on Windows); the take's path then rides
        # the finisher signal instead of the shared streamer.
        self.assertIsNotNone(controller.live_streamer.stop())
        wav_path = controller.live_streamer.wav_path
        self.assertTrue(wav_path)
        controller.live_streamer.wav_path = ""
        with tempfile.TemporaryDirectory() as tmp:
            seen = []
            with mock.patch.object(cfg, "RECORDINGS_DIR",
                                   pathlib.Path(tmp) / "recordings"), \
                 _rescue_spy(seen):
                controller._on_live_failed("connection timed out", op_id,
                                           wav_path)
            controller.overlay.show_error.assert_called()
            # The failure is reported through the tray with the rescue path.
            bodies = [call.args[1] for call in
                      controller.tray.showMessage.call_args_list]
            self.assertTrue(seen, "rescue produced no output path")
            kept = seen[-1]
            self.assertTrue(kept, "rescue produced no output path")
            self.assertTrue(any(kept in body for body in bodies),
                            f"notification is missing the rescued path: {kept!r}")
            with wave.open(kept, "rb") as check:
                self.assertEqual(check.getnframes(), 6 * audio.CHUNK_FRAMES)


class TestMeetingDied(unittest.TestCase):
    def _started_meeting(self, path):
        # Synthetic only: the mic/loopback openers are faked and the real
        # loopback class is guarded, so no physical device can be touched.
        recorder = audio.MeetingRecorder()
        with mock.patch.object(audio, "_match_input_device",
                               return_value=1), \
             mock.patch.object(audio, "_match_loopback_device",
                               return_value=2), \
             mock.patch.object(audio, "_open_portaudio_stream",
                               side_effect=lambda **kw: _FakeStream(**kw)), \
             mock.patch.object(audio, "AudioCapture",
                               side_effect=AssertionError(
                                   "synthetic test must not open real loopback")):
            recorder.start(path)
        assert recorder.active
        return recorder

    def test_device_loss_keeps_a_readable_partial_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(pathlib.Path(tmp) / "meeting.wav")
            recorder = self._started_meeting(path)
            try:
                indata = mock.Mock()
                indata.tobytes.return_value = _tone()
                for _ in range(20):
                    recorder._mic_cb(indata, audio.CHUNK_FRAMES, None, None)
                    recorder._sys_cb(indata, audio.CHUNK_FRAMES, None, None)
                died = []
                recorder.died.connect(lambda: died.append(True))
                recorder._sys_cb(indata, audio.CHUNK_FRAMES, None, "lost")
                self.assertEqual(died, [True])
                stopped = []
                recorder.stopped.connect(
                    lambda p, d: stopped.append((p, d)))
                recorder.stop()
                self.assertEqual(len(stopped), 1)
                self.assertEqual(stopped[0][0], path)
                with wave.open(path, "rb") as check:
                    self.assertEqual(check.getnchannels(), 2)
                    self.assertGreater(check.getnframes(), 0)
            finally:
                recorder.cancel()

    def test_meeting_died_routes_to_stop(self):
        controller = _live_controller()
        controller.meeting_state = wordarc.M_RECORDING
        controller.meeting_recorder = mock.Mock()
        with mock.patch.object(controller, "stop_meeting") as stop:
            controller._on_meeting_died()
            stop.assert_called_once_with()

    def test_slow_writer_defers_close_and_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(pathlib.Path(tmp) / "meeting.wav")
            recorder = self._started_meeting(path)
            try:
                gate = threading.Event()
                entered = threading.Event()
                real_writeframes = recorder._wav.writeframes

                def _gated(data):
                    entered.set()
                    self.assertTrue(gate.wait(timeout=30))
                    return real_writeframes(data)

                recorder._wav.writeframes = _gated
                indata = mock.Mock()
                indata.tobytes.return_value = _tone()
                for _ in range(10):
                    recorder._mic_cb(indata, audio.CHUNK_FRAMES, None, None)
                    recorder._sys_cb(indata, audio.CHUNK_FRAMES, None, None)
                self.assertTrue(entered.wait(timeout=10))
                stopped = []
                # The deferred completion fires from the closer thread, and
                # there is no event loop pumping here: take it directly.
                recorder.stopped.connect(
                    lambda p, d: stopped.append((p, d)),
                    Qt.ConnectionType.DirectConnection)
                started = time.monotonic()
                recorder.stop()
                recorder.stop()
                self.assertLess(time.monotonic() - started, 1.0)
                # The join timeout expired with the writer still draining:
                # nothing closed under it, nothing reported yet.
                self.assertEqual(stopped, [])
                self.assertIsNotNone(recorder._wav)
                other_path = str(pathlib.Path(tmp) / "another.wav")
                recorder.start(other_path)
                self.assertFalse(os.path.exists(other_path))
                gate.set()
                deadline = time.monotonic() + 10
                while not stopped and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertEqual(len(stopped), 1)
                self.assertEqual(stopped[0][0], path)
                self.assertIsNone(recorder._wav)
                with wave.open(path, "rb") as check:
                    self.assertEqual(check.getnchannels(), 2)
                    self.assertEqual(check.getnframes(),
                                     10 * audio.CHUNK_FRAMES)
            finally:
                gate.set()
                recorder.cancel()
                recorder.stop(wait=True)


class TestLongTakes(unittest.TestCase):
    """Accelerated takes with synthetic audio (no microphone involved).

    The PCM is generated once and fed straight into the capture callbacks,
    so a 3-minute dictation and a 30-minute meeting run in seconds. Each
    test reports its own wall time.
    """

    def test_three_minute_dictation_stays_readable(self):
        started = time.monotonic()
        recorder = audio.Recorder()
        with mock.patch.object(audio, "_match_input_device",
                               return_value=None), \
             mock.patch.object(audio, "_open_portaudio_stream",
                               side_effect=lambda **kw: _FakeStream(**kw)):
            recorder.start("", max_seconds=300)
        assert recorder.active
        stopped = []
        recorder.stopped.connect(
            lambda path, duration, _rms: stopped.append((path, duration)))
        indata = mock.Mock()
        indata.tobytes.return_value = _tone()
        callbacks = 3 * 60 * audio.RATE // audio.CHUNK_FRAMES
        for _ in range(callbacks):
            recorder._callback(indata, audio.CHUNK_FRAMES, None, None)
        recorder.stop()
        elapsed = time.monotonic() - started
        print(f"\n3-minute dictation feed: {elapsed:.1f}s wall", flush=True)
        self.assertEqual(len(stopped), 1)
        path, duration = stopped[0]
        expected_frames = callbacks * audio.CHUNK_FRAMES
        try:
            self.assertAlmostEqual(duration, expected_frames / audio.RATE,
                                   places=1)
            with wave.open(path, "rb") as check:
                self.assertEqual(check.getnchannels(), 1)
                self.assertEqual(check.getframerate(), audio.RATE)
                self.assertEqual(check.getnframes(), expected_frames)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def test_thirty_minute_meeting_stays_readable(self):
        started = time.monotonic()
        with tempfile.TemporaryDirectory() as tmp:
            path = str(pathlib.Path(tmp) / "meeting.wav")
            recorder = audio.MeetingRecorder()
            with mock.patch.object(audio, "_match_input_device",
                                   return_value=1), \
                 mock.patch.object(audio, "_match_loopback_device",
                                   return_value=2), \
                 mock.patch.object(audio, "_open_portaudio_stream",
                                   side_effect=lambda **kw: _FakeStream(**kw)), \
                 mock.patch.object(audio, "AudioCapture",
                                   side_effect=AssertionError(
                                       "synthetic test must not open real loopback")):
                recorder.start(path, max_seconds=4 * 3600)
            assert recorder.active
            stopped = []
            completed = threading.Event()

            def on_stopped(path, duration):
                stopped.append((path, duration))
                completed.set()

            recorder.stopped.connect(on_stopped, Qt.ConnectionType.DirectConnection)
            indata = mock.Mock()
            indata.tobytes.return_value = _tone()
            last_block = _tone(level=1500)
            callbacks = 30 * 60 * audio.RATE // audio.CHUNK_FRAMES
            for index in range(callbacks):
                if index == callbacks - 1:
                    indata.tobytes.return_value = last_block
                recorder._mic_cb(indata, audio.CHUNK_FRAMES, None, None)
                recorder._sys_cb(indata, audio.CHUNK_FRAMES, None, None)
                if recorder._q.qsize() > 128:
                    # Let the writer drain; dropping chunks here would
                    # shrink the take and fail the frame count below.
                    time.sleep(0.01)
            recorder.stop()
            self.assertTrue(completed.wait(timeout=10))
            elapsed = time.monotonic() - started
            print(f"\n30-minute meeting feed: {elapsed:.1f}s wall",
                  flush=True)
            self.assertEqual(len(stopped), 1)
            self.assertEqual(stopped[0][0], path)
            self.assertAlmostEqual(stopped[0][1], 1800.0, places=0)
            with wave.open(path, "rb") as check:
                self.assertEqual(check.getnchannels(), 2)
                self.assertEqual(check.getnframes(), 1800 * audio.RATE)
                # The last block on disk is the last fed pair, interleaved.
                check.setpos(check.getnframes() - audio.CHUNK_FRAMES)
                tail = check.readframes(audio.CHUNK_FRAMES)
            mono = array.array("h")
            mono.frombytes(last_block)
            stereo = array.array("h", bytes(len(mono) * 4))
            stereo[0::2] = mono
            stereo[1::2] = mono
            self.assertEqual(len(tail), len(mono) * 2 * 2)
            self.assertEqual(tail, stereo.tobytes())


if __name__ == "__main__":
    unittest.main()
