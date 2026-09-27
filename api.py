"""Gemini API client implemented with the Python standard library."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import logging
import mimetypes
import os
import random
import time
import urllib.error
import urllib.request
from typing import Callable

from brand import BRAND
from i18n import t

APP_URL = "https://github.com/zeitgeist-c/wordarc"
USER_AGENT = f"wordarc/{BRAND.version} (+{APP_URL})"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_UPLOAD_URL = "https://generativelanguage.googleapis.com/upload/v1beta/files"
MAX_INLINE_AUDIO_BYTES = 14_000_000
RETRY_STATUSES = {429, 500, 502, 503, 504}
_log = logging.getLogger("wordarc.api")


@dataclass(frozen=True)
class Target:
    provider: str
    service: str
    api_key: str
    base_url: str
    model: str


class ApiError(Exception):
    def __init__(self, message, status=None, category="service"):
        super().__init__(message)
        self.status = status
        self.category = category


class Cancelled(ApiError):
    pass


def explain(exc, service):
    """Turn an HTTP status into something the user can act on."""
    if exc.status in (401, 403):
        return ApiError(t("{service} rejected the API key (HTTP {code}). Open "
                          "Settings and check it.", service=service, code=exc.status),
                        exc.status, "user")
    if exc.status == 404:
        return ApiError(t(
            "The selected Gemini model is unavailable. Open Settings and choose "
            "gemini-3.5-flash-lite or gemini-3.6-flash."), exc.status, "user")
    if exc.status == 402:
        return ApiError(t("{service} says the account is out of credit (HTTP 402).",
                          service=service), exc.status, "user")
    if exc.status == 429:
        return ApiError(t("{service} is rate limiting you (HTTP 429). Try again in "
                          "a moment.", service=service), exc.status, "temporary")
    return ApiError(f"{service}: {exc}", exc.status,
                    "temporary" if exc.status in RETRY_STATUSES else "service")


def _cancelled(should_stop):
    if should_stop is not None and should_stop():
        raise Cancelled(t("Stopped."), category="cancelled")


class _FileBody:
    """A request body that streams a file instead of loading it into memory.

    A long meeting's WAV is hundreds of megabytes, so reading it whole would
    spike memory for nothing. urllib re-sends ``req.data`` on every retry, and a
    consumed stream would send zero bytes the second time, so the handle is
    reopened for each attempt and closed once the request is over.
    """

    def __init__(self, path):
        self.path = path
        self.size = os.path.getsize(path)
        self._handle = None

    def open(self):
        self.close()
        self._handle = open(self.path, "rb")
        return self._handle

    def close(self):
        if self._handle is not None:
            try:
                self._handle.close()
            finally:
                self._handle = None


def _open(req, timeout, attempts=3, should_stop=None, body_factory=None):
    """Open a request with bounded retries for transient HTTP failures."""
    content_length = req.get_header("Content-length")
    for attempt in range(attempts):
        _cancelled(should_stop)
        if body_factory is not None:
            req.data = body_factory()
            # urllib's data setter drops Content-Length on every assignment
            # (CPython issue 16464), which would quietly turn the upload into a
            # chunked one, so the length goes back on for each attempt.
            if content_length is not None:
                req.add_header("Content-Length", content_length)
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRY_STATUSES or attempt + 1 >= attempts:
                raise
            retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
            try:
                delay = min(4.0, max(0.0, float(retry_after)))
            except ValueError:
                delay = 0.5 * (2 ** attempt)
            # A little jitter avoids a group of clients retrying in lockstep.
            delay = min(4.0, delay + random.uniform(0.0, 0.15))
            exc.close()
            end = time.monotonic() + delay
            while time.monotonic() < end:
                _cancelled(should_stop)
                time.sleep(min(0.1, end - time.monotonic()))


def _read_response(req, timeout=120, attempts=3, should_stop=None,
                   body_factory=None):
    try:
        with _open(req, timeout, attempts, should_stop, body_factory) as resp:
            return resp.read(), resp.headers
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", "replace")
        finally:
            exc.close()
        raise ApiError(f"HTTP {exc.code}: {_extract_error(body)}", exc.code) from exc
    except urllib.error.URLError as exc:
        raise ApiError(t("Could not connect: {reason}", reason=exc.reason),
                       category="temporary") from exc
    except TimeoutError as exc:
        raise ApiError(t("Could not connect: {reason}", reason=exc),
                       category="temporary") from exc


def _request(url, data, headers, timeout=120, attempts=3, should_stop=None,
             method="POST", body_factory=None):
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    body, _headers = _read_response(req, timeout, attempts, should_stop,
                                    body_factory)
    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ApiError(t("Could not parse the response: {error}", error=exc)) from exc


def _extract_error(body):
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body[:300]
    err = payload.get("error")
    if isinstance(err, dict):
        return err.get("message") or json.dumps(err)[:300]
    if isinstance(err, str):
        return err
    return body[:300]


def _get_json(url, headers, timeout=20, attempts=3, should_stop=None):
    return _request(url, None, headers, timeout, attempts, should_stop, "GET")


def _headers(api_key, **extra):
    return {"User-Agent": USER_AGENT, "x-goog-api-key": api_key, **extra}


def _upload_file(path, api_key, mime_type, should_stop=None):
    size = os.path.getsize(path)
    start_headers = _headers(
        api_key,
        **{
            "Content-Type": "application/json; charset=UTF-8",
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(size),
            "X-Goog-Upload-Header-Content-Type": mime_type,
        },
    )
    req = urllib.request.Request(
        GEMINI_UPLOAD_URL,
        data=json.dumps({"file": {"display_name": os.path.basename(path)}}).encode(),
        headers=start_headers,
        method="POST",
    )
    _body, response_headers = _read_response(req, 60, 3, should_stop)
    upload_url = response_headers.get("X-Goog-Upload-URL")
    if not upload_url:
        raise ApiError(t("Gemini did not provide a file upload URL."))
    _cancelled(should_stop)
    # Streamed rather than read whole: a long meeting is hundreds of megabytes.
    # The explicit length keeps urllib from falling back to chunked transfer.
    body = _FileBody(path)
    try:
        data = _request(
            upload_url,
            body.open(),
            {
                "Content-Type": mime_type,
                "Content-Length": str(body.size),
                "X-Goog-Upload-Offset": "0",
                "X-Goog-Upload-Command": "upload, finalize",
            },
            timeout=300,
            attempts=3,
            should_stop=should_stop,
            body_factory=body.open,
        )
    finally:
        body.close()
    file_row = data.get("file") or {}
    name = file_row.get("name", "")
    uri = file_row.get("uri", "")
    if not name or not uri:
        _delete_file(name, api_key)
        raise ApiError(t("Gemini returned an invalid uploaded file."))
    try:
        for _ in range(60):
            _cancelled(should_stop)
            row = _get_json(f"{GEMINI_URL}/{name}", _headers(api_key),
                            timeout=20, should_stop=should_stop)
            state = (row.get("state") or "ACTIVE").upper()
            if state == "ACTIVE":
                return name, uri
            if state == "FAILED":
                raise ApiError(t("Gemini could not process the uploaded audio file."))
            time.sleep(0.5)
        raise ApiError(t("Gemini did not finish processing the uploaded audio file."),
                       category="temporary")
    except Exception:
        _delete_file(name, api_key)
        raise


def _delete_file(name, api_key):
    if not name:
        return
    try:
        req = urllib.request.Request(
            f"{GEMINI_URL}/{name}", headers=_headers(api_key), method="DELETE")
        with urllib.request.urlopen(req, timeout=20):
            pass
    except (OSError, urllib.error.URLError):
        pass


def _candidate_text(data, empty_message):
    candidates = data.get("candidates") or []
    if not candidates:
        raise ApiError(t("Gemini returned no candidates."))
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise ApiError(t(empty_message))
    return text


def transcribe(api_key, model, wav_path, language="", prompt="", timeout=300,
               should_stop: Callable[[], bool] | None = None):
    """Transcribe audio via Gemini, uploading files that are unsafe to inline."""
    if not api_key:
        raise ApiError(t("Gemini API key is empty. Add it in Settings."), category="user")
    instruction = "Transcribe the audio exactly as spoken, word for word."
    if prompt:
        instruction += f" Pay attention to these terms: {prompt}"
    if language and language != "auto":
        instruction += f" The audio is in {language}."
    uploaded_name = ""
    try:
        if os.path.getsize(wav_path) <= MAX_INLINE_AUDIO_BYTES:
            with open(wav_path, "rb") as fh:
                audio_part = {"inlineData": {
                    "mimeType": "audio/wav",
                    "data": base64.b64encode(fh.read()).decode("ascii"),
                }}
        else:
            mime_type = mimetypes.guess_type(wav_path)[0] or "audio/wav"
            uploaded_name, uri = _upload_file(
                wav_path, api_key, mime_type, should_stop)
            audio_part = {"fileData": {"mimeType": mime_type, "fileUri": uri}}
        payload = {
            "contents": [{"parts": [audio_part]}],
            "systemInstruction": {"parts": [{"text": instruction}]},
        }
        data = _request(
            f"{GEMINI_URL}/models/{model}:generateContent",
            json.dumps(payload).encode("utf-8"),
            _headers(api_key, **{"Content-Type": "application/json"}),
            timeout=timeout,
            should_stop=should_stop,
        )
        return _candidate_text(data, "Transcript came back empty.")
    except ApiError as exc:
        if isinstance(exc, Cancelled):
            raise
        raise explain(exc, "Gemini") from None
    finally:
        _delete_file(uploaded_name, api_key)


def gemini_chat(messages, api_key, model, system_prompt="", timeout=180,
                 should_stop=None):
    if not api_key:
        raise ApiError(t("Gemini API key is empty. Add it in Settings."), category="user")
    contents = []
    for message in messages:
        role = "model" if message["role"] == "assistant" else message["role"]
        contents.append({"role": role, "parts": [{"text": message["content"]}]})
    payload = {"contents": contents}
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
    try:
        data = _request(
            f"{GEMINI_URL}/models/{model}:generateContent",
            json.dumps(payload).encode("utf-8"),
            _headers(api_key, **{"Content-Type": "application/json"}),
            timeout=timeout,
            should_stop=should_stop,
        )
    except ApiError as exc:
        if isinstance(exc, Cancelled):
            raise
        raise explain(exc, "Gemini") from None
    return _candidate_text(data, "Gemini returned an empty reply.")


def cleanup(text, api_key, model, system_prompt, reasoning="", timeout=180,
            should_stop=None):
    return gemini_chat([{"role": "user", "content": text}], api_key, model,
                       system_prompt, timeout, should_stop)


def gemini_models(api_key):
    if not api_key:
        raise ApiError(t("Gemini API key is empty. Add it in Settings."), category="user")
    try:
        data = _get_json(f"{GEMINI_URL}/models", _headers(api_key))
    except ApiError as exc:
        raise explain(exc, "Gemini") from None
    models = data.get("models") or []
    supported = [m["name"] for m in models
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
    return sorted(name.replace("models/", "", 1) for name in supported)


class GeminiClient:
    """Gemini facade with operation-scoped, ordered API-key failover."""

    FAILOVER_STATUSES = {401, 402, 403, 429, 500, 502, 503, 504}

    def __init__(self, api_keys, should_stop=None, on_fallback=None,
                 start_slot=0):
        if isinstance(api_keys, str):
            api_keys = [api_keys]
        self.api_keys = []
        for value in api_keys or []:
            key = str(value or "").strip()
            if key and key not in self.api_keys:
                self.api_keys.append(key)
        self.should_stop = should_stop
        self.on_fallback = on_fallback
        try:
            start = int(start_slot)
        except (TypeError, ValueError):
            start = 0
        if not self.api_keys or not 0 <= start < len(self.api_keys):
            start = 0
        self._active = start
        self._unavailable = set()

    @property
    def active_slot(self):
        """İşin gerçekten yapıldığı slot (failover sonrası değişmiş olabilir)."""
        return self._active

    @staticmethod
    def _can_fail_over(exc):
        return (not isinstance(exc, Cancelled)
                and (exc.status in GeminiClient.FAILOVER_STATUSES
                     or exc.category == "temporary"))

    def _call(self, function, *args, **kwargs):
        if not self.api_keys:
            raise ApiError(t("Gemini API key is empty. Add it in Settings."),
                           category="user")
        order = [self._active] + [
            index for index in range(len(self.api_keys))
            if index != self._active
        ]
        last_error = None
        for position, index in enumerate(order):
            if index in self._unavailable:
                continue
            try:
                result = function(self.api_keys[index], *args, **kwargs)
                self._active = index
                return result
            except ApiError as exc:
                if not self._can_fail_over(exc):
                    raise
                last_error = exc
                self._unavailable.add(index)
                remaining = [candidate for candidate in order[position + 1:]
                             if candidate not in self._unavailable]
                _log.warning(
                    "Gemini API slot %d failed (status=%s category=%s); fallback=%s",
                    index + 1, exc.status, exc.category,
                    remaining[0] + 1 if remaining else "none",
                )
                if remaining and self.on_fallback is not None:
                    self.on_fallback(remaining[0] + 1, exc, failed=index + 1)
        if last_error is not None:
            raise ApiError(t(
                "All configured Gemini APIs failed. Last error: {error}",
                error=last_error,
            ), last_error.status, last_error.category) from None
        raise ApiError(t("All configured Gemini APIs failed."), category="service")

    def transcribe(self, model, path, **kwargs):
        return self._call(transcribe, model, path,
                          should_stop=self.should_stop, **kwargs)

    def cleanup(self, text, model, system_prompt, reasoning="", timeout=180):
        return self._call(
            lambda key: cleanup(text, key, model, system_prompt, reasoning,
                                timeout, self.should_stop)
        )

    def complete(self, messages, model, system_prompt="", timeout=180):
        return self._call(
            lambda key: gemini_chat(messages, key, model, system_prompt,
                                     timeout, self.should_stop)
        )

    def list_models(self):
        return self._call(gemini_models)
