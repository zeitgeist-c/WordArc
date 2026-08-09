import io
import os
import tempfile
import unittest, json
import urllib.error
from unittest import mock
import api

class TestExtractError(unittest.TestCase):
    def test_json_error_dict(self):
        body = json.dumps({"error": {"message": "bad key"}})
        self.assertEqual(api._extract_error(body), "bad key")
    def test_json_error_str(self):
        body = json.dumps({"error": "oops"})
        self.assertEqual(api._extract_error(body), "oops")
    def test_plain_text_truncated(self):
        self.assertEqual(api._extract_error("x" * 500)[:10], "xxxxxxxxxx")
        self.assertTrue(len(api._extract_error("x" * 500)) <= 300)

class TestExplain(unittest.TestCase):
    def setUp(self):
        import i18n
        self._old_lang = i18n.language()
        i18n.set_language("en")

    def tearDown(self):
        import i18n
        i18n.set_language(self._old_lang)

    def test_401_message(self):
        exc = api.ApiError("HTTP 401", 401)
        out = api.explain(exc, "Gemini")
        self.assertIn("rejected the API key", str(out))
        self.assertEqual(out.status, 401)

    def test_404_recommends_a_current_model(self):
        out = api.explain(api.ApiError("gone", 404), "Gemini")
        self.assertIn("gemini-3.5-flash-lite", str(out))


class TestGeminiRequests(unittest.TestCase):
    def test_transcribe_uses_header_and_no_deprecated_temperature(self):
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.write(fd, b"audio")
        os.close(fd)
        seen = {}

        def request(url, data, headers, **kwargs):
            seen.update(url=url, payload=json.loads(data), headers=headers)
            return {"candidates": [{"content": {"parts": [{"text": "hello"}]}}]}

        try:
            with mock.patch.object(api, "_request", side_effect=request):
                self.assertEqual(api.transcribe("secret", "gemini-3.5-flash-lite", path),
                                 "hello")
        finally:
            os.unlink(path)
        self.assertNotIn("?key=", seen["url"])
        self.assertEqual(seen["headers"]["x-goog-api-key"], "secret")
        self.assertNotIn("generationConfig", seen["payload"])

    def test_transient_http_error_is_retried(self):
        error = urllib.error.HTTPError(
            "https://example.test", 429, "busy", {"Retry-After": "0"},
            io.BytesIO(b'{"error":"busy"}'))
        response = mock.MagicMock()
        with mock.patch.object(api.urllib.request, "urlopen",
                               side_effect=[error, response]) as opened:
            self.assertIs(api._open(mock.Mock(), 1), response)
        self.assertEqual(opened.call_count, 2)

    def test_large_audio_upload_is_deleted(self):
        with mock.patch.object(api.os.path, "getsize",
                               return_value=api.MAX_INLINE_AUDIO_BYTES + 1), \
             mock.patch.object(api, "_upload_file",
                               return_value=("files/123", "gemini://file")), \
             mock.patch.object(api, "_delete_file") as delete, \
             mock.patch.object(api, "_request", return_value={
                 "candidates": [{"content": {"parts": [{"text": "large"}]}}]
             }) as request:
            out = api.transcribe("secret", "gemini-3.5-flash-lite", "large.wav")
        self.assertEqual(out, "large")
        payload = json.loads(request.call_args.args[1])
        self.assertEqual(payload["contents"][0]["parts"][0]["fileData"]["fileUri"],
                         "gemini://file")
        delete.assert_called_once_with("files/123", "secret")

    def test_upload_is_deleted_when_remote_processing_fails(self):
        upload_response = {
            "file": {"name": "files/failed", "uri": "gemini://failed"}
        }
        with mock.patch.object(api.os.path, "getsize", return_value=10), \
             mock.patch("builtins.open", mock.mock_open(read_data=b"audio")), \
             mock.patch.object(api, "_read_response",
                               return_value=(b"", {"X-Goog-Upload-URL": "upload"})), \
             mock.patch.object(api, "_request", return_value=upload_response), \
             mock.patch.object(api, "_get_json", return_value={"state": "FAILED"}), \
             mock.patch.object(api, "_delete_file") as delete:
            with self.assertRaises(api.ApiError):
                api._upload_file("large.wav", "secret", "audio/wav")
        delete.assert_called_once_with("files/failed", "secret")


class TestGeminiFallback(unittest.TestCase):
    def test_rejected_primary_uses_backup_and_stays_on_it(self):
        seen = []
        fallback = mock.Mock()

        def models(key):
            seen.append(key)
            if key == "primary":
                raise api.ApiError("rejected", 401, "user")
            return ["model"]

        client = api.GeminiClient(
            ["primary", "backup"], on_fallback=fallback
        )
        with mock.patch.object(api, "gemini_models", side_effect=models):
            self.assertEqual(client.list_models(), ["model"])
            self.assertEqual(client.list_models(), ["model"])
        self.assertEqual(seen, ["primary", "backup", "backup"])
        fallback.assert_called_once()
        self.assertEqual(fallback.call_args.args[0], 2)

    def test_invalid_model_does_not_try_another_key(self):
        with mock.patch.object(
            api, "gemini_models", side_effect=api.ApiError("missing", 404, "user")
        ) as models:
            with self.assertRaises(api.ApiError):
                api.GeminiClient(["one", "two"]).list_models()
        self.assertEqual(models.call_count, 1)

    def test_cancel_does_not_try_another_key(self):
        with mock.patch.object(api, "gemini_models",
                               side_effect=api.Cancelled("stopped")) as models:
            with self.assertRaises(api.Cancelled):
                api.GeminiClient(["one", "two"]).list_models()
        self.assertEqual(models.call_count, 1)

    def test_all_keys_fail_without_leaking_secrets(self):
        with mock.patch.object(
            api, "gemini_models",
            side_effect=api.ApiError("temporary", 503, "temporary"),
        ):
            with self.assertRaises(api.ApiError) as raised:
                api.GeminiClient(["secret-one", "secret-two"]).list_models()
        message = str(raised.exception)
        self.assertIn("Gemini", message)
        self.assertNotIn("secret-one", message)
        self.assertNotIn("secret-two", message)

if __name__ == "__main__":
    unittest.main()
