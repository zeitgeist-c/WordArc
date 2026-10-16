"""Update flow: version comparison, release parsing, download safety, swap."""

import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import update


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


class StampTests(unittest.TestCase):
    def test_missing_and_old_stamps_need_a_check(self):
        self.assertTrue(update.last_check_is_old(""))
        self.assertTrue(update.last_check_is_old("garbage"))
        self.assertTrue(update.last_check_is_old("2020-01-01T00:00:00"))
        self.assertFalse(update.last_check_is_old(update.now_stamp()))


class SwapTests(unittest.TestCase):
    def test_swap_script_targets_the_new_exe_and_self_deletes(self):
        with tempfile.TemporaryDirectory() as tmp:
            new_exe = Path(tmp) / "WordArc-9.9.9.exe"
            with mock.patch("update.subprocess.Popen") as popen:
                update.spawn_swap(4242, new_exe)
            script = Path(tmp) / "wordarc-swap.bat"
            body = script.read_text(encoding="ascii")
            self.assertIn("4242", body)
            self.assertIn(str(new_exe), body)
            self.assertIn("del ", body)
            self.assertTrue(popen.called)


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


if __name__ == "__main__":
    unittest.main()
