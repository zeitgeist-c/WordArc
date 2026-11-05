"""Update flow: version comparison, release parsing, download safety, swap."""

import os
import tempfile
import threading
import ssl
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import update


class TestUpdateFailureRecovery(unittest.TestCase):
    def test_context_uses_explicit_roots_and_preserves_verification(self):
        update._https_context.cache_clear()
        try:
            context = update._https_context()
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)
            self.assertGreater(context.cert_store_stats()["x509_ca"], 0)
            self.assertIs(update._https_context(), context)
        finally:
            update._https_context.cache_clear()

    def test_context_creation_failure_is_reported(self):
        with mock.patch.object(update, "_https_context", side_effect=ssl.SSLError("BIO lib")):
            with self.assertRaises(update.UpdateError):
                update.fetch_latest()

    def test_bad_server_shape_is_reported(self):
        import io
        with mock.patch.object(update.urllib.request, "urlopen", return_value=io.BytesIO(b'[]')):
            with self.assertRaises(update.UpdateError):
                update.fetch_latest()

    def test_ssl_context_failure_becomes_a_reportable_update_error(self):
        with mock.patch.object(update.urllib.request, "urlopen", side_effect=ssl.SSLError("[X509] BIO lib")):
            with self.assertRaises(update.UpdateError):
                update.fetch_latest()

    def test_system_store_failure_keeps_shipped_roots(self):
        import ssl as ssl_module
        update._https_context.cache_clear()
        try:
            with mock.patch.object(ssl_module.SSLContext, "load_default_certs",
                                   side_effect=OSError("store unavailable")):
                context = update._https_context()
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)
            self.assertGreater(context.cert_store_stats()["x509_ca"], 0)
        finally:
            update._https_context.cache_clear()

    def test_unexpected_worker_failure_always_emits_a_terminal_result(self):
        from PyQt6.QtWidgets import QApplication
        import wordarc
        app = QApplication.instance() or QApplication([])
        worker = wordarc._UpdateWorker("0.10.1")
        failures = []
        worker.failed.connect(failures.append)
        with mock.patch.object(update, "check_for_update", side_effect=ssl.SSLError("[X509] BIO lib")):
            worker.run()
        self.assertEqual(len(failures), 1)


REAL_085 = {
    "tag_name": "v0.8.5",
    "html_url": "https://github.com/x/y/releases/tag/v0.8.5",
    "assets": [
        {"name": "WordArc-0.8.5.bat", "size": 313,
         "digest": "sha256:4bd7", "browser_download_url": "https://x/bat"},
        {"name": "WordArc-0.8.5.exe", "size": 1582170592,
         "digest": "sha256:a54a13df",
         "browser_download_url": "https://x/exe"},
    ],
}


class VersionTests(unittest.TestCase):
    def test_parse_and_compare(self):
        self.assertEqual(update.parse_version("v0.8.10"), (0, 8, 10))
        self.assertTrue(update.is_newer("v0.8.6", "0.8.5"))
        self.assertTrue(update.is_newer("0.10.0", "0.8.99"))
        self.assertFalse(update.is_newer("v0.8.5", "0.8.5"))
        self.assertFalse(update.is_newer("v0.8.4", "0.8.5"))

    def test_unparsable_version_raises(self):
        with self.assertRaises(update.UpdateError):
            update.parse_version("latest")


class ReleaseParsingTests(unittest.TestCase):
    def test_exe_asset_with_digest(self):
        info = update.parse_release(REAL_085)
        self.assertEqual(info.version, "0.8.5")
        self.assertEqual(info.asset_name, "WordArc-0.8.5.exe")
        self.assertEqual(info.sha256, "a54a13df")
        self.assertEqual(info.size, 1582170592)

    def test_missing_exe_asset_raises(self):
        payload = dict(REAL_085, assets=[REAL_085["assets"][0]])
        with self.assertRaises(update.UpdateError):
            update.parse_release(payload)

    def test_unknown_tag_shape_raises(self):
        with self.assertRaises(update.UpdateError):
            update.parse_release(dict(REAL_085, tag_name="latest"))


class DownloadTests(unittest.TestCase):
    def _serve(self, tmp, payload: bytes, declared: int):
        data = Path(tmp) / "payload.bin"
        data.write_bytes(payload)
        return update.UpdateInfo(
            version="9.9.9", asset_name="WordArc-9.9.9.exe",
            download_url=data.as_uri(), sha256=update._sha256_of(data),
            size=declared, page_url="")

    def test_download_verifies_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = self._serve(tmp, b"installer-bytes", 15)
            dest = Path(tmp) / "next" / "WordArc-9.9.9.exe"
            update.download(info, dest)
            self.assertEqual(dest.read_bytes(), b"installer-bytes")

    def test_bad_checksum_deletes_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = self._serve(tmp, b"installer-bytes", 15)
            info.sha256 = "0" * 64
            dest = Path(tmp) / "bad.exe"
            with self.assertRaises(update.UpdateError):
                update.download(info, dest)
            self.assertFalse(dest.exists())

    def test_cancel_stops_and_deletes(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = self._serve(tmp, b"x" * 4096, 4096)
            cancel = threading.Event()
            cancel.set()
            dest = Path(tmp) / "half.exe"
            with self.assertRaises(update.UpdateError):
                update.download(info, dest, cancel=cancel)
            self.assertFalse(dest.exists())

    def test_transient_network_failure_is_retried(self):
        import urllib.error
        with tempfile.TemporaryDirectory() as tmp:
            info = self._serve(tmp, b"installer-bytes", 15)
            dest = Path(tmp) / "next" / "WordArc-9.9.9.exe"
            real_urlopen = update.urllib.request.urlopen

            def flaky(request, timeout=None, context=None):
                if not getattr(flaky, "failed", False):
                    flaky.failed = True
                    raise urllib.error.URLError("connection reset")
                return real_urlopen(request, timeout=timeout, context=context)

            with mock.patch.object(update.urllib.request, "urlopen",
                                   side_effect=flaky) as urlopen:
                update.download(info, dest)
            self.assertEqual(dest.read_bytes(), b"installer-bytes")
            self.assertEqual(urlopen.call_count, 2)

    def test_repeated_failure_still_reports_and_cleans_up(self):
        import urllib.error
        with tempfile.TemporaryDirectory() as tmp:
            info = self._serve(tmp, b"installer-bytes", 15)
            dest = Path(tmp) / "bad.exe"
            with mock.patch.object(update.urllib.request, "urlopen",
                                   side_effect=urllib.error.URLError("down")) as urlopen:
                with self.assertRaises(update.UpdateError):
                    update.download(info, dest)
            self.assertFalse(dest.exists())
            self.assertEqual(urlopen.call_count, 3)

    def test_stray_copy_blocks_setup_before_any_quit(self):
        with mock.patch.object(update, "other_copies_running",
                               return_value=[4321]):
            with self.assertRaises(update.UpdateError) as ctx:
                update.spawn_setup(Path("WordArc-9.9.9.exe"),
                                   version="9.9.9", sha256="0" * 64)
        self.assertIn("Another copy of WordArc", str(ctx.exception))

    def test_no_stray_copy_reported_from_source_checkout(self):
        # The test suite runs unfrozen: there is no installed copy to
        # collide with, even while the user's own app is running.
        self.assertEqual(update.other_copies_running(), [])


class StampTests(unittest.TestCase):
    def test_missing_and_old_stamps_need_a_check(self):
        self.assertTrue(update.last_check_is_old(""))
        self.assertTrue(update.last_check_is_old("garbage"))
        self.assertTrue(update.last_check_is_old("2020-01-01T00:00:00"))
        self.assertFalse(update.last_check_is_old(update.now_stamp()))


class SetupTests(unittest.TestCase):
    def test_setup_download_is_in_durable_user_storage(self):
        import config
        with mock.patch.object(config, "DATA_DIR", Path("C:/user-data/WordArc")):
            dest = update.setup_temp_path("9.9.9")
        self.assertEqual(dest, Path("C:/user-data/WordArc/updates/downloads/WordArc-9.9.9.exe"))

    def test_tampered_setup_is_not_launched(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "WordArc-9.9.9.exe"
            path.write_bytes(b"broken")
            with self.assertRaises(update.UpdateError):
                update.spawn_setup(path, version="9.9.9", sha256="a" * 64)


class HelperDirTests(unittest.TestCase):
    def _helper_tree(self, root, payload=b"supervisor-bytes"):
        import hashlib
        (root / "WordArcUpdate.exe").write_bytes(payload)
        (root / "manifest.json").write_text(
            __import__("json").dumps({"sha256": hashlib.sha256(payload).hexdigest()}),
            encoding="utf-8")

    def test_bundle_is_used_and_cache_refreshed(self):
        import config
        with tempfile.TemporaryDirectory() as tmp:
            bundled = Path(tmp) / "bundle"
            bundled.mkdir()
            self._helper_tree(bundled)
            data = Path(tmp) / "data"
            with mock.patch("brand.resource_path", return_value=bundled), \
                 mock.patch.object(config, "DATA_DIR", data):
                self.assertEqual(update._helper_dir(), bundled)
                cached = data / "update-helper" / "WordArcUpdate.exe"
                self.assertTrue(cached.is_file())
                self.assertEqual(cached.read_bytes(), b"supervisor-bytes")

    def test_wiped_bundle_falls_back_to_verified_cache(self):
        import config
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            cached = data / "update-helper"
            cached.mkdir(parents=True)
            self._helper_tree(cached)
            with mock.patch("brand.resource_path",
                                   return_value=Path(tmp) / "wiped-empty"), \
                 mock.patch.object(config, "DATA_DIR", data):
                self.assertEqual(update._helper_dir(), cached)

    def test_tampered_cache_is_rejected(self):
        import config
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            cached = data / "update-helper"
            cached.mkdir(parents=True)
            (cached / "WordArcUpdate.exe").write_bytes(b"evil")
            (cached / "manifest.json").write_text('{"sha256": "' + "0" * 64 + '"}',
                                                  encoding="utf-8")
            with mock.patch("brand.resource_path",
                                   return_value=Path(tmp) / "wiped-empty"), \
                 mock.patch.object(config, "DATA_DIR", data):
                with self.assertRaises(update.UpdateError):
                    update._helper_dir()


class LifecycleTests(unittest.TestCase):
    """WordArc's tray/signal wiring, without Qt threads or the network."""

    def _controller(self):
        import wordarc

        class FakeConf(dict):
            save = mock.Mock()

        controller = wordarc.WordArc.__new__(wordarc.WordArc)
        controller.conf = FakeConf(update_last_check="")
        controller.settings_window = None
        controller.tray = mock.Mock()
        controller.tray.isVisible.return_value = True
        controller.tray.showMessage = mock.Mock()
        controller._update_thread = None
        return controller

    def test_startup_check_is_quiet_and_once_a_day(self):
        controller = self._controller()
        controller._updates_possible = lambda: True
        controller._run_update_check = mock.Mock()
        controller.conf["update_last_check"] = update.now_stamp()
        controller._update_startup_check()
        # fresh stamp -> no run
        controller._run_update_check.assert_not_called()
        controller.conf["update_last_check"] = "2020-01-01T00:00:00"
        controller._update_startup_check()
        # old stamp -> run
        controller._run_update_check.assert_called_once_with(tray=True)

    def test_real_worker_failure_reaches_gui_thread_and_allows_retry(self):
        import time
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        controller = self._controller()
        controller._updates_possible = lambda: True
        controller.settings_window = mock.Mock()
        gui_thread = threading.get_ident()
        received = []
        controller.settings_window.show_update_error.side_effect = lambda message: received.append(threading.get_ident())
        with mock.patch.object(update, "check_for_update", side_effect=ssl.SSLError("BIO lib")):
            controller._run_update_check(tray=False)
            deadline = time.monotonic() + 3
            while getattr(controller, "_active_update_check", None) is not None and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.005)
        self.assertEqual(received, [gui_thread])
        self.assertIsNone(controller._update_thread)
        self.assertFalse(controller._update_check_deadline.isActive())
        with mock.patch.object(update, "check_for_update", return_value=None):
            controller._run_update_check(tray=False)
            deadline = time.monotonic() + 3
            while controller._active_update_check is not None and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.005)
        controller.settings_window.show_update_latest.assert_called_once()

    def test_timeout_releases_check_and_ignores_late_result(self):
        import time
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        controller = self._controller()
        controller._updates_possible = lambda: True
        controller.settings_window = mock.Mock()
        entered, release = threading.Event(), threading.Event()
        def delayed(current):
            entered.set()
            release.wait(3)
            return None
        with mock.patch.object(update, "check_for_update", side_effect=delayed):
            controller._run_update_check(tray=False)
            self.assertTrue(entered.wait(1))
            thread = controller._update_thread
            token = controller._active_update_check
            try:
                controller._update_check_deadline.timeout.emit()
                controller.settings_window.show_update_error.assert_called_once()
                self.assertIsNone(controller._update_thread)
                self.assertIsNone(controller._active_update_check)
            finally:
                release.set()
                thread.join(2)
            app.processEvents()
        controller._finish_update_check(token, info=None)
        controller.settings_window.show_update_latest.assert_not_called()

    def test_new_version_offers_window_when_open_else_tray(self):
        controller = self._controller()
        info = update.UpdateInfo("9.9.9", "WordArc-9.9.9.exe", "", "", 10, "")
        window = mock.Mock()
        controller.settings_window = window
        controller._update_checked(info)
        window.show_update_available.assert_called_once_with(info)
        controller.tray.showMessage.assert_not_called()

        controller.settings_window = None
        controller._update_checked(info)
        self.assertIn("9.9.9", controller.tray.showMessage.call_args[0][1])

    def test_source_checkout_never_checks(self):
        controller = self._controller()
        controller._updates_possible = lambda: False
        controller.settings_window = mock.Mock()
        controller._run_update_check(tray=False)
        controller.settings_window.show_update_error.assert_called_once()

    def test_app_waits_for_setup_readiness_before_quitting(self):
        import wordarc
        from PyQt6.QtWidgets import QApplication
        import time
        app = QApplication.instance() or QApplication([])
        controller = self._controller()
        controller.settings_window = mock.Mock()
        controller.app = mock.Mock()
        controller.shutdown = mock.Mock()
        controller._pending_install_info = update.UpdateInfo("9.9.9", "WordArc-9.9.9.exe", "", "a" * 64, 1, "")
        entered, release = threading.Event(), threading.Event()
        def setup(*args, **kwargs):
            entered.set()
            release.wait(2)
        with mock.patch("update.spawn_setup", side_effect=setup), \
             mock.patch("wordarc._release_instance_mutex"):
            controller._update_installed("9.9.9", "C:/updates/WordArc-9.9.9.exe")
            self.assertTrue(entered.wait(1))
            app.processEvents()
            controller.app.quit.assert_not_called()
            controller.settings_window.show_update_handoff.assert_called_once()
            release.set()
            deadline = time.monotonic() + 3
            while not controller.app.quit.called and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.005)
        controller.app.quit.assert_called_once()

    def test_failed_setup_handoff_keeps_old_app_open(self):
        import wordarc
        from PyQt6.QtWidgets import QApplication
        import time
        app = QApplication.instance() or QApplication([])
        controller = self._controller()
        controller.settings_window = mock.Mock()
        controller.app = mock.Mock()
        controller._pending_install_info = update.UpdateInfo("9.9.9", "", "", "a" * 64, 1, "")
        with mock.patch("update.spawn_setup", side_effect=OSError("setup failed")):
            controller._update_installed("9.9.9", "C:/updates/WordArc-9.9.9.exe")
            deadline = time.monotonic() + 3
            while not controller.settings_window.show_update_error.called and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.005)
        controller.settings_window.show_update_error.assert_called_once()
        controller.app.quit.assert_not_called()
        self.assertFalse(controller._update_handoff_active)


if __name__ == "__main__":
    unittest.main()
