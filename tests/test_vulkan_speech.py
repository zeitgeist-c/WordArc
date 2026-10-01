"""AMD routing/recovery and native isolation contracts, without live drivers."""
import json
from unittest import mock
import wave

import pytest
import localspeech as stt
import vulkan_speech as vk
import config as cfg


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(vk, "_failed", False)
    monkeypatch.setattr(vk, "_failure_note", "")
    monkeypatch.setattr(stt, "cuda_available", lambda: False)


def test_auto_prefers_cuda_then_discrete_amd_then_cpu(monkeypatch):
    monkeypatch.setattr(vk, "devices", lambda: (
        dict(index=0, kind=2, memory=16 * 1024**3, name="AMD Radeon Graphics"),
        dict(index=1, kind=1, memory=8 * 1024**3, name="AMD Radeon RX 6650 XT")))
    assert vk.best_device()["index"] == 1
    assert stt.get_best_device("auto") == ("vulkan", "float16")
    monkeypatch.setattr(stt, "cuda_available", lambda: True)
    assert stt.get_best_device("auto") == ("cuda", "float16")
    assert stt.get_best_device("cpu") == ("cpu", "int8")
    monkeypatch.setattr(stt, "cuda_available", lambda: False)
    monkeypatch.setattr(vk, "devices", lambda: ())
    assert stt.get_best_device("auto") == ("cpu", "int8")
    with pytest.raises(stt.VulkanUnavailable):
        stt.get_best_device("vulkan")


def test_auto_retries_whole_audio_on_ggml_cpu_once(monkeypatch):
    monkeypatch.setattr(vk, "available", lambda: True)
    monkeypatch.setattr(vk, "installed", lambda *args: True)
    with mock.patch.object(vk, "transcribe", side_effect=[vk.VulkanError("driver failed"), "complete transcript"]) as run:
        assert stt.transcribe("base", "original.wav", "tr", "names", device_preference="auto") == "complete transcript"
    assert run.call_count == 2
    assert run.call_args_list[0].kwargs["use_gpu"] is True
    assert run.call_args_list[1].kwargs["use_gpu"] is False
    assert run.call_args_list[1].args[:4] == ("base", "original.wav", "tr", "names")
    assert vk._failed
    with mock.patch.object(vk, "transcribe", return_value="second") as run:
        assert stt.transcribe("base", "second.wav", device_preference="auto") == "second"
        assert run.call_args.kwargs["use_gpu"] is False


def test_explicit_gpu_does_not_change_config_without_consent(monkeypatch):
    monkeypatch.setattr(vk, "installed", lambda *args: True)
    with mock.patch.object(vk, "transcribe", side_effect=vk.VulkanError("AMD driver failed")) as run:
        with pytest.raises(stt.VulkanUnavailable, match="AMD driver"):
            stt.transcribe("base", "same.wav", device_preference="vulkan")
    run.assert_called_once()
    assert not vk._failed


def test_existing_cpu_model_keeps_working_before_vulkan_download(monkeypatch):
    monkeypatch.setattr(vk, "available", lambda: True)
    monkeypatch.setattr(vk, "installed", lambda *args: False)
    monkeypatch.setattr(stt, "_is_installed", lambda *args: True)
    model = mock.Mock()
    model.transcribe.return_value = (iter([mock.Mock(start=0, end=1, text="kept working")]), None)
    with mock.patch.object(stt, "engine", return_value=model) as engine, \
         mock.patch.object(stt, "_read_wav", return_value=[0.1]), \
         mock.patch.object(vk, "transcribe") as gpu:
        assert stt.transcribe("base", "old.wav", device_preference="auto") == "kept working"
    assert engine.call_args.args[2] == "cpu"
    gpu.assert_not_called()


def test_saved_cpu_can_use_the_existing_ggml_model(monkeypatch):
    monkeypatch.setattr(stt, "_is_installed", lambda *args: False)
    monkeypatch.setattr(vk, "installed", lambda *args: True)
    with mock.patch.object(vk, "transcribe", return_value="recovered") as run:
        assert stt.transcribe("base", "same.wav", device_preference="cpu") == "recovered"
    assert run.call_args.kwargs["use_gpu"] is False


def test_auto_uses_ggml_cpu_when_amd_driver_is_unavailable(monkeypatch):
    monkeypatch.setattr(vk, "available", lambda: False)
    monkeypatch.setattr(stt, "_is_installed", lambda *args: False)
    monkeypatch.setattr(vk, "installed", lambda *args: True)
    with mock.patch.object(vk, "transcribe", return_value="CPU without AMD driver") as run:
        assert stt.transcribe("base", "same.wav", device_preference="auto") == "CPU without AMD driver"
    assert run.call_args.kwargs["use_gpu"] is False


def test_config_preserves_vulkan_across_reload(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg.credential_store, "read", lambda *args: "")
    monkeypatch.setattr(cfg.credential_store, "read_all", lambda *args: [])
    cfg.CONFIG_FILE.write_text(json.dumps({"local_stt_device": "vulkan"}))
    assert cfg.Config()["local_stt_device"] == "vulkan"


def test_ggml_storage_and_remove_never_touch_cpu_weights(tmp_path):
    path = vk.model_path("base", tmp_path)
    path.parent.mkdir()
    path.write_bytes(b"lmgg" + b"x" * 1024)
    cpu = tmp_path / "Systran--faster-whisper-base"
    cpu.mkdir()
    (cpu / "model.bin").write_bytes(b"preserve")
    assert stt.state("base", tmp_path, "vulkan").installed
    assert stt.remove("base", tmp_path, "vulkan")
    assert not path.exists()
    assert (cpu / "model.bin").read_bytes() == b"preserve"


def test_failure_diagnostics_do_not_expose_transcript_text():
    logs = "private meeting words\nerror: device lost\nggml_vulkan: failed allocation\n"
    reason = vk.error_details(logs, 3)
    assert "private meeting" not in reason
    assert "device lost" in reason


@pytest.fixture
def native_context(tmp_path, monkeypatch):
    wav = tmp_path / "input.wav"
    with wave.open(str(wav), "wb") as stream:
        stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\x01\x00" * 16000)
    (tmp_path / "whisper-cli.exe").touch()
    weights = tmp_path / "weights.bin"
    weights.write_bytes(b"lmgg" + b"x" * 1024)
    monkeypatch.setattr(vk, "runtime_dir", lambda: tmp_path)
    monkeypatch.setattr(vk, "model_path", lambda *args: weights)
    monkeypatch.setattr(vk, "best_device", lambda: dict(index=1, name="RX 6650 XT"))
    return wav


def test_native_json_offsets_are_seconds_and_proof_of_gpu_is_required(native_context):
    def start(args, **kwargs):
        from pathlib import Path
        result = Path(args[args.index("-of") + 1] + ".json")
        result.write_text(json.dumps({"transcription": [{"offsets": {"from": 1250, "to": 3500}, "text": " merhaba "}]}))
        kwargs["stderr"].write(b"whisper_model_load: Vulkan1 total size = 100 MB\nwhisper_backend_init_gpu: using Vulkan1 backend\n")
        return mock.Mock(poll=lambda: 0, returncode=0)
    with mock.patch.object(vk.subprocess, "Popen", side_effect=start) as popen:
        assert vk.transcribe("base", native_context, "tr", with_segments=True) == [(1.25, 3.5, "merhaba")]
    args = popen.call_args.args[0]
    assert args[args.index("-dev") + 1] == "1"
    assert args[args.index("-l") + 1] == "tr"


def test_cancel_kills_and_reaps_native_process(native_context):
    calls = iter([False, True])
    process = mock.Mock(poll=lambda: None)
    with mock.patch.object(vk.subprocess, "Popen", return_value=process):
        with pytest.raises(stt.Cancelled):
            vk.transcribe("base", native_context, should_stop=lambda: next(calls))
    process.kill.assert_called_once()
    process.wait.assert_called_once()


def test_native_silent_cpu_fallback_is_not_reported_as_gpu(native_context):
    def start(args, **kwargs):
        kwargs["stderr"].write(b"whisper_backend_init_gpu: using Vulkan1 backend\nfailed to initialize Vulkan1 backend\n")
        return mock.Mock(poll=lambda: 0, returncode=0)
    with mock.patch.object(vk.subprocess, "Popen", side_effect=start):
        with pytest.raises(vk.VulkanError):
            vk.transcribe("base", native_context)


def test_vulkan_consent_saves_cpu_and_retries_same_recording(tmp_path, monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from cuda_recovery import CudaRecovery
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg.credential_store, "read", lambda *args: "")
    monkeypatch.setattr(cfg.credential_store, "read_all", lambda *args: [])
    conf = cfg.Config()
    conf["transcribe_engine"] = "local"
    conf["local_stt_device"] = "vulkan"
    recovery = CudaRecovery(conf)
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes) as question, \
         mock.patch.object(stt, "transcribe", side_effect=[stt.VulkanUnavailable("driver failed"), "recovered"]) as run:
        assert stt.transcribe_for(conf, "same.wav", "tr") == "recovered"
    assert "Vulkan" in question.call_args.args[1]
    assert run.call_args.args[1] == "same.wav"
    assert run.call_args.kwargs["device_preference"] == "cpu"
    assert conf["local_stt_device"] == "cpu"
    assert json.loads(cfg.CONFIG_FILE.read_text())["local_stt_device"] == "cpu"
