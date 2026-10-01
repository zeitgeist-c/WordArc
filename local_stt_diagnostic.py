"""Opt-in local transcription check, with an explicit output path and no config writes."""
import argparse
import json
from pathlib import Path
import time
from brand import BRAND
import localspeech
import vulkan_speech


def run(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--models-dir", required=True)
    parser.add_argument("--model", default="large-v3-turbo", choices=localspeech.model_names())
    parser.add_argument("--device", default="vulkan", choices=("vulkan", "cpu", "cuda", "auto"))
    parser.add_argument("--language", default="auto")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    payload = dict(version=BRAND.version, requested_device=args.device)
    try:
        segments = localspeech.transcribe(args.model, args.audio, args.language,
                                         with_segments=True, where=args.models_dir,
                                         device_preference=args.device)
        payload.update(ok=True, elapsed=time.perf_counter() - started,
                       segments=segments, fallback=localspeech.last_fallback_note(),
                       vulkan_devices=vulkan_speech.devices())
    except Exception as exc:
        payload.update(ok=False, error=str(exc))
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if payload["ok"] else 1
