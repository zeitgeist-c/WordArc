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


def test_frame_roundtrip_over_socketpair():
    import socket
    from livespeech import _Socket, _send_frame, _read_message
    left, right = socket.socketpair()
    try:
        sender = _Socket(left, bytearray())
        reader = _Socket(right, bytearray())
        carry = bytearray()
        _send_frame(sender, 1, b'{"hello": "dunya"}')
        assert _read_message(reader, carry, 5) == b'{"hello": "dunya"}'
    finally:
        left.close()
        right.close()


def test_frame_answers_ping_with_pong():
    import socket
    from livespeech import _Socket, _send_frame, _read_message
    left, right = socket.socketpair()
    try:
        sender = _Socket(left, bytearray())
        reader = _Socket(right, bytearray())
        carry = bytearray()
        _send_frame(sender, 9, b"ping-data")
        # Ping tek başına kullanıcı mesajı değildir; sonraki gerçek
        # mesaj okunur, pong karşıya yazılmış olur.
        _send_frame(sender, 1, b"after")
        assert _read_message(reader, carry, 5) == b"after"
        import select
        assert select.select([left], [], [], 1)[0], "pong yazılmadı"
    finally:
        left.close()
        right.close()
