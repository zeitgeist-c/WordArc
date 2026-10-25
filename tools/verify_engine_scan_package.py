"""Exercise discovery, explicit UI selection and decode in the delivery executable."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from brand import BRAND


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ct2-root", required=True)
    parser.add_argument("--ggml-root", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    exe = root / "dist" / "inner" / "WordArc.exe"
    checks = {}
    with tempfile.TemporaryDirectory(prefix="wordarc-scan-acceptance-") as scratch:
        scratch = Path(scratch)
        env = dict(os.environ, APPDATA=str(scratch / "roaming"),
                   LOCALAPPDATA=str(scratch / "local"), QT_QPA_PLATFORM="offscreen")
        for kind, model, device, folder in (
                ("ggml", "large-v3-turbo", "vulkan", args.ggml_root),
                ("ggml", "large-v3-turbo", "cpu", args.ggml_root),
                ("ct2", "base", "cpu", args.ct2_root)):
            key = kind + "-" + device
            report = scratch / (key + ".json")
            state = scratch / key
            result = subprocess.run([str(exe), "--engine-scan-check",
                                     "--root", str(Path(folder).resolve()),
                                     "--state-dir", str(state), "--audio", str(Path(args.audio).resolve()),
                                     "--output", str(report), "--kind", kind,
                                     "--model", model, "--device", device],
                                    env=env, capture_output=True, timeout=150)
            assert report.is_file(), f"no scan report for {key}, exit={result.returncode}"
            payload = json.loads(report.read_text(encoding="utf-8"))
            assert result.returncode == 0 and payload["ok"], payload
            assert payload["frozen"] and payload["version"] == BRAND.version, payload
            assert payload["selection_saved"] and payload["linked_without_copy"], payload
            assert "probe" in payload["progress_seen"] and "search" in payload["progress_seen"], payload
            assert "country" in payload["text"].lower(), payload
            if device == "vulkan":
                assert not payload["fallback"], payload
            checks[key] = payload
        assert checks["ggml-cpu"]["text"] == checks["ggml-vulkan"]["text"], checks
    Path(args.output).write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("DELIVERY SCAN -> UI SELECTION -> SAVED SOURCE -> GPU/CPU TRANSCRIPTION OK")


if __name__ == "__main__":
    main()
