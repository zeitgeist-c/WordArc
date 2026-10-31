# WordArc 0.10.4 — verification (October 25, 2026)

Reliable install handoff: the app no longer quits on the setup launch
result alone. An independent supervisor waits until Inno reports readiness
after its offline launch check of the new payload, then the old process
exits; the install exit code, the installed app's health, and a real startup
acknowledgment are tracked. Errors stay in the log. A permission or
readiness failure never closes the running app. After a failed handoff past
old-process exit, the verified recovery copy can be reopened.

The target is fixed at 64-bit `C:\Program Files\WordArc`. Old files are
cleaned only after the new app verifies and starts, and only on matching
recorded path and SHA256. Settings, recordings, and models are outside
install cleanup.

## Package and verification

- Setup: `dist/WordArc-0.10.4.exe`, 320,531,332 bytes.
- SHA256:
  `024bf0b262f635e7f91a77d02d3a85179027917073efda060658bae59f867b26`.
- Inner EXE SHA256:
  `d1d22c05a87a58511f8f80d63f28579032a694458ca04778bcd0c755e0d4b869`.
- Vulkan repair ZIP unchanged
  (SHA256 `a38e401921fecb9e5b71f95b84405a6d88a2d9ec816a53ccd586af309abc0786`).
- Official CPU package build: **744 tests, 2 skipped, 12 subtests**;
  dependency audit clean. Embedded sources, supervisor hashes, `--version`,
  real HTTPS/Qt update check, and offline install check passed.
- Scan → select → save → resolve on the shipped inner EXE; GGML Turbo
  Vulkan/CPU and HF Base CPU passed (no physical NVIDIA/CUDA device).
- A hostile-payload Inno run preserved the old files. A separate-AppId
  full install/start/cleanup cycle passed with user documents intact.

## Live migration

- The real admin migration completed: the new app acknowledged startup of
  0.10.4 from `C:\Program Files\WordArc\WordArc.exe`. Installed EXE hash
  matches the shipped inner EXE. The 64-bit uninstall entry shows 0.10.4
  with the correct path; the old 32-bit entry was removed. Settings
  comparison passed with no cleanup warnings. Opening Settings over the new
  app's command channel verified.
