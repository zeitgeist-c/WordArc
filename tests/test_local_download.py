"""Resumable model downloads and download presentation, without network calls."""
import io
import hashlib
import threading
from pathlib import Path
from unittest import mock
import pytest
import localspeech
from tests import test_settings_smoke as smoke

class Response(io.BytesIO):
    def __init__(self, data, offset=0, stop=None, ignore_range=False):
        super().__init__(data if ignore_range else data[offset:])
        self.status = 206 if offset and not ignore_range else 200
        self.headers = {"Content-Range": f"bytes {offset}-{len(data)-1}/{len(data)}"}
        self.stop = stop
        self.reads = 0
    def read(self, size=-1):
        data = super().read(size)
        self.reads += 1
        if self.stop and data and self.reads == 2:
            self.stop.set()
        return data

@pytest.fixture
def files():
    payloads = {name: b'{"test":true}' for name in ("config.json", "tokenizer.json", "vocabulary.txt")}
    payloads["model.bin"] = b"weights" * 100000
    rows = []
    for name, data in payloads.items():
        row = {"rfilename": name, "size": len(data), "blobId": hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()}
        if name == "model.bin":
            row["lfs"] = {"sha256": hashlib.sha256(data).hexdigest()}
        rows.append(row)
    return payloads, rows


def test_force_redownload_keeps_verified_model_until_replacement_is_ready(tmp_path, files):
    payloads, rows = files
    root = Path(localspeech._root("base", tmp_path))
    root.mkdir(parents=True)
    for name, data in payloads.items():
        (root / name).write_bytes(data)
    assert localspeech._is_installed("base", tmp_path)
    calls = []
    def fetch(url, offset=0):
        name = url.split("/")[-1].split("?")[0]
        calls.append(name)
        assert (root / "model.bin").read_bytes() == payloads["model.bin"]
        return Response(payloads[name], offset)
    with mock.patch.object(localspeech, "_download_manifest", return_value=("public/model", "revision-123456789", rows)), \
         mock.patch.object(localspeech, "_download_open", side_effect=fetch):
        localspeech.download("base", tmp_path, force=True)
    assert set(calls) == set(payloads)
    assert localspeech._is_installed("base", tmp_path)

@pytest.mark.parametrize("ignore_range", [False, True])
def test_cancel_keeps_part_and_retry_resumes_or_restarts_safely(tmp_path, files, ignore_range):
    payloads, rows = files
    stop = threading.Event()
    def first(url, offset=0):
        name = url.split("/")[-1].split("?")[0]
        return Response(payloads[name], offset, stop if name == "model.bin" else None)
    with mock.patch.object(localspeech, "_download_manifest", return_value=("public/model", "revision-123456789", rows)), \
         mock.patch.object(localspeech, "_download_open", side_effect=first):
        with pytest.raises(localspeech.Cancelled):
            localspeech.download("base", tmp_path, should_stop=stop.is_set)
    assert not localspeech.state("base", tmp_path).installed
    parts = list(Path(localspeech._root("base", tmp_path)).glob("model.bin.*.part"))
    assert len(parts) == 1 and parts[0].stat().st_size > 0
    offsets = []
    progress = []
    def retry(url, offset=0):
        name = url.split("/")[-1].split("?")[0]
        offsets.append(offset)
        return Response(payloads[name], offset, ignore_range=ignore_range)
    with mock.patch.object(localspeech, "_download_manifest", return_value=("public/model", "revision-123456789", rows)), \
         mock.patch.object(localspeech, "_download_open", side_effect=retry):
        localspeech.download("base", tmp_path, on_progress=progress.append)
    assert offsets[0] > 0
    assert localspeech.state("base", tmp_path).installed
    assert progress[-1].phase == "complete"
    assert progress[-1].completed == progress[-1].total
    assert not parts[0].exists()


def test_bad_checksum_is_not_committed_as_installed(tmp_path, files):
    payloads, rows = files
    def corrupt(url, offset=0):
        name = url.split("/")[-1].split("?")[0]
        data = payloads[name]
        return Response(b"x" * len(data) if name == "model.bin" else data, offset)
    with mock.patch.object(localspeech, "_download_manifest", return_value=("public/model", "revision", rows)), \
         mock.patch.object(localspeech, "_download_open", side_effect=corrupt), \
         mock.patch.object(localspeech.time, "sleep"):
        with pytest.raises(localspeech.LocalSpeechError, match="checksum"):
            localspeech.download("base", tmp_path)
    assert not localspeech.state("base", tmp_path).installed
    assert not Path(localspeech._root("base", tmp_path), "model.bin").exists()


def test_failure_message_is_preserved_and_progress_is_displayed():
    smoke.TestSettingsSmoke.setUpClass()
    fixture = smoke.TestSettingsSmoke()
    fixture.setUp()
    window = fixture.window
    try:
        window.transcribe_engine.setCurrentIndex(
            window.transcribe_engine.findData("local"))
        window._download_name = "base"
        window._on_local_download_progress(localspeech.DownloadProgress("base", 50, 100, 10, 5, "model.bin"))
        assert window.download_bar.value() == 500
        assert "model.bin" in window.download_file.text()
        window.download_cancel.click()
        assert window._download_stop.is_set()
        window._download_stop.clear()
        window._on_local_download_done("base", "network detail")
        fixture.wait_local_inspection()
        assert "network detail" in window.local_status.text()
        assert window.local_download_button.isEnabled()
        window._download_name = "base"
        window._on_local_download_done("base", "")
        assert window.download_bar.value() == 1000
        assert window._download_name is None
    finally:
        fixture.tearDown()
