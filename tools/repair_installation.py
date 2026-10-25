"""One-time bridge from the old updater into the supervised Program Files install."""
import argparse
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def process_image(pid):
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = [w.DWORD, w.BOOL, w.DWORD], w.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise ctypes.WinError()
    try:
        buffer, size = ctypes.create_unicode_buffer(32768), w.DWORD(32768)
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            raise ctypes.WinError()
        return Path(buffer.value).resolve()
    finally:
        kernel.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--old-exe", required=True)
    parser.add_argument("--old-pid", required=True, type=int)
    parser.add_argument("--helper-dir", required=True)
    parser.add_argument("--recovery-exe")
    parser.add_argument("--old-sha256")
    parser.add_argument("--close-unresponsive", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    import config
    import update
    import update_protocol as protocol
    from PyQt6.QtCore import QCoreApplication
    import wordarc
    app = QCoreApplication.instance() or QCoreApplication([])
    current = Path(args.old_exe).resolve()
    original_location = str(current)
    image = process_image(args.old_pid)
    if current.name.lower() != "wordarc.exe":
        raise RuntimeError("The specified PID does not belong to the expected WordArc installation")
    if image != current:
        # A deleted/moved running image can retain its original CIM command
        # line. Require an explicit known hash and identical archived backup;
        # never bypass the identity check or recreate an obsolete temp install.
        if not args.recovery_exe or not args.old_sha256:
            raise RuntimeError("Running image moved; an explicitly verified recovery executable is required")
        recovery = Path(args.recovery_exe).resolve()
        if protocol.digest(image) != args.old_sha256 or protocol.digest(recovery) != args.old_sha256:
            raise RuntimeError("The running image does not match the recovery version")
        if current.exists():
            raise RuntimeError("The original path was replaced; preserve it for investigation")
        current = config.DATA_DIR / "updates" / "bridge" / uuid.uuid4().hex / "WordArc.exe"
        current.parent.mkdir(parents=True)
        shutil.copy2(recovery, current)
    image_sha256 = protocol.digest(image)
    source = Path(args.setup).resolve()
    assert protocol.digest(source) == args.sha256, "Unverified setup"
    before = json.loads(config.CONFIG_FILE.read_text(encoding="utf-8")) if config.CONFIG_FILE.is_file() else None
    staged = update.setup_temp_path(args.version)
    staged.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, staged)
    assert protocol.digest(staged) == args.sha256
    print("Setup verified; requesting Windows administrator permission. Old app is still running.", flush=True)
    folder = update.spawn_setup(staged, version=args.version, sha256=args.sha256,
                               old_exe=current, old_pid=args.old_pid, helper_dir=args.helper_dir)
    if protocol.digest(process_image(args.old_pid)) != image_sha256:
        raise RuntimeError("The original application changed during installation preparation")
    print("New payload passed preflight; installer is ready. Requesting graceful exit of old app.", flush=True)
    if not wordarc.send_command("quit"):
        if not args.close_unresponsive:
            (folder / "cancel.requested").touch()
            raise RuntimeError("The old application could not be asked to close; installation cancelled")
        # One-time repair only: never terminate a responsive UI or another PID.
        windows = []
        callback_type = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        def inspect_window(hwnd, _):
            owner = w.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == args.old_pid:
                windows.append(hwnd)
            return True
        callback = callback_type(inspect_window)
        ctypes.windll.user32.EnumWindows(callback, 0)
        if windows or protocol.digest(process_image(args.old_pid)) != image_sha256:
            (folder / "cancel.requested").touch()
            raise RuntimeError("Old application has windows or changed identity; preserve it")
        kernel = ctypes.windll.kernel32
        kernel.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
        kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        handle = kernel.OpenProcess(0x1000 | 0x100000 | 1, False, args.old_pid)
        if not handle:
            raise ctypes.WinError()
        try:
            print("Verified old process has no windows and no command endpoint; closing that exact PID.", flush=True)
            if not kernel.TerminateProcess(handle, 0):
                raise ctypes.WinError()
            if kernel.WaitForSingleObject(handle, 10000) != 0:
                raise RuntimeError("Old process did not exit")
        finally:
            kernel.CloseHandle(handle)
    deadline = time.monotonic() + 700
    while time.monotonic() < deadline:
        state = protocol.read_state(folder)
        if state.get("stage") in ("complete", "failed"):
            break
        time.sleep(.2)
    else:
        raise RuntimeError("No terminal installation result; inspect " + str(folder))
    after = json.loads(config.CONFIG_FILE.read_text(encoding="utf-8")) if config.CONFIG_FILE.is_file() else None
    natural = {"update_last_check", "settings_size"}
    preserved = before is None or after is not None and all(after.get(key) == value for key, value in before.items() if key not in natural)
    result = dict(ok=state.get("stage") == "complete", transaction=str(folder), state=state,
                  config_preserved=preserved, old_location=original_location,
                  recovery_location=str(current), new_location=str(protocol.install_directory() / "WordArc.exe"))
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False), flush=True)
    assert result["ok"] and preserved, result


if __name__ == "__main__":
    main()
