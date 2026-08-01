# WordArc reliability, security and brand migration

WordArc uses `%APPDATA%\WordArc` and `%LOCALAPPDATA%\WordArc`, schema version 3,
and `WordArc/GeminiApiKey`. On first launch, files missing at the destination are
copied atomically from the former Verbatim locations. Existing destination files
win, legacy directories are retained, and the old credential is deleted only
after the new credential can be read back. The compatibility `verbatim.py`
entry point and legacy IPC alias remain for one release.

## Runtime model policy

- Dictation and lightweight cleanup default to `gemini-3.5-flash-lite`.
- Meeting minutes default to `gemini-3.6-flash`.
- Known retired Gemini 2.0 defaults migrate automatically; custom model IDs do
  not.
- API keys travel in `x-goog-api-key`, never in URLs. Transient 429/5xx errors
  receive bounded retries. Audio above the safe inline size uses the Gemini
  Files API and is deleted remotely after the request.

## Local security policy

- The Gemini key lives in Windows Credential Manager. A legacy plaintext key
  migrates on the next successful settings save.
- Dictation history is opt-in for new installations. Meeting Markdown files
  remain readable local files and the UI says so explicitly.
- Agent runs require a per-command choice: read-only, write once inside an
  explicitly selected directory, or cancel. Dangerous persistent modes are not
  exposed.

## Capture policy

- PortAudio loopback is preferred. SoundCard supplies a Windows Core Audio
  fallback when PortAudio exposes no loopback input.
- Capture queues are bounded. Overflow, device status and writer failures are
  surfaced to the application instead of silently killing a worker.
- Every recording lifecycle follows the validated operation state transitions
  in `operation.py`; worker signals carry the operation ID so stale results are
  ignored. `audio_capture.py` keeps Core Audio selection free of Qt.

## Build policy

- `requirements-lock.txt` is the known-working runtime set.
- `check.ps1` runs tests, compilation and an offscreen import smoke test; its
  `-Audit` switch also runs dependency auditing and creates `sbom.json`.
- `build.ps1` verifies the expected FFmpeg 8.1.1 version and SHA-256, runs the
  audit/SBOM gate, and only then invokes PyInstaller.
