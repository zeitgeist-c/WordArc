"""Prove the frozen build can transcribe, not merely start.

Run after a release build:

    .venv/Scripts/python.exe tools/verify_frozen_build.py <models-dir> <model> <wav>

Why this exists as its own check: wordarc.spec once listed faster_whisper as a
hidden import while the package was absent from the build environment. The exe
built anyway — 88 MB, started fine, showed the settings card — and failed only
when someone pressed record. Every source-tree test passed the whole time,
because the failure was in what the build left out.

Reading that failure back needs a console, so frozen-check.spec is a twin of the
shipped spec: same inputs, same hidden imports, console=True. The shipped spec
stays console=False, which is right for a tray app and useless for evidence.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PYTHON = os.path.join(REPO, ".venv", "Scripts", "python.exe")


def main():
    models, model, audio = sys.argv[1], sys.argv[2], sys.argv[3]
    scratch = tempfile.mkdtemp(prefix="wa-frozen-")
    dist = os.path.join(scratch, "dist")
    work = os.path.join(scratch, "build")
    exe = os.path.join(dist, "wafrozen.exe")

    print("building the console twin of the shipped spec...")
    built = subprocess.run(
        [PYTHON, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", dist, "--workpath", work, "frozen-check.spec"],
        cwd=REPO, capture_output=True, text=True, timeout=3600)
    if built.returncode != 0 or not os.path.exists(exe):
        print("RESULT: FAILED — the console twin did not build")
        print(built.stdout[-2000:])
        print(built.stderr[-2000:])
        return 1
    print(f"built {exe} ({os.path.getsize(exe) // (1024 * 1024)} MB)")

    print("transcribing from inside the frozen bundle...")
    # PYTHONIOENCODING matters: the Turkish text comes back as mojibake without
    # it, and mojibake here looks exactly like a broken model.
    env = dict(os.environ, PYTHONIOENCODING="utf-8",
               HF_HUB_DISABLE_SYMLINKS_WARNING="1")
    run = subprocess.run([exe, models, model, audio], env=env,
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=1800)
    print(run.stdout[-2500:])
    if run.stderr.strip():
        print("stderr:", run.stderr[-1500:])

    if "FROZEN TRANSCRIPTION OK" in run.stdout:
        print("RESULT: the frozen bundle carries a working engine.")
        return 0
    print("RESULT: FAILED — the frozen bundle could not transcribe.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
