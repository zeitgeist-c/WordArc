"""Small, stdlib-only transaction contract shared by the app and update helper."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_state(folder, stage, **details):
    target = Path(folder) / "status.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(dict(stage=stage, **details), ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, target)


def read_state(folder):
    try:
        return json.loads((Path(folder) / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def clean_environment():
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("_PYI_") and key not in ("_MEIPASS2", "PYTHONHOME", "PYTHONPATH")}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def install_directory():
    return Path(os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles") or "C:/Program Files") / "WordArc"


def validate_job(job, folder):
    if job.get("schema") != 1 or not re.fullmatch(r"\d+\.\d+\.\d+", job.get("version", "")):
        raise ValueError("Invalid update transaction")
    folder = Path(folder).resolve()
    setup = Path(job["setup"]).resolve(strict=True)
    if setup.parent != (folder.parent.parent / "downloads").resolve() or setup.name != f"WordArc-{job['version']}.exe":
        raise ValueError("The setup is not an owned update download")
    if not re.fullmatch(r"[0-9a-f]{64}", job.get("sha256", "")) or digest(setup) != job["sha256"]:
        raise ValueError("The setup checksum does not match")
    if Path(job["new_exe"]).resolve() != (install_directory() / "WordArc.exe").resolve():
        raise ValueError("The install destination is not Program Files/WordArc")
    if int(job["old_pid"]) <= 0 or folder.name != job.get("id"):
        raise ValueError("Invalid update owner")
    if not re.fullmatch(r"WordArc(?:-\d+\.\d+\.\d+)?\.exe", Path(job["old_exe"]).name, re.I):
        raise ValueError("Previous application is not a WordArc executable")
    return folder


def cleanup_previous(job):
    """Only exact, pre-recorded old application files; never recursive removal."""
    old = Path(job["old_exe"]).resolve()
    new = Path(job["new_exe"]).resolve()
    if old == new:
        return []
    warnings = []
    for item in job.get("old_files", []):
        path = Path(item["path"]).resolve()
        if path.parent != old.parent or path.name not in (old.name, "unins000.exe", "unins000.dat"):
            warnings.append("Skipped unrelated path: " + str(path))
            continue
        try:
            if path.exists():
                if digest(path) != item["sha256"]:
                    warnings.append("Previous file changed: " + str(path))
                    continue
                path.unlink()
        except OSError as exc:
            warnings.append(str(exc))
    try:
        old.parent.rmdir()  # Succeeds only if empty. Unrelated files are retained.
    except OSError:
        pass
    return warnings


def confirm_startup(job_path, current_version, current_exe, data_dir):
    """A normal new-app startup acknowledges only its own private transaction."""
    path = Path(job_path).resolve()
    base = (Path(data_dir) / "updates" / "sessions").resolve()
    if not path.is_relative_to(base) or path.name != "job.json":
        return False
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
        if job["version"] != current_version or Path(job["new_exe"]).resolve() != Path(current_exe).resolve():
            return False
        report = path.parent / "started.json"
        report.write_text(json.dumps(dict(version=current_version, pid=os.getpid(),
                                           exe=str(Path(current_exe).resolve()))), encoding="utf-8")
        return True
    except (OSError, ValueError, KeyError):
        return False


def run_transaction(job, folder, host, *, sleep=time.sleep, clock=time.monotonic):
    """Inno owns installation/rollback; we supervise its handoff and application start."""
    folder = validate_job(job, folder)
    installer = None
    old_closed = False
    try:
        write_state(folder, "requesting_permission")
        installer = host.launch_setup(job, folder)
        deadline = clock() + 90
        ready = folder / "installer.ready"
        while not ready.is_file():
            if (folder / "cancel.requested").exists():
                installer.terminate()
                raise RuntimeError("The update request was cancelled; the current app was kept open")
            code = installer.poll()
            if code is not None:
                raise RuntimeError(f"Setup exited before it was ready (code {code})")
            if clock() >= deadline:
                installer.terminate()
                raise RuntimeError("Setup did not become ready in time; the current app was kept open")
            sleep(0.1)
        write_state(folder, "ready")
        deadline = clock() + 90
        while host.old_running(job):
            if (folder / "cancel.requested").exists():
                installer.terminate()
                raise RuntimeError("The update request was cancelled before installation")
            if installer.poll() is not None:
                raise RuntimeError("Setup stopped before the old app exited")
            if clock() >= deadline:
                installer.terminate()
                raise RuntimeError("The current app did not close; installation cancelled")
            sleep(0.1)
        old_closed = True
        write_state(folder, "installing")
        code = installer.wait(timeout=600)
        if code != 0:
            raise RuntimeError(f"Setup failed (code {code}); see setup.log")
        write_state(folder, "checking_installation")
        report = host.check_installation(job, folder)
        if not report.get("ok") or report.get("version") != job["version"]:
            raise RuntimeError("The installed application did not pass its startup check")
        host.start_new(job, folder)
        deadline = clock() + 60
        while not (folder / "started.json").is_file():
            if clock() >= deadline:
                raise RuntimeError("The installed application did not confirm startup")
            sleep(0.1)
        startup = json.loads((folder / "started.json").read_text(encoding="utf-8"))
        if startup.get("version") != job["version"] or Path(startup.get("exe", "")).resolve() != Path(job["new_exe"]).resolve():
            raise RuntimeError("The startup confirmation does not match the installed application")
        warnings = cleanup_previous(job)
        backup = folder / "previous" / "WordArc.exe"
        try:
            if backup.is_file() and digest(backup) == job["old_sha256"]:
                backup.unlink()
                backup.parent.rmdir()
        except OSError as exc:
            warnings.append(str(exc))
        # The validated setup is an owned transaction artifact, not a user file.
        try:
            setup = Path(job["setup"])
            if digest(setup) == job["sha256"]:
                setup.unlink()
        except OSError as exc:
            warnings.append(str(exc))
        write_state(folder, "complete", version=job["version"], cleanup_warnings=warnings)
        return True
    except Exception as exc:
        # Do not start a second application while an installer may still write.
        recovered = host.recover(job, folder) if old_closed and installer.poll() is not None else False
        message = str(exc)
        write_state(folder, "failed", error=message, previous_restarted=recovered, log=str(folder / "setup.log"))
        if old_closed:
            host.report_failure(message, folder, recovered)
        return False
    finally:
        if installer is not None:
            installer.close()
