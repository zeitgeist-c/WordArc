"""Tests for the Gemini Live streaming engine (livespeech)."""


def test_setup_message_smart():
    from livespeech import LiveSession
    session = LiveSession(api_key="k", mode="SMART")
    message = session._setup_message()
    assert message["setup"]["model"] == "models/gemini-3.5-transcribe-live"
    assert message["setup"]["inputAudioTranscription"] == {"mode": "SMART"}


def test_setup_message_verbatim():
    from livespeech import LiveSession
    session = LiveSession(api_key="k", mode="verbatim")
    message = session._setup_message()
    assert message["setup"]["inputAudioTranscription"] == {"mode": "VERBATIM"}


def test_setup_message_unknown_mode_falls_back_to_smart():
    from livespeech import LiveSession
    session = LiveSession(api_key="k", mode="mumble")
    message = session._setup_message()
    assert message["setup"]["inputAudioTranscription"] == {"mode": "SMART"}
