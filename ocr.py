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
import re
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


def _run_engine(engine, image):
    """One engine pass -> [(text, score, box|None)] in engine order.

    ``box`` is a float (N, 2) array in image pixels when the engine
    reports one, else None. Empty/garbage-free: blank texts are dropped,
    everything else survives for the merge/filter stages to judge.
    """
    import numpy as np
    result = engine(image)
    txts = list(getattr(result, "txts", ()) or ())
    boxes = getattr(result, "boxes", None)
    scores = list(getattr(result, "scores", None) or [])
    lines = []
    for i, raw in enumerate(txts):
        text = str(raw).strip()
        if not text:
            continue
        box = None
        try:
            if boxes is not None and i < len(boxes) and boxes[i] is not None:
                box = np.asarray(boxes[i], dtype=float).reshape(-1, 2)
        except Exception:
            box = None
        try:
            score = float(scores[i]) if i < len(scores) else 0.0
        except Exception:
            score = 0.0
        lines.append((text, score, box))
    return lines


def _bbox(box):
    x0, y0 = box.min(axis=0)
    x1, y1 = box.max(axis=0)
    return float(x0), float(y0), float(x1), float(y1)


def _iou(a, b):
    ax0, ay0, ax1, ay1 = _bbox(a)
    bx0, by0, bx1, by1 = _bbox(b)
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / union if union > 0 else 0.0


def _similar(a: str, b: str) -> bool:
    """Whether two reads plausibly show the same line (not neighbours)."""
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a.strip().lower(),
                           b.strip().lower()).ratio() > 0.5


def _merge_lines(base, extra):
    """Fuse a second pass into the first, keeping reading order.

    A second-pass box that matches a first-pass box *and* reads alike
    replaces it when its recognition score is higher (small text often
    misreads first, then reads clean on the scaled pass). A near-identical
    box (IoU > 0.8) is the same line even when both reads garble
    differently, so the higher score wins there too. Anything else
    is appended: dense neighbouring rows overlap, and must never knock
    each other out. A re-read of one physical line collapses into it,
    keeping the best; the same text in two places is two lines and both
    survive.
    """
    merged = list(base)
    for text, score, box in extra:
        if box is None:
            merged.append((text, score, box))
            continue
        best, best_iou = -1, 0.0
        for i, (_t, _s, bb) in enumerate(merged):
            if bb is None:
                continue
            value = _iou(box, bb)
            if value > best_iou:
                best, best_iou = i, value
        same_line = best_iou > 0.8 or (
            best_iou > 0.6 and _similar(text, merged[best][0])) \
            if best >= 0 else False
        if best >= 0 and same_line:
            # A clear margin: at epsilon gaps the original-scale read wins
            # over a same-box garble that happens to score a hair higher.
            if score > merged[best][1] + 0.03:
                merged[best] = (text, score, merged[best][2])
        else:
            merged.append((text, score, box))
    heights = [_bbox(bb)[3] - _bbox(bb)[1] for _t, _s, bb in merged
               if bb is not None]
    row_tol = max(4.0, (sorted(heights)[len(heights) // 2] * 0.5
                        if heights else 8.0))

    def key(item):
        _t, _s, bb = item
        if bb is None:
            return (10 ** 9, 0.0)
        x0, y0, x1, y1 = _bbox(bb)
        return (int(((y0 + y1) / 2) // row_tol), (x0 + x1) / 2)

    merged.sort(key=key)
    # Collapse only geometric re-reads: the same text (or, on a long line,
    # one character apart) inside boxes that really overlap. The same word
    # in two places never shares a box, and neighbours like
    # "Sipariş 12345"/"Sipariş 12346" do not overlap, so both survive.
    out = []
    for text, score, box in merged:
        if (box is not None and out and out[-1][2] is not None
                and key(out[-1])[0] == key((text, score, box))[0]):
            prev_text, prev_score, prev_box = out[-1]
            folded = text.strip().lower()
            if _iou(box, prev_box) > 0.5 and (
                    folded == prev_text.strip().lower()
                    or _near_dupe(text, prev_text)):
                if score > prev_score:
                    out[-1] = (text, score, box)
                continue
        out.append((text, score, box))
    return out


def _near_dupe(a: str, b: str) -> bool:
    """Whether two reads are one character apart (same line, twice read).

    Short headers ("Bölüm 1"/"Bölüm 2") also differ by one character, so
    this only applies to longer lines.
    """
    from difflib import SequenceMatcher
    a, b = a.strip().lower(), b.strip().lower()
    if min(len(a), len(b)) < 10:
        return False
    return SequenceMatcher(None, a, b).ratio() > 0.85


# Code points no real script uses for words: box drawing, block elements,
# geometric shapes and dingbats. The multilingual recogniser emits these
# for icons and ornaments; CJK, kana and hangul are real writing and must
# never count as junk by script alone.
_SYMBOL_NOISE_RANGES = (
    (0x2500, 0x25FF),  # box drawing, blocks, geometric shapes
    (0x2700, 0x27BF),  # dingbats
)


def _symbol_noise(char: str) -> bool:
    code = ord(char)
    return any(lo <= code <= hi for lo, hi in _SYMBOL_NOISE_RANGES)


def _has_word(text: str) -> bool:
    """Whether the text holds a run of 2+ letters/digits (any script)."""
    run = 0
    for char in text:
        run = run + 1 if char.isalnum() else 0
        if run >= 2:
            return True
    return False


def _drop_junk(lines):
    """Remove icon/ornament hallucinations, keep real short text.

    Multi-letter lines in any script always survive. A box holding pure
    symbol noise (geometric shapes, dingbats) is junk at any score. Any
    other single character — Latin ``A``, a digit ``7``, ``%`` or CJK
    ``日`` — is kept once the recogniser is reasonably certain of it;
    only a shaky small read is dropped.
    """
    kept = []
    for text, score, box in lines:
        if _has_word(text):
            kept.append((text, score, box))
            continue
        chars = [c for c in text.strip() if not c.isspace()]
        if not chars:
            continue
        small = True
        if box is not None:
            x0, y0, x1, y1 = _bbox(box)
            small = max(x1 - x0, y1 - y0) < 30
        if all(_symbol_noise(c) for c in chars):
            log.debug("OCR junk dropped (%0.2f): %r", score, text)
            continue
        if small and score < 0.9:
            log.debug("OCR junk dropped (%0.2f): %r", score, text)
            continue
        kept.append((text, score, box))
    return kept


def _needs_second_pass(lines, height: int, width: int) -> bool:
    """Whether a scaled re-read is worth its second."""
    if not lines:
        # Nothing at all, yet room for text: the pass may have missed all.
        return height >= 40 and width >= 100
    boxes = [bb for _t, _s, bb in lines if bb is not None]
    if boxes:
        heights = sorted(_bbox(bb)[3] - _bbox(bb)[1] for bb in boxes)
        if heights[len(heights) // 2] < 14:
            return True  # small glyphs: recognition earns more pixels
    for text, score, _bb in lines:
        if _has_word(text) and score < 0.9:
            return True  # a shaky read worth a second opinion
    return False


def _row_tol(lines) -> float:
    """Row band height from the median line height of a line set."""
    heights = sorted(_bbox(bb)[3] - _bbox(bb)[1] for _t, _s, bb in lines
                     if bb is not None)
    return max(4.0, (heights[len(heights) // 2] * 0.5 if heights else 8.0))


def _fuse_fragments(prev, cur, row_tol):
    """Fuse one physical line's head and tail, writing shared words once.

    The left tile reads the line's head, the right tile its tail, and the
    overlap region appears in both ("... starts here and continues" /
    "here and continues past ..."). Two fragments fuse only when they sit
    on the same row, their boxes touch or overlap, and the head's last
    words equal the tail's first words (two or more, eight characters at
    least) with fresh words on both sides. Columns, neighbour rows and
    repeated text never satisfy all at once, so they survive. Returns the
    fused (text, score, box) or None.
    """
    pt, ps, pb = prev
    ct, cs, cb = cur
    if pb is None or cb is None:
        return None
    px0, py0, px1, py1 = _bbox(pb)
    cx0, cy0, cx1, cy1 = _bbox(cb)
    height = min(py1 - py0, cy1 - cy0)
    if height <= 0:
        return None
    if int(((py0 + py1) / 2) // row_tol) != int(((cy0 + cy1) / 2) // row_tol):
        return None
    if abs((py0 + py1) / 2 - (cy0 + cy1) / 2) > 0.5 * height:
        return None
    if cx0 > px1 + max(8.0, 0.5 * height):
        return None
    prev_words = pt.split()
    cur_words = ct.split()
    shared = 0
    for size in range(min(len(prev_words), len(cur_words)), 1, -1):
        if ([w.lower() for w in prev_words[-size:]]
                == [w.lower() for w in cur_words[:size]]):
            shared = size
            break
    if shared < 2:
        return None
    if shared >= len(prev_words) or shared >= len(cur_words):
        return None  # repetition, not a split: both sides add nothing
    if sum(len(w) for w in cur_words[:shared]) < 8:
        return None
    import numpy as np
    merged_box = np.array([[min(px0, cx0), min(py0, cy0)],
                           [max(px1, cx1), min(py0, cy0)],
                           [max(px1, cx1), max(py1, cy1)],
                           [min(px0, cx0), max(py1, cy1)]], dtype=float)
    return (" ".join(prev_words + cur_words[shared:]), max(ps, cs),
            merged_box)


def _stitch_pair(left, right):
    """Fuse seam-split lines across two neighbouring tiles only.

    Provenance is the guard: only a line from the left tile may fuse with
    one from the right tile. Two boxes from the same tile never fuse here,
    no matter their shared words — that is what columns and repeated
    labels look like.

    Returns (done, carry): ``done`` holds left lines that matched nothing
    and can never match a later tile; ``carry`` holds fused lines plus
    unmatched right lines, which may still fuse with the next tile.
    """
    row_tol = _row_tol(list(left) + list(right))

    def centre_x(item):
        _t, _s, bb = item
        if bb is None:
            return float("inf")
        x0, _y0, x1, _y1 = _bbox(bb)
        return (x0 + x1) / 2

    remaining = sorted(left, key=centre_x)
    carry = []
    for cur in sorted(right, key=centre_x):
        match = None
        for index, prev in enumerate(remaining):
            fused = _fuse_fragments(prev, cur, row_tol)
            if fused is not None:
                match = (index, fused)
                break
        if match is not None:
            index, fused = match
            del remaining[index]
            carry.append(fused)
        else:
            carry.append(cur)
    return remaining, carry


def _tile_spans(length: int, tile: int, overlap: int):
    """Split one axis into overlapping spans covering [0, length)."""
    spans = []
    start = 0
    while start < length:
        end = min(length, start + tile)
        spans.append((start, end))
        if end >= length:
            break
        start += tile - overlap
    return spans


def _recognize_tiled(engine, image):
    """Read a very wide capture in overlapping vertical tiles.

    The detector normalises its input size, so on a 4K-wide selection
    small glyphs shrink past recognition and whole lines vanish (1 of 6
    kept, measured). Tiles give the recogniser real pixels again; the
    overlap plus the geometric merge collapse the seam re-reads, so no
    line is lost or doubled.
    """
    import numpy as np
    tiles = []
    for x0, x1 in _tile_spans(image.shape[1], 1920, 480):
        tile_lines = []
        for text, score, bb in _recognize_multipass(
                engine, image[:, x0:x1]):
            if bb is not None:
                bb = bb + np.array([x0, 0], dtype=float)
            tile_lines.append((text, score, bb))
        tiles.append(tile_lines)
    # Stitch only across neighbouring tiles, where a seam split can occur;
    # lines from one tile never fuse with each other. The geometric merge
    # below then collapses the remaining seam re-reads.
    pooled = []
    carry = tiles[0] if tiles else []
    for nxt in tiles[1:]:
        done, carry = _stitch_pair(carry, nxt)
        pooled.extend(done)
    pooled.extend(carry)
    return _drop_junk(_merge_lines([], pooled))


def _recognize_multipass(engine, image):
    """Run the engine, then a scaled pass when the first looks shaky.

    The detector normalises its input size, so one pass is enough for
    normal text; the second pass (up to 2x, capped by pixel budget) feeds
    the recogniser more glyph pixels for small or shaky lines. Returns
    merged, filtered [(text, score, box)] in reading order.
    """
    import math
    import numpy as np
    from PIL import Image
    height, width = image.shape[:2]
    # Very wide captures (4K selections) lose small lines entirely: the
    # detector downscales them away and no upscale budget brings them back.
    # Tiles are the measured fix (1/6 -> 6/6 lines); anything narrower keeps
    # the single fast path.
    if width > 2000:
        return _recognize_tiled(engine, image)
    with _rapid_lock:
        base = _run_engine(engine, image)
    height, width = image.shape[:2]
    if not _needs_second_pass(base, height, width):
        return _drop_junk(base)
    # Pixel budget, not long side: wide regions still earn their upscale.
    scale = min(2.0, math.sqrt(6_000_000.0 / (height * width)))
    if scale < 1.15:
        return _drop_junk(base)
    big = np.array(Image.fromarray(image).resize(
        (round(width * scale), round(height * scale)), Image.LANCZOS))
    with _rapid_lock:
        extra = _run_engine(engine, big)
    extra = [(t, s, b / scale if b is not None else None)
             for t, s, b in extra]
    log.info("OCR second pass (%.1fx): %d + %d lines", scale,
             len(base), len(extra))
    return _drop_junk(_merge_lines(base, extra))


def _recognize_rapid(png_bytes: bytes) -> str:
    """PNG bytes -> recognised text, via the shared ONNX engine."""
    global _last_mean_score
    if cv2 is None:
        raise OcrUnavailable("OpenCV is not installed")
    import numpy as np
    engine = _get_rapid_engine()
    image = cv2.imdecode(np.frombuffer(png_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise OcrUnavailable("the captured image could not be decoded")
    lines = _recognize_multipass(engine, image)
    _last_mean_score = _mean_score(lines)
    return "\n".join(text for text, _score, _box in lines).strip()


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
    """Choose the Windows recogniser for the UI language.

    First an installed pack whose full tag matches, then a pack in the
    same language (region and case do not matter), then the English
    fallback, then whatever the OS has at all. A pack whose engine the
    OS cannot create is skipped in favour of the next suitable one; only
    when nothing can be created does the caller hear about it.
    """
    available = list(OcrEngine.available_recognizer_languages)
    if not available:
        raise OcrUnavailable("No Windows OCR language pack is installed")
    ui = (ui_language or "").strip().lower().replace("_", "-")
    ui_base = ui.split("-")[0] if ui else ""

    def norm(tag) -> str:
        return str(tag).strip().lower().replace("_", "-")

    tags = [norm(getattr(lang, "language_tag", "")) for lang in available]
    ordered: list[int] = []

    def consider(index: int):
        if index not in ordered:
            ordered.append(index)

    for i, tag in enumerate(tags):  # the exact installed tag
        if tag and tag == ui:
            consider(i)
    for i, tag in enumerate(tags):  # the same language, any region
        if tag and ui_base and tag.split("-")[0] == ui_base:
            consider(i)
    for want in ("en-us", "en"):  # the fallback language
        for i, tag in enumerate(tags):
            if tag == want:
                consider(i)
    for i, tag in enumerate(tags):
        if tag and tag.split("-")[0] == "en":
            consider(i)
    for i in range(len(available)):  # anything the OS has at all
        consider(i)
    for i in ordered:
        engine = OcrEngine.try_create_from_language(available[i])
        if engine is not None:
            log.info("Windows OCR engine: %s (of %s installed)",
                     available[i].language_tag, len(available))
            return engine
    return None


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
    rapid_text = None
    rapid_ran = False
    try:
        rapid_text = _recognize_rapid(png_bytes)
        rapid_ran = True
    except OcrUnavailable:
        pass  # not installed / not started: Windows takes over below
    except Exception as exc:
        log.warning("RapidOCR failed, falling back to Windows OCR: %s", exc)
    if rapid_text and rapid_text.strip():
        return rapid_text
    # RapidOCR ran but read nothing: it may simply have missed the text,
    # so the Windows recogniser still gets its turn before the capture is
    # reported as unreadable.
    try:
        return asyncio.run(_recognize(png_bytes, ui_language))
    except OcrUnavailable as exc:
        if not rapid_ran:
            import asset_cache
            if not asset_cache.bundle_intact():
                raise OcrUnavailable(
                    "WordArc's own files were deleted while it was running "
                    "(temp cleaner); restart WordArc and try again") from None
            raise
        log.info("Windows OCR unavailable after an empty RapidOCR read: %s",
                 exc)
        return ""
    except Exception as exc:
        if not rapid_ran:
            log.warning("Windows OCR failed: %s", exc)
            raise OcrUnavailable("No OCR engine could read the image") from exc
        log.warning("Windows OCR failed after an empty RapidOCR read: %s",
                    exc)
        return ""


# Mean recognition score of the most recent real RapidOCR pass in this
# process (None when the last call was mocked, empty or failed). The
# translate flow reads it right after each engine call, so a confident
# Latin read can overrule the guesswork of a wrong-script recogniser.
_last_mean_score = None


def _mean_score(lines) -> float | None:
    scores = [s for _t, s, _b in lines if isinstance(s, (int, float))]
    if not scores:
        return None
    return sum(scores) / len(scores)


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
    return _nonlatin_letters(text) > 0


def _nonlatin_letters(text: str) -> int:
    """Count letters in a non-Latin script (Cyrillic, Arabic, CJK…)."""
    count = 0
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
            count += 1
    return count


_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _coverage_score(text: str) -> float:
    """How much consistent reading one candidate holds, no score attached.

    Coverage is alphanumeric characters plus whole words; consistency is
    the dominant script's share of the letters, so a garbled mix scores
    below a clean read of the same length.
    """
    words = _WORD_RE.findall(text)
    alnum = sum(1 for c in text if c.isalnum())
    good_words = sum(1 for w in words
                     if sum(1 for c in w if c.isalnum()) >= 2)
    letters = [c for c in text if c.isalpha()]
    if letters:
        nonlatin = _nonlatin_letters(text)
        share = max(nonlatin, len(letters) - nonlatin) / len(letters)
    else:
        share = 1.0
    return (alnum + 2 * good_words) * (0.5 + 0.5 * share)


def _translation_score(text: str, confidence=None) -> float:
    """Score one translation candidate: coverage scaled by confidence.

    A recognition score, where the engine reports one, scales the
    coverage instead of replacing it: a tiny confident read must not
    outrank a far fuller one on confidence alone.
    """
    score = _coverage_score(text)
    if confidence is not None:
        try:
            clamped = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            clamped = 0.5
        score *= 0.6 + 0.4 * clamped
    return score


def _substantive_nonlatin(text: str) -> bool:
    """Whether a non-Latin script carries this candidate, not a stray mark.

    One wrong CJK character must never outrank a clean Latin read, while a
    real Japanese, Cyrillic or Arabic passage keeps its priority over a
    longer Latin guess.
    """
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    nonlatin = _nonlatin_letters(text)
    return nonlatin >= 2 and nonlatin / len(letters) >= 0.5


def _choose_translation_source(candidates) -> str:
    """Pick the text the translate flow sends to Gemini.

    ``candidates`` is [(text, confidence|None)]. A candidate with a real
    non-Latin passage wins over Latin guesses — unless a confident Latin
    candidate holds comparable coverage while the non-Latin one reports
    no score, which marks the guesswork of a wrong-script recogniser.
    Confidence alone never bridges a wide coverage gap. Between
    candidates of the same kind the fuller, more consistent read wins;
    real mixed-script text is one candidate and passes through untouched.
    """
    items = [(t, c) for t, c in candidates if t and t.strip()]
    if not items:
        return ""
    scored = [(t, c, _translation_score(t, c)) for t, c in items]
    flagged = [item for item in items if _substantive_nonlatin(item[0])]
    if flagged:
        best_flagged = max(
            (item for item in scored if _substantive_nonlatin(item[0])),
            key=lambda item: (item[2], len(item[0])),
        )
        unflagged = [item for item in scored
                     if not _substantive_nonlatin(item[0])]
        if unflagged:
            best_plain = max(unflagged, key=lambda item: (item[2],
                                                          len(item[0])))
            if (best_plain[1] is not None and best_plain[1] >= 0.9
                    and (best_flagged[1] is None
                         or best_flagged[1] < best_plain[1])
                    and _coverage_score(best_plain[0])
                    >= 0.5 * _coverage_score(best_flagged[0])):
                return best_plain[0]
        return best_flagged[0]
    return max(scored, key=lambda item: (item[2], len(item[0])))[0]


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
    global _last_mean_score
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
    lines = _recognize_multipass(engine, image)
    _last_mean_score = _mean_score(lines)
    return "\n".join(text for text, _score, _box in lines).strip()


async def _recognize_all(png_bytes: bytes) -> str:
    """Recognise with every installed Windows language pack; keep the best.

    The screenshot-translate flow must not assume the source language matches
    the UI language, so each recogniser reads the same bitmap and the
    chooser keeps the best read. An empty string means no pack could read
    anything.
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
    best = []
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
        # WinRT reports no recognition score, so every pack's read joins
        # the chooser without one; coverage and script consistency decide.
        if text:
            best.append((text, None))
    return _choose_translation_source(best)


def extract_text_for_translate(image) -> str:
    """QImage -> recognised text for the screenshot-translate flow.

    Unlike extract_text this never consults the UI language: RapidOCR's
    multilingual model reads first, then every installed Windows recogniser
    gets a turn, plus the extra Arabic/Cyrillic engines when their models
    are on disk. The chooser weighs coverage, script consistency and any
    reported recognition score: a real non-Latin passage beats longer
    Latin look-alikes, one stray foreign character never beats a clean
    Latin read, and '' means nothing was readable.
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
    candidates: list = []
    rapid_ok = False

    def take_scored(call, *args):
        """Call one engine, pairing its text with its reported score.

        Mocked engines in tests report no score (None); real RapidOCR
        passes record their mean line score on the way out.
        """
        global _last_mean_score
        _last_mean_score = None
        return call(*args), _last_mean_score

    if rapid_available:
        try:
            text, confidence = take_scored(_recognize_rapid, png_bytes)
            rapid_ok = True
            if text.strip():
                candidates.append((text, confidence))
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
            candidates.append((text, None))
    except OcrUnavailable as exc:
        windows_error = exc
    except Exception as exc:
        log.warning("Windows OCR failed: %s", exc)
    for lang in _SCRIPT_LANGS:
        try:
            text, confidence = take_scored(_recognize_script, png_bytes,
                                           lang)
        except OcrUnavailable as exc:
            log.info("script OCR (%s) unavailable: %s", lang, exc)
            continue
        except Exception as exc:
            log.warning("script OCR (%s) failed: %s", lang, exc)
            continue
        if text.strip():
            candidates.append((text, confidence))
    if candidates:
        return _choose_translation_source(candidates)
    if windows_error is not None and not rapid_ok:
        import asset_cache
        if not asset_cache.bundle_intact():
            raise OcrUnavailable(
                "WordArc's own files were deleted while it was running "
                "(temp cleaner); restart WordArc and try again") from None
        raise windows_error
    return ""
