import unittest

import diagnostics


class TestRedaction(unittest.TestCase):
    def test_google_key_is_removed(self):
        secret = "AIza" + "A" * 32
        self.assertNotIn(secret, diagnostics.redact(f"failed {secret}"))

    def test_query_key_is_removed(self):
        out = diagnostics.redact("https://example.test/path?key=secret-value&x=1")
        self.assertNotIn("secret-value", out)
