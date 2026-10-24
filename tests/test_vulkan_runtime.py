"""Engine recovery contracts using isolated files, no user config or drivers."""
import hashlib
import json
from pathlib import Path
from unittest import mock
import zipfile

import pytest

import vulkan_runtime as runtime


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "managed_dir", lambda: tmp_path / "managed")
    monkeypatch.setattr(runtime, "_cached", None)
    monkeypatch.setattr(runtime, "_checked", {})


def engine(path):
    path.mkdir(parents=True)
    (path / "whisper-cli.exe").write_bytes(b"test cli")
    return path


def test_external_cli_requires_vulkan_and_the_flags_we_use(tmp_path):
    path = engine(tmp_path / "external")
    # Windows native stderr can contain CR CR LF rather than LF.
    output = b"--output-json --device --no-gpu --no-flash-attn\r\r\nggml_vulkan: 1 = AMD Radeon RX | uma: 0 | fp16: 1\r\r\n"
    with mock.patch.object(runtime.subprocess, "run", return_value=mock.Mock(
            returncode=0, stdout=b"", stderr=output)) as run:
        assert runtime.inspect(path) == (dict(index=1, name="AMD Radeon RX", kind=1, memory=0),)
        assert runtime.inspect(path)
        assert run.call_count == 1
        assert run.call_args.kwargs["env"]["VK_LOADER_LAYERS_DISABLE"] == "~implicit~"
    runtime._checked.clear()
    with mock.patch.object(runtime.subprocess, "run", return_value=mock.Mock(
            returncode=0, stdout=b"", stderr=b"--output-json --no-gpu")):
        assert not runtime.inspect(path)


def test_discovery_skips_missing_and_incompatible_engines(tmp_path, monkeypatch):
    good = engine(tmp_path / "good")
    monkeypatch.setattr(runtime, "candidates", lambda: iter([tmp_path / "missing", good]))
    monkeypatch.setattr(runtime, "inspect", lambda path: (dict(index=0),) if path == good else ())
    assert runtime.resolve() == good


def test_selection_is_persisted_only_after_compatibility_check(tmp_path, monkeypatch):
    good = engine(tmp_path / "external")
    monkeypatch.setattr(runtime, "inspect", lambda path: ())
    with pytest.raises(RuntimeError):
        runtime.select(good / "whisper-cli.exe")
    assert not runtime._selection_file().exists()
    monkeypatch.setattr(runtime, "inspect", lambda path: (dict(index=0),))
    runtime.select(good / "whisper-cli.exe")
    assert json.loads(runtime._selection_file().read_text())["directory"] == str(good.resolve())


def test_bundled_copy_is_hash_verified_and_survives_temp_cleanup(tmp_path, monkeypatch):
    source = engine(tmp_path / "bundle")
    manifest = dict(files={"whisper-cli.exe": hashlib.sha256(b"test cli").hexdigest()})
    (source / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(runtime, "resource_path", lambda *args: source)
    monkeypatch.setattr(runtime, "candidates", lambda: iter([source]))
    monkeypatch.setattr(runtime, "inspect", lambda path: (dict(index=0),))
    installed = runtime.resolve()
    assert installed == runtime.managed_dir()
    (source / "whisper-cli.exe").unlink()
    assert (runtime.resolve() / "whisper-cli.exe").read_bytes() == b"test cli"


def test_bad_payload_preserves_previous_runtime(tmp_path):
    old = engine(runtime.managed_dir())
    broken = engine(tmp_path / "broken")
    with pytest.raises(RuntimeError):
        runtime._install(broken, dict(files={"whisper-cli.exe": "0" * 64}))
    assert (old / "whisper-cli.exe").read_bytes() == b"test cli"


def test_repair_download_is_pinned_and_installs_without_model_download(tmp_path, monkeypatch):
    import update
    source = engine(tmp_path / "source")
    manifest = dict(files={"whisper-cli.exe": hashlib.sha256(b"test cli").hexdigest()})
    pins = tmp_path / "runtime.json"
    pins.write_text(json.dumps(dict(version="1.9.2", file="WordArcVulkan-1.9.2.zip",
                                   url="https://example.invalid/engine.zip", sha256="a" * 64, size=10)))
    monkeypatch.setattr(runtime, "resource_path", lambda *args: pins)
    monkeypatch.setattr(runtime, "ready", lambda: False)
    monkeypatch.setattr(runtime, "inspect", lambda path: (dict(index=0),))
    def download(info, archive, progress, cancel):
        assert info.sha256 == "a" * 64
        assert not cancel.is_set()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("whisper-cli.exe", b"test cli")
            bundle.writestr("manifest.json", json.dumps(manifest))
        progress(10, 10)
    monkeypatch.setattr(update, "download", download)
    assert runtime.ensure() == runtime.managed_dir()
    assert (runtime.managed_dir() / "whisper-cli.exe").is_file()


def test_existing_engine_avoids_network(monkeypatch, tmp_path):
    import update
    path = engine(tmp_path / "external")
    monkeypatch.setattr(runtime, "ready", lambda: True)
    monkeypatch.setattr(runtime, "resolve", lambda: path)
    with mock.patch.object(update, "download") as download:
        assert runtime.ensure() == path
    download.assert_not_called()
