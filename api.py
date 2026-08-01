"""Gemini API client implemented with the Python standard library."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import mimetypes
import os
import random
import time
import urllib.error
import urllib.request
from typing import Callable

from i18n import t

APP_URL = "https://github.com/zeitgeist-c/wordarc"
USER_AGENT = f"wordarc/0.3 (+{APP_URL})"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_UPLOAD_URL = "https://generativelanguage.googleapis.com/upload/v1beta/files"
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
MAX_INLINE_AUDIO_BYTES = 14_000_000
RETRY_STATUSES = {429, 500, 502, 503, 504}


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


def _open(req, timeout, attempts=3, should_stop=None):
    """Open a request with bounded retries for transient HTTP failures."""
    for attempt in range(attempts):
        _cancelled(should_stop)
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


def _read_response(req, timeout=120, attempts=3, should_stop=None):
    try:
        with _open(req, timeout, attempts, should_stop) as resp:
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
             method="POST"):
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    body, _headers = _read_response(req, timeout, attempts, should_stop)
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
    with open(path, "rb") as fh:
        content = fh.read()
    data = _request(
        upload_url,
        content,
        {
            "Content-Type": mime_type,
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        },
        timeout=300,
        attempts=3,
        should_stop=should_stop,
    )
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


def chat(messages, api_key, model, system_prompt, reasoning="", timeout=180,
         should_stop=None):
    return gemini_chat(messages, api_key, model, system_prompt, timeout, should_stop)


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
    """Small injectable facade used by non-UI services and tests."""

    def __init__(self, api_key, should_stop=None):
        self.api_key = api_key
        self.should_stop = should_stop

    def transcribe(self, model, path, **kwargs):
        return transcribe(self.api_key, model, path,
                          should_stop=self.should_stop, **kwargs)

    def complete(self, messages, model, system_prompt="", timeout=180):
        return gemini_chat(messages, self.api_key, model, system_prompt, timeout,
                           self.should_stop)

    def list_models(self):
        return gemini_models(self.api_key)
