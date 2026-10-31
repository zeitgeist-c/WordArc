# WordArc 0.10.1 — verification (October 24, 2026)

Vulkan engine repair without reinstall, verified model re-download,
and restored application and window icons.

## Changes

- `vulkan_runtime.py` scans the saved selection, the user data directory,
  the package, PATH, common installs, and a bounded set of directories.
  CLI flags and real Vulkan device output are checked; other applications'
  files are never modified.
- The packaged engine is copied to the permanent user directory only after
  its hash manifest verifies. A missing engine is repaired with the
  SHA256-pinned `WordArcVulkan-1.9.2.zip`. Engine and model states are
  reported separately, with scan, manual selection, and safe re-download.
- Model refresh atomically swaps in the verified `.part` file; a failed
  download never deletes the verified weights. Windows CR LF output is
  normalized.
- Icon pixels reload from scratch with a drawn fallback; the caption,
  application window, and QApplication share the icon.

## Evidence

- Full suite: **702 passed, 2 skipped, 12 subtests**.
- Audit gates (imports, build, installer flags, dependency scan) passed with
  no known issues in pinned dependencies.
- Real RX 6650 XT, large-v3-turbo: source Vulkan 3.31 s; shipped inner EXE
  Vulkan 5.01 s, CPU 8.38 s; identical text, no GPU fallback.
- Isolated test with no preinstalled engine: the full-hash engine ZIP was
  downloaded, verified, and installed over a local URL, then the same audio
  and model resolved on Vulkan.
- Logo and working re-download/scan/select controls checked visually; small
  and large icon handles populated on a real Windows window.
- `tools/verify_release_package.py --cuda` passed: embedded version and
  source bytecode, native file manifest, icons, repair ZIP, TTS/CUDA pins,
  isolated `--version` launch.

## Package identity

- `WordArc-0.10.1.exe`: 312,178,298 bytes;
  SHA256 `066fe6b45db603cbf1fd4b8e8904a5ea4d19895e1960009a2b9b96a99ba93284`.
- `WordArcVulkan-1.9.2.zip`: 19,741,654 bytes;
  SHA256 `a38e401921fecb9e5b71f95b84405a6d88a2d9ec816a53ccd586af309abc0786`.
- Built with Python 3.12.10 / PyInstaller 6.22.3 and locked dependencies.
  CUDA libraries stay optional downloads; no physical NVIDIA test on this
  machine. The installed app was not modified in place.
