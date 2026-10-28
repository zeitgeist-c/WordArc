"""Tests for local Turkish text-to-speech (EMA Lightning ONNX, no torch)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib
import tempfile
import unittest
import wave
from unittest import mock

import numpy as np
import pytest

import config as cfg
import tts_ema


class TestChunk(unittest.TestCase):
    def test_short_text_stays_one_piece(self):
        pieces = tts_ema.chunk("Merhaba dünya.")
        self.assertEqual(len(pieces), 1)
        self.assertEqual(pieces[0][1], 0.0)

    def test_long_text_splits_at_sentence(self):
        text = " ".join(f"Bu {i}. cümle bitiyor." for i in range(30))
        pieces = tts_ema.chunk(text)
        self.assertGreater(len(pieces), 1)
        for piece, _pause in pieces:
            self.assertTrue(piece.rstrip().endswith((".", "!", "?")))

    def test_empty_text_gives_no_pieces(self):
        self.assertEqual(tts_ema.chunk("   "), [])

    def test_finish_adds_period(self):
        self.assertEqual(tts_ema._finish("yarım cümle"), "yarım cümle.")
        self.assertEqual(tts_ema._finish("tamam!"), "tamam!")


class TestPlan(unittest.TestCase):
    def _piece_inputs(self, text="merhaba dünya."):
        vocab = sorted(set(text))
        stoi = {ch: i for i, ch in enumerate(vocab)}
        ids = np.array([stoi[ch] for ch in text], dtype=np.int64)
        starts = [i for i, ch in enumerate(text)
                  if ch != " " and (i == 0 or text[i - 1] == " ")] or [0]
        bounds = [0] + starts[1:] + [len(text)]
        cw, wstart = [], []
        for w, (a, b) in enumerate(zip(bounds, bounds[1:])):
            cw += [w] * (b - a)
            wstart += [a] * (b - a)
        dur = np.full(len(ids), 6.0, dtype=np.float32)
        return ids, np.array(cw), np.array(wstart), dur

    def test_frame_counts_match(self):
        ids, cw, wstart, dur = self._piece_inputs()
        fw, cg, fg, length = tts_ema.plan(ids, cw, wstart, dur)
        self.assertEqual(length, len(ids))
        self.assertEqual(len(cg), len(ids))  # per-letter positions
        self.assertEqual(len(fg), len(fw))  # per-frame positions
        self.assertGreater(len(fw), 0)

    def test_speed_shortens(self):
        ids, cw, wstart, dur = self._piece_inputs()
        slow = tts_ema.plan(ids, cw, wstart, dur, speed=1.0)[0]
        fast = tts_ema.plan(ids, cw, wstart, dur, speed=2.0)[0]
        self.assertLess(len(fast), len(slow))

    def test_windows_cover_frames(self):
        spans = tts_ema.windows(250)
        self.assertEqual(spans[0][0], 0)
        self.assertEqual(spans[-1][1], 250)
        for (a, b), (c, d) in zip(spans, spans[1:]):
            self.assertEqual(b, c)


class TestFrontend(unittest.TestCase):
    def test_alphabet_lowercases_turkish(self):
        fe = tts_ema.Frontend(list("abcçdefgğhıijklmnoöprsştuüvyz "))
        out = fe.alphabet("İSTANBUL'DA Çağdaş")
        self.assertNotIn("İ", out)
        self.assertIn("ğ", out)

    def test_empty_stays_empty(self):
        fe = tts_ema.Frontend([" "])
        self.assertEqual(fe("   "), "")


class TestFiles(unittest.TestCase):
    def test_save_wav_roundtrip(self):
        audio = (np.sin(np.linspace(0, 20, 4800)) * 0.5).astype(np.float32)
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "x.wav"
            tts_ema.save_wav(audio, path)
            with wave.open(str(path), "rb") as fh:
                self.assertEqual(fh.getnchannels(), 1)
                self.assertEqual(fh.getframerate(), 48000)
                self.assertEqual(fh.getnframes(), 4800)

    def test_models_ready_needs_all_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.assertFalse(tts_ema.models_ready(root))
            for name in tts_ema.FILES:
                (root / name).write_bytes(b"x")
            self.assertTrue(tts_ema.models_ready(root))

    def test_resolve_prefers_bundled_weights(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundled = pathlib.Path(tmp) / "bundled"
            bundled.mkdir()
            for name in tts_ema.FILES:
                (bundled / name).write_bytes(b"x")
            with mock.patch.object(tts_ema, "bundled_models_dir",
                                   return_value=bundled):
                self.assertEqual(tts_ema.resolve_models(), bundled)

    def test_resolve_falls_back_to_data_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(tts_ema, "bundled_models_dir",
                                   return_value=pathlib.Path(tmp) / "empty"):
                self.assertEqual(tts_ema.resolve_models(),
                                 tts_ema.models_dir())

    def test_ensure_uses_bundled_without_downloading(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundled = pathlib.Path(tmp) / "bundled"
            bundled.mkdir()
            for name in tts_ema.FILES:
                (bundled / name).write_bytes(b"x")
            with mock.patch.object(tts_ema, "bundled_models_dir",
                                   return_value=bundled), \
                 mock.patch.object(tts_ema, "snapshot_download",
                                   side_effect=AssertionError("must not download")):
                self.assertEqual(tts_ema.ensure_models(), bundled)

    def test_config_defaults(self):
        for key in ("tts_format", "tts_speed", "tts_autoplay",
                    "tts_shortcut", "tts_stop_shortcut", "tts_last_dir"):
            self.assertIn(key, cfg.DEFAULTS)


class TestPlaybackWatchdog(unittest.TestCase):
    def _fake_sd(self, stall=True):
        import sys
        import types
        fake = types.ModuleType("sounddevice")

        class CallbackStop(Exception):
            pass

        class FakeStream:
            def __init__(self, **kwargs):
                self.callback = kwargs.get("callback")
                self._active = True
                self.aborted = False

            @property
            def active(self):
                return self._active

            def start(self):
                if not stall:
                    self._active = False

            def abort(self):
                self.aborted = True
                self._active = False

            def stop(self):
                self._active = False

            def close(self):
                pass

        fake.CallbackStop = CallbackStop
        fake.OutputStream = FakeStream
        return fake

    def test_stalled_device_raises_timeout_and_frees(self):
        import sys
        import threading
        import time
        import numpy as np
        fake = self._fake_sd(stall=True)
        old = sys.modules.get("sounddevice")
        sys.modules["sounddevice"] = fake
        try:
            stop = threading.Event()
            errors = []
            thread = threading.Thread(
                target=lambda: errors.append(self._run_play(stop)),
                daemon=True)
            thread.start()
            thread.join(10)
            self.assertFalse(thread.is_alive())
            self.assertIsInstance(errors[0], TimeoutError)
        finally:
            if old is None:
                del sys.modules["sounddevice"]
            else:
                sys.modules["sounddevice"] = old

    def _run_play(self, stop):
        import numpy as np
        try:
            tts_ema._play_pcm(np.zeros(4800, dtype=np.float32), stop,
                              timeout=0.3)
            return None
        except Exception as exc:
            return exc

    def test_stop_aborts_playback_immediately(self):
        import sys
        import threading
        import time
        fake = self._fake_sd(stall=True)
        old = sys.modules.get("sounddevice")
        sys.modules["sounddevice"] = fake
        try:
            stop = threading.Event()
            errors = []
            thread = threading.Thread(
                target=lambda: errors.append(self._run_play_long(stop)),
                daemon=True)
            thread.start()
            time.sleep(0.2)
            stop.set()  # the Durdur button
            thread.join(10)
            self.assertFalse(thread.is_alive())
            self.assertIsInstance(errors[0], InterruptedError)
        finally:
            if old is None:
                del sys.modules["sounddevice"]
            else:
                sys.modules["sounddevice"] = old

    def _run_play_long(self, stop):
        import numpy as np
        try:
            tts_ema._play_pcm(np.zeros(48000, dtype=np.float32), stop,
                              timeout=30)
            return None
        except Exception as exc:
            return exc

    def test_healthy_device_plays_through(self):
        import sys
        import threading
        fake = self._fake_sd(stall=False)
        old = sys.modules.get("sounddevice")
        sys.modules["sounddevice"] = fake
        try:
            import numpy as np
            tts_ema._play_pcm(np.zeros(4800, dtype=np.float32),
                              threading.Event(), timeout=5)
        finally:
            if old is None:
                del sys.modules["sounddevice"]
            else:
                sys.modules["sounddevice"] = old


class TestSilentProgress(unittest.TestCase):
    def test_never_touches_stderr(self):
        import sys
        old = sys.stderr
        sys.stderr = None
        try:
            bar = tts_ema._SilentProgress(desc="x", total=10, initial=2)
            with bar as active:
                active.update(3)
                active.update_transfer(3)
                active.set_postfix_str("…")
                active.set_description_str("…")
                active.refresh()
                self.assertEqual(active.n, 5)
                self.assertEqual(active.total, 10)
                active.close()
        finally:
            sys.stderr = old

    def test_download_uses_silent_bar(self):
        import pathlib
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for name in tts_ema.FILES:
                (root / name).write_bytes(b"x")
            with mock.patch.object(tts_ema, "models_dir",
                                   return_value=root), \
                 mock.patch.object(tts_ema, "snapshot_download") as dl:
                # Fresh check: remove one file so download triggers.
                list(root.glob("*"))[0].unlink()
                with self.assertRaises(RuntimeError):
                    # models_ready False after download mock → failure path,
                    # but tqdm_class must have been passed silently.
                    tts_ema.ensure_models()
                self.assertIs(dl.call_args.kwargs["tqdm_class"],
                              tts_ema._SilentProgress)


class TestSpeakTab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        import settings_ui
        self.patchers = [
            mock.patch.object(cfg, "CONFIG_DIR", root / "cfg"),
            mock.patch.object(cfg, "CONFIG_FILE", root / "cfg" / "config.json"),
            mock.patch.object(cfg, "DATA_DIR", root / "data"),
            mock.patch.object(cfg, "HISTORY_FILE", root / "data" / "history.jsonl"),
            mock.patch.object(cfg, "MEETINGS_DIR", root / "data" / "meetings"),
            mock.patch.object(cfg, "MEETINGS_FILE", root / "data" / "meetings.jsonl"),
            mock.patch.object(cfg.credential_store, "read", return_value=""),
            mock.patch.object(cfg.credential_store, "read_all", return_value=[]),
            mock.patch.object(cfg.credential_store, "write_all"),
            mock.patch.object(settings_ui.audio, "list_sources", return_value=[]),
            mock.patch.object(settings_ui.audio, "refresh_devices"),
            mock.patch.object(settings_ui.audio, "list_monitors", return_value=[]),
            mock.patch.object(settings_ui.startup, "is_enabled", return_value=False),
            mock.patch.object(settings_ui.localspeech.vulkan_speech, "available",
                              return_value=False),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self._stop_patchers)
        self.window = settings_ui.SettingsWindow(cfg.Config(), "wordarc toggle")
        self.window.show()

    def _stop_patchers(self):
        for patcher in self.patchers:
            patcher.stop()

    def test_speak_tab_registered(self):
        self.assertTrue(self.window.navigate_to("speak"))
        self.assertEqual(self.window.speak_input.toPlainText(), "")

    def test_settings_card_loads(self):
        self.assertEqual(self.window.tts_format.currentData(), "opus")
        self.assertFalse(self.window.tts_autoplay.isChecked())
        self.assertIn("34 MB", self.window.tts_status.text())

    def test_empty_text_refuses(self):
        self.window.navigate_to("speak")
        self.window.speak_input.setPlainText("   ")
        self.window._run_speak()
        self.assertIn("readable", self.window.speak_status.text())

    def test_add_files_skips_duplicates(self):
        self.window.navigate_to("speak")
        with mock.patch("settings_ui.QFileDialog.getOpenFileNames",
                        return_value=(["C:/x/notlar.txt", "C:/x/notlar.txt"], "")):
            self.window._add_speak_files()
        self.assertEqual(self.window.speak_files.count(), 1)

    def test_convert_empty_list_refuses(self):
        self.window.navigate_to("speak")
        self.window.speak_files.clear()
        self.window._convert_speak_files()
        self.assertIn("readable", self.window.speak_status.text())


class TestReadTextFile(unittest.TestCase):
    def test_txt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "a.txt"
            path.write_text("Merhaba   dünya.\nİkinci satır.", encoding="utf-8")
            self.assertEqual(tts_ema.read_text_file(path),
                             "Merhaba dünya. İkinci satır.")

    def test_markdown_strips_formatting(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "a.md"
            path.write_text("# Başlık\n\n- madde bir\n\n```kod()\n```\n",
                            encoding="utf-8")
            text = tts_ema.read_text_file(path)
            self.assertIn("Başlık", text)
            self.assertIn("madde bir", text)
            self.assertNotIn("```", text)
            self.assertNotIn("#", text)

    def test_pdf(self):
        fitz = pytest.importorskip("fitz")
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "a.pdf"
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 72), "Merhaba PDF dünyası.")
            doc.save(path)
            doc.close()
            self.assertIn("Merhaba PDF", tts_ema.read_text_file(path))

    def test_unsupported_and_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = pathlib.Path(tmp) / "a.docx"
            bad.write_bytes(b"x")
            with self.assertRaises(ValueError):
                tts_ema.read_text_file(bad)
            empty = pathlib.Path(tmp) / "b.txt"
            empty.write_text("   ", encoding="utf-8")
            with self.assertRaises(ValueError):
                tts_ema.read_text_file(empty)


class TestConvertFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_converts_each_file_to_wav(self):
        import time
        from PyQt6.QtCore import Qt
        direct = Qt.ConnectionType.DirectConnection

        class FakeEngine:
            def synthesize(self, text, speed=1.0, stop=None, progress=None):
                if progress:
                    progress("…")
                return np.zeros(4800, dtype=np.float32)

        worker = tts_ema.TtsWorker(engine=FakeEngine())
        done, failed = [], []
        worker.finished.connect(done.append, direct)
        worker.failed.connect(failed.append, direct)
        with tempfile.TemporaryDirectory() as tmp:
            first = pathlib.Path(tmp) / "bir.txt"
            first.write_text("Birinci metin.", encoding="utf-8")
            second = pathlib.Path(tmp) / "iki.md"
            second.write_text("İkinci metin.", encoding="utf-8")
            out = pathlib.Path(tmp) / "out"
            worker.convert_files([str(first), str(second)], str(out), fmt="wav")
            deadline = time.time() + 30
            while len(done) < 2 and time.time() < deadline:
                time.sleep(0.05)
            self.assertEqual(failed, [])
            self.assertEqual(len(done), 2)
            self.assertTrue((out / "bir.wav").is_file())
            self.assertTrue((out / "iki.wav").is_file())


if __name__ == "__main__":
    unittest.main()
