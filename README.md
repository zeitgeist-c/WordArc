# WordArc — Voice-to-text for Windows

WordArc turns speech into polished text and captures microphone and system audio for reliable meeting minutes.

## Install

1. Download `wordarc.exe` or build it from source.
2. Put `wordarc.exe` and `install.ps1` in the same folder, then run `install.ps1`.
3. Start WordArc. Settings opens on first launch.

The default shortcut is `Ctrl+Space`: press once to record and again to transcribe. The tray menu exposes dictation, agent, meeting and settings actions.

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements-lock.txt -r requirements-dev.txt
python wordarc.py
```

Run the reproducible checks and build:

```powershell
.\check.ps1
.\build.ps1
```

The packaged result is `dist\wordarc.exe`. Build verifies the pinned FFmpeg binary, runs tests and import checks, audits dependencies, emits `sbom.json`, renders the deterministic WordArc icon, and then invokes PyInstaller.

## Data, privacy and migration

Configuration lives at `%APPDATA%\WordArc\config.json`; recordings, meetings and diagnostics live under `%LOCALAPPDATA%\WordArc\`. Gemini credentials are stored in Windows Credential Manager as `WordArc/GeminiApiKey`.

On first launch, missing files are copied atomically from the old Verbatim directories. A legacy credential is copied, verified and only then removed. Existing WordArc files are never overwritten and old directories are not deleted, so they remain a rollback copy. `verbatim.py` remains a compatibility entry point for one release.

Transcript history is off by default. If enabled, history and meeting transcripts are readable local text files. Successful meeting audio is deleted by default.

## Branding and themes

The canonical SVG sources are in `assets\brand`. `tools\build_brand_assets.py` generates the multi-resolution Windows icon. Dark is the default theme; Light and System modes can be switched instantly in Settings.

WordArc is GPL-3.0. The original Linux project was created by [yusufipk](https://github.com/yusufipk/dikte).
