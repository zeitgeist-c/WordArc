# Verbatim for Windows — Design Spec

- **Date:** 2026-07-30
- **Source project:** [yusufipk/dikte](https://github.com/yusufipk/dikte) (Linux / KDE Plasma 6 / Wayland, GPL-3.0)
- **Target:** Windows 10 (22H2) and Windows 11, x64
- **Goal:** A feature-for-feature Windows port of Verbatim, a press-to-talk
  voice-to-text dictation tool. Press `Ctrl+Space`, talk, press again: the
  recording is transcribed by OpenAI or OpenRouter, cleaned up by an OpenRouter
  model, and pasted into whatever window had focus.
- **License:** GPL-3.0, inherited from the upstream project.

## 1. Approach: a Windows-only port

Three routes were considered:

- **A) Cross-platform abstraction in one codebase.** Rejected: the Linux
  modules (`pw-record`, `wl-clipboard`, `ydotool`, `/dev/input` evdev,
  `kglobalshortcutsrc`) have no Windows equivalent on the same API surface, so a
  `if windows:` branch would run through every module and the code would read
  as two programs stapled together.
- **B) A Windows-only port (chosen).** A new codebase under
  `C:\Users\user\projects\Verbatim`. Modules that are pure logic and talk only to
  the network or the filesystem are carried over nearly verbatim; the
  platform-bound modules (`audio.py`, `paste.py`, `hotkey.py`) are rewritten
  against Windows APIs. The upstream repo is the reference, not a dependency.
- **C) A fresh re-architecture.** Rejected: it would add risk and time for no
  user-visible gain.

This is a hard-fork Windows port, not a reimplementation: file names, the
module split, the public interfaces between modules, the config keys, the
prompt texts and the user-facing strings are all preserved so that anyone who
knows the Linux version recognises the Windows one.

## 2. Distribution

- Single self-contained `Verbatim.exe` built with PyInstaller (`--onefile
  --windowed`).
- No Python installation required on the user's machine.
- `ffmpeg.exe` (~70 MB) is bundled inside the executable so file transcription
  of `.mp3`/`.mp4`/`.m4a` works out of the box. Resulting `.exe` ≈ 110 MB.
- `PortAudio_64.dll` (~700 KB) is bundled so `sounddevice` works without a
  system PortAudio.
- `install.ps1` (delivered alongside the `.exe`) creates a Start Menu shortcut
  and a `Run` registry entry (or a Startup-folder shortcut) for autostart, and
  is optional — double-clicking `Verbatim.exe` is enough to run.
- During development the program also runs from source: `python Verbatim.py`.

## 3. Module-by-module change map

| File | Change | Notes |
|---|---|---|
| `api.py` | Carried over verbatim | stdlib `urllib` only; OpenAI + OpenRouter transcription and cleanup |
| `worker.py` | Carried over verbatim | transcribe → cleanup → clipboard → paste pipeline |
| `vad.py` | Carried over verbatim | silence floor + hallucination detection |
| `i18n.py` | Minor | Turkish + English string table; the `TR` dict and `t()`/`name()` helpers are carried over, but the Linux-specific error/UI strings are reworded for Windows (see §4.8) |
| `assistant.py` | Carried over verbatim | `claude -p` / `codex exec` / OpenRouter; CLIs are expected on `PATH` |
| `filetranscribe.py` | Carried over verbatim | ffmpeg subprocess; finds the bundled `ffmpeg.exe` via `sys._MEIPASS` shim |
| `meeting.py` | Minor | device-name lists now come from `audio.py`'s Windows enumerator |
| `settings_ui.py` | Minor | device lists from `audio.py`; tray icon drawn as a vector `QPixmap` instead of an icon theme |
| `overlay.py` | One line | the `X11BypassWindowManagerHint` flag is a no-op on Windows and is kept (harmless); the rest is verbatim |
| `audio.py` | **Rewritten** | `sounddevice` with the WASAPI host API; meetings use a WASAPI loopback stream for the system output |
| `paste.py` | **Rewritten** | ctypes Win32 clipboard + `SendInput` key injection; no third-party library |
| `hotkey.py` | **Rewritten** | `RegisterHotKey` via a hidden `QWidget`'s `nativeEvent`; the key is swallowed (does not reach the focused app) |
| `config.py` | Minor | paths move to `%APPDATA%\Verbatim` and `%LOCALAPPDATA%\Verbatim`; `chmod 600` is dropped (the user profile ACL already restricts access) |
| `Verbatim.py` | Minor | `os.getuid()` → `getpass.getuser()`; the `QT_QPA_PLATFORM=xcb` block is removed; `restart()` uses `subprocess.Popen` + `app.quit()` instead of `os.execv` |
| `install.sh` | Replaced by `install.ps1` | Start Menu shortcut, autostart |
| — (new) | `trayicon.py` | draws the tray icon as a vector `QPixmap` for each state (idle/recording/busy/meeting) |
| — (new) | `ffmpeg_path.py` | resolves the bundled `ffmpeg.exe` location for PyInstaller and dev runs |
| — (new) | `wasapi_loopback.py` | ctypes WASAPI loopback capture fallback for the meeting system-output side, used only when PortAudio exposes no loopback device (see §4.1) |

## 4. The rewritten Windows modules

### 4.1 `audio.py` — sounddevice (WASAPI)

`sounddevice` wraps PortAudio, which on Windows talks to WASAPI. The WASAPI
host API is selected at import time by finding the entry named `'WASAPI'` in
`sd.query_hostapis()` and setting `sd.default.hostapi` to its index (with a
fallback to the system default if WASAPI is unavailable — relevant only on
exotic hosts, not on stock Windows 10/11).

**`Recorder(QObject)`** (dictation, mono):
- `InputStream(channels=1, dtype='int16', samplerate=16000, blocksize=1024,
  callback=...)`.
- The callback computes per-chunk peak and RMS over the `int16` samples and
  appends the bytes to an in-memory buffer, mirroring the Linux `Recorder`'s
  buffer. `level` is emitted with the peak, `stopped` is emitted with
  `(wav_path, duration, rms_values)` exactly as in `worker.py`.
- `max_seconds` caps the buffer length exactly as on Linux.
- `cancel()` stops the stream and discards the buffer; `stop()` stops the
  stream, writes a WAV via the stdlib `wave` module, and emits `stopped`.
- The WAV writer is the same `write_wav()` helper, writing to `tempfile`.

**`MeetingRecorder(QObject)`** (stereo, mic + system loopback):
- Two parallel capture paths: one `InputStream` on the chosen input device
  (left channel), and one capture of the system default render endpoint
  (right channel) run through **WASAPI loopback** (`AUDCLNT_STREAMFLAGS_LOOPBACK`).
- Capturing the system output is the highest technical risk of the port, so a
  two-stage fallback is specified, tried in this order:
  1. **PortAudio WASAPI loopback input device.** PortAudio 19.7+ exposes
     loopback capture endpoints on Windows under `sd.query_devices()` when
     WASAPI is the host API. If a loopback device is available for the default
     output, it is opened as a second `InputStream`.
  2. **Direct ctypes WASAPI loopback.** If PortAudio does not surface a
     loopback device on the user's build, `audio.py` opens the default render
     endpoint with `AUDCLNT_STREAMFLAGS_LOOPBACK` directly via ctypes
     (`CoInitialize`, `IMMDeviceEnumerator`, `IAudioClient`, the loopback flag
     on `Initialize`, `IAudioCaptureClient`, a small reader thread pushing
     `int16` chunks onto the same queue as path 1). This is self-contained in a
     new `wasapi_loopback.py` helper so the rest of `audio.py` is unaffected.
  If both fail (an old build, or no default audio device), the recorder emits
  `failed("Could not start the system loopback")` exactly as the Linux version
  does when it cannot find a monitor sink — the user still gets a dictating
  dictation tool; only meetings are unavailable.
- Each capture path pushes its mono `int16` chunk into a paired queue; a writer
  thread interleaves them into a stereo `int16` stream and writes it to a
  `wave.open(path, "wb")` with `nchannels=2`, `sampwidth=2`, `framerate=16000`
  as on Linux. Writing to disk as it arrives means an hour-long meeting does
  not need to fit in memory and a crash costs only the tail.
- `levels.emit(mine, theirs)` is emitted with the two peaks, so the overlay
  draws the dual waveform the same way it does on Linux.
- `died` is emitted when PortAudio reports the device went away mid-recording,
  matching the Linux `died` signal.
- `list_sources()` enumerates input devices (`sd.query_devices()` filtered to
  `max_input_channels > 0`); `list_monitors()` is kept as a stable name for the
  loopback of the current default output (Windows has no PulseAudio-style
  monitor list, so the meeting UI does not offer a system-target dropdown — the
  loopback is always the default output, set automatically).

### 4.2 `paste.py` — ctypes Win32

Three operations, all via `ctypes.windll.user32` / `kernel32`:

- `read_clipboard()` → `bytes | None`: `OpenClipboard`, `GetClipboardData(CF_UNICODETEXT)`,
  copy, `CloseClipboard`. Returns `None` on any failure, matching the Linux
  signature.
- `copy(text)` → raises `PasteError` on failure: `GlobalAlloc(GMEM_MOVEABLE)`,
  `GlobalLock`, `memcpy` the UTF-16, `GlobalUnlock`, `OpenClipboard`,
  `EmptyClipboard`, `SetClipboardData(CF_UNICODETEXT, handle)`,
  `CloseClipboard`.
- `copy_bytes(data)` → best-effort copy of raw bytes (used to restore the
  previous clipboard contents); swallows errors as on Linux.
- `press("ctrl+v")`: parse the `+`-separated shortcut against a
  `{name: VK_code}` table (`ctrl→VK_CONTROL`, `shift→VK_SHIFT`,
  `alt→VK_MENU`, `super/meta→VK_LWIN`, letters → their `ord(upper)`), then
  `SendInput` a KEYDOWN for each modifier and the key, followed by KEYUP events
  in reverse. A `time.sleep(delay)` before sending lets the focus settle, as on
  Linux. `PasteError` when a key name is unknown.

`PasteError` is kept; `worker.py` is unchanged.

### 4.3 `hotkey.py` — RegisterHotKey

`WindowsHotkey(QObject)`:
- A hidden `QWidget` is created (never shown). Its
  `nativeEvent(event)` checks for `WM_HOTKEY` (0x0312); `wParam` is the hotkey
  id and `lParam` packs the modifiers and VK. The id is looked up to the
  binding name and `triggered.emit(name)` is fired.
- `start({"toggle": "Ctrl+Space", "ask": "Ctrl+Alt+S", "meeting": "Ctrl+Alt+M"})`:
  parse each shortcut with the same `parse_shortcut()` helper (kept from the
  Linux version), map to `MOD_CONTROL/MOD_SHIFT/MOD_ALT/MOD_WIN` and the VK
  code, and `RegisterHotKey(hwnd, id, mod, vk)`. IDs are assigned 1, 2, 3 …
  Empty bindings are skipped. Returns `False` if none parsed.
- `stop()`: `UnregisterHotKey` for every registered id.
- **The key is swallowed**: RegisterHotKey grabs the combination globally and
  the focused application does not receive it — an improvement over the Linux
  evdev listener, which let the key through. The "logout before the shortcut
  works" problem from the Linux version does not exist on Windows.
- **Conflict reporting**: if `RegisterHotKey` fails for an id, the binding is
  recorded as failed and `failed.emit(...)` names the combination and suggests
  the other application likely owns it. This replaces the Linux
  `conflicting_shortcuts()` kglobalshortcutsrc scan.
- The KDE-shortcut install/remove/status functions (`install_kde_shortcut`,
  `remove_kde_shortcut`, `kde_shortcut_status`, `conflicting_shortcuts`) are
  removed entirely; `settings_ui.py`'s Shortcut tab is simplified to "the
  shortcut is active the moment you save it, no logout needed".

### 4.4 `config.py`

- `CONFIG_DIR = Path(os.environ["APPDATA"]) / "Verbatim"`
- `DATA_DIR = Path(os.environ["LOCALAPPDATA"]) / "Verbatim"`
- `HISTORY_FILE`, `RECORDINGS_DIR`, `MEETINGS_DIR`, `MEETINGS_FILE`,
  `SESSION_FILE` all sit under `DATA_DIR`.
- `os.chmod(tmp, 0o600)` in `save()` is dropped (a no-op or error on Windows);
  the user-profile ACL already keeps the file private to the user.
- Every config key, every default, every prompt string, the legacy-prompt
  fingerprint migration and the corner-name migration are kept unchanged so a
  user's `config.json` is interchangeable between the two platforms. Keys that
  have no meaning on Windows are kept in the dict but ignored by the code:
  `meeting_system_target` (Windows always uses WASAPI loopback on the default
  render endpoint), `mic_target`/`meeting_mic_target` are read but the device
  is matched by substring rather than a PulseAudio object name. `shortcut`
  defaults to `Ctrl+Space`; `evdev_hotkey` is kept in the dict for config
  compatibility but never read on Windows (the hotkey module ignores it).
- All prompt constants (`CLEANUP_PROMPT_*`, `FILE_CLEANUP_PROMPT_*`,
  `MEETING_PROMPT_*`, `ASSISTANT_PROMPT_*`, `GLOSSARY_RULE_*`,
  `TIMESTAMP_RULE_*`, `SPEAKER_RULE_*`, `PARTICIPANTS_RULE_*`) and the
  `DEFAULTS` dict are carried over verbatim.

### 4.5 `Verbatim.py`

- `SERVER_NAME = "Verbatim-" + getpass.getuser()` (no `os.getuid()` on Windows).
  `QLocalServer`/`QLocalSocket` work as-is on Windows (named pipes).
- The `if XDG_SESSION_TYPE == "wayland": QT_QPA_PLATFORM=xcb` block is removed
  (Windows uses native Qt).
- `restart()` replaces `os.execv(...)` with `subprocess.Popen([sys.executable,
  ...])` followed by `app.quit()`. Under PyInstaller `sys.executable` is
  `Verbatim.exe`; under source it is `python.exe`.
- `launch_command()` / `meeting_command()` / `ask_command()` return
  `f'"{sys.executable}" toggle'` etc. (quoted, to survive spaces in the path).
- The tray icon is built through the new `trayicon.py` helper (see §4.6)
  instead of `QIcon.fromTheme`; otherwise the tray construction, the state
  machine, the IPC, the meeting flow and the agent flow are unchanged.

### 4.6 `trayicon.py` (new)

`QIcon.fromTheme("audio-input-microphone")` returns a null icon on Windows, so
the tray icon is drawn with `QPainter` onto a `QPixmap` for each state:

- `{name: QIcon}` cache keyed by `(state, theme)` where state ∈ idle,
  recording, busy, meeting, asking.
- drawing is a vector microphone glyph plus an overlay dot (red for recording,
  spinner arc for busy, soft blue for meeting) — the same colour vocabulary the
  overlay uses.
- No binary assets are shipped; the icon is rendered at 22×22 and scaled to the
  tray's requested size.

### 4.7 `ffmpeg_path.py` (new)

`ffmpeg()` returns the path to use:

- If `sys._MEIPASS` is set (PyInstaller frozen) and `ffmpeg.exe` exists next
  to the executable, that path.
- Otherwise, if `shutil.which("ffmpeg")` finds one on `PATH` (developer machine
  with ffmpeg installed), use it.
- Otherwise raise `api.ApiError(t("ffmpeg not found. ..."))`.

`filetranscribe.py` calls `ffmpeg_path.ffmpeg()` instead of the bare
`"ffmpeg"` string, keeping the Linux behaviour (PATH lookup) intact for source
runs and adding the bundled-binary path for the frozen build. The meeting
recorder does not use ffmpeg at all on Windows — it captures both channels
through sounddevice/WASAPI (see §4.1).

### 4.8 `i18n.py` — string rewording

The string table and the `t()`, `name()`, `resolve()`, `set_language()`,
`language()` helpers are carried over verbatim. The English **source** strings
that name Linux specifics are reworded so their Turkish translations can be
updated to match; the set of keys does not change:

| Linux source string | Windows source string |
|---|---|
| `pw-record not found. Is pipewire-audio installed?` | `Could not open the microphone.` |
| `wl-copy not found. Install wl-clipboard.` | `Could not open the clipboard.` |
| `wl-copy exited with code {code}.` | `Could not copy to the clipboard.` |
| `ydotool not found, cannot paste automatically.` | `Could not send the paste keystroke.` |
| `Could not run ydotool: {error}` | `Could not send the paste keystroke: {error}` |
| `ydotool failed: {error}\nIs ydotoold running? ...` | `Paste failed: {error}` |
| `Install as a KDE shortcut` | (removed; no KDE on Windows) |
| `Registered in KDE: {shortcut}` | `Active shortcut: {shortcut}` |
| `No KDE shortcut installed.` | `No shortcut set.` |
| `No KDE shortcut installed. The tray menu asks it too.` | `No shortcut set. The tray menu asks it too.` |
| `No KDE shortcut installed. The tray menu starts a meeting too.` | `No shortcut set. The tray menu starts a meeting too.` |
| `The KDE shortcut is live now, so the built-in listener has been turned off. ...` | (removed) |
| `Use the built-in listener (/dev/input), for when the KDE shortcut is not active yet` | (removed) |
| `Works immediately, no session restart. The only difference: the key combination also reaches the focused application.` | `Works the moment you save — no logout needed. The key does not reach the focused application.` |
| `KWin only reads shortcut settings at startup. ...` | `The shortcut is registered with Windows and takes effect immediately.` |
| `Could not write the desktop file: {error}` | (removed) |
| `Could not write kglobalshortcutsrc: {error}` | (removed) |
| `Could not parse the shortcut: {shortcut}` | `Could not parse the shortcut: {shortcut}` (kept) |
| `Cannot read /dev/input. Your user needs to be in the 'input' group: ...` | `Could not register the shortcut. Another program may already be using it: {shortcut}` |
| `Keep audio files (~/.local/share/Verbatim/recordings)` | `Keep audio files (%LOCALAPPDATA%\\Verbatim\\recordings)` |

The Turkish translations for these keys are updated to translate the new
English source text. The `CLAUDE_TOOLS`/`CODEX_ITEMS` tool-stage labels (used
by `assistant.py`) and every prompt-body string in `config.py` are unchanged.

### 4.9 `meeting.py` and `settings_ui.py` — minor edits

`meeting.py` is carried over verbatim. Its only Windows-sensitive calls are
`audio.list_sources()` / `audio.list_monitors()` indirect uses — but `meeting.py`
does not call those; `settings_ui.py` does, when building the meeting tab's
device dropdowns. So `meeting.py` needs no edits.

`settings_ui.py` edits:
- `_shortcut_tab()`: drop the "Install as a KDE shortcut" / "Remove" buttons and
  the `evdev_enabled` checkbox; replace the KWin note with the §4.8 "takes
  effect immediately" note. The shortcut is applied on Save (via the `applied`
  signal → `_apply_settings`).
- `_assistant_tab()` and `_meeting_tab()`: drop the install/remove buttons next
  to those shortcuts; the status label shows the stored shortcut ("Active
  shortcut: …" / "No shortcut set.").
- Remove the methods `_install_shortcut`, `_remove_shortcut`,
  `_refresh_shortcut_status`, `_install_ask_shortcut`, `_remove_ask_shortcut`,
  `_refresh_ask_shortcut_status`, `_install_meeting_shortcut`,
  `_remove_meeting_shortcut`, `_refresh_meeting_shortcut_status`; replace with
  simple `_refresh_shortcut_status` / `_refresh_ask_shortcut_status` /
  `_refresh_meeting_shortcut_status` that read from `self.conf`.
- The meeting "system" dropdown (`self.meeting_system`) is populated by
  `audio.list_monitors()`, which on Windows returns the single default render
  endpoint; the dropdown is otherwise unchanged.
- Device dropdowns (`self.mic`, `self.meeting_mic`) are populated by
  `audio.list_sources()`; unchanged in structure.

## 5. Feature parity checklist

Every feature listed in the upstream README is present on Windows:

- [x] `Ctrl+Space` start/stop dictation; tray icon click also stops
- [x] Cancel a recording (tray menu / `Verbatim cancel`)
- [x] Speak a command to an agent (tray menu / `Verbatim ask`): Claude Code,
      Codex, OpenRouter, with conversation continuity across dictations and a
      session timeout
- [x] Reset the agent conversation (`Verbatim ask-reset`)
- [x] Cancel the agent (`Verbatim ask-cancel`)
- [x] Meeting recording: microphone + system loopback into a stereo WAV,
      channel-based speaker labelling, minute generation by a second model,
      saved under `%LOCALAPPDATA%\Verbatim\meetings`
- [x] Meeting cancel and meeting retry-from-transcript
- [x] Audio/video file transcription with optional `[mm:ss]` timestamps,
      ffmpeg chunking for long files, `.txt` and `.srt` output, subtitle-style
      cleanup rules
- [x] History with size limit, right-click delete, and full clear
- [x] Silence detection (per-recording noise floor + absolute floor + minimum
      voiced seconds) and stock-phrase hallucination filter
- [x] Cleanup rules: a glossary of names/terms used as a transcription hint
      and as a cleanup-model glossary
- [x] Turkish and English interface, following the system locale by default
- [x] Corner overlay indicator with live waveform, elapsed time, stage label,
      multi-monitor placement, dual waveform for meetings, dismissable
      long-running jobs
- [x] Tray menu, tray notification messages, restart, IPC single-instance
- [x] Auto-paste and clipboard restore
- [x] Five settings tabs: General, API & models, Cleanup rules, Audio file,
      History (plus Meeting and Agent sections), matching the upstream layout
- [x] OpenAI and OpenRouter keys stored in `config.json`, falling back to
      `OPENAI_API_KEY` / `OPENROUTER_API_KEY` environment variables
- [x] OpenRouter key status check and model list
- [x] Autostart on login (via `install.ps1`)

## 6. Dependencies

**Runtime (third-party Python):**
- `PyQt6`
- `sounddevice` (pulls in `PortAudio_64.dll`)

**Runtime (stdlib):** `ctypes`, `urllib`, `json`, `wave`, `subprocess`,
`threading`, `tempfile`, `pathlib`, `getpass`, `os`, `sys`, `array`, `math`,
`hashlib`, `secrets`, `mimetypes`, `collections`, `re`, `contextlib`,
`shutil`. (`signal` is not used on Windows: `audio.py` stops its streams with
`sounddevice`'s `stream.stop()`, not `SIGINT`, and `filetranscribe.py` runs
ffmpeg via `subprocess.run` that completes naturally — there is no long-lived
ffmpeg child to interrupt.)

**Bundled binary:**
- `ffmpeg.exe` (~70 MB)

**Build:**
- PyInstaller (development dependency only)

## 7. Build pipeline

- `requirements.txt` pins `PyQt6` and `sounddevice`.
- `Verbatim.spec` (PyInstaller):
  - `--onefile --windowed`
  - `datas=[('ffmpeg.exe', '.')]`
  - `--collect-submodules sounddevice` and `--collect-binaries sounddevice` so
    PortAudio_64.dll is included.
  - `name='Verbatim'`, `console=False`.
- `install.ps1` (optional): copies `Verbatim.exe` to
  `%LOCALAPPDATA%\Programs\Verbatim\`, creates a Start Menu shortcut, and writes
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\Verbatim` pointing at the
  copied path.
- Build verification: `pyinstaller Verbatim.spec` produces `dist\Verbatim.exe`;
  running it should show the tray icon.

## 8. Verification plan

The upstream repo ships no tests; verification is manual, against the feature
checklist in §5:

1. WordPad open and focused: `Ctrl+Space`, speak, `Ctrl+Space` → cleaned text
   is pasted at the cursor. Tray shows "Pasted: <preview>".
2. `Ctrl+Space`, then tray → Cancel recording → no file, no paste, overlay
   hides.
3. A sub-0.3 s tap → "Recording too short" error.
4. Room-tone only recording (no speech) → "No speech detected (X dB)".
5. Ayarlar → API & models → wrong OpenAI key → "rejected the API key (HTTP
   401)" from the next dictation.
6. Ayarlar → Agent: `Ctrl+Alt+S`, speak "bugün nedir?" → Claude/Codex answer
   or OpenRouter answer pasted; second command "ya yarın?" carries context.
7. Meeting: record ~30 s, stop → `%LOCALAPPDATA%\Verbatim\meetings\<base>.md`
   written with headed sections; tray notification appears.
8. Meeting with the mic unplugged mid-recording → "the recording stopped on
   its own" warning, partial WAV kept.
9. Settings → Audio file: drop a `.mp3` in, enable timestamps, choose `.srt`
   → output file has SRT cues with shifted timestamps.
10. Settings → History: shows the entry from step 1; right-click → Delete
    removes it; Size limit trims oldest beyond it.
11. Settings → General → UI language toggle TR/EN → all strings switch.
12. Hotkey conflict: set another app to grab `Ctrl+Space`, run Verbatim → the
    shortcut tab reports the conflict and stays usable from the tray.
13. Restart from the tray menu relaunches `Verbatim.exe` cleanly.
14. Build: `pyinstaller Verbatim.spec` on a clean checkout produces a
    double-clickable `dist\Verbatim.exe` that passes steps 1, 7 and 9.

## 9. Risks and mitigations

- **`claude` / `codex` not on `PATH`.** The agent flow already raises
  `AssistantError` naming the missing binary and pointing to Settings → Agent.
  Windows installers for both CLIs put them on `PATH`; the message is the
  safety net.
- **`Ctrl+Space` IME conflict.** Some East-Asian IMEs use `Ctrl+Space` to
  switch input methods. RegisterHotKey still grabs it, but the IME stops
  switching; the shortcut default remains `Ctrl+Space` and the conflict, if
  hit, is resolved by changing the shortcut in Settings, as on Linux.
- **WASAPI loopback (meeting system side).** PortAudio does not always expose
  a loopback input device; the spec mandates a ctypes WASAPI fallback (§4.1)
  so meetings work on the stock drivers. On older Windows 10 builds where
  neither path lands, the recorder reports "Could not start the system
  loopback" rather than crashing — dictation is unaffected. This is the
  primary technical risk and the first thing to verify during implementation.
- **`os.execv`/restart.** Replaced by `Popen + quit`, which is the idiomatic
  Windows way to relaunch a GUI process.
- **PyInstaller onefile startup time.** ~1–2 s while the bundled ffmpeg is
  unpacked; a splash screen is optional and not in scope.
- **Single-instance IPC.** `QLocalServer` uses a named pipe on Windows
  (`\\.\pipe\Verbatim-<user>`); the `UserAccessOption` socket option maps to a
  pipe ACL that keeps it to the current user, matching the Linux intent.

## 10. Out of scope

- A cross-platform single codebase (deliberate non-goal; see §1).
- Linux/macOS support in this codebase.
- An MSI/WiX installer (the single `.exe` plus optional `install.ps1` covers
  the need).
- Auto-update of the `.exe` itself.
- Translation into languages beyond Turkish and English.
- A splash screen during the PyInstaller onefile unpack.
- Changing the prompt texts, defaults or config schema relative to the
  upstream project — the Windows port keeps the user's data interchangeable.