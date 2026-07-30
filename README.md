# Dikte — Voice-to-text dictation for Windows

Press a global hotkey, speak, press again — the cleaned transcription is pasted at your cursor.

## Quick start

1. Download `dikte.exe` from Releases (or build from source).
2. Run `install.ps1` in the same folder to add a Start Menu shortcut and autostart entry.
3. Launch Dikte — the settings window opens on first run.
4. Add a Gemini or OpenRouter API key in **Settings → API**.

## Usage

| Action | Result |
|--------|--------|
| `Ctrl+Space` | Start / stop dictation |
| Speak, then `Ctrl+Space` | Transcription pasted at cursor |
| Tray → Cancel recording | Discard current recording |
| Tray → Ask assistant | Dictate a question to Claude/Codex/OpenRouter |
| Tray → Record a meeting | Stereo meeting recording (mic + system audio) |
| Tray → Settings | Configure API keys, shortcuts, language, file transcription |

## Run from source

```powershell
python -m pip install -r requirements.txt
python dikte.py
```

PyQt6, sounddevice, Python 3.10+ required.

## Build with PyInstaller

Place `ffmpeg.exe` (from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/), essentials build) in the project root, then:

```powershell
python -m pip install pyinstaller
python -m PyInstaller --onefile --windowed --add-data "ffmpeg.exe;." --collect-all sounddevice --name dikte dikte.py
```

Output: `dist\dikte.exe` (~110 MB, self-contained).

## Configuration

Stored at `%APPDATA%\Dikte\config.json`. Audio output and meeting data at `%LOCALAPPDATA%\Dikte\`.

## Upstream

Dikte was originally created by [yusufipk](https://github.com/yusufipk/dikte) for Linux (GPL-3.0). This is a Windows hard-fork with the same license.
