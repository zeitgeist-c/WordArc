"""Tests for audio.LiveStreamer (Gemini Live capture path)."""

from unittest import mock

import audio


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


def _started_streamer(target=""):
    streamer = audio.LiveStreamer()
    with mock.patch.object(audio, "_match_input_device", return_value=None), \
         mock.patch.object(audio, "_open_portaudio_stream",
                           side_effect=lambda **kw: _FakeStream(**kw)):
        streamer.start(target)
    assert streamer.active
    return streamer


def _feed(streamer, n_callbacks):
    indata = mock.Mock()
    indata.tobytes.return_value = b"\x00\x00" * audio.CHUNK_FRAMES
    for _ in range(n_callbacks):
        streamer._stream.callback(indata, audio.CHUNK_FRAMES, None, None)


def test_emits_100ms_chunks_covering_all_bytes():
    streamer = _started_streamer()
    emitted = []
    streamer.chunk.connect(emitted.append)
    _feed(streamer, 10)  # 10 x 1024 frames = 20480 bytes -> 6 x 3200 + 1280
    total = sum(len(part) for part in emitted)
    assert total == 6 * 3200
    assert all(len(part) == 3200 for part in emitted)
    result = streamer.stop()
    assert result is not None
    assert sum(len(part) for part in emitted) == 10 * audio.CHUNK_FRAMES * 2


def test_stop_flushes_remainder_and_reports_duration():
    streamer = _started_streamer()
    emitted = []
    streamer.chunk.connect(emitted.append)
    levels = []
    streamer.level.connect(levels.append)
    _feed(streamer, 4)  # 8192 bytes -> 2 x 3200 + 1792 bekleyen
    assert sum(len(part) for part in emitted) == 2 * 3200
    result = streamer.stop()
    assert result is not None
    duration, rms = result
    assert duration == 4 * audio.CHUNK_FRAMES / audio.RATE
    assert len(rms) == 4
    assert sum(len(part) for part in emitted) == 4 * audio.CHUNK_FRAMES * 2
    assert len(levels) == 4
    assert not streamer.active


def test_short_capture_reports_failure():
    streamer = _started_streamer()
    errors = []
    streamer.failed.connect(errors.append)
    assert streamer.stop() is None
    assert errors


def test_cancel_discards_and_returns_none():
    streamer = _started_streamer()
    emitted = []
    streamer.chunk.connect(emitted.append)
    _feed(streamer, 5)
    streamer.cancel()
    assert streamer.stop() is None
    assert not streamer.active
