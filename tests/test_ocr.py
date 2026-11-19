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

    def test_german_ui_skips_english_for_installed_german(self):
        # The reported bug: en-US first in the list won over installed de-DE.
        engine = ocr._pick_engine(FakeEngineClass(["en-US", "de-DE"]), "de")
        self.assertEqual(engine.recognizer_language.language_tag, "de-DE")

    def test_same_language_variant_wins_over_the_fallback(self):
        engine = ocr._pick_engine(FakeEngineClass(["en-US", "de-AT"]), "de")
        self.assertEqual(engine.recognizer_language.language_tag, "de-AT")

    def test_region_and_case_do_not_matter(self):
        engine = ocr._pick_engine(FakeEngineClass(["pt-PT", "en-US"]),
                                  "pt-BR")
        self.assertEqual(engine.recognizer_language.language_tag, "pt-PT")
        engine = ocr._pick_engine(FakeEngineClass(["DE-de"]), "de")
        self.assertEqual(engine.recognizer_language.language_tag, "DE-de")

    def test_missing_pack_falls_back_to_whatever_is_installed(self):
        engine = ocr._pick_engine(FakeEngineClass(["fr-FR"]), "de")
        self.assertEqual(engine.recognizer_language.language_tag, "fr-FR")

    def test_fallback_prefers_en_us_over_en_gb(self):
        # The tags are lowercased before comparing, so the literal has to
        # be lowercase too; otherwise en-GB wins by list order.
        engine = ocr._pick_engine(FakeEngineClass(["en-GB", "en-US"]), "ja")
        self.assertEqual(engine.recognizer_language.language_tag, "en-US")

    def test_uncreatable_engine_is_skipped_for_the_next_pack(self):
        class FlakyEngine(FakeEngineClass):
            @classmethod
            def try_create_from_language(cls, language, /):
                if language.language_tag == "de-DE":
                    return None
                return fake_engine(language.language_tag)

        FlakyEngine.available_recognizer_languages = [FakeLanguage("de-DE"),
                                                      FakeLanguage("en-US")]
        engine = ocr._pick_engine(FlakyEngine, "de")
        self.assertEqual(engine.recognizer_language.language_tag, "en-US")


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
                 ("Tema: Koyu", 0.98, self._box(12, 42, 198, 60))]
        merged = ocr._merge_lines(base, extra)
        texts = [t for t, _s, _b in merged]
        self.assertIn("Tema: Koyu", texts)
        self.assertIn("Kaynak: mikrofon", texts)
        self.assertEqual(len(texts), 2)

    def test_same_word_in_two_places_survives(self):
        # The reported bug: the second pass used to swallow the second
        # "Ayarlar". Two different boxes are two lines, same text or not.
        base = [("Ayarlar", 0.99, self._box(10, 10, 200, 30))]
        extra = [("Ayarlar", 0.98, self._box(10, 120, 200, 140))]
        merged = ocr._merge_lines(base, extra)
        self.assertEqual([t for t, _s, _b in merged],
                         ["Ayarlar", "Ayarlar"])

    def test_adjacent_similar_numbers_survive(self):
        # "Sipariş 12345" and "Sipariş 12346" side by side are neighbours,
        # not a double read: their boxes do not overlap.
        base = [("Sipariş 12345", 1.00, self._box(10, 40, 150, 58))]
        extra = [("Sipariş 12346", 0.99, self._box(160, 40, 300, 58))]
        merged = ocr._merge_lines(base, extra)
        self.assertEqual([t for t, _s, _b in merged],
                         ["Sipariş 12345", "Sipariş 12346"])

    def test_same_line_reread_collapses_to_the_best(self):
        base = [("Ayarlar", 0.90, self._box(10, 10, 200, 30))]
        extra = [("Ayarlar", 0.97, self._box(11, 11, 199, 29))]
        merged = ocr._merge_lines(base, extra)
        self.assertEqual([t for t, _s, _b in merged], ["Ayarlar"])
        self.assertEqual(merged[0][1], 0.97)

    def test_reading_order_is_top_to_bottom(self):
        base = [("ikinci", 0.99, self._box(10, 60, 200, 78))]
        extra = [("birinci", 0.99, self._box(10, 10, 200, 28))]
        merged = ocr._merge_lines(base, extra)
        self.assertEqual([t for t, _s, _b in merged],
                         ["birinci", "ikinci"])

    def test_same_text_at_two_places_is_two_lines(self):
        # Geometry decides, not the text: the same reading in two boxes
        # is two lines.
        base = [("merhaba", 0.90, self._box(10, 10, 200, 30))]
        extra = [("Merhaba", 0.99, self._box(300, 50, 490, 70))]
        merged = ocr._merge_lines(base, extra)
        self.assertEqual(len(merged), 2)

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
                 ("■", 1.00, self._box(16)),
                 ("×", 0.52, self._box(14)),
                 ("Toplantı notları", 0.97, self._box(300))]
        kept = ocr._drop_junk(lines)
        self.assertEqual([t for t, _s, _b in kept], ["Toplantı notları"])

    def test_valid_single_characters_survive(self):
        # Small but real: a CJK day mark, a digit, a percent sign and a
        # capital letter must survive a certain read.
        lines = [("日", 0.99, self._box(12)),
                 ("7", 0.98, self._box(10)),
                 ("%", 0.96, self._box(10)),
                 ("A", 1.00, self._box(10))]
        kept = ocr._drop_junk(lines)
        self.assertEqual([t for t, _s, _b in kept], ["日", "7", "%", "A"])

    def test_symbol_noise_dropped_at_any_score(self):
        lines = [("■", 1.00, self._box(16)),
                 ("●", 0.99, self._box(14)),
                 ("□", 0.90, self._box(16))]
        self.assertEqual(ocr._drop_junk(lines), [])

    def test_shaky_small_read_dropped_whatever_the_script(self):
        lines = [("日", 0.50, self._box(10)),
                 ("A", 0.40, self._box(10))]
        self.assertEqual(ocr._drop_junk(lines), [])

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


class TestTranslationChoice(unittest.TestCase):
    """The translate flow sends the right source text, never a stray mark."""

    def test_stray_foreign_character_loses_to_clean_latin(self):
        self.assertEqual(
            ocr._choose_translation_source([("Sipariş 12345", None),
                                            ("日", None)]),
            "Sipariş 12345")

    def test_confident_single_letter_loses_to_full_foreign_passage(self):
        # Confidence scales coverage, never replaces it: a 0.99 on one
        # letter must not outrank a whole scoreless passage.
        self.assertEqual(
            ocr._choose_translation_source([("A", 0.99),
                                            ("Привет мир", None)]),
            "Привет мир")

    def test_confident_latin_with_cover_beats_scoreless_guess(self):
        # The reverse: comparable coverage plus confidence wins.
        self.assertEqual(
            ocr._choose_translation_source([("Sipariş 12345", 0.95),
                                            ("設定画面の設定", None)]),
            "Sipariş 12345")

    def test_real_nonlatin_passage_beats_longer_latin_guess(self):
        self.assertEqual(
            ocr._choose_translation_source(
                [("IIPVlBeT MI/IP, OTO TeCT 123", None),
                 ("Привет\nмир,", None)]),
            "Привет\nмир,")

    def test_fuller_consistent_read_wins_without_scores(self):
        self.assertEqual(
            ocr._choose_translation_source([("kisa", None),
                                            ("daha uzun windows metni",
                                             None)]),
            "daha uzun windows metni")

    def test_empty_candidates_choose_nothing(self):
        self.assertEqual(ocr._choose_translation_source([]), "")
        self.assertEqual(ocr._choose_translation_source([("  ", None)]), "")

    def test_windows_chooser_ignores_a_stray_char_pack(self):
        import asyncio

        class FakeLanguage:
            def __init__(self, tag):
                self.language_tag = tag

        class FakeEngine:
            available_recognizer_languages = [FakeLanguage("ja"),
                                              FakeLanguage("en-US")]

            @classmethod
            def try_create_from_language(cls, language, /):
                engine = mock.Mock()
                engine.recognizer_language = language

                async def recognize_async(_bitmap):
                    if language.language_tag == "ja":
                        return mock.Mock(lines=[mock.Mock(text="日")])
                    return mock.Mock(
                        lines=[mock.Mock(text="Settings panel")])

                engine.recognize_async = recognize_async
                return engine

        class FakeDecoder:
            async def get_software_bitmap_async(self):
                return "bitmap"

            @staticmethod
            async def create_async(_stream):
                return FakeDecoder()

        class FakeStream:
            async def write_async(self, _data):
                return None

            def seek(self, _pos):
                pass

        with mock.patch.object(
                ocr, "_imports",
                return_value=(FakeDecoder, FakeEngine, FakeStream)):
            self.assertEqual(asyncio.run(ocr._recognize_all(b"png")),
                             "Settings panel")


class TestExtractFallback(unittest.TestCase):
    """RapidOCR empty is a missed read (try Windows), not a verdict."""

    def _white_image(self):
        from PyQt6.QtGui import QColor
        image = QImage(4, 4, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        return image

    def test_empty_rapid_falls_through_to_windows(self):
        windows = mock.AsyncMock(return_value="windows metni")
        with mock.patch.object(ocr, "_recognize_rapid", return_value="  "), \
             mock.patch.object(ocr, "_recognize", windows):
            self.assertEqual(
                ocr.extract_text(self._white_image(), "tr"), "windows metni")
        self.assertEqual(windows.call_count, 1)

    def test_empty_rapid_and_empty_windows_means_no_text(self):
        windows = mock.AsyncMock(return_value="")
        with mock.patch.object(ocr, "_recognize_rapid", return_value=""), \
             mock.patch.object(ocr, "_recognize", windows):
            self.assertEqual(ocr.extract_text(self._white_image(), "tr"),
                             "")

    def test_empty_rapid_with_missing_windows_means_no_text(self):
        with mock.patch.object(ocr, "_recognize_rapid", return_value=""), \
             mock.patch.object(ocr, "_recognize",
                               side_effect=ocr.OcrUnavailable("yok")):
            self.assertEqual(ocr.extract_text(self._white_image(), "tr"),
                             "")


class TestEnginePackLogging(unittest.TestCase):
    def test_pick_logs_the_installed_pack_it_uses(self):
        with self.assertLogs("wordarc.ocr", level="INFO") as captured:
            ocr._pick_engine(FakeEngineClass(["en-US", "tr"]), "tr")
        self.assertTrue(any("tr" in line and "2 installed" in line
                            for line in captured.output))


class TestTiling(unittest.TestCase):
    """Very wide captures are read in overlapping tiles, never squeezed."""

    def _stub_engine(self, calls):
        import numpy as np

        def read(image):
            calls.append(image.shape[1])
            _h, w = image.shape[:2]
            result = mock.Mock()
            result.txts = ["kısım"]
            result.boxes = np.array([[[0, 0], [w, 0], [w, 20], [0, 20]]],
                                    dtype=float)
            result.scores = [0.9]
            return result

        return read

    def test_tile_spans_cover_with_overlap(self):
        self.assertEqual(ocr._tile_spans(3840, 1920, 480),
                         [(0, 1920), (1440, 3360), (2880, 3840)])
        self.assertEqual(ocr._tile_spans(1000, 1920, 480), [(0, 1000)])

    def test_wide_image_read_per_tile_with_offset_boxes(self):
        import numpy as np
        calls = []
        image = np.zeros((60, 3840, 3), dtype=np.uint8)
        lines = ocr._recognize_multipass(self._stub_engine(calls), image)
        self.assertEqual(len(calls), 3)
        self.assertEqual([t for t, _s, _b in lines], ["kısım"] * 3)
        lefts = sorted(ocr._bbox(bb)[0] for _t, _s, bb in lines)
        self.assertEqual(lefts, [0, 1440, 2880])

    def test_narrow_image_keeps_the_single_fast_path(self):
        import numpy as np
        calls = []
        image = np.zeros((60, 1000, 3), dtype=np.uint8)
        lines = ocr._recognize_multipass(self._stub_engine(calls), image)
        self.assertEqual(len(calls), 1)
        self.assertEqual([t for t, _s, _b in lines], ["kısım"])

    def test_seam_split_line_stitches_once(self):
        import numpy as np

        def box(x0, y0, x1, y1):
            return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                            dtype=float)

        head = ("A long line starts here and continues", 0.9,
                box(0, 10, 1900, 30))
        repeated = (head[0], head[1], box(0, 0, 400, 8))
        tail = ("here and continues past the boundary", 0.88,
                box(1500, 12, 3400, 32))
        done, carry = ocr._stitch_pair([repeated, head], [tail])
        self.assertEqual(len(done), 1)
        self.assertIs(done[0], repeated)
        self.assertEqual(len(carry), 1)
        self.assertEqual(carry[0][0],
                         "A long line starts here and continues "
                         "past the boundary")
        x0, _y0, x1, _y1 = ocr._bbox(carry[0][2])
        self.assertEqual((x0, x1), (0, 3400))

    def test_columns_neighbour_rows_and_repeats_survive(self):
        import numpy as np

        def box(x0, y0, x1, y1):
            return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                            dtype=float)

        left = [("Toplam 20 geldi", 0.9, box(0, 10, 900, 30)),
                ("Toplam 20", 0.9, box(0, 50, 400, 70)),
                ("Ayarlar", 0.9, box(0, 100, 300, 120))]
        right = [("Toplam 20 gitti", 0.9, box(1000, 10, 1900, 30)),
                 ("Toplam 20", 0.9, box(420, 50, 820, 70)),
                 ("Ayarlar", 0.88, box(2000, 100, 2300, 120))]
        done, carry = ocr._stitch_pair(left, right)
        self.assertEqual(len(done) + len(carry), 6)

    def test_same_tile_boxes_never_stitch_through_tiled_path(self):
        # Repro: two boxes from the SAME tile, one row, 6 px apart, with
        # shared words ("Flights to San Francisco" / "San Francisco
        # weather") used to fuse into one line. Through _recognize_tiled
        # they stay two lines: provenance limits fusing to neighbours.
        import numpy as np

        def box(x0, y0, x1, y1):
            return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                            dtype=float)

        first = ("Flights to San Francisco", 0.9, box(100, 40, 700, 64))
        second = ("San Francisco weather", 0.9, box(706, 40, 1200, 64))
        calls = []

        def read(image):
            result = mock.Mock()
            if image.shape[1] > 2000:
                self.fail("tiles must stay under the wide-image gate")
            calls.append(1)
            if len(calls) == 1:
                result.txts = [first[0], second[0]]
                result.boxes = np.array([first[2], second[2]])
                result.scores = [0.9, 0.9]
            else:
                result.txts = []
                result.boxes = np.zeros((0, 4, 2))
                result.scores = []
            return result

        image = np.zeros((80, 2100, 3), dtype=np.uint8)
        lines = ocr._recognize_tiled(read, image)
        self.assertEqual([t for t, _s, _b in lines],
                         ["Flights to San Francisco",
                          "San Francisco weather"])


if __name__ == "__main__":
    unittest.main()
