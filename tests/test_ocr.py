import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import asyncio
import unittest
from unittest import mock

from PyQt6.QtGui import QImage

import ocr


class FakeLanguage:
    def __init__(self, tag):
        self.language_tag = tag


def fake_engine(tag):
    engine = mock.Mock()
    engine.recognizer_language = FakeLanguage(tag)
    return engine


class FakeEngineClass:
    def __init__(self, tags):
        self.available_recognizer_languages = [FakeLanguage(tag) for tag in tags]

    @classmethod
    def try_create_from_language(cls, language, /):
        return fake_engine(language.language_tag)


class TestEngineChoice(unittest.TestCase):
    def test_turkish_ui_prefers_the_turkish_recogniser(self):
        engine = ocr._pick_engine(FakeEngineClass(["en-US", "tr"]), "tr")
        self.assertEqual(engine.recognizer_language.language_tag, "tr")

    def test_english_ui_prefers_english(self):
        engine = ocr._pick_engine(FakeEngineClass(["tr", "en-US"]), "en")
        self.assertEqual(engine.recognizer_language.language_tag, "en-US")

    def test_wanted_language_falls_back_to_any_installed_one(self):
        # Machine has neither exact wish nor prefix match: first installed.
        engine = ocr._pick_engine(FakeEngineClass(["de-DE"]), "tr")
        self.assertEqual(engine.recognizer_language.language_tag, "de-DE")

    def test_prefix_match_when_exact_tag_is_absent(self):
        engine = ocr._pick_engine(FakeEngineClass(["tr-TR"]), "tr")
        self.assertEqual(engine.recognizer_language.language_tag, "tr-TR")

    def test_no_language_pack_is_a_clean_refusal(self):
        with self.assertRaises(ocr.OcrUnavailable):
            ocr._pick_engine(FakeEngineClass([]), "tr")


class TestRecognitionPlumbing(unittest.TestCase):
    def test_lines_join_with_newlines(self):
        lines = [mock.Mock(text="bir"), mock.Mock(text="iki")]
        result = mock.Mock(lines=lines)
        engine = mock.Mock()
        decoder = mock.Mock()

        async def bitmap_async():
            return "bitmap"

        async def decode_async(stream):
            return decoder

        async def recognize_async(bitmap):
            assert bitmap == "bitmap"
            return result

        class Stream:
            async def write_async(self, data):
                return None

            def seek(self, pos):
                pass

        decoder.get_software_bitmap_async = bitmap_async
        engine.recognize_async = recognize_async
        decoder_class = mock.Mock()
        decoder_class.create_async = decode_async

        with mock.patch.object(ocr, "_imports",
                               return_value=(decoder_class,
                                             mock.Mock(), Stream)), \
             mock.patch.object(ocr, "_pick_engine", return_value=engine):
            text = asyncio.run(ocr._recognize(b"png", "tr"))
        self.assertEqual(text, "bir\niki")


class TestRapidPrimary(unittest.TestCase):
    """RapidOCR is the primary engine; Windows OCR is the fallback."""

    def _white_image(self):
        from PyQt6.QtGui import QColor
        image = QImage(4, 4, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        return image

    def test_rapid_result_wins(self):
        with mock.patch.object(ocr, "_recognize_rapid", return_value="rapid metni"), \
             mock.patch.object(ocr, "_recognize", side_effect=AssertionError("winrt calismamali")):
            self.assertEqual(ocr.extract_text(self._white_image(), "tr"), "rapid metni")

    def test_windows_takes_over_when_rapid_is_absent(self):
        async def win(*_a, **_k):
            return "windows metni"
        with mock.patch.object(ocr, "_recognize_rapid",
                               side_effect=ocr.OcrUnavailable("yok")), \
             mock.patch.object(ocr, "_recognize", win):
            self.assertEqual(ocr.extract_text(self._white_image(), "tr"), "windows metni")

    def test_windows_takes_over_when_rapid_glitches(self):
        async def win(*_a, **_k):
            return "windows metni"
        with mock.patch.object(ocr, "_recognize_rapid",
                               side_effect=RuntimeError("model patladi")), \
             mock.patch.object(ocr, "_recognize", win):
            self.assertEqual(ocr.extract_text(self._white_image(), "tr"), "windows metni")

    def test_rapid_ready_false_refuses_cleanly(self):
        saved = (ocr._rapid_engine, ocr._rapid_failed)
        ocr._rapid_engine, ocr._rapid_failed = None, False
        try:
            with mock.patch.object(ocr, "_rapid_ready", return_value=False):
                with self.assertRaises(ocr.OcrUnavailable):
                    ocr._get_rapid_engine()
        finally:
            ocr._rapid_engine, ocr._rapid_failed = saved

    def test_is_available_true_when_only_rapid_is_present(self):
        with mock.patch.object(ocr, "_rapid_ready", return_value=True), \
             mock.patch.object(ocr, "_imports",
                               side_effect=ocr.OcrUnavailable("winrt yok")):
            self.assertTrue(ocr.is_available())


class TestMultipassMerge(unittest.TestCase):
    """A scaled second pass must heal garbles, never eat neighbours."""

    def _box(self, x0, y0, x1, y1):
        import numpy as np
        return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                        dtype=float)

    def test_higher_score_replaces_same_line(self):
        base = [("Due ae", 0.52, self._box(10, 10, 200, 30))]
        extra = [("Dil: Türkçe", 0.97, self._box(11, 11, 199, 29))]
        merged = ocr._merge_lines(base, extra)
        self.assertEqual([t for t, _s, _b in merged], ["Dil: Türkçe"])

    def test_lower_score_does_not_replace(self):
        base = [("Dil: Türkçe", 0.97, self._box(10, 10, 200, 30))]
        extra = [("Due ae", 0.52, self._box(11, 11, 199, 29))]
        merged = ocr._merge_lines(base, extra)
        self.assertEqual([t for t, _s, _b in merged], ["Dil: Türkçe"])

    def test_epsilon_higher_score_does_not_replace(self):
        base = [("Genel ayarlar", 0.997, self._box(10, 10, 200, 30))]
        extra = [("Genel ayariar", 0.999, self._box(11, 11, 199, 29))]
        merged = ocr._merge_lines(base, extra)
        self.assertEqual([t for t, _s, _b in merged], ["Genel ayarlar"])

    def test_dense_neighbours_both_survive(self):
        base = [("Tema: Koyu", 1.00, self._box(10, 40, 200, 58)),
                ("Kaynak: mikrofon", 1.00, self._box(300, 40, 520, 58))]
        extra = [("Kaynak: mikrofon", 0.99, self._box(298, 42, 522, 60)),
                 ("Tema: Koyu", 0.98, self._box(12, 70, 198, 88))]
        merged = ocr._merge_lines(base, extra)
        texts = [t for t, _s, _b in merged]
        self.assertIn("Tema: Koyu", texts)
        self.assertIn("Kaynak: mikrofon", texts)
        self.assertEqual(len(texts), 2)

    def test_reading_order_is_top_to_bottom(self):
        base = [("ikinci", 0.99, self._box(10, 60, 200, 78))]
        extra = [("birinci", 0.99, self._box(10, 10, 200, 28))]
        merged = ocr._merge_lines(base, extra)
        self.assertEqual([t for t, _s, _b in merged],
                         ["birinci", "ikinci"])

    def test_exact_dupes_collapse(self):
        base = [("merhaba", 0.90, self._box(10, 10, 200, 30))]
        extra = [("Merhaba", 0.99, self._box(300, 50, 490, 70))]
        merged = ocr._merge_lines(base, extra)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0][1], 0.99)

    def test_near_dupes_on_one_row_collapse(self):
        base = [("Genel ayarlar", 1.00, self._box(10, 40, 200, 58))]
        extra = [("Genel ayariar", 0.93, self._box(12, 42, 198, 60))]
        merged = ocr._merge_lines(base, extra)
        self.assertEqual([t for t, _s, _b in merged], ["Genel ayarlar"])

    def test_short_headers_never_collapse(self):
        base = [("Bölüm 1", 1.00, self._box(10, 10, 120, 28))]
        extra = [("Bölüm 2", 0.99, self._box(300, 10, 410, 28))]
        merged = ocr._merge_lines(base, extra)
        self.assertEqual(len(merged), 2)

    def test_dissimilar_same_row_lines_survive(self):
        base = [("Kısayol: Ctrl+Shift+W", 1.00, self._box(10, 40, 250, 58))]
        extra = [("Kayıt yolu: Belgeler", 0.98, self._box(300, 40, 540, 58))]
        merged = ocr._merge_lines(base, extra)
        self.assertEqual(len(merged), 2)


class TestJunkFilter(unittest.TestCase):
    def _box(self, size):
        import numpy as np
        return np.array([[0, 0], [size, 0], [size, size], [0, size]],
                        dtype=float)

    def test_icon_hallucinations_dropped(self):
        lines = [("□", 0.96, self._box(16)),
                 ("田", 1.00, self._box(16)),
                 ("×", 0.52, self._box(14)),
                 ("Toplantı notları", 0.97, self._box(300))]
        kept = ocr._drop_junk(lines)
        self.assertEqual([t for t, _s, _b in kept], ["Toplantı notları"])

    def test_certain_latin_labels_survive(self):
        lines = [("B", 1.00, self._box(12)),
                 ("I", 1.00, self._box(12)),
                 ("t", 0.69, self._box(10))]
        kept = ocr._drop_junk(lines)
        self.assertEqual([t for t, _s, _b in kept], ["B", "I"])

    def test_japanese_lines_survive(self):
        lines = [("日本語のテスト行です", 0.95, self._box(300)),
                 ("概要を説明します", 0.93, self._box(240))]
        kept = ocr._drop_junk(lines)
        self.assertEqual(len(kept), 2)

    def test_lines_without_boxes_use_score_only(self):
        lines = [("自", 0.67, None),
                 ("gerçek satır burada", 0.99, None)]
        kept = ocr._drop_junk(lines)
        self.assertEqual([t for t, _s, _b in kept],
                         ["gerçek satır burada"])


class TestSecondPassTrigger(unittest.TestCase):
    def _box(self, h):
        import numpy as np
        return np.array([[0, 0], [200, 0], [200, h], [0, h]], dtype=float)

    def test_empty_image_with_room_triggers(self):
        self.assertTrue(ocr._needs_second_pass([], 800, 1000))

    def test_tiny_empty_image_skips(self):
        self.assertFalse(ocr._needs_second_pass([], 20, 30))

    def test_small_glyphs_trigger(self):
        lines = [("satır bir", 0.99, self._box(10)),
                 ("satır iki", 0.99, self._box(10))]
        self.assertTrue(ocr._needs_second_pass(lines, 600, 900))

    def test_shaky_word_triggers(self):
        lines = [("Due ae", 0.52, self._box(20))]
        self.assertTrue(ocr._needs_second_pass(lines, 600, 900))

    def test_clean_tall_read_skips(self):
        lines = [("Temiz satır burada", 0.99, self._box(24)),
                 ("İkinci temiz satır", 0.98, self._box(24))]
        self.assertFalse(ocr._needs_second_pass(lines, 600, 900))


class TestUnavailableGracefully(unittest.TestCase):
    def test_missing_projections_raise_ocr_unavailable(self):
        with mock.patch.object(ocr, "_recognize_rapid",
                               side_effect=ocr.OcrUnavailable("yok")), \
             mock.patch.object(ocr, "_imports",
                               side_effect=ocr.OcrUnavailable("yok")):
            image = QImage(4, 4, QImage.Format.Format_RGB32)
            with self.assertRaises(ocr.OcrUnavailable):
                ocr.extract_text(image, "tr")

    def test_is_available_never_raises(self):
        with mock.patch.object(ocr, "_rapid_ready", return_value=False), \
             mock.patch.object(ocr, "_imports", side_effect=RuntimeError("boom")):
            self.assertFalse(ocr.is_available())

    def test_extract_text_reports_a_clean_failure_when_the_engine_breaks(self):
        broken = mock.Mock()

        async def boom(*_args, **_kwargs):
            raise RuntimeError("WinRT blew up")
        broken.side_effect = lambda *a: boom()
        with mock.patch.object(ocr, "_recognize_rapid",
                               side_effect=ocr.OcrUnavailable("yok")), \
             mock.patch.object(ocr, "_recognize", broken):
            image = QImage(4, 4, QImage.Format.Format_RGB32)
            image.fill(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor("white"))
            with self.assertRaises(ocr.OcrUnavailable):
                ocr.extract_text(image, "tr")

    def test_wiped_bundle_points_at_restart_instead_of_a_missing_engine(self):
        import asset_cache
        broken = mock.Mock()

        async def gone(*_args, **_kwargs):
            raise ocr.OcrUnavailable("Windows OCR is not available on this system")
        broken.side_effect = lambda *a: gone()
        with mock.patch.object(ocr, "_recognize_rapid",
                               side_effect=ocr.OcrUnavailable("RapidOCR stack is gone")), \
             mock.patch.object(ocr, "_recognize", broken), \
             mock.patch.object(asset_cache, "_canary", [True, True, True]), \
             mock.patch("brand.resource_path",
                        return_value=__import__("pathlib").Path("no-such-file")):
            image = QImage(4, 4, QImage.Format.Format_RGB32)
            image.fill(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor("white"))
            with self.assertRaisesRegex(ocr.OcrUnavailable, "restart WordArc"):
                ocr.extract_text(image, "tr")


if __name__ == "__main__":
    unittest.main()
