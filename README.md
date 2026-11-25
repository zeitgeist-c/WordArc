# WordArc — Voice-to-text for Windows

**Press `Ctrl+Space`, talk, press again. The text lands where you work — cleaned up.**

WordArc is a Windows dictation and transcription tool. It records your microphone (and, in meeting mode, your system audio too), transcribes it locally or through Gemini, polishes the result with an AI cleanup pass, and pastes it into whatever window had focus. No cloud clipboard, no account, no background upload of your audio.

![WordArc · Dictation](./docs/screenshots/01-dictation.png)

---

## Contents

- [What it does](#what-it-does)
- [Screens, one by one](#screens-one-by-one)
  - [1. Dictation](#1-dictation)
  - [2. Meeting](#2-meeting)
  - [3. Audio file](#3-audio-file)
  - [4. Speak](#4-speak)
  - [5. Screenshot](#5-screenshot)
  - [6. Text selection toolbar](#6-text-selection-toolbar)
  - [7. Settings](#7-settings)
  - [8. Dark theme](#8-dark-theme)
- [Install](#install)
- [Command line](#command-line)
- [Build from source](#build-from-source)
- [Speech engines](#speech-engines)
- [Data and privacy](#data-and-privacy)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## What it does

| Capability | Detail |
|---|---|
| **Push-to-talk dictation** | `Ctrl+Space` starts and stops; `Escape` discards without transcribing |
| **Meeting mode** | microphone + system audio via WASAPI loopback, minutes-grade output |
| **Audio file transcription** | any file ffmpeg can read, with timestamps and `.srt` export |
| **Read aloud** | text-to-speech with speed and format control, saveable to a file |
| **Screenshot capture** | `Ctrl+Alt+S` region select, OCR read-aloud, clipboard, PNG/JPEG |
| **Text selection toolbar** | select text in any app: copy, translate to Turkish, explain, summarise |
| **Cleanup pass** | an AI model removes filler words, fixes punctuation and keeps meaning |
| **Local or cloud** | whisper on CPU/CUDA/Vulkan, Gemini batch or instant — your choice per mode |
| **Interface in 13 languages** | English default; switching reopens Settings, never restarts the app |

---

## Screens, one by one

### 1. Dictation

![Dictation](./docs/screenshots/01-dictation.png)

The default page, built around one button.

- `Start recording` — begins capture. The same action is bound to `Ctrl+Space` globally, so you can dictate into any application.
- **Microphone** selector with a `Reload` button, so a headset plugged in mid-session appears without a restart.
- **Speech language** for the dictation model.
- **Shortcut** field — the global hotkey, editable.
- **Clean the transcript with a model** — when on, the raw transcript goes through the cleanup pass before it is pasted.
- **Paste the text into the focused window** — when off, the result stays in WordArc for you to copy manually.
- **Lower background audio while dictating** — when on, the speaker/headphone volume drops while you record (adjustable `Reduction`, 80% by default) and returns as soon as recording ends. Playback keeps playing. It stays off while a meeting records.
- `Latest dictation` — the final text; `History` keeps previous dictations (`Store dictation history on computer`, off by default).
- `Copy`, `Delete selected`, `Clear history`, `Reload`. `Save` writes the page's settings.

**Why two steps.** Recording and transcription are separate: the recording finishes first, then transcription runs, then cleanup runs. If cleanup fails you still have the raw transcript — WordArc never discards the transcription because the polish step broke.

### 2. Meeting

![Meeting](./docs/screenshots/02-meeting.png)

Records both sides of a call without asking anyone to share their screen.

- `Start recording` — start/stop the meeting recording.
- **Microphone** — `Same as dictation`, or a specific device.
- **Meeting audio source** — `Current output` captures what you hear through WASAPI loopback, so the other participants are recorded even on headphones.
- **Who is talking** — speaker labels for you and the other side, one name per line.
- `Minutes` — one entry per recording, timestamped (`No meetings yet.` until the first one).
- `Copy`, `Write it up`, `Open the folder`, `Delete selected`, `Reload`.

**Audio handling.** The recording is written to `%LOCALAPPDATA%\WordArc\` and deleted after a successful transcription by default. If transcription fails, the audio stays so you can retry — nothing is silently thrown away.

### 3. Audio file

![Audio file](./docs/screenshots/03-audio-file.png)

Transcribe an existing recording instead of a live one.

- `Choose file...` — pick the audio file.
- **Add timestamps** — prefix each segment with its offset.
- **Run through the cleanup model afterwards** — same polish pass as dictation.
- `Transcribe`, `Stop` — the stop is cooperative; a partial transcript is kept.
- `Copy`, `Save as .txt`, `Save as .srt` — subtitle export uses the timestamps.

Long files stream: the progress bar advances and the partial text appears while the file is still being processed, so you can stop early if the first minutes are wrong.

### 4. Speak

![Speak](./docs/screenshots/04-speak.png)

Text-to-speech, in the same window.

- **Text to read** — paste or type anything.
- Format (`opus`, `mp3`, `wav`) and playback speed.
- `Read aloud`, `Stop`, `Save audio...` — writes the rendered speech to a file.

The voice models are vendored into the build, so this tab works offline.

### 5. Screenshot

![Screenshot](./docs/screenshots/05-screenshot.png)

Capture and reuse what is on screen.

- `Select area...` — the same action as the global `Ctrl+Alt+S`.
- `Convert to audio and read` — OCR the capture and speak the text.
- `Capture this screen`, `Capture active window`.
- **Capture shortcut** field — the global capture hotkey.
- **Save folder** with `Choose folder...`, and an image format selector (`PNG`).

Captures stay local. Nothing is uploaded for the read-aloud path — the OCR runs on your machine.

### 6. Text selection toolbar

Select text in any application and a small toolbar appears next to it: copy, translate to Turkish, explain, summarise. Copy writes straight to the clipboard and works offline; the three AI actions show the answer in a small window whose own Copy button is the only path to the clipboard. Password fields and empty selections are skipped quietly, and the toolbar never steals focus from the application you selected in. Enable it under Settings → Application → `Text selection bar` (off by default).

### 7. Settings

![Settings](./docs/screenshots/06-settings.png)

Nine sections down the left: four shared ones, then one per tool.

**Audio and models**
- **Where it runs** — `Batch Transcription (Gemini)`, `Instant Transcription (Gemini)` or `Local (this computer)`.
- **Cloud model** — the transcription model, with `Fetch model list`.
- **Transcript cleanup** — one polish pass shared by dictation, meeting and audio files: model, `Fetch model list`, `Thinking` (`Model's own default`, or forced on/off).

**Text and terms** — custom vocabulary and replacements, so names and jargon survive transcription.

**API keys** — stored in Windows Credential Manager under `WordArc/GeminiApiKey`, never in `config.json`. Usage counters (`Used today`, `All time`), test, reorder and one slot per row.

![API keys](./docs/screenshots/09-api-keys.png)

**Application** — theme, interface language (13 languages, English default), startup behaviour, tray behaviour, and the text selection bar.

`Save` writes the settings. Changes that affect a running recording take effect on the next one, never mid-recording.

### 8. Dark theme

![Dark theme — dictation](./docs/screenshots/07-dictation-dark.png)

![Dark theme — meeting](./docs/screenshots/08-meeting-dark.png)

Dark, light or `System` (follows the Windows setting). Every panel, table, status colour and disabled state is drawn for both themes; the layout does not shift when you switch.

---

## Install

1. Download `WordArc-<version>.exe` from [Releases](https://github.com/zeitgeist-c/WordArc/releases/latest).
2. Run it. It installs to `Program Files\WordArc` with an administrator prompt; the installer is roughly 500 MB.
3. Settings opens on first launch. Enter your Gemini API key, or select a local model.
4. Press `Ctrl+Space`, talk, press again.

GPU support is downloaded on demand — the base installer does not carry CUDA libraries. On an NVIDIA card WordArc fetches the CUDA runtime the first time you select a GPU device; on AMD it uses the bundled whisper.cpp Vulkan engine with a separate GGML model download. Previously downloaded CPU or CUDA weights stay on disk and keep working.

## Command line

```powershell
python wordarc.py             # open Settings, keep the tray service running
python wordarc.py background  # run in the background (Windows startup)
python wordarc.py toggle      # start / stop recording
python wordarc.py cancel      # discard the current recording
python wordarc.py meeting     # start / end a meeting recording
python wordarc.py settings    # open the settings window
python wordarc.py quit        # shut the application down
```

A single instance is enforced through local IPC: running `toggle` while WordArc is already open reaches the running process instead of starting a second one.

## Build from source

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements-lock.txt -r requirements-dev.txt
python wordarc.py
```

Checks and packaging:

```powershell
.\check.ps1
.\build.ps1
```

`check.ps1` runs pytest, `compileall` and an import check over every module. `build.ps1` verifies the pinned FFmpeg binary, runs the tests, audits dependencies, emits `sbom.json`, renders the deterministic icon, vendors the TTS weights, and produces the installer through PyInstaller + Inno Setup.

`build.ps1 -Cuda` additionally prepares and verifies the NVIDIA DLL set; without the flag the package carries the CPU and Vulkan engines only.

## Speech engines

| Engine | Where it runs | Notes |
|---|---|---|
| **Gemini batch / instant** | cloud | needs an API key; batch types up a finished recording, instant streams it live |
| **faster-whisper (CPU)** | local | default local path, no GPU needed |
| **faster-whisper (CUDA)** | local GPU | downloaded on demand, NVIDIA only |
| **whisper.cpp Vulkan** | local GPU | AMD path since 0.6.9, separate GGML model |

`Automatic` picks CUDA, then Vulkan, then CPU. If a GPU engine fails mid-recording, an automatic run retries the same audio on CPU; an explicit AMD/NVIDIA choice asks for consent first. Audio never leaves the machine in the local paths.

## Data and privacy

- Settings: `%APPDATA%\WordArc\config.json`
- Recordings, meetings, diagnostics, downloaded models: `%LOCALAPPDATA%\WordArc\` — speech models under `whisper`, GPU runtime under `cuda`. The installer and uninstaller never touch these.
- Gemini key: Windows Credential Manager, `WordArc/GeminiApiKey`.
- History is **off** by default. When enabled it is plain local text files.
- Successful meeting audio is deleted by default.
- No telemetry. The only network calls are the model list, the transcription request when you choose a cloud engine, and update checks.

## Project structure

```text
wordarc.py             tray app, CLI, single-instance IPC
worker.py              dictation pipeline
meeting.py             meeting pipeline
audio.py, audio_capture.py   microphone and WASAPI loopback capture
settings_ui.py         rail-navigation settings window
screenshot_capture.py  region and full-screen capture, local preview
hotkey.py              global hotkeys
api.py, cleanup         Gemini client and the cleanup pass
filetranscribe.py      audio-file transcription
livespeech.py          read-aloud
engine_discovery.py    local model discovery and selection
cuda_*.py, cuda_libs.py  CUDA detection, recovery and DLL staging
brand.py, theme.py, i18n.py  identity, theming, 13-language strings
assets/brand           canonical SVG sources and icon build
tools/                 packaging, verification and screenshot harnesses
tests/                 pytest suite
```

## Troubleshooting

- **`Ctrl+Space` does nothing** — another application owns the hotkey. Change it in the Dictation tab, or free it, then `python wordarc.py restart`.
- **Meeting has no other-side audio** — loopback capture needs an active output device. Check the Windows sound settings and that the meeting audio source is `Current output`.
- **Key rejected** — re-enter it in Settings; it is stored only in Credential Manager, so a Windows profile reset removes it.
- **GPU engine fails late** — an automatic run retries on CPU; an explicit GPU choice asks before falling back. A Vulkan-free CPU payload can use already downloaded GGML weights without another download.
- **Cleanup returns empty text** — an empty cleanup result is never pasted and never counted as success; the raw transcript is kept.

## License

GPL-3.0. The original Linux project was created by [yusufipk](https://github.com/yusufipk/dikte).
