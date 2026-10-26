"""Create the reproducible, hash-pinned repair asset before freezing WordArc."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.build_vulkan import DEST, FILES, ROOT, VERSION, verify
from brand import BRAND


def main():
    assert verify(), "Unverified Vulkan runtime"
    name = f"WordArcVulkan-{VERSION}.zip"
    output = ROOT / "dist" / name
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for filename in sorted((*FILES, "manifest.json")):
            info = zipfile.ZipInfo(filename, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (DEST / filename).read_bytes())
    with output.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    pins = dict(version=VERSION, file=name, size=output.stat().st_size, sha256=digest,
                url=f"https://github.com/zeitgeist-c/WordArc/releases/download/v{BRAND.version}/{name}")
    target = ROOT / "assets" / "vulkan" / "runtime.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(pins, indent=2) + "\n", encoding="utf-8")
    print(f"VULKAN REPAIR ASSET OK: {name} SHA256={digest}")


if __name__ == "__main__":
    main()
