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
