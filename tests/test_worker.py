"""The temporary recording is never destroyed when the user asked to keep it."""

import pathlib
import tempfile
from unittest import mock

import config as cfg
import worker


def _pipeline(keep_audio):
    conf = cfg.Config()
    conf.data["keep_audio"] = keep_audio
    return worker.Pipeline(conf)


def _temp_wav(directory):
    wav = pathlib.Path(directory) / "wordarc-test.wav"
    wav.write_bytes(b"RIFF")
    return wav


def test_keep_audio_keeps_the_recording_when_it_cannot_be_filed_away(caplog):
    pipeline = _pipeline(True)
    with tempfile.TemporaryDirectory() as tmp:
        wav = _temp_wav(tmp)
        with mock.patch.object(worker.shutil, "move",
                               side_effect=OSError("disk full")), \
             mock.patch.object(worker.cfg, "RECORDINGS_DIR",
                               pathlib.Path(tmp) / "recordings"):
            with caplog.at_level("WARNING", logger="wordarc.worker"):
                pipeline._discard(str(wav))
        assert wav.exists(), "kayıt silinmemeliydi"
        assert any("could not file the recording away" in record.message
                   for record in caplog.records), "sessiz kalmamalı"


def test_keep_audio_files_the_recording_away():
    pipeline = _pipeline(True)
    with tempfile.TemporaryDirectory() as tmp:
        wav = _temp_wav(tmp)
        target = pathlib.Path(tmp) / "recordings"
        with mock.patch.object(worker.cfg, "RECORDINGS_DIR", target):
            pipeline._discard(str(wav))
        assert not wav.exists()
        assert len(list(target.glob("*.wav"))) == 1


def test_discard_removes_the_temporary_recording_by_default():
    pipeline = _pipeline(False)
    with tempfile.TemporaryDirectory() as tmp:
        wav = _temp_wav(tmp)
        pipeline._discard(str(wav))
        assert not wav.exists()


def _dictation_conf(**overrides):
    conf = cfg.Config()
    conf.data.update({"skip_silent": False, "filter_hallucinations": False,
                      "cleanup_enabled": True, "history_enabled": False,
                      "keep_audio": False, "auto_paste": True})
    conf.data.update(overrides)
    return conf


def test_a_stop_during_cleanup_is_not_a_cleanup_failure():
    """Cancelled is an ApiError.

    Caught as one, a stop that landed during the cleanup request was reported
    as a cleanup failure and the run went on to paste the raw text: the user
    asked for it to stop and it kept going.
    """
    pipeline = worker.Pipeline(_dictation_conf())
    seen = {"cancelled": 0, "finished": 0}
    pipeline.cancelled.connect(lambda *_: seen.update(
        cancelled=seen["cancelled"] + 1))
    pipeline.finished.connect(lambda *_: seen.update(
        finished=seen["finished"] + 1))
    client = mock.Mock()
    client.cleanup.side_effect = worker.api.Cancelled("Stopped.")

    with mock.patch.object(worker.localspeech, "transcribe_for",
                           return_value="raw words"), \
         mock.patch.object(worker.api, "GeminiClient", return_value=client), \
         mock.patch.object(worker.paste, "copy") as copied, \
         mock.patch.object(worker.paste, "press") as pressed:
        pipeline._work("no-such-recording.wav", 1.0, [], "op-1", auto_paste=True)

    assert seen["cancelled"] == 1
    assert seen["finished"] == 0, "iptal edilen dikte yapıştırılmamalı"
    copied.assert_not_called()
    pressed.assert_not_called()


def test_a_failed_paste_puts_the_clipboard_back():
    """The restore used to sit after the keystroke: when press() raised, the
    user's own clipboard was gone for good."""
    pipeline = worker.Pipeline(_dictation_conf(restore_clipboard=True))
    failures = []
    pipeline.failed.connect(lambda message, _op: failures.append(message))

    with mock.patch.object(worker.localspeech, "transcribe_for",
                           return_value="raw words"), \
         mock.patch.object(worker.api, "GeminiClient", return_value=mock.Mock()), \
         mock.patch.object(worker.paste, "read_clipboard",
                           return_value=b"onceki icerik"), \
         mock.patch.object(worker.paste, "copy"), \
         mock.patch.object(worker.paste, "copy_bytes") as restored, \
         mock.patch.object(worker.paste, "press",
                           side_effect=worker.paste.PasteError("no input")):
        pipeline._work("no-such-recording.wav", 1.0, [], "op-2", auto_paste=True)

    restored.assert_called_once_with(b"onceki icerik")
    assert failures, "hata kullanıcıya ulaşmalı"
