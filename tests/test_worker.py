"""The temporary recording is never destroyed when the user asked to keep it."""

import pathlib
import tempfile
from unittest import mock

import config as cfg
import worker


def _pipeline(keep_audio):
    conf = cfg.Config()
    conf.data["keep_audio"] = keep_audio
    return worker.Pipeline(conf)


def _temp_wav(directory):
    wav = pathlib.Path(directory) / "wordarc-test.wav"
    wav.write_bytes(b"RIFF")
    return wav


def test_keep_audio_keeps_the_recording_when_it_cannot_be_filed_away(caplog):
    pipeline = _pipeline(True)
    with tempfile.TemporaryDirectory() as tmp:
        wav = _temp_wav(tmp)
        with mock.patch.object(worker.shutil, "move",
                               side_effect=OSError("disk full")), \
             mock.patch.object(worker.cfg, "RECORDINGS_DIR",
                               pathlib.Path(tmp) / "recordings"):
            with caplog.at_level("WARNING", logger="wordarc.worker"):
                pipeline._discard(str(wav))
        assert wav.exists(), "kayıt silinmemeliydi"
        assert any("could not file the recording away" in record.message
                   for record in caplog.records), "sessiz kalmamalı"


def test_keep_audio_files_the_recording_away():
    pipeline = _pipeline(True)
    with tempfile.TemporaryDirectory() as tmp:
        wav = _temp_wav(tmp)
        target = pathlib.Path(tmp) / "recordings"
        with mock.patch.object(worker.cfg, "RECORDINGS_DIR", target):
            pipeline._discard(str(wav))
        assert not wav.exists()
        assert len(list(target.glob("*.wav"))) == 1


def test_discard_removes_the_temporary_recording_by_default():
    pipeline = _pipeline(False)
    with tempfile.TemporaryDirectory() as tmp:
        wav = _temp_wav(tmp)
        pipeline._discard(str(wav))
        assert not wav.exists()


def _dictation_conf(**overrides):
    conf = cfg.Config()
    conf.data.update({"skip_silent": False, "filter_hallucinations": False,
                      "cleanup_enabled": True, "translate_enabled": False,
                      "history_enabled": False,
                      "keep_audio": False, "auto_paste": True,
                      # Sıra durumu gerçek kullanıcı ayarından sızmamalı.
                      "gemini_next_slot": 0, "gemini_last_used": []})
    conf.data.update(overrides)
    return conf


def _run_dictation(conf, keys, transcribe_return="raw words",
                   transcribe_effect=None, cleanup_return="clean words"):
    """Run pipeline._work with a capturing GeminiClient factory.

    Returns (created, client, finished, failures); created holds the keys and
    kwargs the pipeline built its client with.
    """
    pipeline = worker.Pipeline(conf)
    finished, failures = [], []
    pipeline.finished.connect(lambda *args: finished.append(args))
    pipeline.failed.connect(lambda message, _op: failures.append(message))
    created = {}
    client = mock.Mock()
    client.cleanup.return_value = cleanup_return
    transcribe = (mock.Mock(side_effect=transcribe_effect)
                  if transcribe_effect is not None
                  else mock.Mock(return_value=transcribe_return))
    def factory(api_keys, **kwargs):
        created.update(keys=list(api_keys), kwargs=kwargs)
        client.active_slot = kwargs.get("start_slot", 0)
        return client
    with mock.patch.object(worker.localspeech, "transcribe_for", transcribe), \
         mock.patch.object(worker.api, "GeminiClient", side_effect=factory), \
         mock.patch.object(cfg.Config, "gemini_keys", return_value=list(keys)), \
         mock.patch.object(cfg.Config, "save"), \
         mock.patch.object(worker.paste, "copy"), \
         mock.patch.object(worker.paste, "press"):
        pipeline._work("no-such-recording.wav", 1.0, [], "op-rot", auto_paste=True)
    return created, client, finished, failures


def test_successful_dictation_starts_at_claimed_slot_and_advances():
    conf = _dictation_conf()
    conf.data["gemini_next_slot"] = 1
    created, _client, finished, failures = _run_dictation(conf, ["k1", "k2"])
    assert created["kwargs"]["start_slot"] == 1
    assert len(finished) == 1 and not failures
    assert conf["gemini_next_slot"] == 0
    assert conf["gemini_last_used"][0] == ""
    assert conf["gemini_last_used"][1] != "", "başarılı işlem damga yazmalı"


def test_failed_dictation_advances_without_a_stamp():
    conf = _dictation_conf()
    created, _client, finished, failures = _run_dictation(
        conf, ["k1", "k2"],
        transcribe_effect=worker.api.ApiError("busy", 429, "temporary"))
    assert not finished and failures, "hata kullanıcıya ulaşmalı"
    assert conf["gemini_next_slot"] == 1
    assert conf["gemini_last_used"] == ["", ""], "başarısız deneme damga yazmamalı"


def test_local_dictation_without_cleanup_leaves_rotation_alone():
    conf = _dictation_conf(transcribe_engine="local", cleanup_enabled=False)
    created, _client, finished, failures = _run_dictation(conf, ["k1", "k2"])
    assert len(finished) == 1 and not failures
    assert created["kwargs"]["start_slot"] == 0
    assert conf["gemini_next_slot"] == 0
    assert conf["gemini_last_used"] == [], "bulut kullanılmadı, sıra oynamamalı"


def test_local_dictation_with_cleanup_rotates_the_cleanup_api():
    """Local transcribe uses no API, but cleanup still calls Gemini."""
    conf = _dictation_conf(transcribe_engine="local", cleanup_enabled=True)
    created, _client, finished, failures = _run_dictation(conf, ["k1", "k2"])
    assert len(finished) == 1 and not failures
    assert created["kwargs"]["start_slot"] == 0
    assert conf["gemini_next_slot"] == 1
    assert conf["gemini_last_used"][0] != ""


def test_noise_only_cleanup_does_not_paste_or_change_the_clipboard():
    conf = _dictation_conf()
    pipeline = worker.Pipeline(conf)
    client = mock.Mock(active_slot=0)
    client.cleanup.return_value = ""
    finished, failures = [], []
    pipeline.finished.connect(lambda *args: finished.append(args))
    pipeline.failed.connect(lambda *args: failures.append(args))
    with mock.patch.object(worker.localspeech, "transcribe_for", return_value="eee"), \
         mock.patch.object(worker.api, "GeminiClient", return_value=client), \
         mock.patch.object(cfg.Config, "gemini_keys", return_value=["key"]), \
         mock.patch.object(cfg.Config, "save"), \
         mock.patch.object(worker.paste, "copy") as copy, \
         mock.patch.object(worker.paste, "press") as press:
        pipeline._work("no-such-recording.wav", 1.0, [], "op-empty", auto_paste=True)
    assert client.cleanup.call_args.kwargs["allow_empty"] is True
    assert not finished and failures
    copy.assert_not_called()
    press.assert_not_called()


def test_stages_log_their_durations(caplog):
    conf = _dictation_conf()
    with caplog.at_level("INFO", logger="wordarc.worker"):
        _created, _client, finished, _failures = _run_dictation(conf, ["k1"])
    assert len(finished) == 1
    messages = [record.message for record in caplog.records]
    assert any(message.startswith("transcribe took") for message in messages), messages
    assert any(message.startswith("cleanup took") for message in messages), messages


def test_fallback_stage_names_the_failing_slot():
    """Rotasyonda 'Default API' yalan söyler; mesaj giden slotu adıyla söyler."""
    import i18n
    old_lang = i18n.language()
    conf = _dictation_conf()
    # Config() dili saklanan ui_language'e sıfırlar; test dilini sonra kur.
    i18n.set_language("en")
    try:
        pipeline = worker.Pipeline(conf)
        stages = []
        pipeline.stage.connect(lambda message, _op: stages.append(message))
        client = mock.Mock()
        client.cleanup.return_value = "clean words"
        def factory(api_keys, **kwargs):
            client.active_slot = kwargs.get("start_slot", 0)
            if kwargs.get("on_fallback") is not None:
                kwargs["on_fallback"](
                    2, worker.api.ApiError("busy", 429, "temporary"),
                    failed=1)
            return client
        with mock.patch.object(worker.localspeech, "transcribe_for",
                               return_value="raw words"), \
             mock.patch.object(worker.api, "GeminiClient",
                               side_effect=factory), \
             mock.patch.object(cfg.Config, "gemini_keys",
                               return_value=["k1", "k2"]), \
             mock.patch.object(cfg.Config, "save"), \
             mock.patch.object(worker.paste, "copy"), \
             mock.patch.object(worker.paste, "press"):
            pipeline._work("no-such-recording.wav", 1.0, [], "op-fb",
                           auto_paste=True)
    finally:
        i18n.set_language(old_lang)
    assert "API 1 did not respond; trying API 2..." in stages, stages


def test_a_stop_during_cleanup_is_not_a_cleanup_failure():
    """Cancelled is an ApiError.

    Caught as one, a stop that landed during the cleanup request was reported
    as a cleanup failure and the run went on to paste the raw text: the user
    asked for it to stop and it kept going.
    """
    pipeline = worker.Pipeline(_dictation_conf())
    seen = {"cancelled": 0, "finished": 0}
    pipeline.cancelled.connect(lambda *_: seen.update(
        cancelled=seen["cancelled"] + 1))
    pipeline.finished.connect(lambda *_: seen.update(
        finished=seen["finished"] + 1))
    client = mock.Mock()
    client.cleanup.side_effect = worker.api.Cancelled("Stopped.")

    with mock.patch.object(worker.localspeech, "transcribe_for",
                           return_value="raw words"), \
         mock.patch.object(worker.api, "GeminiClient", return_value=client), \
         mock.patch.object(worker.paste, "copy") as copied, \
         mock.patch.object(worker.paste, "press") as pressed:
        pipeline._work("no-such-recording.wav", 1.0, [], "op-1", auto_paste=True)

    assert seen["cancelled"] == 1
    assert seen["finished"] == 0, "iptal edilen dikte yapıştırılmamalı"
    copied.assert_not_called()
    pressed.assert_not_called()


def test_a_failed_paste_puts_the_clipboard_back():
    """The restore used to sit after the keystroke: when press() raised, the
    user's own clipboard was gone for good."""
    pipeline = worker.Pipeline(_dictation_conf(restore_clipboard=True))
    failures = []
    pipeline.failed.connect(lambda message, _op: failures.append(message))

    with mock.patch.object(worker.localspeech, "transcribe_for",
                           return_value="raw words"), \
         mock.patch.object(worker.api, "GeminiClient", return_value=mock.Mock()), \
         mock.patch.object(worker.paste, "read_clipboard",
                           return_value=b"onceki icerik"), \
         mock.patch.object(worker.paste, "copy"), \
         mock.patch.object(worker.paste, "copy_bytes") as restored, \
         mock.patch.object(worker.paste, "press",
                           side_effect=worker.paste.PasteError("no input")):
        pipeline._work("no-such-recording.wav", 1.0, [], "op-2", auto_paste=True)

    restored.assert_called_once_with(b"onceki icerik")
    assert failures, "hata kullanıcıya ulaşmalı"


def test_transcript_entry_skips_transcription_but_cleans_and_pastes():
    """Live engine hands over ready text: no transcribe call, same finish."""
    conf = _dictation_conf()
    pipeline = worker.Pipeline(conf)
    finished, failures = [], []
    pipeline.finished.connect(lambda *args: finished.append(args))
    pipeline.failed.connect(lambda message, _op: failures.append(message))
    transcribe = mock.Mock()
    client = mock.Mock()
    client.active_slot = 0
    client.cleanup.return_value = "clean words"
    with mock.patch.object(worker.localspeech, "transcribe_for", transcribe), \
         mock.patch.object(worker.api, "GeminiClient", return_value=client), \
         mock.patch.object(cfg.Config, "gemini_keys", return_value=["k1"]), \
         mock.patch.object(cfg.Config, "save"), \
         mock.patch.object(worker.paste, "copy"), \
         mock.patch.object(worker.paste, "press"):
        pipeline._work_text("raw words", 2.0, [], "op-live", auto_paste=True)
    transcribe.assert_not_called()
    assert not failures
    assert len(finished) == 1
    raw, text, _warning, _op = finished[0]
    assert (raw, text) == ("raw words", "clean words")
