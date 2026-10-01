"""Reproduce and verify WordArc's pinned Windows Vulkan native payload.

No SDK installer is executed. Required SDK files are extracted into .cache;
only the compiled CLI, probe, ggml/Whisper DLLs and licenses enter the EXE.
Run with requirements-native-build.txt and Visual Studio C++ installed.
"""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import shutil
import ssl
import struct
import subprocess
import urllib.request
import zipfile
import zlib
import sys

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"
DEST = ROOT / "native" / "whisper-vulkan"
VERSION = "1.9.2"
SOURCE_URL = f"https://api.github.com/repos/ggml-org/whisper.cpp/zipball/v{VERSION}"
SOURCE_SHA = "e9e14fa4ce2607eb6adf2cee0699757c22fc722094ab861268247fa3af65679e"
SDK_VERSION = "1.4.363.0"
SDK_URL = f"https://sdk.lunarg.com/sdk/download/{SDK_VERSION}/windows/vulkansdk-windows-X64-{SDK_VERSION}.exe"
SDK_SHA = "94a82d378f7a5e3e54c9db7d2fb7016af136e14ac0a18dbf0f2f67a36352d141"
CRT_FILES = ("concrt140.dll", "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
             "msvcp140_atomic_wait.dll", "msvcp140_codecvt_ids.dll", "vccorlib140.dll",
             "vcruntime140.dll", "vcruntime140_1.dll", "vcruntime140_threads.dll")
FILES = ("whisper-cli.exe", "wordarc-vulkan-probe.exe", "whisper.dll", "ggml.dll",
         "ggml-base.dll", "ggml-cpu.dll", "ggml-vulkan.dll", "LICENSE",
         "cpu/whisper-cli.exe", "cpu/whisper.dll", "cpu/ggml.dll",
         "cpu/ggml-base.dll", "cpu/ggml-cpu.dll") + CRT_FILES + tuple("cpu/" + name for name in CRT_FILES)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify():
    try:
        manifest = json.loads((DEST / "manifest.json").read_text())
        assert manifest["whisper_version"] == VERSION and manifest["sdk_version"] == SDK_VERSION
        assert manifest["source_sha256"] == SOURCE_SHA
        assert all(digest(DEST / name) == manifest["files"][name] for name in FILES)
    except (OSError, ValueError, KeyError, AssertionError):
        return False
    return True


def fetch(url, path, expected):
    if path.is_file() and digest(path) == expected:
        return
    import certifi
    context = ssl.create_default_context(cafile=certifi.where())
    request = urllib.request.Request(url, headers={"User-Agent": "WordArc-native-build"})
    part = path.with_suffix(path.suffix + ".part")
    with urllib.request.urlopen(request, context=context, timeout=60) as response, part.open("wb") as stream:
        shutil.copyfileobj(response, stream, 1024 * 1024)
    if digest(part) != expected:
        raise RuntimeError(f"Checksum mismatch: {url}")
    part.replace(path)


def extract_sdk(installer, sdk):
    import py7zr
    data = installer.read_bytes()
    pos = 0
    while True:
        pos = data.find(b"7z\xbc\xaf\x27\x1c", pos)
        if pos < 0:
            break
        header = data[pos:pos + 32]
        if zlib.crc32(header[12:]) == struct.unpack_from("<I", header, 8)[0]:
            offset, size = struct.unpack_from("<QQ", header, 12)
            with py7zr.SevenZipFile(io.BytesIO(data[pos:pos + 32 + offset + size])) as archive:
                wanted = [name for name in archive.getnames()
                          if name.startswith(("Include/", "Lib/", "Bin/glslc"))]
                if wanted:
                    archive.extract(path=sdk, targets=wanted)
        pos += 6
    if not (sdk / "Bin" / "glslc.exe").is_file():
        raise RuntimeError("Vulkan SDK compiler extraction failed")


def run(*args):
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)


def main():
    if verify() and "--rebuild" not in sys.argv:
        print(f"VULKAN PAYLOAD OK: whisper.cpp {VERSION}")
        return
    CACHE.mkdir(exist_ok=True)
    source_zip = CACHE / f"whisper-{VERSION}.zip"
    fetch(SOURCE_URL, source_zip, SOURCE_SHA)
    source_parent = CACHE / "whisper-src"
    with zipfile.ZipFile(source_zip) as archive:
        source = source_parent / archive.namelist()[0].split("/")[0]
        if not (source / "CMakeLists.txt").is_file():
            archive.extractall(source_parent)
    sdk = CACHE / "vulkan-sdk"
    installer = CACHE / "vulkansdk.exe"
    fetch(SDK_URL, installer, SDK_SHA)
    if not (sdk / "Include" / "vulkan" / "vulkan.h").is_file():
        extract_sdk(installer, sdk)
    import cmake
    cmake_exe = Path(cmake.CMAKE_BIN_DIR) / "cmake.exe"
    build = CACHE / "whisper-build"
    run(cmake_exe, "-S", source, "-B", build, "-G", "Visual Studio 17 2022", "-A", "x64",
        "-DGGML_VULKAN=ON", f"-DVulkan_INCLUDE_DIR={sdk / 'Include'}",
        f"-DVulkan_LIBRARY={sdk / 'Lib/vulkan-1.lib'}",
        f"-DVulkan_GLSLC_EXECUTABLE={sdk / 'Bin/glslc.exe'}", f"-DCMAKE_PREFIX_PATH={sdk}",
        "-DWHISPER_BUILD_TESTS=OFF", "-DWHISPER_BUILD_SERVER=OFF", "-DGGML_NATIVE=OFF",
        "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded", "-DGGML_OPENMP=OFF")
    run(cmake_exe, "--build", build, "--config", "Release", "--target", "whisper-cli", "--parallel", "8")
    probe = CACHE / "probe-build"
    run(cmake_exe, "-S", ROOT / "tools/native", "-B", probe,
        "-G", "Visual Studio 17 2022", "-A", "x64",
        f"-DWHISPER_SOURCE={source}", f"-DWHISPER_BUILD={build}")
    run(cmake_exe, "--build", probe, "--config", "Release", "--parallel", "4")
    DEST.mkdir(parents=True, exist_ok=True)
    for file in (build / "bin/Release").glob("*.dll"):
        shutil.copy2(file, DEST / file.name)
    shutil.copy2(build / "bin/Release/whisper-cli.exe", DEST / "whisper-cli.exe")
    shutil.copy2(probe / "Release/wordarc-vulkan-probe.exe", DEST / "wordarc-vulkan-probe.exe")
    shutil.copy2(source / "LICENSE", DEST / "LICENSE")
    # This vendor snapshot ships ggml under whisper.cpp's repository MIT license.
    # A CPU fallback must not import Vulkan DLLs or initialize the failed driver.
    cpu_build = CACHE / "whisper-cpu-build"
    run(cmake_exe, "-S", source, "-B", cpu_build, "-G", "Visual Studio 17 2022", "-A", "x64",
        "-DGGML_VULKAN=OFF", "-DWHISPER_BUILD_TESTS=OFF", "-DWHISPER_BUILD_SERVER=OFF",
        "-DGGML_NATIVE=OFF", "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded", "-DGGML_OPENMP=OFF")
    run(cmake_exe, "--build", cpu_build, "--config", "Release", "--target", "whisper-cli", "--parallel", "8")
    (DEST / "cpu").mkdir(exist_ok=True)
    for filename in ("whisper-cli.exe", "whisper.dll", "ggml.dll", "ggml-base.dll", "ggml-cpu.dll"):
        shutil.copy2(cpu_build / "bin/Release" / filename, DEST / "cpu" / filename)
    # GGML's older CMake policy uses /MD despite the runtime option. Ship the
    # compiler's redistributable DLLs beside both children, rather than relying
    # on a development PC's globally installed Visual C++ runtime.
    compiler_record = next((build / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
    import re
    compiler = Path(re.search(r'set\(CMAKE_CXX_COMPILER "([^"]+)"', compiler_record.read_text()).group(1))
    vc = next(path for path in compiler.parents if path.name == "VC")
    candidates = list((vc / "Redist/MSVC").glob("14.*/x64/Microsoft.VC143.CRT"))
    redist = max(candidates, key=lambda path: tuple(int(part) for part in path.parents[1].name.split('.')))
    for filename in CRT_FILES:
        shutil.copy2(redist / filename, DEST / filename)
        shutil.copy2(redist / filename, DEST / "cpu" / filename)
    manifest = dict(whisper_version=VERSION, sdk_version=SDK_VERSION, source_sha256=SOURCE_SHA,
                    source=SOURCE_URL, sdk_sha256=SDK_SHA,
                    files={name: digest(DEST / name) for name in FILES})
    (DEST / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    assert verify(), "native artifact verification failed"
    print(f"VULKAN PAYLOAD BUILT: whisper.cpp {VERSION}")


if __name__ == "__main__":
    main()
