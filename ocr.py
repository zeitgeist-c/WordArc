"""Read text out of an image with Windows' own OCR engine.

The capture editor offers this as one click: crop, OCR, text in clipboard.
Windows ships the recogniser (Windows.Media.Ocr) as part of the OS — no model
download, no bundled engine, Turkish included when its language pack is
installed. The WinRT projections are imported lazily so a machine without
them (or a non-Windows test host) still imports this module; the editor then
hides the button instead of failing.
"""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger("wordarc.ocr")


class OcrUnavailable(RuntimeError):
    """No WinRT OCR projection or no recogniser language on this machine."""


# WordArc UI language -> preferred Windows recogniser tags, in order. The
# machine only offers what language packs it has, so every tag is a wish.
_PREFERRED = {
    "tr": ("tr", "en-US", "en"),
    "en": ("en-US", "en", "tr"),
}


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
    try:
        return asyncio.run(_recognize(png_bytes, ui_language))
    except OcrUnavailable:
        raise
    except Exception as exc:
        log.warning("Windows OCR failed: %s", exc)
        raise OcrUnavailable("Windows OCR could not read the image") from exc
