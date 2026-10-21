"""On-demand CUDA runtime: pins, layout checks, and offer logic."""

import os
import shutil
import unittest
import zipfile
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cuda_libs
import cuda_runtime


class PinsTests(unittest.TestCase):
    def test_pins_name_tag_file_and_wheels(self):
        data = cuda_libs.pins()
        self.assertEqual(data["tag"], "cuda-libs-v1")
        self.assertEqual(data["file"], "WordArc-CudaLibs.zip")
        self.assertIn("nvidia-cudnn-cu12", data["wheels"])

    def test_download_url_points_at_the_libs_release(self):
        url = cuda_libs.download_url()
        self.assertIn("cuda-libs-v1", url)
        self.assertTrue(url.endswith("WordArc-CudaLibs.zip"))

    def test_libs_dir_is_versioned_under_app_data(self):
        import config
        self.assertEqual(cuda_libs.libs_dir(),
                         config.DATA_DIR / "cuda" / "cuda-libs-v1")


class InstalledTests(unittest.TestCase):
    def _fake_tree(self, root: Path):
        for name in ("cudart64_12.dll", "cublasLt64_12.dll", "cublas64_12.dll"):
            (root / "nvidia" / "cublas" / "bin").mkdir(parents=True, exist_ok=True)
            (root / "nvidia" / "cublas" / "bin" / name).write_bytes(b"x")
        for name in cuda_runtime.LIBRARIES:
            if name.startswith(("cudart", "cublas")):
                continue
            (root / "nvidia" / "cudnn" / "bin").mkdir(parents=True, exist_ok=True)
            (root / "nvidia" / "cudnn" / "bin" / name).write_bytes(b"x")

    def test_empty_dir_is_not_installed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(cuda_libs, "libs_dir",
                                   return_value=Path(tmp) / "empty"):
                self.assertFalse(cuda_libs.installed())

    def test_full_dll_set_counts_as_installed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "cuda-libs-v1"
            self._fake_tree(root)
            with mock.patch.object(cuda_libs, "libs_dir", return_value=root):
                self.assertTrue(cuda_libs.installed())

    def test_missing_single_dll_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "cuda-libs-v1"
            self._fake_tree(root)
            (root / "nvidia" / "cudnn" / "bin" / "cudnn64_9.dll").unlink()
            with mock.patch.object(cuda_libs, "libs_dir", return_value=root):
                self.assertFalse(cuda_libs.installed())


class OfferTests(unittest.TestCase):
    def test_offer_needs_driver_and_missing_libs(self):
        with mock.patch.object(cuda_libs, "available", return_value=False), \
             mock.patch("localspeech.cuda_driver_present", return_value=True):
            self.assertTrue(cuda_libs.offer("auto"))
            self.assertTrue(cuda_libs.offer("cuda"))
            self.assertFalse(cuda_libs.offer("cpu"))
            self.assertFalse(cuda_libs.offer("vulkan"))

    def test_no_offer_when_libs_present_or_no_driver(self):
        with mock.patch.object(cuda_libs, "available", return_value=True), \
             mock.patch("localspeech.cuda_driver_present", return_value=True):
            self.assertFalse(cuda_libs.offer("auto"))
        with mock.patch.object(cuda_libs, "available", return_value=False), \
             mock.patch("localspeech.cuda_driver_present", return_value=False):
            self.assertFalse(cuda_libs.offer("auto"))


class EnsureTests(unittest.TestCase):
    def _make_zip(self, path: Path):
        with zipfile.ZipFile(path, "w") as bundle:
            for name in cuda_runtime.LIBRARIES:
                bundle.writestr(f"nvidia/cudnn/bin/{name}", b"x")

    def test_ensure_downloads_verifies_and_extracts(self):
        import tempfile
        import update
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            archive = tmp / "WordArc-CudaLibs.zip"
            self._make_zip(archive)
            import hashlib
            sha = hashlib.sha256(archive.read_bytes()).hexdigest()
            root = tmp / "libs"
            info = update.UpdateInfo("cuda-libs-v1", "WordArc-CudaLibs.zip",
                                     "", sha, archive.stat().st_size, "")
            with mock.patch.object(cuda_libs, "libs_dir", return_value=root), \
                 mock.patch.object(cuda_libs, "pins", return_value={
                     "tag": "cuda-libs-v1", "file": "WordArc-CudaLibs.zip",
                     "sha256": sha, "size": archive.stat().st_size}), \
                 mock.patch.object(update, "download",
                                   side_effect=lambda i, d, progress=None,
                                   cancel=None: (shutil.copyfile(archive, d),
                                                  d)[1]):
                out = cuda_libs.ensure()
                self.assertEqual(out, root)
                self.assertTrue(cuda_libs.installed())

    def test_bad_checksum_leaves_no_half_dir(self):
        import tempfile
        import update
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            root = tmp / "libs"
            with mock.patch.object(cuda_libs, "libs_dir", return_value=root), \
                 mock.patch.object(cuda_libs, "pins", return_value={
                     "tag": "cuda-libs-v1", "file": "WordArc-CudaLibs.zip",
                     "sha256": "0" * 64, "size": 10}), \
                 mock.patch.object(update, "download",
                                   side_effect=update.UpdateError("bad")):
                with self.assertRaises(cuda_libs.CudaLibsError):
                    cuda_libs.ensure()
            self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
