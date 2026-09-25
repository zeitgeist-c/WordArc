"""The dictation path itself, on a real recording and the real local engine.

A unit test with a fake client proves the plumbing; this proves that pressing
the key produces text, which is the only thing the user actually does.
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

import config as cfg  # noqa: E402
import localspeech  # noqa: E402
from PyQt6.QtCore import QCoreApplication, QTimer  # noqa: E402

AUDIO = r"C:\Users\user\AppData\Local\hermes\cache\scratch\wa-bench\hard.wav"
MODELS = sys.argv[1] if len(sys.argv) > 1 else "/Users/user/AppData/Local/hermes/cache/scratch/wa-e2e"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "base"


def main():
    from worker import Pipeline

    app = QCoreApplication([])
    conf = cfg.Config()
    conf.data.update({
        "transcribe_engine": "local",
        "local_stt_model": MODEL,
        "language": "tr",
        "cleanup_enabled": False,
        "filter_hallucinations": False,
        "auto_paste": False,
        "history_enabled": False,
        # This is a probe file, not a real take: the level meter reads it as
        # silence, and the point here is the transcription, not the VAD.
        "skip_silent": False,
    })
    # The app's model directory is what the engine reads. Point it at this
    # run's own directory and make sure the model is there, so the check never
    # touches the real one and never depends on a previous run's leftovers.
    cfg.DATA_DIR = pathlib.Path(MODELS)
    here = cfg.DATA_DIR / "whisper"
    localspeech.models_dir = lambda: here
    if not localspeech.state(MODEL, str(here)).installed:
        print(f"downloading {MODEL} into {here}…", flush=True)
        localspeech.download(MODEL, str(here))
    print(f"models_dir -> {here}", flush=True)

    workdir = tempfile.mkdtemp(prefix="wa-pipeline-")
    wav = os.path.join(workdir, "take.wav")
    shutil.copyfile(AUDIO, wav)
    with wave.open(wav) as w:
        duration = w.getnframes() / w.getframerate()
    print(f"recording {duration:.1f}s, engine=local model={MODEL}", flush=True)

    pipeline = Pipeline(conf)
    got = {}

    def done(raw, text, warning, _op):
        got["text"] = text
        app.quit()

    def failed(message, _op):
        got["error"] = message
        app.quit()

    def stage(line, _op):
        print(f"  … {line}", flush=True)

    pipeline.finished.connect(done)
    pipeline.failed.connect(failed)
    pipeline.cancelled.connect(lambda _op: app.quit())
    pipeline.stage.connect(stage)

    started = time.monotonic()
    pipeline.run(wav, duration)
    QTimer.singleShot(180_000, app.quit)
    app.exec()
    elapsed = time.monotonic() - started

    if "error" in got:
        print(f"\nFAILED after {elapsed:.1f}s: {got['error']}")
        return 1
    text = got.get("text", "")
    print(f"\nPIPELINE RESULT ({elapsed:.1f}s, {duration / elapsed:.1f}x realtime):")
    print(text)
    assert text.strip(), "the pipeline produced nothing"
    shutil.rmtree(workdir, ignore_errors=True)
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
