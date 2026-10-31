"""Independent, small Windows process supervising the Inno update transaction."""
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import subprocess
import sys

from update_protocol import clean_environment, digest, run_transaction, write_state


class WindowsProcess:
    def __init__(self, handle):
        self.handle = handle

    def poll(self):
        code = w.DWORD()
        if not ctypes.windll.kernel32.GetExitCodeProcess(self.handle, ctypes.byref(code)):
            raise ctypes.WinError()
        return None if code.value == 259 else code.value

    def wait(self, timeout):
        result = ctypes.windll.kernel32.WaitForSingleObject(self.handle, int(timeout * 1000))
        if result != 0:
            self.terminate()
            raise RuntimeError("Setup timed out")
        return self.poll()

    def terminate(self):
        ctypes.windll.kernel32.TerminateProcess(self.handle, 1)

    def close(self):
        ctypes.windll.kernel32.CloseHandle(self.handle)


class NativeHost:
    def launch_setup(self, job, folder):
        class ShellInfo(ctypes.Structure):
            _fields_ = [("cbSize", w.DWORD), ("fMask", w.ULONG), ("hwnd", w.HWND),
                        ("lpVerb", w.LPCWSTR), ("lpFile", w.LPCWSTR), ("lpParameters", w.LPCWSTR),
                        ("lpDirectory", w.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", w.HINSTANCE),
                        ("lpIDList", w.LPVOID), ("lpClass", w.LPCWSTR), ("hkeyClass", w.HKEY),
                        ("dwHotKey", w.DWORD), ("hIcon", w.HANDLE), ("hProcess", w.HANDLE)]
        params = ["/SILENT", "/NORESTART", "/SUPPRESSMSGBOXES", "/SP-",
                  "/LOG=" + str(folder / "setup.log"),
                  "/WORDARC_READY=" + str(folder / "installer.ready"),
                  "/WORDARC_OLDPID=" + str(job["old_pid"]), "/WORDARC_MANAGED=1"]
        info = ShellInfo()
        info.cbSize = ctypes.sizeof(info)
        info.fMask = 0x40 | 0x100  # SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC
        info.lpVerb = "runas"
        info.lpFile = job["setup"]
        info.lpParameters = subprocess.list2cmdline(params)
        info.lpDirectory = str(folder)
        info.nShow = 1
        # External native installers must not inherit the frozen DLL directory.
        ctypes.windll.kernel32.SetDllDirectoryW(None)
        os.environ.clear()
        os.environ.update(clean_environment_from_job(self._environment))
        call = ctypes.WinDLL("shell32", use_last_error=True).ShellExecuteExW
        call.argtypes, call.restype = [ctypes.POINTER(ShellInfo)], w.BOOL
        if not call(ctypes.byref(info)) or not info.hProcess:
            code = ctypes.get_last_error()
            raise OSError(code, "Administrator permission was cancelled" if code == 1223 else "Setup could not be started")
        return WindowsProcess(info.hProcess)

    def __init__(self):
        self._environment = clean_environment()
        kernel = ctypes.windll.kernel32
        kernel.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
        kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        kernel.CloseHandle.argtypes = [w.HANDLE]
        kernel.TerminateProcess.argtypes = [w.HANDLE, w.UINT]

    def old_running(self, job):
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = [w.DWORD, w.BOOL, w.DWORD], w.HANDLE
        handle = kernel.OpenProcess(0x100000, False, int(job["old_pid"]))
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)

    def check_installation(self, job, folder):
        report = folder / "health.json"
        result = subprocess.run([job["new_exe"], "--installation-check", "--output", str(report)],
                                env=self._environment, creationflags=0x08000000, timeout=60)
        if result.returncode != 0 or not report.is_file():
            raise RuntimeError("The new application could not be loaded")
        return json.loads(report.read_text(encoding="utf-8"))

    def start_new(self, job, folder):
        subprocess.Popen([job["new_exe"], "--update-session=" + str(folder / "job.json")],
                         env=self._environment, close_fds=True)

    def recover(self, job, folder):
        for path in (Path(job["old_exe"]), folder / "previous" / "WordArc.exe"):
            try:
                if path.is_file() and digest(path) == job["old_sha256"]:
                    subprocess.Popen([str(path)], env=self._environment, close_fds=True)
                    return True
            except OSError:
                pass
        return False

    def report_failure(self, message, folder, recovered):
        text = "The update did not complete.\n" + message + "\n\nSetup log: " + str(folder / "setup.log")
        if recovered:
            text += "\nThe previous version was reopened."
        ctypes.windll.user32.MessageBoxW(None, text, "WordArc update", 0x10)


def clean_environment_from_job(environment):
    return {**environment, "PYINSTALLER_RESET_ENVIRONMENT": "1"}


def main():
    folder = Path(sys.argv[sys.argv.index("--job") + 1]).resolve().parent
    try:
        job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
        return 0 if run_transaction(job, folder, NativeHost()) else 1
    except Exception as exc:
        write_state(folder, "failed", error=str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
