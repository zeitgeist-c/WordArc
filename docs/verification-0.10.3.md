# WordArc 0.10.3 — verification (October 25, 2026)

Engine and model discovery screen: CPU, CUDA, and AMD Vulkan options are
collected independently of the selected device, with a progress indicator,
found-model counts, a details view, and explicit model selection.

## Changes and package

- Drives that cannot be fully walked report partial results. An access
  error never blocks the next candidate. Shared files are never moved or
  deleted; WordArc keeps a link to the existing file.
- External executables are never run during the scan. Automatic checks run
  only on engines matching the app's native manifest; external engines are
  verified after explicit selection.
- Setup: `dist/WordArc-0.10.3.exe`, **312,251,266 bytes**.
- Setup SHA256:
  `b08be38282ffa812a9a960ff77ece933ee3de10e69f91adba57ab7e834846556`.
- Inner app SHA256:
  `1e90b86b4e7a988f5435148c6bb85bdb69672de33c5cffc357b530ae59808fc9`.
- Engine repair pack `WordArcVulkan-1.9.2.zip` unchanged
  (19,741,654 bytes;
  SHA256 `a38e401921fecb9e5b71f95b84405a6d88a2d9ec816a53ccd586af309abc0786`).

## Verification

- Build gates: **731 tests, 2 skipped, 12 subtests**; Python build, import,
  and installer checks passed; dependency audit clean with SBOM produced.
- Native Vulkan payload, CPU fallback files, TTS models, icons, and embedded
  Python sources/version verified. New discovery, UI, source-link, and
  diagnostics modules matched against source.
- CUDA download definitions and hash manifest inside the package; CUDA
  libraries still download on demand. The `--cuda` release-package gate
  passed.
- Shipped inner EXE: `--version` launch 5.38 s (extraction included), real
  HTTPS + Qt update check 0.36 s with certificate and hostname verification
  on. Scan → select → save → resolve chain passed on the real scan window:

  | Model | Device | Time |
  | --- | --- | --- |
  | GGML Large v3 Turbo | AMD RX 6650 XT / Vulkan | 6.11 s |
  | GGML Large v3 Turbo | CPU | 13.33 s |
  | Hugging Face CT2 Base | CPU | 2.44 s |

  (Times exclude the EXE's first extraction/startup cost. Vulkan never fell
  back to CPU; GGML CPU/Vulkan texts identical.)

## Acceptance limits

No physical NVIDIA/CUDA device on this machine: CUDA-unavailable is shown
correctly, real CUDA resolution untested. Long microphone sessions and every
folder on every machine are outside this test's scope. An OS-level access
block is not treated as removed; the app skips that candidate safely and
continues. The installed app was not upgraded in place.
