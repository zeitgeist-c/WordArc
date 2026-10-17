"""Frozen-bundle OCR probe: prove the RapidOCR stack lives and reads inside exe.

argv[1]: 'ocr' <png-path>. Asserts, does not merely print: the engine module
resolves from the bundle, its model files are present under sys._MEIPASS, a
real screenshot decodes to non-empty text through the shipped ocr.extract_text.
"""
import os
import sys


def main() -> None:
    probe = sys.argv[1] if len(sys.argv) > 1 else "ocr"
    if probe != "ocr":
        raise SystemExit(f"unknown probe: {probe}")
    png_path = sys.argv[2]
    import rapidocr
    print(f"rapidocr file: {rapidocr.__file__}", flush=True)
    from rapidocr import RapidOCR  # noqa: F401
    package_dir = os.path.dirname(os.path.abspath(rapidocr.__file__))
    config = os.path.join(package_dir, "config.yaml")
    models = os.path.join(package_dir, "models")
    assert os.path.isfile(config), config
    onnx = [f for f in os.listdir(models) if f.endswith(".onnx")]
    assert onnx, f"no .onnx model shipped in {models}"
    print(f"models in bundle: {sorted(onnx)}", flush=True)
    import cv2
    print(f"cv2 file: {cv2.__file__}", flush=True)
    import ocr as wordarc_ocr
    assert wordarc_ocr._rapid_ready(), "rapid stack not importable in bundle"
    assert wordarc_ocr.is_available(), "is_available() false in bundle"
    from PyQt6.QtGui import QImage
    image = QImage(png_path)
    assert not image.isNull(), f"png did not load: {png_path}"
    import time
    t0 = time.perf_counter()
    text = wordarc_ocr.extract_text(image, "tr")
    dt = time.perf_counter() - t0
    assert text and len(text) > 20, f"empty OCR text ({dt:.2f}s)"
    assert "RapidOCR" not in text and "onnx" not in text
    print(f"FROZEN OCR OK text_len={len(text)} first={text.splitlines()[0][:60]!r} "
          f"secs={dt:.2f}", flush=True)


main()
