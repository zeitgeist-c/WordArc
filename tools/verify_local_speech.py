"""End-to-end proof on the real engine: download, load, transcribe.

Run outside the unit suite because it needs the model on disk and takes
minutes. It is the check that the app's own path works, not that a mock does.
"""
import os
import shutil
import sys
import tempfile
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import localspeech  # noqa: E402
from tests.test_localspeech import _write_wav  # noqa: E402

AUDIO = r"C:\Users\user\AppData\Local\hermes\cache\scratch\wa-bench\test.wav"


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="wa-e2e-")
    name = sys.argv[2] if len(sys.argv) > 2 else "base"
    print(f"models under {root}", flush=True)

    before = localspeech.state(name, root)
    print(f"before: installed={before.installed} size={before.size}", flush=True)

    t0 = time.monotonic()
    localspeech.download(name, root)
    print(f"downloaded in {time.monotonic() - t0:.1f}s", flush=True)

    after = localspeech.state(name, root)
    print(f"after: installed={after.installed} size={after.size/1_048_576:.0f} MB",
          flush=True)
    assert after.installed, "download did not land"

    # The app's own recorded shape, made here so the run does not depend on a
    # file outside the repo.
    probe = os.path.join(root, "probe.wav")
    shutil.copyfile(AUDIO, probe)
    with wave.open(probe) as wav:
        print(f"probe: {wav.getframerate()} Hz, {wav.getnchannels()} ch, "
              f"{wav.getsampwidth() * 8}-bit, "
              f"{wav.getnframes() / wav.getframerate():.1f}s", flush=True)

    t0 = time.monotonic()
    text = localspeech.transcribe(name, probe, language="tr",
                                  prompt="WordArc, API, GPU, transkripsiyon.",
                                  where=root)
    elapsed = time.monotonic() - t0
    print(f"\nTRANSCRIPT ({elapsed:.1f}s):\n{text}", flush=True)
    assert text.strip(), "empty transcript"

    t0 = time.monotonic()
    segments = localspeech.transcribe(name, probe, language="tr",
                                      with_segments=True, where=root)
    print(f"\nSEGMENTS ({time.monotonic() - t0:.1f}s):", flush=True)
    for start, end, body in segments:
        print(f"  [{start:6.2f} -> {end:6.2f}] {body}", flush=True)
    assert segments and segments[0][1] > segments[0][0], "no usable timings"

    assert localspeech.remove(name, root), "remove did nothing"
    assert not localspeech.state(name, root).installed, "remove left files"
    print("\nOK", flush=True)


if __name__ == "__main__":
    main()
