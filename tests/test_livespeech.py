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


def test_redact_masks_api_key():
    from livespeech import _redact
    out = _redact("hata: key SECRETKEY reddedildi", "SECRETKEY")
    assert "SECRETKEY" not in out
    assert "reddedildi" in out


def test_connect_handshake_carries_key_and_upgrades():
    from livespeech import _Socket, _connect

    sent = []

    class FakeSock:
        def sendall(self, data):
            sent.append(bytes(data))

        def recv(self, size):
            return (b"HTTP/1.1 101 Switching Protocols\r\n"
                    b"Upgrade: websocket\r\n"
                    b"Connection: Upgrade\r\n\r\n")

        def settimeout(self, value):
            pass

        def close(self):
            pass

    holder = _connect("DUMMYKEY", socket_factory=lambda host, port, timeout: FakeSock())
    assert isinstance(holder, _Socket)
    request = b"".join(sent).decode("ascii")
    assert "key=DUMMYKEY" in request
    assert "Upgrade: websocket" in request


def test_connect_rejects_non_101_status():
    from livespeech import LiveError, _connect

    class FakeSock:
        def sendall(self, data):
            pass

        def recv(self, size):
            return b"HTTP/1.1 401 Unauthorized\r\n\r\n"

        def settimeout(self, value):
            pass

        def close(self):
            pass

    try:
        _connect("DUMMYKEY", socket_factory=lambda host, port, timeout: FakeSock())
    except LiveError:
        return
    raise AssertionError("401 el sıkışması kabul edildi")


def _feed(session, *messages):
    for message in messages:
        session._apply(message)


def test_interim_then_final_has_no_duplication():
    from livespeech import LiveSession
    session = LiveSession(api_key="k")
    _feed(session,
          {"serverContent": {"interimInputTranscription": {"text": "merha"}}})
    assert session.preview() == "merha"
    _feed(session,
          {"serverContent": {"inputTranscription": {"text": "merhaba"}}})
    assert session.preview() == "merhaba"


def test_extending_final_replaces_previous():
    from livespeech import LiveSession
    session = LiveSession(api_key="k")
    _feed(session,
          {"serverContent": {"inputTranscription": {"text": "merhaba"}}},
          {"serverContent": {"inputTranscription": {"text": "merhaba dünya"}}})
    assert session.preview() == "merhaba dünya"


def test_server_error_sets_redacted_error():
    from livespeech import LiveSession
    session = LiveSession(api_key="SECRETKEY")
    _feed(session, {"error": {"message": "key SECRETKEY invalid"}})
    assert session.error
    assert "SECRETKEY" not in session.error
