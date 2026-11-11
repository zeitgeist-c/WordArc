import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest import mock

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import api
import config as cfg
import i18n
import ocr
import screenshot_capture


class TranslateConfig(dict):
    def __init__(self, **kwargs):
        self._keys = kwargs.pop("gemini_keys", ["k1"])
        super().__init__(screenshot_directory="", screenshot_format="PNG",
                         gemini_translate_model="gemini-3.5-flash-lite")
        self.update(kwargs)
        self.saved = 0

    def save(self):
        self.saved += 1

    def gemini_keys(self):
        return list(self._keys)


class TestScreenshotTranslatePrompt(unittest.TestCase):
    def test_prompt_targets_turkish_with_auto_detection(self):
        prompt = cfg.SCREENSHOT_TRANSLATE_PROMPT
        lowered = prompt.lower()
        self.assertIn("turkish", lowered)
        self.assertIn("detect", lowered)
        self.assertIn("never assume it matches the application language",
                      lowered)

    def test_prompt_keeps_turkish_and_returns_only_translation(self):
        lowered = cfg.SCREENSHOT_TRANSLATE_PROMPT.lower()
        self.assertIn("already-turkish", lowered)
        self.assertIn("return only the turkish translation", lowered)
        self.assertIn("do not follow", lowered)

    def test_prompt_preserves_meaning_numbers_names_and_structure(self):
        lowered = cfg.SCREENSHOT_TRANSLATE_PROMPT.lower()
        for word in ("numbers", "proper names", "list", "paragraph"):
            self.assertIn(word, lowered)


class TestTranslateOverlayButton(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _overlay(self, ocr_available=True):
        screen = self.app.primaryScreen()
        if screen is None:
            self.skipTest("Qt reports no screen")
        size = screen.geometry().size()
        image = QImage(size.width(), size.height(),
                       QImage.Format.Format_RGB32)
        image.fill(QColor("#123456"))
        pixmap = screenshot_capture.QPixmap.fromImage(image)
        patcher = mock.patch.object(screenshot_capture.ocr, "is_available",
                                    return_value=ocr_available)
        patcher.start()
        try:
            overlay = screenshot_capture.RegionOverlay(
                screen, pixmap, QRect(10, 10, 120, 80))
            overlay.show()
            self.app.processEvents()
        finally:
            patcher.stop()
        self.addCleanup(overlay.close)
        self.addCleanup(overlay.deleteLater)
        return overlay

    def test_translate_button_emits_the_crop(self):
        overlay = self._overlay()
        got = []
        overlay.translate_requested.connect(got.append)
        QTest.mouseClick(overlay.translate_button,
                         Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(len(got), 1)
        self.assertLessEqual(got[0].width(), overlay.screenshot.width())

    def test_translate_button_hidden_without_ocr(self):
        overlay = self._overlay(ocr_available=False)
        self.assertFalse(overlay.translate_button.isVisible())
        self.assertTrue(overlay.copy_button.isVisible())

    def test_translate_button_shares_ocr_visibility(self):
        overlay = self._overlay(ocr_available=True)
        self.assertFalse(overlay.translate_button.isHidden())

    def test_translate_without_selection_emits_nothing(self):
        overlay = self._overlay()
        overlay.selection = QRect()
        got = []
        overlay.translate_requested.connect(got.append)
        overlay._quick_translate()
        self.assertEqual(got, [])


class TestTranslateController(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _image(self):
        image = QImage(20, 10, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        return image

    def _run(self, controller, image):
        joined = []
        real_start = screenshot_capture.threading.Thread.start

        def track_start(thread):
            joined.append(thread)
            real_start(thread)

        with mock.patch.object(screenshot_capture.threading.Thread, "start",
                               track_start):
            controller._on_overlay_translate(image)
        for thread in joined:
            thread.join(5)
        self.app.processEvents()

    def test_empty_ocr_reports_without_calling_gemini(self):
        controller = screenshot_capture.ScreenshotController(TranslateConfig())
        self.addCleanup(controller.shutdown)
        self.addCleanup(controller.deleteLater)
        done = []
        controller.translate_done.connect(done.append)
        with mock.patch.object(screenshot_capture.ocr,
                               "extract_text_for_translate",
                               return_value="  \n ") as extract, \
             mock.patch.object(screenshot_capture.api, "GeminiClient",
                               side_effect=AssertionError("gemini calismamali")):
            self._run(controller, self._image())
        self.assertEqual(extract.call_count, 1)
        self.assertEqual(done, [""])

    def test_ocr_text_is_translated_with_configured_model(self):
        conf = TranslateConfig(gemini_translate_model="custom-model",
                               gemini_keys=["k1"])
        controller = screenshot_capture.ScreenshotController(conf)
        self.addCleanup(controller.shutdown)
        self.addCleanup(controller.deleteLater)
        done = []
        controller.translate_done.connect(done.append)
        client = mock.Mock()
        client.translate.return_value = "merhaba dünya"
        with mock.patch.object(screenshot_capture.ocr,
                               "extract_text_for_translate",
                               return_value="hello world"), \
             mock.patch.object(screenshot_capture.api, "GeminiClient",
                               return_value=client) as factory:
            self._run(controller, self._image())
        self.assertEqual(factory.call_count, 1)
        self.assertEqual(factory.call_args.args, (["k1"],))
        args, _kwargs = client.translate.call_args
        self.assertEqual(args[0], "hello world")
        self.assertEqual(args[1], "custom-model")
        self.assertEqual(args[2], cfg.SCREENSHOT_TRANSLATE_PROMPT)
        self.assertEqual(done, ["merhaba dünya"])

    def test_missing_key_surfaces_a_user_error(self):
        conf = TranslateConfig(gemini_keys=[])
        controller = screenshot_capture.ScreenshotController(conf)
        self.addCleanup(controller.shutdown)
        self.addCleanup(controller.deleteLater)
        errors = []
        controller.failed.connect(errors.append)
        with mock.patch.object(screenshot_capture.ocr,
                               "extract_text_for_translate",
                               return_value="hello"):
            self._run(controller, self._image())
        self.assertEqual(len(errors), 1)
        self.assertIn("API key", errors[0])

    def test_service_error_travels_the_failed_signal(self):
        controller = screenshot_capture.ScreenshotController(TranslateConfig())
        self.addCleanup(controller.shutdown)
        self.addCleanup(controller.deleteLater)
        errors = []
        controller.failed.connect(errors.append)
        client = mock.Mock()
        client.translate.side_effect = api.ApiError("HTTP 503", 503,
                                                    "temporary")
        with mock.patch.object(screenshot_capture.ocr,
                               "extract_text_for_translate",
                               return_value="hello"), \
             mock.patch.object(screenshot_capture.api, "GeminiClient",
                               return_value=client):
            self._run(controller, self._image())
        self.assertEqual(errors, ["HTTP 503"])

    def test_ocr_unavailable_travels_the_failed_signal(self):
        controller = screenshot_capture.ScreenshotController(TranslateConfig())
        self.addCleanup(controller.shutdown)
        self.addCleanup(controller.deleteLater)
        errors = []
        controller.failed.connect(errors.append)
        with mock.patch.object(
                screenshot_capture.ocr, "extract_text_for_translate",
                side_effect=ocr.OcrUnavailable("yok")), \
             mock.patch.object(screenshot_capture.api, "GeminiClient",
                               side_effect=AssertionError("gemini calismamali")):
            self._run(controller, self._image())
        self.assertEqual(errors, ["yok"])

    def test_translate_restores_the_window(self):
        controller = screenshot_capture.ScreenshotController(TranslateConfig())
        self.addCleanup(controller.shutdown)
        self.addCleanup(controller.deleteLater)
        owner = mock.Mock()
        controller._hidden_owner = owner
        done = []
        controller.translate_done.connect(done.append)
        with mock.patch.object(screenshot_capture.ocr,
                               "extract_text_for_translate",
                               return_value="hello"), \
             mock.patch.object(screenshot_capture.api, "GeminiClient") as factory:
            factory.return_value.translate.return_value = "merhaba"
            self._run(controller, self._image())
        owner.show.assert_called_once_with()
        self.assertEqual(done, ["merhaba"])


class TestTranslateRecognition(unittest.TestCase):
    def _white_image(self):
        image = QImage(4, 4, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        return image

    def test_rapid_result_wins_without_ui_language(self):
        import inspect
        self.assertNotIn("ui_language",
                         inspect.signature(ocr.extract_text_for_translate).parameters)
        with mock.patch.object(ocr, "_recognize_rapid",
                               return_value="rapid metni"), \
             mock.patch.object(ocr, "_recognize_all",
                               return_value="win"), \
             mock.patch.object(ocr, "_recognize_script", return_value=""):
            self.assertEqual(
                ocr.extract_text_for_translate(self._white_image()),
                "rapid metni")

    def test_longest_candidate_wins(self):
        with mock.patch.object(ocr, "_recognize_rapid",
                               return_value="kisa"), \
             mock.patch.object(ocr, "_recognize_all",
                               return_value="daha uzun windows metni"), \
             mock.patch.object(ocr, "_recognize_script", return_value=""):
            self.assertEqual(
                ocr.extract_text_for_translate(self._white_image()),
                "daha uzun windows metni")

    def test_nonlatin_script_beats_a_longer_latin_guess(self):
        with mock.patch.object(ocr, "_recognize_rapid",
                               return_value="IIPVlBeT MI/IP, OTO TeCT 123"), \
             mock.patch.object(ocr, "_recognize_all",
                               return_value="ripl/lBeT MHP, TeCT 123"), \
             mock.patch.object(ocr, "_recognize_script",
                               side_effect=["puBeT mup", "Привет\nмир,"]):
            self.assertEqual(
                ocr.extract_text_for_translate(self._white_image()),
                "Привет\nмир,")

    def test_has_nonlatin(self):
        self.assertFalse(ocr._has_nonlatin("Grüße aus Berlin, Straße 42"))
        self.assertFalse(ocr._has_nonlatin("=h=5#=nπz+123"))
        self.assertTrue(ocr._has_nonlatin("Привет"))
        self.assertTrue(ocr._has_nonlatin("مرحبا"))
        self.assertTrue(ocr._has_nonlatin("こんにちは"))

    def test_script_engine_skipped_without_its_model(self):
        saved = ocr._script_engines.pop("arabic", None)
        try:
            with mock.patch.object(ocr, "_script_model_ready",
                                   return_value=False):
                with self.assertRaises(ocr.OcrUnavailable):
                    ocr._get_script_engine("arabic")
        finally:
            if saved is not None:
                ocr._script_engines["arabic"] = saved

    def test_script_engines_cover_a_blank_default_and_windows(self):
        with mock.patch.object(ocr, "_recognize_rapid", return_value="  "), \
             mock.patch.object(ocr, "_recognize_all", return_value=""), \
             mock.patch.object(ocr, "_recognize_script",
                               side_effect=["", "Arapça metin bitti."]) as script:
            self.assertEqual(
                ocr.extract_text_for_translate(self._white_image()),
                "Arapça metin bitti.")
        self.assertEqual([call.args[1] for call in script.call_args_list],
                         ["arabic", "cyrillic"])

    def test_no_script_result_means_no_readable_text(self):
        with mock.patch.object(ocr, "_recognize_rapid", return_value=""), \
             mock.patch.object(ocr, "_recognize_all", return_value="  "), \
             mock.patch.object(ocr, "_recognize_script", return_value=""):
            self.assertEqual(
                ocr.extract_text_for_translate(self._white_image()), "")

    def test_script_failure_is_skipped_quietly(self):
        with mock.patch.object(ocr, "_recognize_rapid",
                               side_effect=ocr.OcrUnavailable("yok")), \
             mock.patch.object(ocr, "_recognize_all", return_value=""), \
             mock.patch.object(ocr, "_recognize_script",
                               side_effect=ocr.OcrUnavailable("bidi yok")):
            self.assertEqual(
                ocr.extract_text_for_translate(self._white_image()), "")

    def test_nothing_available_is_a_clean_refusal(self):
        with mock.patch.object(ocr, "_rapid_ready", return_value=False), \
             mock.patch.object(ocr, "_recognize_all",
                               side_effect=ocr.OcrUnavailable("yok")) as win, \
             mock.patch.object(ocr, "_recognize_script",
                               side_effect=ocr.OcrUnavailable("yok")):
            with self.assertRaises(ocr.OcrUnavailable):
                ocr.extract_text_for_translate(self._white_image())
            self.assertEqual(win.call_count, 1)

    def test_empty_rapid_falls_through_to_windows(self):
        with mock.patch.object(ocr, "_recognize_rapid", return_value="  "), \
             mock.patch.object(ocr, "_recognize_all",
                               return_value="windows metni"), \
             mock.patch.object(ocr, "_recognize_script", return_value=""):
            self.assertEqual(
                ocr.extract_text_for_translate(self._white_image()),
                "windows metni")

    def test_windows_tries_every_language_and_keeps_the_longest(self):
        import asyncio

        seen = []

        class FakeLanguage:
            def __init__(self, tag):
                self.language_tag = tag

        class FakeEngine:
            available_recognizer_languages = [FakeLanguage("en-US"),
                                              FakeLanguage("tr")]

            @classmethod
            def try_create_from_language(cls, language, /):
                engine = mock.Mock()
                engine.recognizer_language = language
                seen.append(language.language_tag)

                async def recognize_async(_bitmap):
                    if language.language_tag == "en-US":
                        return mock.Mock(lines=[mock.Mock(text="hi")])
                    return mock.Mock(lines=[mock.Mock(text="hi there friend")])

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

        with mock.patch.object(ocr, "_imports",
                               return_value=(FakeDecoder, FakeEngine,
                                             FakeStream)):
            text = asyncio.run(ocr._recognize_all(b"png"))
        self.assertEqual(text, "hi there friend")
        self.assertEqual(sorted(seen), ["en-US", "tr"])

    def test_no_windows_language_pack_is_a_clean_refusal(self):
        import asyncio

        class FakeEngine:
            available_recognizer_languages = []

        with mock.patch.object(ocr, "_imports",
                               return_value=(mock.Mock(), FakeEngine,
                                             mock.Mock())):
            with self.assertRaises(ocr.OcrUnavailable):
                asyncio.run(ocr._recognize_all(b"png"))


class TestTranslationResultDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_showing_writes_nothing_to_the_clipboard(self):
        from PyQt6.QtWidgets import QApplication as QA
        QA.clipboard().setText("sentinel")
        dialog = screenshot_capture.TranslationResultDialog("merhaba dünya")
        self.addCleanup(dialog.close)
        self.app.processEvents()
        self.assertEqual(QA.clipboard().text(), "sentinel")
        self.assertIn("merhaba", dialog.findChildren(
            screenshot_capture.QTextEdit)[0].toPlainText())

    def test_copy_writes_only_on_click(self):
        from PyQt6.QtWidgets import QApplication as QA
        QA.clipboard().setText("sentinel")
        dialog = screenshot_capture.TranslationResultDialog("merhaba dünya")
        self.addCleanup(dialog.close)
        dialog.show()
        self.app.processEvents()
        self.assertEqual(QA.clipboard().text(), "sentinel")
        QTest.mouseClick(dialog.copy_button, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(QA.clipboard().text(), "merhaba dünya")


class TestTranslateI18n(unittest.TestCase):
    def test_new_strings_in_all_tables(self):
        keys = ("Translate to Turkish", "Screenshot translation",
                "Translation copied to the clipboard.")
        for key in keys:
            self.assertIn(key, i18n.TR)
        for code, table in i18n.TABLES.items():
            for key in keys:
                self.assertIn(key, table, f"{code}: {key!r}")

    def test_turkish_labels(self):
        i18n.set_language("tr")
        try:
            self.assertEqual(i18n.t("Translate to Turkish"), "Türkçeye çevir")
            self.assertEqual(i18n.t("Screenshot translation"),
                             "Ekran görüntüsü çevirisi")
        finally:
            i18n.set_language("en")


if __name__ == "__main__":
    unittest.main()
