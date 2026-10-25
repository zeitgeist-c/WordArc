"""Build the small independent Inno supervisor and pin it into the main bundle."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "tools" / "vendor" / "update-helper"


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
                    "--onefile", "--windowed", "--name", "WordArcUpdate", "--paths", str(ROOT),
                    "--distpath", str(DEST), "--workpath", str(ROOT / ".cache/update-helper-build"),
                    "--specpath", str(ROOT / ".cache/update-helper-spec"), str(ROOT / "update_helper.py")], check=True)
    files = ("update_helper.py", "update_protocol.py")
    manifest = dict(sources={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files},
                    sha256=hashlib.sha256((DEST / "WordArcUpdate.exe").read_bytes()).hexdigest())
    (DEST / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("UPDATE HELPER VERIFIED", manifest["sha256"])


if __name__ == "__main__":
    main()
