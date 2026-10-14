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
        self._finals = []
        self._interim = ""
        self._completed = False
        self.error = ""
        self.text = ""

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
