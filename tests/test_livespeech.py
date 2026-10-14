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


def _server_send(sock, payload):
    """Sunucu gibi maskesiz çerçeve yaz (test yardımcısı)."""
    import json
    from livespeech import _send_frame, _Socket
    raw = json.dumps(payload).encode("utf-8")
    header = bytearray([0x80 | 1])
    assert len(raw) < 126
    header.append(len(raw))
    sock.sendall(bytes(header) + raw)


def _open_with_scripted_server(api_key="k", script=()):
    import socket
    from livespeech import LiveSession
    client_end, server_end = socket.socketpair()
    server_end.sendall(b"HTTP/1.1 101 Switching Protocols\r\n"
                       b"Upgrade: websocket\r\n"
                       b"Connection: Upgrade\r\n\r\n")
    for message in script:
        _server_send(server_end, message)
    session = LiveSession(api_key=api_key)
    session.open(socket_factory=lambda host, port, timeout: client_end)
    return session, server_end


def test_finish_returns_final_text():
    from livespeech import CHUNK
    session, server = _open_with_scripted_server(script=(
        {"setupComplete": {}},
        {"serverContent": {"inputTranscription": {"text": "merhaba dünya"}}},
        {"serverContent": {"generationComplete": True}},
    ))
    try:
        session.push(b"\x00" * CHUNK * 3)
        assert session.finish() == "merhaba dünya"
    finally:
        server.close()


def test_finish_without_speech_raises():
    from livespeech import CHUNK, LiveError
    session, server = _open_with_scripted_server(script=(
        {"setupComplete": {}},
        {"serverContent": {"generationComplete": True}},
    ))
    try:
        session.push(b"\x00" * CHUNK * 3)
        try:
            session.finish()
        except LiveError:
            return
        raise AssertionError("sessiz kayıt metin döndürdü")
    finally:
        server.close()


def test_cancel_ends_thread():
    session, server = _open_with_scripted_server(script=(
        {"setupComplete": {}},
    ))
    try:
        session.cancel()
        assert session.done.wait(2)
    finally:
        server.close()


def test_open_without_key_raises():
    from livespeech import LiveError, LiveSession
    try:
        LiveSession(api_key="").open()
    except LiveError:
        return
    raise AssertionError("anahtarsız oturum açıldı")


def test_open_with_keys_falls_over_to_second_key():
    import socket
    from livespeech import CHUNK, LiveSession
    ends = []
    for script in (
        ({"error": {"message": "API key not valid. Pass a valid key."}},),
        ({"setupComplete": {}},
         {"serverContent": {"inputTranscription": {"text": "ikinci anahtar"}}},
         {"serverContent": {"generationComplete": True}}),
    ):
        client_end, server_end = socket.socketpair()
        server_end.sendall(b"HTTP/1.1 101 Switching Protocols\r\n\r\n")
        for message in script:
            _server_send(server_end, message)
        ends.append((client_end, server_end))
    try:
        attempt = {"n": 0}

        def factory(host, port, timeout):
            client_end, _server = ends[attempt["n"]]
            attempt["n"] += 1
            return client_end

        session = LiveSession.open_with_keys(["BIRINCI", "IKINCI"], "SMART",
                                             socket_factory=factory)
        assert attempt["n"] == 2
        session.push(b"\x00" * CHUNK * 3)
        assert session.finish() == "ikinci anahtar"
    finally:
        for _client, server in ends:
            server.close()


def test_open_with_keys_all_rejected_raises():
    import socket
    from livespeech import LiveError, LiveSession
    client_end, server_end = socket.socketpair()
    try:
        server_end.sendall(b"HTTP/1.1 101 Switching Protocols\r\n\r\n")
        _server_send(server_end, {"error": {"message": "bad key"}})
        factory = lambda host, port, timeout: client_end
        try:
            LiveSession.open_with_keys(["KOTU"], "SMART",
                                       socket_factory=factory)
        except LiveError:
            return
        raise AssertionError("reddedilen anahtar kabul edildi")
    finally:
        server_end.close()
