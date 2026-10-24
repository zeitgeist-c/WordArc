"""Exercise GPU and Vulkan-free CPU transcription in the actual delivery EXE."""
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
    parser.add_argument("--audio", required=True)
    parser.add_argument("--models-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    exe = root / "dist" / "inner" / "WordArc.exe"
    audio = str(Path(args.audio).resolve())
    models = str(Path(args.models_dir).resolve())
    checks = {}
    with tempfile.TemporaryDirectory(prefix="wordarc-acceptance-") as scratch:
        env = dict(os.environ, APPDATA=scratch, LOCALAPPDATA=scratch, QT_QPA_PLATFORM="offscreen")
        for device in ("vulkan", "cpu"):
            output = Path(scratch) / f"{device}.json"
            result = subprocess.run([str(exe), "--local-stt-check", "--device", device,
                                     "--model", "large-v3-turbo", "--language", "en",
                                     "--audio", audio, "--models-dir", models,
                                     "--output", str(output)], env=env, capture_output=True, timeout=180)
            assert output.is_file(), f"packaged {device} produced no evidence; exit={result.returncode}"
            payload = json.loads(output.read_text(encoding="utf-8"))
            assert result.returncode == 0 and payload["ok"], payload
            assert payload["version"] == BRAND.version
            assert payload["segments"] and "country" in payload["segments"][0][2]
            if device == "vulkan":
                assert payload["vulkan_devices"] and not payload["fallback"], payload
            checks[device] = payload
        assert [row[2] for row in checks["cpu"]["segments"]] == [row[2] for row in checks["vulkan"]["segments"]]
    Path(args.output).write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("DELIVERY GPU + CPU TRANSCRIPTION OK")


if __name__ == "__main__":
    main()
