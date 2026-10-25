"""Real Inno handoff in an isolated AppId/path, using a small synthetic payload."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import update_protocol as protocol
from update_helper import NativeHost


def main():
    root = ROOT / ".cache/installer-cycle"
    root.mkdir(parents=True, exist_ok=True)
    target = root / "Program Files/WordArc"
    os.environ["ProgramW6432"] = str(target.parent)
    source = root / "fixture.py"
    source.write_text('''import json,sys
from pathlib import Path
if "--installation-check" in sys.argv:
    Path(sys.argv[sys.argv.index("--output")+1]).write_text(json.dumps(dict(ok=True,version="9.9.9",exe=sys.executable)))
else:
    for arg in sys.argv[1:]:
        if arg.startswith("--update-session="):
            folder=Path(arg.split("=",1)[1]).parent
            (folder/"started.json").write_text(json.dumps(dict(version="9.9.9",exe=sys.executable)))
''', encoding="utf-8")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed",
                    "--name", "WordArc", "--distpath", str(root / "payload"),
                    "--workpath", str(root / "build"), "--specpath", str(root), str(source)], check=True)
    downloads = root / "updates/downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    iscc = Path.home() / "AppData/Local/Programs/Inno Setup 6/ISCC.exe"
    env = dict(os.environ, WORDARC_VERSION="9.9.9", WORDARC_VERSION_NUM="9.9.9.0")
    subprocess.run([str(iscc), "/DWordArcTest", "/DWordArcTestDir=" + str(target),
                    "/DWordArcTestPayload=" + str(root / "payload/WordArc.exe"),
                    "/O" + str(downloads), str(ROOT / "installer/wordarc.iss")], env=env, check=True)
    folder = root / "updates/sessions" / uuid.uuid4().hex
    folder.mkdir(parents=True)
    old = root / "old-location/WordArc.exe"
    old.parent.mkdir(exist_ok=True)
    old.write_bytes(b"old fixture app")
    document = old.parent / "user-document.txt"
    document.write_text("must survive", encoding="utf-8")
    # This is our own disposable old-process stand-in, never a live WordArc PID.
    previous = subprocess.Popen([sys.executable, "-c", "input()"], stdin=subprocess.PIPE)
    setup = downloads / "WordArc-9.9.9.exe"
    job = dict(schema=1, id=folder.name, version="9.9.9", old_pid=previous.pid,
               setup=str(setup), sha256=protocol.digest(setup), old_exe=str(old), old_sha256=protocol.digest(old),
               new_exe=str(target / "WordArc.exe"), old_files=[dict(path=str(old), sha256=protocol.digest(old))])
    (folder / "job.json").write_text(json.dumps(job), encoding="utf-8")

    class Process:
        def __init__(self, process): self.process = process
        def poll(self): return self.process.poll()
        def wait(self, timeout): return self.process.wait(timeout=timeout)
        def terminate(self): self.process.terminate()
        def close(self): pass

    class Host(NativeHost):
        def launch_setup(self, job, folder):
            # Test installer is explicitly non-admin, with a different AppId.
            return Process(subprocess.Popen([job["setup"], "/VERYSILENT", "/SUPPRESSMSGBOXES", "/SP-",
                "/NORESTART", "/NOICONS", "/TASKS=", "/WORDARC_MANAGED=1",
                "/LOG=" + str(folder / "setup.log"), "/WORDARC_READY=" + str(folder / "installer.ready"),
                "/WORDARC_OLDPID=" + str(job["old_pid"])]))
        def report_failure(self, message, folder, recovered):
            print("FAILED:", message, folder, recovered, flush=True)
        def recover(self, job, folder): return False

    result = []
    thread = threading.Thread(target=lambda: result.append(protocol.run_transaction(job, folder, Host())))
    thread.start()
    try:
        deadline = time.monotonic() + 90
        while protocol.read_state(folder).get("stage") != "ready":
            assert thread.is_alive(), protocol.read_state(folder)
            assert time.monotonic() < deadline, "No installer readiness"
            time.sleep(.05)
        assert previous.poll() is None and old.exists(), "Old app must survive until setup is ready"
        previous.communicate(b"quit\n", timeout=10)
        thread.join(120)
        assert result == [True], protocol.read_state(folder)
        assert (target / "WordArc.exe").is_file() and not old.exists()
        assert document.read_text() == "must survive"
        report = dict(ok=True, app_dir=str(target), readiness_observed=True,
                      old_file_removed=True, user_document_preserved=True,
                      status=protocol.read_state(folder))
        (root / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("REAL INNO HANDOFF, STARTUP CONFIRMATION AND OWNED-FILE CLEANUP OK", flush=True)
    finally:
        if previous.poll() is None:
            previous.communicate(b"quit\n", timeout=10)


if __name__ == "__main__":
    main()
