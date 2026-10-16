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


class TestUnavailableGracefully(unittest.TestCase):
    def test_missing_projections_raise_ocr_unavailable(self):
        with mock.patch.object(ocr, "_imports",
                               side_effect=ocr.OcrUnavailable("yok")):
            image = QImage(4, 4, QImage.Format.Format_RGB32)
            with self.assertRaises(ocr.OcrUnavailable):
                ocr.extract_text(image, "tr")

    def test_is_available_never_raises(self):
        with mock.patch.object(ocr, "_imports", side_effect=RuntimeError("boom")):
            self.assertFalse(ocr.is_available())

    def test_extract_text_reports_a_clean_failure_when_the_engine_breaks(self):
        broken = mock.Mock()

        async def boom(*_args, **_kwargs):
            raise RuntimeError("WinRT blew up")
        broken.side_effect = lambda *a: boom()
        with mock.patch.object(ocr, "_recognize", broken):
            image = QImage(4, 4, QImage.Format.Format_RGB32)
            image.fill(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor("white"))
            with self.assertRaises(ocr.OcrUnavailable):
                ocr.extract_text(image, "tr")


if __name__ == "__main__":
    unittest.main()
