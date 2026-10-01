"""Compare the same audio/model on Vulkan and CPU, including model load time."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time
import wave
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import localspeech as stt
import vulkan_speech as vk


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--ggml-models", required=True)
    parser.add_argument("--ct2-models")
    parser.add_argument("--output", required=True)
    parser.add_argument("--language", default="en")
    args = parser.parse_args()
    results = {}
    for backend in ("vulkan", "cpu-ctranslate2", "cpu-whisper.cpp"):
        runs = []
        for _ in range(3):
            started = time.perf_counter()
            if backend == "cpu-ctranslate2":
                stt._model = None
                stt._model_name = ""
                segments = stt.transcribe("large-v3-turbo", args.audio, args.language,
                                         with_segments=True, where=args.ct2_models, device_preference="cpu")
            else:
                segments = vk.transcribe("large-v3-turbo", args.audio, args.language,
                                         with_segments=True, where=args.ggml_models, use_gpu=backend == "vulkan")
            runs.append(dict(seconds=time.perf_counter() - started, text=" ".join(row[2] for row in segments)))
            print(backend, round(runs[-1]["seconds"], 3), flush=True)
        results[backend] = dict(runs=runs, median_seconds=statistics.median(row["seconds"] for row in runs))
    with wave.open(args.audio) as wav:
        duration = wav.getnframes() / wav.getframerate()
    payload = dict(audio_seconds=duration, model="large-v3-turbo", vulkan_devices=vk.devices(), results=results)
    Path(args.output).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
