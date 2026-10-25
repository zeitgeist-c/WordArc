"""Installation success, failure and old-file preservation across the handoff."""
import json
from pathlib import Path
from unittest import mock

import pytest

import update_protocol as protocol


@pytest.fixture
def transaction(tmp_path, monkeypatch):
    folder = tmp_path / "updates/sessions/transaction-id"
    folder.mkdir(parents=True)
    downloads = tmp_path / "updates/downloads"
    downloads.mkdir()
    setup = downloads / "WordArc-9.9.9.exe"
    setup.write_bytes(b"verified setup")
    old = tmp_path / "old-app/WordArc.exe"
    old.parent.mkdir()
    old.write_bytes(b"previous app")
    (old.parent / "user-document.txt").write_text("preserve me")
    new = tmp_path / "Program Files/WordArc/WordArc.exe"
    new.parent.mkdir(parents=True)
    new.write_bytes(b"new app")
    monkeypatch.setattr(protocol, "install_directory", lambda: new.parent)
    job = dict(schema=1, id=folder.name, version="9.9.9", old_pid=123,
               setup=str(setup), sha256=protocol.digest(setup), old_exe=str(old),
               old_sha256=protocol.digest(old), new_exe=str(new),
               old_files=[dict(path=str(old), sha256=protocol.digest(old))])
    (folder / "job.json").write_text(json.dumps(job))
    return folder, job


class Host:
    def __init__(self, *, ready=True, code=0, health=True, startup=True):
        self.ready, self.code, self.health, self.startup = ready, code, health, startup
        self.process = mock.Mock()
        self.process.poll.return_value = None
        def finish(timeout):
            self.process.poll.return_value = code
            return code
        self.process.wait.side_effect = finish
        self.recover = mock.Mock(return_value=True)
        self.report_failure = mock.Mock()
        self.launch_count = 0

    def launch_setup(self, job, folder):
        self.launch_count += 1
        assert Path(job["old_exe"]).exists()
        if self.ready:
            (folder / "installer.ready").write_text("ready")
        return self.process

    def old_running(self, job):
        return False

    def check_installation(self, job, folder):
        assert Path(job["old_exe"]).exists(), "Never clean the old install before health passes"
        return dict(ok=self.health, version=job["version"])

    def start_new(self, job, folder):
        assert Path(job["old_exe"]).exists(), "Keep the previous files until actual new startup"
        if self.startup:
            (folder / "started.json").write_text(json.dumps(dict(version=job["version"], exe=job["new_exe"])))


def fake_clock():
    elapsed = 0
    def now():
        nonlocal elapsed
        elapsed += 10
        return elapsed
    return now


def test_success_cleans_only_old_program_after_new_startup(transaction):
    folder, job = transaction
    host = Host()
    assert protocol.run_transaction(job, folder, host, sleep=lambda _: None)
    assert protocol.read_state(folder)["stage"] == "complete"
    assert not Path(job["old_exe"]).exists()
    assert (Path(job["old_exe"]).parent / "user-document.txt").read_text() == "preserve me"
    assert Path(job["new_exe"]).exists()
    assert not Path(job["setup"]).exists()
    host.recover.assert_not_called()


@pytest.mark.parametrize("code", [1, 2, 5, 8])
def test_failed_install_never_deletes_old_app(transaction, code):
    folder, job = transaction
    host = Host(code=code)
    assert not protocol.run_transaction(job, folder, host, sleep=lambda _: None)
    assert Path(job["old_exe"]).exists() and Path(job["setup"]).exists()
    assert protocol.read_state(folder)["stage"] == "failed"
    host.recover.assert_called_once()


def test_early_exit_or_uac_cancel_keeps_current_app(transaction):
    folder, job = transaction
    host = Host(ready=False)
    host.process.poll.return_value = 2
    assert not protocol.run_transaction(job, folder, host, sleep=lambda _: None)
    host.recover.assert_not_called()
    assert Path(job["old_exe"]).exists()
    assert "before it was ready" in protocol.read_state(folder)["error"]


def test_hung_setup_before_readiness_is_bounded_and_current_app_is_preserved(transaction):
    folder, job = transaction
    host = Host(ready=False)
    assert not protocol.run_transaction(job, folder, host, sleep=lambda _: None, clock=fake_clock())
    host.process.terminate.assert_called_once()
    host.recover.assert_not_called()
    assert Path(job["old_exe"]).exists()


@pytest.mark.parametrize("health,startup", [(False, True), (True, False)])
def test_bad_new_health_or_missing_startup_retains_old_files(transaction, health, startup):
    folder, job = transaction
    host = Host(health=health, startup=startup)
    assert not protocol.run_transaction(job, folder, host, sleep=lambda _: None, clock=fake_clock())
    assert Path(job["old_exe"]).exists()
    host.recover.assert_called_once()


def test_tampered_setup_is_rejected_before_any_process(transaction):
    folder, job = transaction
    Path(job["setup"]).write_bytes(b"tampered")
    host = Host()
    with pytest.raises(ValueError, match="checksum"):
        protocol.run_transaction(job, folder, host)
    assert host.launch_count == 0


def test_same_folder_update_keeps_installed_exe(transaction):
    folder, job = transaction
    job["old_exe"] = job["new_exe"]
    assert protocol.cleanup_previous(job) == []
    assert Path(job["new_exe"]).exists()


def test_changed_old_files_are_kept(transaction):
    folder, job = transaction
    Path(job["old_exe"]).write_bytes(b"someone changed it")
    warnings = protocol.cleanup_previous(job)
    assert warnings and Path(job["old_exe"]).exists()


def test_restart_environment_is_independent(monkeypatch):
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "C:/Temp/old-mei")
    monkeypatch.setenv("_PYI_ARCHIVE_FILE", "old.exe")
    monkeypatch.setenv("_PYI_PARENT_PROCESS_LEVEL", "1")
    env = protocol.clean_environment()
    assert not any(key.startswith("_PYI_") for key in env)
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


def test_startup_ack_is_restricted_to_transaction_storage(transaction, tmp_path):
    folder, job = transaction
    assert protocol.confirm_startup(folder / "job.json", "9.9.9", job["new_exe"], tmp_path)
    assert (folder / "started.json").is_file()
    assert not protocol.confirm_startup(tmp_path / "elsewhere.json", "9.9.9", job["new_exe"], tmp_path)
