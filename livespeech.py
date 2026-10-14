"""Gemini Live API ile akan konuşma yazımı (üçüncü motor: ``live``).

Bulut motoru (``api.py``) sesi kaydedip tek REST çağrısıyla yazıya çevirir;
bu modül sesi 100 ms parçalar hâlinde websocket üzerinden akıtır ve ara
metni daha kayıt sürerken verir. Harici bağımlılık yok: websocket el sıkışma
ve çerçeveleme stdlib (``socket`` + ``ssl``) ile yapılır.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import select
import socket
import ssl
import threading
import time
import urllib.parse

from i18n import t

HOST = "generativelanguage.googleapis.com"
PATH = ("/ws/google.ai.generativelanguage.v1beta.GenerativeService."
        "BidiGenerateContent")
RATE = 16000
WIDTH = 2
CHUNK = 3200  # 100 ms, 1600 frames
MAX_PCM = 8 * 60 * RATE * WIDTH  # yumuşak sınır: 8 dk (sunucu 10 dk keser)
MIN_PCM = RATE * WIDTH // 5  # 0,2 sn altı kayıt sayılmaz
MIME = "audio/pcm;rate=16000"
MODEL = "models/gemini-3.5-transcribe-live"


class LiveSession:
    """Tek canlı yazı oturumu: aç, PCM it, bitir ya da iptal et."""

    def __init__(self, api_key, mode="SMART"):
        self._key = (api_key or "").strip()
        self._mode = ("VERBATIM" if str(mode).strip().upper() == "VERBATIM"
                      else "SMART")
        self._lock = threading.Lock()
        self._queue = queue.Queue()
        self._thread = None
        self._sock = None
        self._socket_factory = None
        self._buf = bytearray()
        self._finals = []
        self._interim = ""
        self._sent = 0
        self._closing = False
        self._opened = 0.0
        self._end_seen = False
        self._completed = False
        self.error = ""
        self.text = ""
        self.limit_hit = threading.Event()
        self.done = threading.Event()
        self.setup_ok = threading.Event()
        self.key_index = -1

    @classmethod
    def open_with_keys(cls, keys, mode="SMART", socket_factory=None,
                       should_stop=None):
        """Sırayla anahtar dene; kurulumu kabul edeni döndür.

        Bir oturum tek anahtar kullanır: kimlik hatası ortada değil,
        açılışta belli olur, o yüzden failover burada, kayıt başlamadan.
        """
        last_error = ""
        tried = 0
        for index, key in enumerate(keys or []):
            if should_stop is not None and should_stop():
                raise LiveError(t("Stopped."))
            if not (key or "").strip():
                continue
            tried += 1
            session = cls(api_key=key, mode=mode)
            session.open(socket_factory=socket_factory)
            while not session.done.is_set():
                if session.setup_ok.wait(0.2):
                    session.key_index = index
                    return session
            session.cancel()
            last_error = session.error or last_error
        if tried == 0:
            raise LiveError(t("Gemini API key is empty. Add it in Settings."))
        raise LiveError(last_error or t("Live transcription failed."))

    def _setup_message(self):
        return {
            "setup": {
                "model": MODEL,
                "generationConfig": {"responseModalities": ["TEXT"]},
                "inputAudioTranscription": {"mode": self._mode},
            },
        }

    def preview(self):
        """Kayıt sürerken ekrana basılacak metin (iplik güvenli)."""
        return self._text()

    def open(self, socket_factory=None):
        if not self._key:
            raise LiveError(t("Gemini API key is empty. Add it in Settings."))
        self._socket_factory = socket_factory
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def push(self, pcm):
        if pcm and not self.done.is_set():
            self._queue.put(pcm)

    def finish(self):
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=25)
        if self.text.strip():
            return self.text.strip()
        if self.error:
            raise LiveError(self.error)
        if self._sent < MIN_PCM:
            raise LiveError(t("Recording too short, speak for at least 0.3 s"))
        raise LiveError(t("No speech detected"))

    def cancel(self):
        self._closing = True
        self._queue.put(None)
        self._close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self):
        try:
            self._sock = _connect(self._key,
                                  socket_factory=self._socket_factory)
            self._send(self._setup_message())
            setup = self._next_message(15)
            if setup is None or "setupComplete" not in setup:
                raise LiveError(_failure(setup, self._key))
            self.setup_ok.set()
            self._opened = _now()
            pending = bytearray()
            ending = False
            while not self._closing:
                self._drain(0)
                if self.error:
                    break
                item = self._take(0 if pending else 0.02)
                if item:
                    pending.extend(item)
                if item is None or self._end_seen:
                    ending = True
                while pending and (ending or len(pending) >= CHUNK):
                    if self._sent >= MAX_PCM:
                        self.limit_hit.set()
                        pending.clear()
                        ending = True
                        break
                    size = len(pending) if ending else CHUNK
                    if self._sent + size > MAX_PCM:
                        size = MAX_PCM - self._sent
                    self._send_audio(bytes(pending[:size]))
                    del pending[:size]
                if not ending:
                    continue
                if self._sent < MIN_PCM:
                    self.error = t("Recording too short, "
                                   "speak for at least 0.3 s")
                    break
                self._send_audio(b"\x00" * (RATE * WIDTH * 12 // 100))
                self._send({"realtimeInput": {"audioStreamEnd": True}})
                self._collect_final()
                break
            self.text = self._text()
            if not self.text and not self.error and not self._closing:
                if self.limit_hit.is_set():
                    self.error = t("Live transcription stops at 8 minutes.")
                else:
                    self.error = t("No speech detected")
        except Exception as exc:
            if not self._closing:
                detail = _redact(str(exc), self._key)
                self.error = detail[:300] or t("Live transcription failed.")
        finally:
            self._close()
            self.done.set()

    def _send_audio(self, pcm):
        self._sent += len(pcm)
        self._send({
            "realtimeInput": {
                "audio": {
                    "data": base64.b64encode(pcm).decode("ascii"),
                    "mimeType": MIME,
                },
            },
        })

    def _send(self, payload):
        _send_frame(self._sock, 1, json.dumps(payload).encode("utf-8"))

    def _next_message(self, timeout):
        payload = _read_message(self._sock, self._buf, timeout)
        if payload is None:
            return None
        if not payload:
            return {}
        return json.loads(payload.decode("utf-8"))

    def _take(self, timeout):
        try:
            item = self._queue.get(timeout=timeout)
        except queue.Empty:
            return False
        if item is None:
            self._end_seen = True
            return None
        blob = bytearray(item)
        while True:
            try:
                extra = self._queue.get_nowait()
            except queue.Empty:
                break
            if extra is None:
                self._end_seen = True
                break
            blob.extend(extra)
        return bytes(blob)

    def _drain(self, timeout):
        got = False
        while True:
            message = self._next_message(0 if got else timeout)
            if message is None:
                return got
            got = True
            self._apply(message)

    def _collect_final(self):
        # Sunucu bitiş işaretine generationComplete ile cevap verir (genelde
        # 0,3-0,7 sn). Metin yatışınca da dönülür, sonsuz beklenmez.
        self._drain(0)
        self._completed = False
        started = _now()
        last = self._text()
        changed = started
        while _now() - started < 1.5 and not self._closing:
            self._drain(0.04)
            if self._completed:
                tail = _now() + 0.12
                while _now() < tail and not self._closing:
                    self._drain(0.04)
                return
            text = self._text()
            if text != last:
                last = text
                changed = _now()
            if _now() - started >= 0.9 and _now() - changed >= 0.3:
                return

    def _close(self):
        sock = self._sock
        self._sock = None
        if sock is None:
            return
        raw = getattr(sock, "sock", None)
        if raw is not None:
            try:
                raw.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
        try:
            _send_frame(sock, 8, b"")
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass

    def _text(self):
        with self._lock:
            parts = [piece.strip() for piece in self._finals
                     if piece and piece.strip()]
            interim = self._interim.strip()
            if interim:
                parts.append(interim)
            return " ".join(parts)

    def _apply(self, message):
        if "error" in message:
            self.error = _failure(message, self._key)
            return
        content = message.get("serverContent") or {}
        if content.get("generationComplete") or content.get("turnComplete"):
            self._completed = True
        interim = content.get("interimInputTranscription") or {}
        final = content.get("inputTranscription") or {}
        with self._lock:
            if interim.get("text"):
                self._interim = interim["text"]
            if final.get("text"):
                text = final["text"].strip()
                if self._finals and text.startswith(self._finals[-1].strip()):
                    self._finals[-1] = text
                elif text:
                    self._finals.append(text)
                # Kesin metin, yerini aldığı aranın gerisinde kalabilir;
                # aranın kalanı ekranda tutulur.
                self._interim = _remainder(self._interim, text)


def _remainder(interim, final):
    words = interim.split()
    done = final.split()
    if len(words) <= len(done):
        return ""
    return " ".join(words[len(done):])


def _failure(message, key):
    if not message:
        return t("Live transcription failed.")
    error = message.get("error") or {}
    text = error.get("message") or error.get("status") or ""
    return _redact(text, key)[:300] or t("Live transcription failed.")


class LiveError(Exception):
    """Kullanıcıya gösterilebilir canlı-yazı hatası."""


class _Socket:
    """Ham ya da TLS'li soket + okunmamış artı baytlar."""

    def __init__(self, sock, leftover):
        self.sock = sock
        self.pending_bytes = bytearray(leftover)

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def _send_frame(holder, opcode, payload):
    mask = os.urandom(4)
    header = bytearray([0x80 | opcode])
    length = len(payload)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header.extend(length.to_bytes(2, "big"))
    else:
        header.append(0x80 | 127)
        header.extend(length.to_bytes(8, "big"))
    header.extend(mask)
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    holder.sock.sendall(header + masked)


def _read_message(holder, carry, timeout):
    pieces = []
    opcode = None
    while True:
        frame = _read_frame(holder, carry, timeout if not pieces else 5)
        if frame is None:
            return None
        fin, kind, payload = frame
        if kind == 9:  # ping: pong yaz, kullanıcı mesajı beklemeye devam et
            _send_frame(holder, 10, payload)
            continue
        if kind == 8:
            reason = (payload[2:].decode("utf-8", errors="replace")
                      if len(payload) > 2 else "")
            raise LiveError(reason or t("Live transcription failed."))
        if kind in (1, 2):
            opcode = kind
            pieces.append(payload)
        elif kind == 0 and pieces:
            pieces.append(payload)
        if fin and pieces:
            return b"".join(pieces)
        if opcode is None and fin:
            return b""


def _read_frame(holder, carry, timeout):
    if not _wait(holder, carry, timeout):
        return None
    head = _exact(holder, carry, 2)
    first, second = head[0], head[1]
    length = second & 0x7F
    if length == 126:
        length = int.from_bytes(_exact(holder, carry, 2), "big")
    elif length == 127:
        length = int.from_bytes(_exact(holder, carry, 8), "big")
    mask = _exact(holder, carry, 4) if second & 0x80 else b""
    payload = _exact(holder, carry, length)
    if mask:
        payload = bytes(byte ^ mask[index % 4]
                        for index, byte in enumerate(payload))
    return bool(first & 0x80), first & 0x0F, payload


def _wait(holder, carry, timeout):
    if len(carry) or holder.pending_bytes:
        return True
    pending = getattr(holder.sock, "pending", None)
    if callable(pending):
        try:
            if pending():
                return True
        except Exception:
            pass
    readable, _, _ = select.select([holder.sock], [], [], timeout)
    return bool(readable)


def _exact(holder, carry, size):
    while len(carry) < size:
        if holder.pending_bytes:
            carry.extend(holder.pending_bytes)
            holder.pending_bytes.clear()
            continue
        chunk = holder.sock.recv(max(4096, size - len(carry)))
        if not chunk:
            raise LiveError(t("Live transcription failed."))
        carry.extend(chunk)
    out = bytes(carry[:size])
    del carry[:size]
    return out


def _now():
    return time.monotonic()


def _ssl_context():
    cafile = os.environ.get("SSL_CERT_FILE") or ""
    if cafile and os.path.isfile(cafile):
        return ssl.create_default_context(cafile=cafile)
    return ssl.create_default_context()


def _default_open(host, port, timeout):
    raw = socket.create_connection((host, port), timeout=timeout)
    try:
        return _ssl_context().wrap_socket(raw, server_hostname=host)
    except Exception:
        raw.close()
        raise


def _connect(key, socket_factory=None):
    """TLS + websocket el sıkışması; hazır soketi döndürür.

    ``socket_factory`` yalnız testler içindir: (host, port, timeout)
    alıp konuşmaya hazır soket verir, TLS sarma atlanır.
    """
    opener = socket_factory or _default_open
    try:
        sock = opener(HOST, 443, 20)
    except LiveError:
        raise
    except Exception as exc:
        raise LiveError(_redact(str(exc), key)
                        or t("Live transcription failed."))
    nonce = base64.b64encode(os.urandom(16)).decode("ascii")
    query = urllib.parse.urlencode({"key": key})
    request = (
        "GET %s?%s HTTP/1.1\r\n"
        "Host: %s\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: %s\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    ) % (PATH, query, HOST, nonce)
    try:
        sock.sendall(request.encode("ascii"))
        status, leftover = _read_headers(sock)
    except Exception as exc:
        try:
            sock.close()
        except Exception:
            pass
        raise LiveError(_redact(str(exc), key)
                        or t("Live transcription failed."))
    if b" 101 " not in status:
        try:
            sock.close()
        except Exception:
            pass
        detail = status.decode("utf-8", errors="replace").split("\r\n", 1)[0]
        raise LiveError(_redact(detail, key)
                        or t("Live transcription failed."))
    try:
        sock.settimeout(None)
    except Exception:
        pass
    return _Socket(sock, leftover)


def _read_headers(sock):
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > 65536:
            break
    head, _, rest = bytes(data).partition(b"\r\n\r\n")
    return head, rest


def _redact(text, key):
    """Hata metninden API anahtarını ayıkla (log/ekran sızdırmasın)."""
    out = str(text or "")
    if key and len(key) >= 8:
        out = out.replace(key, "***")
        head, tail = key[:4], key[-4:]
        if head in out or tail in out:
            out = out.replace(key[:8], "***").replace(key[-8:], "***")
    return out.strip()
