"""Gemini API calls, stdlib only.

Transcription uses Gemini's generateContent endpoint with base64-encoded audio.
Cleanup and chat go through the same endpoint.
"""

import base64
import json
import os
import urllib.error
import urllib.request

from i18n import t

APP_URL = "https://github.com/yusufipk/verbatim"
USER_AGENT = f"verbatim/1.0 (+{APP_URL})"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"

Target = type("Target", (), {"__init__": lambda self, provider, service, api_key, base_url, model: (setattr(self, "provider", provider), setattr(self, "service", service), setattr(self, "api_key", api_key), setattr(self, "base_url", base_url), setattr(self, "model", model))[0]}) if False else None
# Simple namedtuple replacement for Target
import collections
Target = collections.namedtuple("Target", "provider service api_key base_url model")


class ApiError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def explain(exc, service):
    """Turn an HTTP status into something the user can act on."""
    if exc.status in (401, 403):
        return ApiError(t("{service} rejected the API key (HTTP {code}). Open "
                          "Settings and check it.", service=service, code=exc.status),
                        exc.status)
    if exc.status == 402:
        return ApiError(t("{service} says the account is out of credit (HTTP 402).",
                          service=service), exc.status)
    if exc.status == 429:
        return ApiError(t("{service} is rate limiting you (HTTP 429). Try again in "
                          "a moment.", service=service), exc.status)
    return ApiError(f"{service}: {exc}", exc.status)


def _request(url, data, headers, timeout=120):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise ApiError(f"HTTP {exc.code}: {_extract_error(body)}", exc.code) from exc
    except urllib.error.URLError as exc:
        raise ApiError(t("Could not connect: {reason}", reason=exc.reason)) from exc
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


def _get_json(url, headers, timeout=20):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise ApiError(f"HTTP {exc.code}: {_extract_error(body)}", exc.code) from exc
    except urllib.error.URLError as exc:
        raise ApiError(t("Could not connect: {reason}", reason=exc.reason)) from exc
    except json.JSONDecodeError as exc:
        raise ApiError(t("Could not parse the response: {error}", error=exc)) from exc


# --- transcription ---------------------------------------------------------

def transcribe(api_key, model, wav_path, language="", prompt="", timeout=300):
    """Transcribe audio via Gemini generateContent (base64 inline)."""
    if not api_key:
        raise ApiError(t("Gemini API key is empty. Add it in Settings."))
    with open(wav_path, "rb") as f:
        audio_data = base64.b64encode(f.read()).decode("ascii")
    instruction = "Transcribe the audio exactly as spoken, word for word."
    if prompt:
        instruction += f" Pay attention to these terms: {prompt}"
    if language and language != "auto":
        instruction += f" The audio is in {language}."
    payload = {
        "contents": [{
            "parts": [
                {"inlineData": {"mimeType": "audio/wav", "data": audio_data}}
            ]
        }],
        "generationConfig": {"temperature": 0.0},
        "systemInstruction": {"parts": [{"text": instruction}]},
    }
    url = f"{GEMINI_URL}/models/{model}:generateContent?key={api_key}"
    try:
        data = _request(url, json.dumps(payload).encode("utf-8"),
                        {"Content-Type": "application/json"}, timeout=timeout)
    except ApiError as exc:
        raise explain(exc, "Gemini") from None
    candidates = data.get("candidates") or []
    if not candidates:
        raise ApiError(t("Gemini returned no candidates."))
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise ApiError(t("Transcript came back empty."))
    return text


# --- chat / cleanup ---------------------------------------------------------

def gemini_chat(messages, api_key, model, system_prompt="", timeout=180):
    """Direct Gemini chat. Used for cleanup, agent, minutes."""
    if not api_key:
        raise ApiError(t("Gemini API key is empty. Add it in Settings."))
    gemini_msgs = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else m["role"]
        gemini_msgs.append({"role": role, "parts": [{"text": m["content"]}]})
    payload = {
        "contents": gemini_msgs,
        "generationConfig": {"temperature": 0.0},
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
    url = f"{GEMINI_URL}/models/{model}:generateContent?key={api_key}"
    data = _request(url, json.dumps(payload).encode("utf-8"),
                    {"Content-Type": "application/json"}, timeout=timeout)
    candidates = data.get("candidates") or []
    if not candidates:
        raise ApiError(t("Gemini returned no candidates."))
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise ApiError(t("Gemini returned an empty reply."))
    return text


def cleanup(text, api_key, model, system_prompt, reasoning="", timeout=180):
    """Clean transcript text using Gemini."""
    if not api_key:
        raise ApiError(t("Gemini API key is empty. Add it in Settings."))
    messages = [{"role": "user", "content": text}]
    return gemini_chat(messages, api_key, model, system_prompt, timeout)


def chat(messages, api_key, model, system_prompt, reasoning="", timeout=180):
    """A conversation via Gemini."""
    if not api_key:
        raise ApiError(t("Gemini API key is empty. Add it in Settings."))
    return gemini_chat(messages, api_key, model, system_prompt, timeout)


# --- model list -------------------------------------------------------------

def gemini_models(api_key):
    if not api_key:
        raise ApiError(t("Gemini API key is empty. Add it in Settings."))
    try:
        data = _get_json(
            f"{GEMINI_URL}/models?key={api_key}",
            {"User-Agent": USER_AGENT},
        )
    except ApiError as exc:
        raise explain(exc, "Gemini") from None
    models = data.get("models") or []
    supported = [m["name"] for m in models
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
    return sorted(name.replace("models/", "", 1) for name in supported)
