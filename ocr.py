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

try:
    # Static import so frozen builds collect cv2 through normal analysis
    # (hiddenimports silently drop it). Absence must never break importing
    # this module: the editor hides the buttons instead.
    import cv2  # noqa: F401
except ImportError:
    cv2 = None  # type: ignore[assignment]

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
    if cv2 is None:
        raise OcrUnavailable("OpenCV is not installed")
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
        import asset_cache
        if not asset_cache.bundle_intact():
            raise OcrUnavailable(
                "WordArc's own files were deleted while it was running "
                "(temp cleaner); restart WordArc and try again") from None
        raise
    except Exception as exc:
        log.warning("Windows OCR failed: %s", exc)
        raise OcrUnavailable("No OCR engine could read the image") from exc


# Extra per-script engines for the translate flow only (arabic/cyrillic
# PP-OCRv5 rec models). They are built lazily and cached. The model files
# must already sit next to RapidOCR's bundled ones: this flow never downloads
# at runtime, so a machine without them only skips that script.
_SCRIPT_LANGS = ("arabic", "cyrillic")
_script_engines: dict = {}


def _script_model_ready(lang: str) -> bool:
    """Whether the extra rec model for one script is already on disk."""
    try:
        import rapidocr
        from pathlib import Path
        models = Path(rapidocr.__file__).resolve().parent / "models"
        return (models / f"{lang}_PP-OCRv5_rec_mobile.onnx").is_file()
    except Exception:
        return False


def _has_nonlatin(text: str) -> bool:
    """Whether the text holds a non-Latin script (Cyrillic, Arabic, CJK…)."""
    for char in text:
        code = ord(char)
        if (0x0400 <= code <= 0x052F  # Cyrillic
                or 0x0600 <= code <= 0x06FF  # Arabic
                or 0x0750 <= code <= 0x077F  # Arabic Supplement
                or 0x08A0 <= code <= 0x08FF  # Arabic Extended-B
                or 0xFB50 <= code <= 0xFDFF  # Arabic Presentation-A
                or 0xFE70 <= code <= 0xFEFF  # Arabic Presentation-B
                or 0x3040 <= code <= 0x30FF  # Hiragana + Katakana
                or 0x31F0 <= code <= 0x31FF  # Katakana Phonetic Ext.
                or 0x3400 <= code <= 0x4DBF  # CJK Extension A
                or 0x4E00 <= code <= 0x9FFF  # CJK Unified
                or 0xAC00 <= code <= 0xD7AF):  # Hangul Syllables
            return True
    return False


def _get_script_engine(lang):
    """Build (once) the RapidOCR engine for one extra script."""
    engine = _script_engines.get(lang)
    if engine is not None:
        return engine
    if not _script_model_ready(lang):
        raise OcrUnavailable(
            f"the {lang} OCR model is not installed; skipping that script")
    if cv2 is None:
        raise OcrUnavailable("OpenCV is not installed")
    try:
        from rapidocr import RapidOCR
        from rapidocr.utils.typings import ModelType, OCRVersion
        engine = RapidOCR(params={"Global.log_level": "warning",
                                  "Rec.ocr_version": OCRVersion.PPOCRV5,
                                  "Rec.lang_type": lang,
                                  "Rec.model_type": ModelType.MOBILE})
    except Exception as exc:
        raise OcrUnavailable(
            f"the {lang} OCR engine is not available") from exc
    _script_engines[lang] = engine
    return engine


def _recognize_script(png_bytes: bytes, lang: str) -> str:
    """PNG bytes -> recognised text with one extra per-script engine."""
    if cv2 is None:
        raise OcrUnavailable("OpenCV is not installed")
    try:
        import numpy as np
    except ImportError as exc:
        raise OcrUnavailable("numpy is not installed") from exc
    engine = _get_script_engine(lang)
    image = cv2.imdecode(np.frombuffer(png_bytes, dtype=np.uint8),
                         cv2.IMREAD_COLOR)
    if image is None:
        raise OcrUnavailable("the captured image could not be decoded")
    with _rapid_lock:
        result = engine(image)
    lines = [str(t).strip() for t in (getattr(result, "txts", ()) or ())
             if str(t).strip()]
    return "\n".join(lines).strip()


async def _recognize_all(png_bytes: bytes) -> str:
    """Recognise with every installed Windows language pack; keep the best.

    The screenshot-translate flow must not assume the source language matches
    the UI language, so each recogniser reads the same bitmap and the longest
    non-empty result wins. An empty string means no pack could read anything.
    """
    BitmapDecoder, OcrEngine, InMemoryRandomAccessStream = _imports()
    available = list(OcrEngine.available_recognizer_languages)
    if not available:
        raise OcrUnavailable("No Windows OCR language pack is installed")
    stream = InMemoryRandomAccessStream()
    await stream.write_async(png_bytes)
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    best = ""
    for language in available:
        try:
            engine = OcrEngine.try_create_from_language(language)
            if engine is None:
                continue
            result = await engine.recognize_async(bitmap)
        except Exception as exc:
            log.warning("Windows OCR (%s) failed: %s",
                        getattr(language, "language_tag", "?"), exc)
            continue
        text = "\n".join(line.text for line in result.lines).strip()
        if len(text) > len(best):
            best = text
    return best


def extract_text_for_translate(image) -> str:
    """QImage -> recognised text for the screenshot-translate flow.

    Unlike extract_text this never consults the UI language: RapidOCR's
    multilingual model reads first, then every installed Windows recogniser
    gets a turn, plus the extra Arabic/Cyrillic engines when their models
    are on disk. A candidate holding a non-Latin script wins over longer
    Latin look-alikes (a wrong-script recogniser's guesswork); otherwise the
    longest result wins. '' means nothing was readable.
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
    rapid_available = _rapid_ready()
    candidates: list[str] = []
    rapid_ok = False
    if rapid_available:
        try:
            text = _recognize_rapid(png_bytes)
            rapid_ok = True
            if text.strip():
                candidates.append(text)
        except OcrUnavailable:
            rapid_ok = False
        except Exception as exc:
            rapid_ok = True  # the engine exists; this image glitched it
            log.warning("RapidOCR failed, falling back to Windows OCR: %s",
                        exc)
    windows_error = None
    try:
        text = asyncio.run(_recognize_all(png_bytes))
        if text.strip():
            candidates.append(text)
    except OcrUnavailable as exc:
        windows_error = exc
    except Exception as exc:
        log.warning("Windows OCR failed: %s", exc)
    for lang in _SCRIPT_LANGS:
        try:
            text = _recognize_script(png_bytes, lang)
        except OcrUnavailable as exc:
            log.info("script OCR (%s) unavailable: %s", lang, exc)
            continue
        except Exception as exc:
            log.warning("script OCR (%s) failed: %s", lang, exc)
            continue
        if text.strip():
            candidates.append(text)
    if candidates:
        # A real non-Latin script beats a longer Latin guess; otherwise the
        # longest candidate (usually the most complete read) wins.
        return max(candidates, key=lambda s: (_has_nonlatin(s), len(s)))
    if windows_error is not None and not rapid_ok:
        import asset_cache
        if not asset_cache.bundle_intact():
            raise OcrUnavailable(
                "WordArc's own files were deleted while it was running "
                "(temp cleaner); restart WordArc and try again") from None
        raise windows_error
    return ""
