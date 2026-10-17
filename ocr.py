"""Read text out of an image — RapidOCR first, Windows OCR as fallback.

The capture editor offers this as one click: crop, OCR, text in clipboard.
RapidOCR (PaddleOCR models on ONNX Runtime) is the primary engine: it reads
small on-screen text correctly, where Windows' own recogniser garbles it.
Windows ships its recogniser (Windows.Media.Ocr) with the OS and stays as a
fallback for machines where the ONNX stack is unavailable. Heavy imports are
lazy so a machine without them (or a non-Windows test host) still imports
this module; the editor then hides the button instead of failing.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import threading

log = logging.getLogger("wordarc.ocr")


class OcrUnavailable(RuntimeError):
    """No usable OCR engine here (neither RapidOCR nor Windows OCR)."""


# WordArc UI language -> preferred Windows recogniser tags, in order. The
# machine only offers what language packs it has, so every tag is a wish.
# RapidOCR needs no language pick: its model reads Turkish out of the box.
_PREFERRED = {
    "tr": ("tr", "en-US", "en"),
    "en": ("en-US", "en", "tr"),
}

# The ONNX engine loads its models on first use (~1 s); build it once and
# serialise calls. OCR already runs on one worker thread — the lock only
# keeps a second capture from racing the first inside the engine.
_rapid_lock = threading.Lock()
_rapid_engine = None
_rapid_failed = False


def _rapid_ready() -> bool:
    """Cheap import check for the RapidOCR stack (no module loading)."""
    for mod in ("rapidocr", "onnxruntime", "cv2", "numpy"):
        try:
            if importlib.util.find_spec(mod) is None:
                return False
        except (ImportError, ValueError):
            return False
    return True


def _get_rapid_engine():
    """Build (once) the shared RapidOCR engine; raise OcrUnavailable if absent."""
    global _rapid_engine, _rapid_failed
    if _rapid_engine is not None:
        return _rapid_engine
    if _rapid_failed or not _rapid_ready():
        raise OcrUnavailable("RapidOCR stack is not installed")
    with _rapid_lock:
        if _rapid_engine is None:
            try:
                # rapidocr logs INFO lines on every model load; a desktop app
                # has no console for them. The engine's own config knob sets
                # the level of the logger it shares (name "RapidOCR").
                from rapidocr import RapidOCR
                _rapid_engine = RapidOCR(params={"Global.log_level": "warning"})
            except Exception as exc:
                _rapid_failed = True
                log.warning("RapidOCR could not start: %s", exc)
                raise OcrUnavailable("RapidOCR could not start") from exc
    return _rapid_engine


def _recognize_rapid(png_bytes: bytes) -> str:
    """PNG bytes -> recognised text, via the shared ONNX engine."""
    import cv2
    import numpy as np
    engine = _get_rapid_engine()
    image = cv2.imdecode(np.frombuffer(png_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise OcrUnavailable("the captured image could not be decoded")
    with _rapid_lock:
        result = engine(image)
    lines = [str(t).strip() for t in (getattr(result, "txts", ()) or ()) if str(t).strip()]
    return "\n".join(lines).strip()


# --- Windows fallback (kept for machines without the ONNX stack) -----------


def _imports():
    """Import the WinRT projections; raise OcrUnavailable if absent."""
    try:
        from winrt.windows.graphics.imaging import BitmapDecoder
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import InMemoryRandomAccessStream
    except ImportError as exc:
        raise OcrUnavailable(
            "Windows OCR is not available on this system") from exc
    return BitmapDecoder, OcrEngine, InMemoryRandomAccessStream


def is_available() -> bool:
    """Cheap GUI-thread-safe answer: can this machine run OCR at all?

    The editor builds its toolbar before any worker runs; a button that can
    never work on this Windows install must not appear at all.
    """
    if _rapid_ready():
        return True
    try:
        _, OcrEngine, _ = _imports()
        return bool(OcrEngine.available_recognizer_languages)
    except Exception:
        return False


def _pick_engine(OcrEngine, ui_language: str):
    available = list(OcrEngine.available_recognizer_languages)
    if not available:
        raise OcrUnavailable("No Windows OCR language pack is installed")
    wanted = _PREFERRED.get((ui_language or "").lower(), ())
    for tag in wanted:
        for candidate in available:
            if candidate.language_tag.lower() == tag.lower():
                engine = OcrEngine.try_create_from_language(candidate)
                if engine is not None:
                    return engine
    # First look-alike, then anything the OS recognises at all.
    for tag in wanted:
        for candidate in available:
            if candidate.language_tag.lower().startswith(tag.split("-")[0].lower()):
                engine = OcrEngine.try_create_from_language(candidate)
                if engine is not None:
                    return engine
    return OcrEngine.try_create_from_language(available[0])


async def _recognize(png_bytes: bytes, ui_language: str) -> str:
    BitmapDecoder, OcrEngine, InMemoryRandomAccessStream = _imports()
    stream = InMemoryRandomAccessStream()
    await stream.write_async(png_bytes)
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    # OCR wants a SoftwareBitmap; the decoder already hands one over, and
    # JPEG's CMYK and HDR paths are normalised for us here.
    bitmap = await decoder.get_software_bitmap_async()
    engine = _pick_engine(OcrEngine, ui_language)
    if engine is None:
        raise OcrUnavailable("Windows could not create an OCR engine")
    result = await engine.recognize_async(bitmap)
    # Lines, not result.text: its single-space join swallows the line breaks
    # the user just captured.
    return "\n".join(line.text for line in result.lines).strip()


def extract_text(image, ui_language: str = "") -> str:
    """QImage -> recognised text ('' when the image holds no readable text).

    Blocking; call from a worker thread, never the GUI thread: a full-screen
    selection keeps the recogniser busy for a second or two.
    """
    from PyQt6.QtCore import QBuffer, QIODevice
    from PyQt6.QtGui import QImage

    if image.format() != QImage.Format.Format_RGBA8888:
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.ReadWrite)
    if not image.save(buffer, "PNG"):
        raise OcrUnavailable("the captured image could not be encoded")
    png_bytes = bytes(buffer.data())
    buffer.close()
    # Primary: RapidOCR. An engine-side glitch logs and falls through to the
    # Windows recogniser instead of failing the user's one click.
    try:
        return _recognize_rapid(png_bytes)
    except OcrUnavailable:
        pass  # not installed / not started: Windows takes over below
    except Exception as exc:
        log.warning("RapidOCR failed, falling back to Windows OCR: %s", exc)
    try:
        return asyncio.run(_recognize(png_bytes, ui_language))
    except OcrUnavailable:
        raise
    except Exception as exc:
        log.warning("Windows OCR failed: %s", exc)
        raise OcrUnavailable("No OCR engine could read the image") from exc
