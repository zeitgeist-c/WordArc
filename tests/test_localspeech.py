"""The local speech engine: which engine answers, and what it does with audio.

These run without the real model on disk. The ones that would need a 1.6 GB
download assert the routing, the error message and the settings state instead,
because a test that has to download a gigabyte to check a branch is a test
nobody runs. The model call itself was verified on real Turkish audio, not
here.
"""

import array
import os
import shutil
import tempfile
import unittest
import wave
from unittest import mock

import config as cfg
import localspeech
from i18n import t


def _write_wav(path, seconds=1.0, rate=16000, channels=1, width=2):
    frames = int(seconds * rate)
    samples = array.array("h", [0] * (frames * channels))
    with wave.open(path, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(samples.tobytes())
    return path


class _Conf(dict):
    """Just the keys the bridge reads, so a test cannot drift on a real Config."""

    def gemini_keys(self):
        return list(self.get("keys", []))


class TestModelRegistry(unittest.TestCase):
    def test_the_three_offered_names_are_the_ones_on_disk(self):
        self.assertEqual(localspeech.model_names(),
                         ["base", "small", "large-v3-turbo"])

    def test_every_model_has_a_note_for_the_box(self):
        for name in localspeech.model_names():
            label, note = localspeech.model_label(name)
            self.assertIn(name, label)
            self.assertTrue(note, f"{name} has no note")

    def test_engine_labels_name_a_place_not_a_library(self):
        values = [value for _label, value in localspeech.ENGINES]
        self.assertEqual(sorted(values), ["cloud", "local"])


class TestState(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="wordarc-local-speech-")
        self.addCleanup(shutil.rmtree, self.root, True)

    def _fake_model(self, name, complete=True):
        root = localspeech._root(name, self.root)
        os.makedirs(root, exist_ok=True)
        for part in localspeech.REQUIRED_FILES:
            if complete or part != "model.bin":
                with open(os.path.join(root, part), "wb") as fh:
                    fh.write(b"x" * 16)
        return root

    def test_absent_model_is_not_installed_and_says_how_much(self):
        found = localspeech.state("base", self.root)
        self.assertFalse(found.installed)
        self.assertEqual(found.size, 0)
        self.assertGreater(found.expected, 0)

    def test_a_model_missing_one_file_counts_as_absent(self):
        # The model.bin is the whole weight; without it the engine cannot load,
        # so a directory that has everything else is still not installed.
        self._fake_model("base", complete=False)
        self.assertFalse(localspeech.state("base", self.root).installed)

    def test_a_complete_model_is_installed_and_sized(self):
        self._fake_model("base")
        found = localspeech.state("base", self.root)
        self.assertTrue(found.installed)
        self.assertGreater(found.size, 0)

    def test_unknown_model_is_never_installed(self):
        self.assertFalse(localspeech.state("gpt-4", self.root).installed)

    def test_installed_size_sums_only_what_is_there(self):
        self._fake_model("base")
        self._fake_model("small")
        total = localspeech.installed_size(self.root)
        self.assertEqual(total,
                         localspeech.state("base", self.root).size
                         + localspeech.state("small", self.root).size)

    def test_remove_takes_the_directory_and_says_whether_it_did(self):
        self._fake_model("base")
        self.assertTrue(localspeech.remove("base", self.root))
        self.assertFalse(localspeech.state("base", self.root).installed)
        self.assertFalse(localspeech.remove("base", self.root))

    def test_remove_ignores_a_model_that_was_never_there(self):
        self.assertFalse(localspeech.remove("small", self.root))


class TestEngineErrors(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="wordarc-local-engine-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.addCleanup(self._forget_model)
        localspeech._model = None
        localspeech._model_name = ""

    @staticmethod
    def _forget_model():
        localspeech._model = None
        localspeech._model_name = ""

    def test_loading_a_model_that_is_not_there_says_how_to_get_it(self):
        with self.assertRaises(localspeech.LocalSpeechError) as ctx:
            localspeech.engine("base", self.root)
        self.assertIn(t("Settings"), str(ctx.exception))

    def test_an_unknown_name_is_refused_before_anything_is_loaded(self):
        with self.assertRaises(localspeech.LocalSpeechError):
            localspeech.engine("turbo", self.root)

    def test_an_empty_name_falls_back_to_the_default(self):
        # A config written before the setting existed has no model name; it
        # must not look like a broken model.
        with self.assertRaises(localspeech.LocalSpeechError):
            localspeech.engine("", self.root)


class TestReadWav(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="wordarc-local-wav-")
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_mono_16k_comes_back_as_float32(self):
        path = _write_wav(os.path.join(self.root, "a.wav"), seconds=0.5)
        audio = localspeech._read_wav(path)
        self.assertEqual(audio.shape, (8000,))
        self.assertEqual(str(audio.dtype), "float32")

    def test_a_stereo_file_keeps_one_channel(self):
        # A meeting channel split out of a stereo recording can still arrive
        # two-channel from some paths; the engine wants one.
        path = _write_wav(os.path.join(self.root, "b.wav"), seconds=0.5, channels=2)
        self.assertEqual(localspeech._read_wav(path).shape, (8000,))

    def test_the_wrong_sample_rate_is_refused_with_both_numbers(self):
        path = _write_wav(os.path.join(self.root, "c.wav"), rate=48000)
        with self.assertRaises(localspeech.LocalSpeechError) as ctx:
            localspeech._read_wav(path)
        self.assertIn("48", str(ctx.exception))


class TestRouting(unittest.TestCase):
    """Which engine answers is a setting, and the two must be swappable."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="wordarc-local-route-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.calls = []

    class _Client:
        def __init__(self, calls):
            self.calls = calls

        def transcribe(self, model, path, language="", prompt=""):
            self.calls.append(("cloud", model))
            return "cloud words"

    def test_cloud_is_the_default_and_reaches_the_client(self):
        conf = _Conf({"gemini_transcribe_model": "gemini-x", "keys": ["k"]})
        out = localspeech.transcribe_for(
            conf, _write_wav(os.path.join(self.root, "a.wav")),
            client=self._Client(self.calls))
        self.assertEqual(out, "cloud words")
        self.assertEqual(self.calls, [("cloud", "gemini-x")])

    def test_a_missing_engine_setting_is_treated_as_the_cloud(self):
        # A config written before this setting existed has no such key.
        conf = _Conf({"gemini_transcribe_model": "gemini-x", "keys": ["k"]})
        self.assertNotIn("transcribe_engine", conf)
        localspeech.transcribe_for(
            conf, _write_wav(os.path.join(self.root, "b.wav")),
            client=self._Client(self.calls))
        self.assertEqual(self.calls, [("cloud", "gemini-x")])

    def test_a_local_failure_never_uploads_the_audio(self):
        # Choosing the local engine is the user saying the audio stays here. A
        # key being configured must not turn a local error into a silent upload.
        conf = _Conf({"transcribe_engine": "local", "local_stt_model": "base",
                      "gemini_transcribe_model": "gemini-x", "keys": ["k"]})
        with self.assertRaises(localspeech.LocalSpeechError):
            self._fail(conf, "c.wav")
        self.assertEqual(self.calls, [], "the audio was sent to the cloud")

    def test_a_local_failure_without_a_key_is_reported(self):
        # No key means no fallback: swallowing the error would look like a
        # working dictation that silently produced nothing.
        conf = _Conf({"transcribe_engine": "local", "local_stt_model": "base",
                      "gemini_transcribe_model": "gemini-x", "keys": []})
        with self.assertRaises(localspeech.LocalSpeechError):
            self._fail(conf, "d.wav")

    def _fail(self, conf, name):
        """Ask for a model that is on no disk, wherever the machine's own
        models are. Pinned rather than incidental: a test that only passes
        because the model happens not to be installed stops testing the thing
        it is named after the moment somebody downloads it."""
        elsewhere = os.path.join(self.root, "no-models-here")
        os.makedirs(elsewhere, exist_ok=True)
        with mock.patch.object(localspeech, "models_dir",
                               return_value=elsewhere):
            return localspeech.transcribe_for(
                conf, _write_wav(os.path.join(self.root, name)),
                client=self._Client(self.calls))

    def test_the_cloud_engine_reports_one_entry_for_a_whole_chunk(self):
        # Callers that build a timeline place one entry at the chunk's own
        # offset; the cloud engine has no word times, so that is the contract.
        conf = _Conf({"gemini_transcribe_model": "gemini-x", "keys": ["k"]})
        found = localspeech.transcribe_for(
            conf, _write_wav(os.path.join(self.root, "e.wav")),
            with_segments=True, client=self._Client(self.calls))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0], (0.0, 0.0, "cloud words"))


class TestHumanSize(unittest.TestCase):
    """The size goes in front of a download button, so it is said the way a
    person would say it, in the interface language's decimal comma."""

    def test_gigabytes_are_not_written_as_megabytes(self):
        # The model really is 1.54 GB; writing "1545 MB" next to a box that
        # offers "1,6 GB" reads as two different numbers for one file.
        self.assertEqual(localspeech.human_size(1_620_000_000), "1,5 GB")

    def test_megabytes_round_to_whole(self):
        self.assertEqual(localspeech.human_size(147_882_941), "141 MB")

    def test_nothing_on_disk_says_nothing(self):
        self.assertEqual(localspeech.human_size(0), "")

    def test_every_offered_size_renders(self):
        for name in localspeech.model_names():
            shown = localspeech.human_size(
                localspeech.state(name).expected)
            self.assertTrue(shown, name)
            self.assertTrue(shown.endswith(("MB", "GB")), shown)

    def test_the_box_and_the_status_line_quote_one_number(self):
        # The list says what the download costs and the line under it says the
        # same thing; a user who reads both must not see two figures.
        for name in localspeech.model_names():
            in_box = localspeech.MODEL_NOTES[name].split(", ")[1]
            on_line = localspeech.human_size(localspeech.state(name).expected)
            self.assertEqual(in_box, on_line, name)


class TestSpec(unittest.TestCase):
    """The frozen build is the artifact a user runs, so what it must contain is
    checked here rather than discovered from a 88 MB exe that quietly cannot
    transcribe anything."""

    def test_the_spec_asks_for_the_engine_and_its_runtime(self):
        spec = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "wordarc.spec")
        with open(spec, encoding="utf-8") as fh:
            text = fh.read()
        for module in ("faster_whisper", "ctranslate2", "huggingface_hub",
                       "tokenizers", "av"):
            self.assertIn(f"'{module}'", text, module)

    def test_the_build_environment_can_actually_import_them(self):
        # A hidden import of a package that is not installed produces an exe
        # that starts, shows the settings card, and fails the moment someone
        # presses record. The spec listing the name is not proof.
        try:
            import faster_whisper  # noqa: F401
            import ctranslate2  # noqa: F401
            import huggingface_hub  # noqa: F401
            import tokenizers  # noqa: F401
        except ImportError as exc:
            self.fail(f"faster-whisper is not in the environment that builds "
                      f"the exe: {exc}")


class TestModelFilesOnDisk(unittest.TestCase):


    def test_a_model_whose_tokenizer_is_json_counts_as_installed(self):
        # The turbo repository carries vocabulary.json, not vocabulary.txt.
        # Checking for the .txt alone made a complete download report itself
        # incomplete, wipe itself, and leave the button offering it again
        # forever.
        where = tempfile.mkdtemp(prefix="wa-json-vocab")
        self.addCleanup(shutil.rmtree, where, True)
        root = localspeech._root("large-v3-turbo", where)
        os.makedirs(root)
        for part in ("config.json", "model.bin", "tokenizer.json",
                     "vocabulary.json"):
            with open(os.path.join(root, part), "wb") as fh:
                fh.write(b"x" * 64)
        self.assertTrue(
            localspeech.state("large-v3-turbo", where=where).installed)

    def test_a_model_missing_both_tokenizers_is_not_installed(self):
        where = tempfile.mkdtemp(prefix="wa-no-vocab")
        self.addCleanup(shutil.rmtree, where, True)
        root = localspeech._root("large-v3-turbo", where)
        os.makedirs(root)
        for part in ("config.json", "model.bin", "tokenizer.json"):
            with open(os.path.join(root, part), "wb") as fh:
                fh.write(b"x" * 64)
        self.assertFalse(
            localspeech.state("large-v3-turbo", where=where).installed)

    def test_every_offered_model_carries_a_tokenizer_this_check_accepts(self):
        # The download asks for a fixed list of files; a model whose repository
        # carries none of them finishes and then wipes itself. This is the
        # check that catches a repository that changed its layout.
        # Asking the hub means a network call, so it runs only when asked.
        if not os.environ.get("WA_CHECK_HUB"):
            self.skipTest("set WA_CHECK_HUB=1 to ask the hub about the repos")
        from huggingface_hub import list_repo_files
        for name in localspeech.model_names():
            with self.subTest(model=name):
                carried = set(list_repo_files(localspeech._repo(name)))
                for part in localspeech.REQUIRED_FILES:
                    if part not in localspeech.REQUIRED_ANY:
                        self.assertIn(part, carried, part)
                self.assertTrue(
                    [p for p in carried if p in localspeech.REQUIRED_ANY],
                    f"{name} carries no tokenizer this check accepts")


class TestHistoryNaming(unittest.TestCase):
    def test_the_local_engine_is_named_in_the_history_row(self):
        conf = _Cfg()
        conf["transcribe_engine"] = "local"
        conf["local_stt_model"] = "small"
        self.assertEqual(conf.transcribe_name(), "local:small")

    def test_the_cloud_engine_is_named_as_before(self):
        self.assertEqual(_Cfg().transcribe_name(),
                         cfg.DEFAULTS["gemini_transcribe_model"])


class _Cfg(cfg.Config):
    """Config without the file behind it: these tests never read or write one."""

    def __init__(self):
        self.data = dict(cfg.DEFAULTS)


if __name__ == "__main__":
    unittest.main()
