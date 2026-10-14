"""Gemini Live API ile akan konuşma yazımı (üçüncü motor: ``live``).

Bulut motoru (``api.py``) sesi kaydedip tek REST çağrısıyla yazıya çevirir;
bu modül sesi 100 ms parçalar hâlinde websocket üzerinden akıtır ve ara
metni daha kayıt sürerken verir. Harici bağımlılık yok: websocket el sıkışma
ve çerçeveleme stdlib (``socket`` + ``ssl``) ile yapılır.
"""

from __future__ import annotations

import os
import select

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

    def _setup_message(self):
        return {
            "setup": {
                "model": MODEL,
                "generationConfig": {"responseModalities": ["TEXT"]},
                "inputAudioTranscription": {"mode": self._mode},
            },
        }


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
