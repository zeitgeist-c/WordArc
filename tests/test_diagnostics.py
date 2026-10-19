import sys
import tempfile
import unittest
from unittest import mock

import diagnostics


class TestRedaction(unittest.TestCase):
    def test_google_key_is_removed(self):
        secret = "AIza" + "A" * 32
        self.assertNotIn(secret, diagnostics.redact(f"failed {secret}"))

    def test_query_key_is_removed(self):
        out = diagnostics.redact("https://example.test/path?key=secret-value&x=1")
        self.assertNotIn("secret-value", out)


class TestNullStreams(unittest.TestCase):
    def test_missing_streams_go_to_log_file(self):
        import pathlib
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(diagnostics.cfg, "LOG_DIR",
                                   pathlib.Path(tmp)), \
                 mock.patch.object(sys, "stdout", None), \
                 mock.patch.object(sys, "stderr", None):
                diagnostics.redirect_null_streams()
                sys.stderr.write("x")
                sys.stdout.write("y")
                sys.stderr.flush()
            logged = (pathlib.Path(tmp) / "stderr.log").read_text(
                encoding="utf-8")
            self.assertEqual(logged, "xy")

    def test_present_streams_untouched(self):
        sentinel_out, sentinel_err = object(), object()
        with mock.patch.object(sys, "stdout", sentinel_out), \
             mock.patch.object(sys, "stderr", sentinel_err):
            diagnostics.redirect_null_streams()
            self.assertIs(sys.stdout, sentinel_out)
            self.assertIs(sys.stderr, sentinel_err)
