"""Discovery works across stores without executing unknown files or changing them."""
import json
from pathlib import Path
import subprocess
import sys
from unittest import mock

import pytest

import engine_discovery as discovery
import localspeech
import speech_sources
import vulkan_runtime
import vulkan_speech


def ct2(path):
    path.mkdir(parents=True)
    for name in ("config.json", "model.bin", "tokenizer.json", "vocabulary.json"):
        (path / name).write_bytes(b"{}")
    return path


def ggml(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"lmgg" + bytes(2048))
    return path


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(speech_sources, "registry_file", lambda: tmp_path / "sources.json")
    monkeypatch.setattr(discovery, "probe_backend", lambda kind, stop=None: dict(
        ready=kind == "cpu", status="ready" if kind == "cpu" else "unavailable", detail="test"))
    monkeypatch.setattr(discovery, "_trusted_runtime", lambda directory: False)


def test_finds_hermes_style_and_huggingface_models_and_keeps_all_results(tmp_path):
    ggml(tmp_path / "hermes/cache/whisper.cpp/ggml-large-v3-turbo.bin")
    ct2(tmp_path / "hub/models--Systran--faster-whisper-small/snapshots/abc")
    ct2(tmp_path / "models/faster-whisper-large-v3-turbo")
    updates = []
    found = discovery.scan(roots=[tmp_path], progress=updates.append)
    assert {(model.name, model.kind) for model in found.models} == {
        ("large-v3-turbo", "ggml"), ("large-v3-turbo", "ct2"), ("small", "ct2")}
    assert len(found.models) == 3
    assert updates[0]["phase"] == "search" and updates[-1]["phase"] == "complete"
    assert {row["device"] for row in discovery.choices(found)} == {"cpu"}


def test_unknown_executable_is_listed_but_never_run_during_scan(tmp_path, monkeypatch):
    exe = tmp_path / "whisper-cli.exe"
    exe.write_bytes(b"unknown external program")
    ggml(tmp_path / "ggml-base.bin")
    monkeypatch.setattr(discovery, "inspect_cli", mock.Mock(side_effect=AssertionError("must not execute")))
    found = discovery.scan(roots=[tmp_path])
    assert found.runtimes[0]["status"] == "unverified"
    assert len(discovery.choices(found)) == 2
    assert all(row["unverified"] for row in discovery.choices(found))
    assert exe.read_bytes() == b"unknown external program"


def test_denied_directory_does_not_hide_later_model(tmp_path, monkeypatch):
    bad = tmp_path / "denied"
    good = tmp_path / "good"
    ggml(good / "ggml-base.bin")
    original = discovery.os.scandir
    def scandir(path):
        if Path(path) == bad:
            raise PermissionError("blocked")
        return original(path)
    monkeypatch.setattr(discovery.os, "scandir", scandir)
    found = discovery.scan(roots=[bad, good])
    assert len(found.models) == 1
    assert found.issues[0][1] == "denied"


def test_incomplete_ct2_and_wrong_ggml_header_are_not_offered(tmp_path):
    folder = ct2(tmp_path / "faster-whisper-small")
    (folder / "tokenizer.json").unlink()
    (tmp_path / "ggml-base.bin").write_bytes(b"bad!" + bytes(2048))
    assert discovery.scan(roots=[tmp_path]).models == []


def test_duplicate_roots_and_quantized_models(tmp_path):
    ggml(tmp_path / "ggml-large-v3-turbo-q5_0.bin")
    found = discovery.scan(roots=[tmp_path, tmp_path])
    assert len(found.models) == 1
    assert found.models[0].name == "large-v3-turbo"


def test_cancel_prevents_probes_and_limits_are_reported(tmp_path, monkeypatch):
    probe = mock.Mock()
    monkeypatch.setattr(discovery, "probe_backend", probe)
    with pytest.raises(discovery.ScanCancelled):
        discovery.scan(roots=[tmp_path], stop=lambda: True)
    probe.assert_not_called()
    assert discovery.scan(roots=[tmp_path], max_entries=0).partial


def test_native_timeout_and_permission_error_are_distinct(tmp_path, monkeypatch):
    (tmp_path / "whisper-cli.exe").write_bytes(b"not executed")
    monkeypatch.setattr(discovery, "capture", mock.Mock(side_effect=subprocess.TimeoutExpired("cli", 1)))
    assert discovery.inspect_cli(tmp_path)["status"] == "timeout"
    monkeypatch.setattr(Path, "is_file", mock.Mock(side_effect=PermissionError("blocked")))
    assert discovery.inspect_cli(tmp_path)["status"] == "denied"
    assert vulkan_runtime.inspect(tmp_path) == ()


def test_runtime_recovers_from_denied_cached_candidate_to_next_engine(tmp_path, monkeypatch):
    bad, good = tmp_path / "denied", tmp_path / "working"
    good.mkdir()
    (good / "whisper-cli.exe").write_bytes(b"test")
    original = Path.is_file
    def is_file(path):
        if path.parent == bad:
            raise PermissionError("blocked")
        return original(path)
    monkeypatch.setattr(Path, "is_file", is_file)
    monkeypatch.setattr(vulkan_runtime, "_cached", bad)
    monkeypatch.setattr(vulkan_runtime, "_checked", {})
    monkeypatch.setattr(vulkan_runtime, "candidates", lambda: iter([bad, good]))
    output = b"--output-json --device --no-gpu --no-flash-attn\nggml_vulkan: 0 = AMD Radeon | uma: 0\n"
    monkeypatch.setattr(vulkan_runtime.subprocess, "run", mock.Mock(return_value=mock.Mock(
        returncode=0, stdout=output, stderr=b"")))
    assert vulkan_runtime.resolve() == good


def test_multiple_native_copies_do_not_multiply_model_choices():
    found = discovery.Inventory(models=[discovery.Model("base", "ggml", "shared/ggml-base.bin", 2052)])
    for index in range(4):
        found.runtimes.append(dict(path=f"engine-{index}", compatible=True, status="ready", detail="",
                                   devices=[dict(name="AMD Radeon")]))
    assert [row["device"] for row in discovery.choices(found)] == ["cpu", "vulkan"]


def test_timed_out_child_is_reaped():
    with pytest.raises(subprocess.TimeoutExpired):
        discovery.capture([sys.executable, "-c", "import time;time.sleep(5)"], timeout=0.1)


def test_cuda_choice_is_not_offered_when_backend_is_unavailable(tmp_path):
    model = ct2(tmp_path / "faster-whisper-base")
    inventory = discovery.scan(roots=[model])
    assert [row["device"] for row in discovery.choices(inventory)] == ["cpu"]
    inventory.backends["cuda"]["ready"] = True
    assert {row["device"] for row in discovery.choices(inventory)} == {"cpu", "cuda"}


def test_explicit_ct2_selection_reaches_model_loader_without_copying(tmp_path, monkeypatch):
    model = ct2(tmp_path / "hermes/faster-whisper-large-v3-turbo")
    choice = dict(model=discovery.Model("large-v3-turbo", "ct2", str(model), 2), device="cpu", runtime="")
    discovery.activate(choice)
    assert localspeech._root("large-v3-turbo") == str(model)
    monkeypatch.setattr(localspeech, "get_best_device", lambda preference: ("cpu", "int8"))
    monkeypatch.setattr(localspeech, "_model", None)
    loader = mock.Mock(return_value=object())
    monkeypatch.setattr(localspeech, "_load_model", loader)
    localspeech.engine("large-v3-turbo", device_preference="cpu")
    assert loader.call_args.args[0] == str(model)
    assert localspeech.remove("large-v3-turbo", device_preference="cpu")
    assert (model / "model.bin").exists()
    assert speech_sources.selected("ct2", "large-v3-turbo") is None


def test_switching_shared_source_reloads_same_named_model(tmp_path, monkeypatch):
    first = ct2(tmp_path / "one/faster-whisper-base")
    second = ct2(tmp_path / "two/faster-whisper-base")
    monkeypatch.setattr(localspeech, "get_best_device", lambda preference: ("cpu", "int8"))
    monkeypatch.setattr(localspeech, "_model", None)
    loader = mock.Mock(side_effect=[object(), object()])
    monkeypatch.setattr(localspeech, "_load_model", loader)
    speech_sources.link("ct2", "base", first)
    one = localspeech.engine("base", device_preference="cpu")
    speech_sources.link("ct2", "base", second)
    two = localspeech.engine("base", device_preference="cpu")
    assert one is not two
    assert loader.call_count == 2


def test_shared_ggml_choice_wins_and_disconnect_preserves_hermes_files(tmp_path):
    shared = ggml(tmp_path / "hermes/ggml-base.bin")
    speech_sources.link("ggml", "base", shared)
    assert vulkan_speech.model_path("base") == shared
    assert not localspeech._is_installed("base")
    assert localspeech.remove("base", device_preference="cpu")
    assert shared.is_file()


def test_invalid_external_selection_does_not_persist_links(tmp_path, monkeypatch):
    shared = ggml(tmp_path / "ggml-base.bin")
    choice = dict(model=discovery.Model("base", "ggml", str(shared), 2052), device="vulkan", runtime=str(tmp_path))
    monkeypatch.setattr(discovery, "inspect_cli", lambda *a: dict(compatible=False, devices=[], status="incompatible", detail="old CLI"))
    with pytest.raises(ValueError):
        discovery.activate(choice)
    assert not speech_sources.registry_file().exists()


def test_native_cpu_selection_survives_cache_reset(tmp_path, monkeypatch):
    cli = tmp_path / "cpu-cli"
    cli.mkdir()
    (cli / "whisper-cli.exe").write_bytes(b"test")
    monkeypatch.setattr(vulkan_runtime, "managed_dir", lambda: tmp_path / "managed")
    monkeypatch.setattr(discovery, "inspect_cli", lambda *a: dict(compatible=True))
    monkeypatch.setattr(vulkan_runtime, "inspect", lambda *a: ())
    monkeypatch.setattr(vulkan_runtime, "candidates", lambda: iter([cli]))
    monkeypatch.setattr(vulkan_runtime, "_cached", None)
    vulkan_runtime.select(cli / "whisper-cli.exe", cpu=True)
    assert vulkan_runtime.resolve(refresh=True) == cli
