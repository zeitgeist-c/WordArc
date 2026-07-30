import unittest, json
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

if __name__ == "__main__":
    unittest.main()