"""Locate Windows CUDA 12 / cuDNN 9 libraries without changing system PATH."""
from pathlib import Path
import ctypes
import os
import sys
import threading

LIBRARIES = ("cudart64_12.dll", "cublasLt64_12.dll", "cublas64_12.dll", "cudnn64_9.dll",
             "cudnn_ops64_9.dll", "cudnn_cnn64_9.dll",
             "cudnn_adv64_9.dll", "cudnn_graph64_9.dll",
             "cudnn_engines_precompiled64_9.dll",
             "cudnn_engines_runtime_compiled64_9.dll",
             "cudnn_heuristic64_9.dll")
_directories = {}  # Keep add_dll_directory handles alive for delayed loads.
_libraries = {}
_lock = threading.Lock()


def search_directories():
    roots = [Path(sys.prefix) / "Lib" / "site-packages",
             Path(getattr(sys, "_MEIPASS", Path(__file__).parent)),
             Path(sys.executable).parent,
             *_data_cuda_roots()]
    paths = []
    for root in roots:
        paths.extend((root, root / "ctranslate2", root / "cuda"))
        for package in ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc"):
            paths.extend((root / "nvidia" / package / "bin",
                          root / "nvidia" / package / "lib"))
    for key, value in os.environ.items():
        if key == "CUDA_PATH" or key.startswith("CUDA_PATH_V12"):
            paths.extend((Path(value) / "bin", Path(value) / "bin" / "x64"))
    # NVIDIA's Windows cuDNN installer uses a separate versioned tree.
    cudnn = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "NVIDIA" / "CUDNN"
    try:
        if cudnn.is_dir():
            paths.extend(sorted(cudnn.glob("v9*/bin/*"), reverse=True))
    except OSError:
        pass
    paths.extend(Path(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p)
    found = []
    for path in paths:
        try:
            if path.is_dir():
                found.append(path.resolve())
        except OSError:
            # A stale or inaccessible PATH entry must never disable CUDA.
            continue
    return list(dict.fromkeys(found))


def prepare():
    if sys.platform != "win32":
        return
    with _lock:
        for path in search_directories():
            if path not in _directories:
                try:
                    _directories[path] = os.add_dll_directory(str(path))
                except OSError:
                    pass


def _data_cuda_roots():
    """On-demand runtime copies under the app data cuda directory."""
    try:
        import config
    except Exception:
        return []
    try:
        base = config.DATA_DIR / "cuda"
        if not base.is_dir():
            return []
        return [entry for entry in [base, *sorted(base.iterdir())]
                if entry.is_dir()]
    except OSError:
        return []


def missing_libraries():
    """DLL load failures, including dependency failures; a GPU count is insufficient."""
    if sys.platform != "win32":
        return []
    prepare()
    missing = []
    with _lock:
        for name in LIBRARIES:
            if name in _libraries:
                continue
            try:
                candidate = next((path / name for path in search_directories()
                                  if (path / name).is_file()), None)
                _libraries[name] = ctypes.WinDLL(str(candidate) if candidate else name)
            except OSError:
                missing.append(name)
    return missing
