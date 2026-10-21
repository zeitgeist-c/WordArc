# WordArc — Voice-to-text for Windows

> Türkçe için: [README.tr.md](./README.tr.md)

WordArc turns speech into polished text. Press `Ctrl+Space`, talk, press again — the text is transcribed, cleaned up, and pasted where you work. It also captures microphone and system audio for reliable meeting minutes.

![Ayarlar - Dikte](./docs/screenshots/01-ayarlar-dikte.png)

## Features

- **Push-to-talk dictation** — `Ctrl+Space` to start/stop, `Escape` discards without transcription or AI processing.
- **Meeting mode** — `wordarc.py meeting` records mic + system audio (WASAPI loopback), writes minutes-grade transcripts.
- **Screenshots** — `Ctrl+Alt+S` selects a region on the active screen; Settings also offers active-screen capture, clipboard copy, and PNG/JPEG save.
- **System-audio capture** — meeting counterparts are captured even without a mic share.
- **Voice activity detection** — trims silence before sending audio.
- **Paste where you work** — result is pasted into the focused app.
- **Tray service** — dictation, agent, meeting, and settings actions from the tray menu; single instance via local IPC.
- **Transcript history (opt-in)** — off by default; when on, history is plain local text files.
- **Privacy by default** — successful meeting audio is deleted by default; Gemini key lives in Windows Credential Manager (`WordArc/GeminiApiKey`).
- **Bilingual UI** — Turkish and English; dark default with light and system themes.
- **Legacy migration** — first launch copies missing files atomically from previous installs, never overwrites existing WordArc files.

## Quick start (zero-install state)

1. Download the current `WordArc-X.Y.Z.exe` and run it (admin install into Program Files, ~500MB — GPU support downloads later only if you use an NVIDIA card).
2. Start WordArc — Settings opens on first launch. Enter your Gemini API key.
3. Press `Ctrl+Space` once, talk, press again. The polished text is pasted.

CLI:

```powershell
python wordarc.py             # open Settings, keep tray service running
python wordarc.py background  # run in background (Windows startup)
python wordarc.py toggle      # start / stop recording
python wordarc.py cancel      # discard the current recording
python wordarc.py meeting     # start / end a meeting recording
python wordarc.py settings    # open the settings window
python wordarc.py quit        # shut the application down
```

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements-lock.txt -r requirements-dev.txt
python wordarc.py
```

Checks and build:

```powershell
.\check.ps1
.\build.ps1
```

`check.ps1` runs pytest, compileall, and an import check over all modules. `build.ps1` verifies the pinned FFmpeg binary, runs tests, audits dependencies, emits `sbom.json`, renders the deterministic icon, vendors the TTS weights, and produces the setup installer via PyInstaller + Inno Setup.

## Data and privacy

- Settings: `%APPDATA%\WordArc\config.json`
- Recordings, meetings, diagnostics, downloaded models: `%LOCALAPPDATA%\WordArc\` (speech models under `whisper`, GPU runtime under `cuda` — installer and uninstaller never touch these)
- Gemini key: Windows Credential Manager, `WordArc/GeminiApiKey`
- History off by default; meeting audio deleted after success by default.
- `verbatim.py` stays one release as a compatibility entry point.

## Project structure

```text
wordarc.py        tray app, CLI, single-instance IPC
worker.py         dictation pipeline
meeting.py        meeting pipeline
audio*.py         mic + WASAPI loopback capture
settings_ui.py    settings and screenshot tabs
screenshot_capture.py  region/full-screen capture and local preview
hotkey.py         global hotkeys
assets/brand      canonical SVG sources, icon build
tools/            brand asset + helper scripts
tests/            pytest suite
```

## FAQ

- **Nothing happens on `Ctrl+Space`?** Another app may own the hotkey — change or free it, then `wordarc.py restart`.
- **Meeting has no counterpart audio?** System-audio capture needs loopback; check Windows sound settings.
- **Key rejected?** Re-enter it in Settings; it is stored only in Credential Manager.
- **Local model on GPU?** Automatic selects NVIDIA CUDA, then AMD Vulkan, then CPU. Since 0.6.9, AMD uses a bundled whisper.cpp Vulkan engine and a separate GGML model download. Existing CPU/CUDA weights remain intact and work on CPU until the AMD model is downloaded. The standard EXE carries both native engines, their Visual C++ runtime DLLs and NVIDIA CUDA libraries; GPU drivers remain external. No Vulkan SDK/ROCm installation is needed on the user's machine. Select the device and download its model in Settings → Speech to text.
- **GPU recovery:** Automatic retries the same recording on CPU after a Vulkan failure. An explicit AMD/NVIDIA choice asks for consent before saving CPU and retrying. A separate Vulkan-free CPU native payload can use already downloaded GGML weights without another model download. Audio stays local. See [AMD investigation and acceptance](docs/amd-vulkan-0.6.9.md); real NVIDIA hardware acceptance remains separate.

## Roadmap

- Clean-install screenshots in `docs/screenshots/`
- More grammars for cleanup polish
- Per-app paste profiles

## Contributing

See [CONTRIBUTING](./.github/PULL_REQUEST_TEMPLATE.md) flow: open an issue, keep PRs small, run `.\check.ps1` before pushing.

## License

GPL-3.0. The original Linux project was created by [yusufipk](https://github.com/yusufipk/dikte).
