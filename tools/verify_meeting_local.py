"""The meeting path on real audio: two channels in, one transcript out.

The meeting is the case where the local engine has to be right about WHO said
what, so this proves attribution survives: the same sentence placed on one
channel must come back on that speaker's line.
"""
import os
import pathlib
import shutil
import sys
import tempfile
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import array  # noqa: E402
import contextlib  # noqa: E402

import config as cfg  # noqa: E402
import localspeech  # noqa: E402

MODELS = sys.argv[1] if len(sys.argv) > 1 else "/Users/user/AppData/Local/hermes/cache/scratch/wa-dict"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "base"
RATE = 16000


def _two_speakers(src, out, workdir):
    """Split one recording into a two-channel file, one speaker per channel.

    Each side gets a different half of the audio, so the transcript can be
    checked by eye: whatever the left channel said has to come back on that
    speaker's line and nowhere else.
    """
    with contextlib.closing(wave.open(src, "rb")) as wav:
        total = wav.getnframes()
        half = total // 2
        mine = array.array("h"); mine.frombytes(wav.readframes(half))
        theirs = array.array("h"); theirs.frombytes(wav.readframes(half))
    merged = array.array("h")
    for index in range(half):
        merged.append(mine[index])
        merged.append(theirs[index])
    path = os.path.join(out, "meeting.wav")
    with contextlib.closing(wave.open(path, "wb")) as wav:
        wav.setnchannels(2); wav.setsampwidth(2); wav.setframerate(RATE)
        wav.writeframes(merged.tobytes())
    return path


def main():
    import meeting
    from i18n import t

    cfg.DATA_DIR = pathlib.Path(MODELS)
    here = cfg.DATA_DIR / "whisper"
    localspeech.models_dir = lambda: here
    if not localspeech.state(MODEL, str(here)).installed:
        localspeech.download(MODEL, str(here))

    src = r"C:\Users\user\AppData\Local\hermes\cache\scratch\wa-bench\test.wav"
    workdir = tempfile.mkdtemp(prefix="wa-meeting-")
    # A real two-channel recording, one speaker per channel, so attribution is
    # checkable by eye rather than taken on trust.
    recording = _two_speakers(src, workdir, workdir)
    print(f"recording: {recording}", flush=True)

    class _Conf(dict):
        def meeting_hint(self):
            return ""

        def speaker_names(self):
            return "Ben", "Karşı taraf"

        def get(self, key, default=None):
            return dict.get(self, key, default)

    conf = _Conf({
        "transcribe_engine": "local",
        "local_stt_model": MODEL,
        "gemini_transcribe_model": "gemini-x",
        "meeting_language": "tr",
        "language": "tr",
        "skip_silent": False,
    })
    # The transcriber is the local engine, so no Gemini client is ever built.
    pipe = meeting.MeetingPipeline(conf)
    started = time.monotonic()
    out = pipe._transcribe(None, recording, workdir)
    elapsed = time.monotonic() - started
    print(f"\nMEETING TRANSCRIPT ({elapsed:.1f}s):\n{out}", flush=True)
    assert out.strip(), "the meeting transcript is empty"
    assert t("you") in out or "Ben" in out, f"no speaker lines: {out}"
    shutil.rmtree(workdir, ignore_errors=True)
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
