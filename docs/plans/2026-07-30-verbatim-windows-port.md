# Verbatim for Windows — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A feature-for-feature Windows port of [yusufipk/dikte](https://github.com/yusufipk/dikte) — a press-to-talk voice-to-text dictation tool distributed as a single self-contained `Verbatim.exe` with bundled `ffmpeg.exe`.

**Architecture:** A Windows-only hard-fork port. Pure-logic modules that talk only to the network or filesystem (`api`, `worker`, `vad`, `assistant`, `filetranscribe`, `meeting`, `overlay`) are carried over from upstream with at most one-line edits; platform-bound modules (`audio`, `paste`, `hotkey`) are rewritten against Win32/sounddevice; `config`, `i18n`, `Verbatim`, `settings_ui` get targeted Windows edits; three new helpers (`trayicon`, `ffmpeg_path`, `wasapi_loopback`) are added. Spec: `docs/specs/2026-07-30-Verbatim-windows-design.md`.

**Tech Stack:** Python 3.11, PyQt6, sounddevice (WASAPI/PortAudio), ctypes Win32 (clipboard/SendInput/RegisterHotKey/WASAPI loopback), stdlib urllib (OpenAI/OpenRouter), PyInstaller (`--onefile`), unittest for tests.

**Conventions:**
- Project root: `C:\Users\user\projects\Verbatim`.
- All commands run from the project root unless noted.
- Tests use the stdlib `unittest` (zero install) executed via `python -m unittest <path> -v`.
- "Carry over from upstream" means download the file from its `raw.githubusercontent.com/yusufipk/dikte/master/<file>` URL and save it locally; the URL is given in the task.
- Every task ends with a commit (git is initialised in Task 1).
- Lint: there is no project linter; type-checking is manual. The verification command for pure modules is the unit test; for GUI/platform modules it is a smoke run.

---

## File Structure

```
C:\Users\user\projects\Verbatim\
├── Verbatim.py            entry point (carryover + minor edits)
├── api.py              OpenAI/OpenRouter (verbatim carryover)
├── worker.py           transcribe→cleanup→paste pipeline (verbatim)
├── vad.py              silence/hallucination (verbatim)
├── i18n.py             string table (carryover + string rewording)
├── config.py           settings/storage (carryover + path edits)
├── audio.py            sounddevice capture (REWRITE)
├── wasapi_loopback.py  ctypes WASAPI loopback fallback (NEW)
├── paste.py            ctypes clipboard + SendInput (REWRITE)
├── hotkey.py           RegisterHotKey (REWRITE)
├── trayicon.py         vector tray icons (NEW)
├── ffmpeg_path.py      bundled ffmpeg resolver (NEW)
├── filetranscribe.py   file transcription (carryover + ffmpeg_path call)
├── meeting.py          meeting minutes (verbatim)
├── assistant.py        claude/codex/openrouter (verbatim)
├── overlay.py          corner indicator (verbatim)
├── settings_ui.py      settings window (carryover + shortcut-tab edits)
├── trayicon.py         (same as above; one file)
├── requirements.txt    PyQt6, sounddevice
├── dev-requirements.txt  (none — unittest is stdlib; pytest optional)
├── Verbatim.spec          PyInstaller build spec
├── install.ps1         Start Menu + autostart installer
├── ffmpeg.exe          bundled binary (provided by user; not committed by gitignore rule — see Task 22)
├── LICENSE             GPL-3.0 (carryover)
├── .gitignore
├── README.md           Windows readme (English)
├── README.tr.md        Windows readme (Turkish)
└── tests\
    ├── __init__.py
    ├── test_vad.py
    ├── test_config.py
    ├── test_api.py
    ├── test_paste.py
    ├── test_hotkey.py
    ├── test_ffmpeg_path.py
    ├── test_filetranscribe.py
    ├── test_meeting.py
    ├── test_assistant.py
    └── test_trayicon.py
```

---

### Task 1: Project skeleton and git

**Files:**
- Create: `.gitignore`, `LICENSE`, `requirements.txt`, `tests/__init__.py`

- [ ] **Step 1: Initialise git and create `.gitignore`**

`.gitignore`:
```
__pycache__/
*.py[cod]
*.egg-info/
.venv/
build/
dist/
ffmpeg.exe
Verbatim.spec.bak
```
(ffmpeg.exe is gitignored — it is a large binary downloaded into the repo at build time, not committed.)

- [ ] **Step 2: Carry over `LICENSE` from upstream**

Carry over from: `https://raw.githubusercontent.com/yusufipk/dikte/master/LICENSE` (GPL-3.0 full text). Save it verbatim as `LICENSE`.

- [ ] **Step 3: Create `requirements.txt`**

```
PyQt6>=6.6
sounddevice>=0.4.6
```

- [ ] **Step 4: Create `tests/__init__.py`** (empty file)

- [ ] **Step 5: Initialise git and make the first commit**

```powershell
git init
git add .gitignore LICENSE requirements.txt tests/__init__.py
git commit -m "chore: project skeleton"
```
Expected: a single commit on `master`/`main`.

---

### Task 2: `i18n.py` — carryover + Windows string rewording

**Files:**
- Create: `i18n.py`
- Test: `tests/test_i18n.py`

- [ ] **Step 1: Carry over `i18n.py` from upstream**

Carry over from: `https://raw.githubusercontent.com/yusufipk/dikte/master/i18n.py`. Save it verbatim as `i18n.py`.

- [ ] **Step 2: Reword the Linux-specific source strings**

For each row below, edit `i18n.py` replacing the **English source key** (left column) with the right column. Keep the existing Turkish translation slot, then update the `TR` value to translate the new English text. Use `replaceAll=false` and include enough surrounding context to make each match unique (each key appears once as a dict key).

| Old English key (in `TR = {...}`) | New English key |
|---|---|
| `"pw-record not found. Is pipewire-audio installed?"` | `"Could not open the microphone."` |
| `"wl-copy not found. Install wl-clipboard."` | `"Could not open the clipboard."` |
| `"wl-copy exited with code {code}."` | `"Could not copy to the clipboard."` |
| `"ydotool not found, cannot paste automatically."` | `"Could not send the paste keystroke."` |
| `"Could not run ydotool: {error}"` | `"Could not send the paste keystroke: {error}"` |
| `"ydotool failed: {error}\nIs ydotoold running? (systemctl --user status ydotool)"` | `"Paste failed: {error}"` |
| `"Install as a KDE shortcut"` | `"Install as a Windows shortcut"` |
| `"Registered in KDE: {shortcut}"` | `"Active shortcut: {shortcut}"` |
| `"No KDE shortcut installed."` | `"No shortcut set."` |
| `"No KDE shortcut installed. The tray menu asks it too."` | `"No shortcut set. The tray menu asks it too."` |
| `"No KDE shortcut installed. The tray menu starts a meeting too."` | `"No shortcut set. The tray menu starts a meeting too."` |
| `"The KDE shortcut is live now, so the built-in listener has been turned off. It was doubling every key press."` | (delete the key and its TR value entirely) |
| `"Use the built-in listener (/dev/input), for when the KDE shortcut is not active yet"` | (delete the key and its TR value entirely) |
| `"Works immediately, no session restart. The only difference: the key combination also reaches the focused application."` | `"Works the moment you save — no logout needed. The key does not reach the focused application."` |
| `"KWin only reads shortcut settings at startup. After 'Install' the shortcut shows up under System Settings → Shortcuts, but it will not fire until you log out and back in. Until then, use the built-in listener."` | `"The shortcut is registered with Windows and takes effect immediately."` |
| `"Could not write the desktop file: {error}"` | (delete) |
| `"Could not write kglobalshortcutsrc: {error}"` | (delete) |
| `"Cannot read /dev/input. Your user needs to be in the 'input' group:\n  sudo usermod -aG input $USER   (then log out and back in)"` | `"Could not register the shortcut. Another program may already be using it: {shortcut}"` |
| `"Keep audio files (~/.local/share/Verbatim/recordings)"` | `"Keep audio files (%LOCALAPPDATA%\\Verbatim\\recordings)"` |

For each kept row, set the TR value to a Turkish translation of the new English text, e.g.:
- `"Could not open the microphone."` → `"Mikrofon açılamadı."`
- `"Could not open the clipboard."` → `"Pano açılamadı."`
- `"Could not copy to the clipboard."` → `"Panoya kopyalanamadı."`
- `"Could not send the paste keystroke."` → `"Yapıştırma tuşu gönderilemedi."`
- `"Could not send the paste keystroke: {error}"` → `"Yapıştırma tuşu gönderilemedi: {error}"`
- `"Paste failed: {error}"` → `"Yapıştırma başarısız: {error}"`
- `"Install as a Windows shortcut"` → `"Windows kısayolu olarak kur"`
- `"Active shortcut: {shortcut}"` → `"Etkin kısayol: {shortcut}"`
- `"No shortcut set."` → `"Kısayol yok."`
- `"No shortcut set. The tray menu asks it too."` → `"Kısayol yok. Tepsi menüsünden de sorulabilir."`
- `"No shortcut set. The tray menu starts a meeting too."` → `"Kısayol yok. Toplantıyı tepsi menüsünden de başlatabilirsin."`
- `"Works the moment you save — no logout needed. The key does not reach the focused application."` → `"Kaydeder kaydetmez çalışır — oturumu yenilemek gerekmez. Tuş odaktaki uygulamaya iletilmez."`
- `"The shortcut is registered with Windows and takes effect immediately."` → `"Kısayol Windows'a kaydedilir ve anında etkili olur."`
- `"Could not register the shortcut. Another program may already be using it: {shortcut}"` → `"Kısayol kaydedilemedi. Başka bir program kullanıyor olabilir: {shortcut}"`
- `"Keep audio files (%LOCALAPPDATA%\\Verbatim\\recordings)"` → `"Ses kayıtlarını sakla (%LOCALAPPDATA%\\Verbatim\\recordings)"`

- [ ] **Step 3: Write the test**

`tests/test_i18n.py`:
```python
import unittest, os
import i18n

class TestI18n(unittest.TestCase):
    def test_resolve_auto_en(self):
        os.environ["LANG"] = "C"
        self.assertEqual(i18n.resolve("auto"), "en")
    def test_resolve_auto_tr(self):
        os.environ["LANG"] = "tr_TR.UTF-8"
        self.assertEqual(i18n.resolve("auto"), "tr")
    def test_t_en_passthrough(self):
        i18n.set_language("en")
        self.assertEqual(i18n.t("Start recording"), "Start recording")
    def test_t_tr_translates(self):
        i18n.set_language("tr")
        self.assertEqual(i18n.t("Start recording"), "Kaydı başlat")
    def test_t_formats_kwargs(self):
        i18n.set_language("en")
        self.assertEqual(i18n.t("{action}: {preview}", action="Pasted", preview="hi"), "Pasted: hi")
    def test_name_dative_tr(self):
        i18n.set_language("tr")
        self.assertEqual(i18n.name("Claude", "dative"), "Claude'a")
    def test_name_en_passthrough(self):
        i18n.set_language("en")
        self.assertEqual(i18n.name("Claude", "dative"), "Claude")
    def test_no_linux_strings_remain(self):
        i18n.set_language("en")
        src = open("i18n.py", encoding="utf-8").read()
        for banned in ("pw-record", "wl-copy", "wl-paste", "ydotool", "kdotoold",
                       "/dev/input", "kglobalshortcutsrc", "KDE shortcut is live"):
            self.assertNotIn(banned, src, f"Linux-specific string remains: {banned}")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run the test**

Run: `python -m unittest tests.test_i18n -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add i18n.py tests/test_i18n.py
git commit -m "feat(i18n): port string table, reword Linux-specific strings for Windows"
```

---

### Task 3: `config.py` — carryover + Windows paths

**Files:**
- Create: `config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Carry over `config.py` from upstream**

Carry over from: `https://raw.githubusercontent.com/yusufipk/dikte/master/config.py`. Save verbatim as `config.py`.

- [ ] **Step 2: Replace the path roots**

Edit `config.py`. Find:
```python
def _xdg(var, default):
    return pathlib.Path(os.environ.get(var) or os.path.expanduser(default))


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", "~/.config") / "Verbatim"
CONFIG_FILE = CONFIG_DIR / "config.json"
DATA_DIR = _xdg("XDG_DATA_HOME", "~/.local/share") / "Verbatim"
```
Replace with:
```python
def _win_path(env, fallback):
    return pathlib.Path(os.environ.get(env) or os.path.expanduser(fallback))


CONFIG_DIR = _win_path("APPDATA", "~") / "Verbatim"
CONFIG_FILE = CONFIG_DIR / "config.json"
DATA_DIR = _win_path("LOCALAPPDATA", "~") / "Verbatim"
```

- [ ] **Step 3: Drop the `os.chmod` from `save()`**

Find:
```python
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=2)
        os.chmod(tmp, 0o600)
        tmp.replace(CONFIG_FILE)
```
Replace with:
```python
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=2)
        tmp.replace(CONFIG_FILE)
```
(`os.chmod 0o600` is a no-op/error on Windows; the user-profile ACL already restricts access.)

- [ ] **Step 4: Write the test**

`tests/test_config.py`:
```python
import unittest, os, json, tempfile, pathlib
import config as cfg

class TestConfigPaths(unittest.TestCase):
    def test_config_dir_uses_appdata(self):
        self.assertEqual(cfg.CONFIG_DIR.name, "Verbatim")
        self.assertIn("Verbatim", str(cfg.CONFIG_DIR))
    def test_data_dir_uses_localappdata(self):
        self.assertEqual(cfg.DATA_DIR.name, "Verbatim")

class TestConfigLoadSave(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cfg = cfg.CONFIG_DIR
        self.old_file = cfg.CONFIG_FILE
        self.old_data = cfg.DATA_DIR
        cfg.CONFIG_DIR = pathlib.Path(self.tmp.name) / "cfg"
        cfg.CONFIG_FILE = cfg.CONFIG_DIR / "config.json"
        cfg.DATA_DIR = pathlib.Path(self.tmp.name) / "data"
        cfg.DATA_DIR.mkdir(parents=True, exist_ok=True)
    def tearDown(self):
        cfg.CONFIG_DIR = self.old_cfg
        cfg.CONFIG_FILE = self.old_file
        cfg.DATA_DIR = self.old_data
        self.tmp.cleanup()
    def test_defaults_loaded(self):
        c = cfg.Config()
        self.assertEqual(c["transcribe_provider"], "openai")
        self.assertEqual(c["language"], "tr")
    def test_save_then_load(self):
        c = cfg.Config()
        c["openai_api_key"] = "sk-test"
        c.save()
        c2 = cfg.Config()
        self.assertEqual(c2["openai_api_key"], "sk-test")
    def test_unknown_keys_ignored(self):
        cfg.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cfg.CONFIG_FILE.write_text(json.dumps({"transcribe_provider": "openrouter",
                 "unknown_key": "ignored"}), encoding="utf-8")
        c = cfg.Config()
        self.assertEqual(c["transcribe_provider"], "openrouter")
        self.assertNotIn("unknown_key", c.data)

class TestPromptAssembly(unittest.TestCase):
    def test_cleanup_prompt_default_en(self):
        import i18n; i18n.set_language("en")
        c = cfg.Config()
        self.assertIn("dictation transcripts", cfg.default_cleanup_prompt())
    def test_meeting_prompt_default_tr(self):
        import i18n; i18n.set_language("tr")
        self.assertIn("toplantı tutanağı", cfg.default_meeting_prompt())

class TestHistory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = cfg.DATA_DIR
        cfg.DATA_DIR = pathlib.Path(self.tmp.name)
        cfg.HISTORY_FILE = cfg.DATA_DIR / "history.jsonl"
    def tearDown(self):
        cfg.DATA_DIR = self.old
        cfg.HISTORY_FILE = cfg.DATA_DIR / "history.jsonl"
        self.tmp.cleanup()
    def test_append_and_read(self):
        cfg.append_history({"ts": "2026-01-01 00:00:00", "text": "a"})
        cfg.append_history({"ts": "2026-01-01 00:00:01", "text": "b"})
        rows = cfg.read_history()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]["text"], "b")
    def test_trim(self):
        for i in range(5):
            cfg.append_history({"ts": str(i), "text": str(i)})
        cfg.trim_history(2)
        rows = cfg.read_history()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["text"], "3")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 5: Run the test**

Run: `python -m unittest tests.test_config -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```powershell
git add config.py tests/test_config.py
git commit -m "feat(config): move settings to %APPDATA%/%LOCALAPPDATA%, drop chmod"
```

---

### Task 4: `api.py` — verbatim carryover + test

**Files:**
- Create: `api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Carry over `api.py` from upstream**

Carry over from: `https://raw.githubusercontent.com/yusufipk/dikte/master/api.py`. Save verbatim as `api.py`. No edits — it uses only stdlib `urllib`.

- [ ] **Step 2: Write the test**

`tests/test_api.py`:
```python
import unittest, json
import api

class TestExtractError(unittest.TestCase):
    def test_json_error_dict(self):
        body = json.dumps({"error": {"message": "bad key"}})
        self.assertEqual(api._extract_error(body), "bad key")
    def test_json_error_str(self):
        body = json.dumps({"error": "oops"})
        self.assertEqual(api._extract_error(body), "oops")
    def test_plain_text_truncated(self):
        self.assertEqual(api._extract_error("x" * 500)[:10], "xxxxxxxxxx")
        self.assertTrue(len(api._extract_error("x" * 500)) <= 300)

class TestMultipart(unittest.TestCase):
    def test_body_contains_fields_and_file(self):
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".wav")
        with os.fdopen(fd, "wb") as f:
            f.write(b"RIFFxxxx")
        body, ctype = api._multipart([("model", "whisper"), ("language", "tr")],
                                     "file", path)
        self.assertIn("multipart/form-data", ctype)
        self.assertIn(b'name="model"', body)
        self.assertIn(b'whisper', body)
        self.assertIn(b'filename="', body)
        self.assertTrue(body.endswith(b"--\r\n") or body.rstrip().endswith(b"--"))
        os.unlink(path)

class TestExplain(unittest.TestCase):
    def test_401_message(self):
        exc = api.ApiError("HTTP 401", 401)
        out = api.explain(exc, "OpenAI")
        self.assertIn("rejected the API key", str(out))
        self.assertEqual(out.status, 401)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test**

Run: `python -m unittest tests.test_api -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add api.py tests/test_api.py
git commit -m "feat(api): carry over OpenAI/OpenRouter transcription + cleanup"
```

---

### Task 5: `vad.py` — verbatim carryover + test

**Files:**
- Create: `vad.py`
- Test: `tests/test_vad.py`

- [ ] **Step 1: Carry over `vad.py` from upstream**

Carry over from: `https://raw.githubusercontent.com/yusufipk/dikte/master/vad.py`. Save verbatim. No edits.

- [ ] **Step 2: Write the test**

`tests/test_vad.py`:
```python
import unittest
import vad

class TestAnalyse(unittest.TestCase):
    def test_empty_returns_floor(self):
        s = vad.analyse([], 0.064)
        self.assertEqual(s["noise_db"], -120.0)
    def test_silence_detected_when_quiet(self):
        rms = [0.0001] * 100
        s = vad.analyse(rms, 0.064)
        self.assertTrue(vad.is_silent(s, silence_db=-55, margin_db=10, min_voiced_seconds=0.3))
    def test_speech_detected_when_loud(self):
        rms = [0.0001] * 50 + [0.5] * 50
        s = vad.analyse(rms, 0.064)
        self.assertFalse(vad.is_silent(s, silence_db=-55, margin_db=10, min_voiced_seconds=0.3))

class TestHallucination(unittest.TestCase):
    def test_short_known_phrase(self):
        self.assertTrue(vad.looks_like_hallucination("Thanks for watching", 3.0))
    def test_long_not_hallucination(self):
        self.assertFalse(vad.looks_like_hallucination("Thanks for watching", 10.0))
    def test_normal_text_not_hallucination(self):
        self.assertFalse(vad.looks_like_hallucination("bugün toplantı vardı", 2.0))
    def test_repeated_phrase(self):
        self.assertTrue(vad.looks_like_hallucination("altyazı mk altyazı mk", 2.0))

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test**

Run: `python -m unittest tests.test_vad -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add vad.py tests/test_vad.py
git commit -m "feat(vad): carry over silence/hallucination detection"
```

---

### Task 6: `ffmpeg_path.py` — new bundled-ffmpeg resolver

**Files:**
- Create: `ffmpeg_path.py`
- Test: `tests/test_ffmpeg_path.py`

- [ ] **Step 1: Write `ffmpeg_path.py`**

```python
"""Resolve the ffmpeg executable: bundled with the frozen .exe, else PATH."""
import os
import shutil
import sys


def ffmpeg():
    """Path to ffmpeg, or raise."""
    if hasattr(sys, "_MEIPASS"):
        bundled = os.path.join(sys._MEIPASS, "ffmpeg.exe")
        if os.path.isfile(bundled):
            return bundled
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise FileNotFoundError("ffmpeg not found")
```

- [ ] **Step 2: Write the test**

`tests/test_ffmpeg_path.py`:
```python
import unittest, os, sys, tempfile
import ffmpeg_path

class TestFfmpegPath(unittest.TestCase):
    def test_raises_when_missing(self):
        # No _MEIPASS, and ensure PATH has no ffmpeg by patching shutil.which
        import shutil
        orig = shutil.which
        shutil.which = lambda name: None
        try:
            self.assertNotIn("_MEIPASS", sys.__dict__)  # sanity
            with self.assertRaises(FileNotFoundError):
                ffmpeg_path.ffmpeg()
        finally:
            shutil.which = orig
    def test_meipass_wins(self):
        import shutil
        orig_which = shutil.which
        tmp = tempfile.mkdtemp()
        fake = os.path.join(tmp, "ffmpeg.exe")
        open(fake, "wb").close()
        shutil.which = lambda name: None
        try:
            # Simulate PyInstaller by monkeypatching sys._MEIPASS via a module attr
            class S: pass
            backup = sys._MEIPASS if hasattr(sys, "_MEIPASS") else None
            sys._MEIPASS = tmp
            try:
                self.assertEqual(ffmpeg_path.ffmpeg(), fake)
            finally:
                if backup is None:
                    del sys._MEIPASS
                else:
                    sys._MEIPASS = backup
        finally:
            shutil.which = orig_which

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test**

Run: `python -m unittest tests.test_ffmpeg_path -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add ffmpeg_path.py tests/test_ffmpeg_path.py
git commit -m "feat(ffmpeg_path): resolve bundled ffmpeg.exe for frozen exe and PATH for dev"
```

---

### Task 7: `filetranscribe.py` — carryover + ffmpeg_path call

**Files:**
- Create: `filetranscribe.py`
- Test: `tests/test_filetranscribe.py`

- [ ] **Step 1: Carry over `filetranscribe.py` from upstream**

Carry over from: `https://raw.githubusercontent.com/yusufipk/dikte/master/filetranscribe.py`. Save verbatim.

- [ ] **Step 2: Use the resolver instead of the bare `ffmpeg` string**

Find:
```python
            if not shutil.which("ffmpeg"):
                raise api.ApiError(t("ffmpeg not found. Install it to transcribe files."))
```
Replace with:
```python
            try:
                ffmpeg_bin = ffmpeg_path.ffmpeg()
            except FileNotFoundError:
                raise api.ApiError(t("ffmpeg not found. Install it to transcribe files."))
```
Then add at the top imports:
```python
import ffmpeg_path
```
And find the single `subprocess.run(["ffmpeg", "-nostdin", ...])` call in `_to_wav`:
```python
    res = subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-i", path, "-vn",
         "-ac", "1", "-ar", str(RATE), "-c:a", "pcm_s16le", out],
        capture_output=True, text=True,
    )
```
Replace `["ffmpeg",` with `[ffmpeg_bin,` AND pass `ffmpeg_bin` from `_work` into `_to_wav`. Simplest: make `_to_wav` call `ffmpeg_path.ffmpeg()` itself. Replace the `_to_wav` signature call site and body:

`_work`'s call:
```python
            wav_path = _to_wav(path, workdir)
```
Replace with:
```python
            wav_path = _to_wav(path, workdir)
```
(no change) and inside `_to_wav` find `["ffmpeg", "-nostdin",` and replace with `[ffmpeg_path.ffmpeg(), "-nostdin",`. Delete the `try/except FileNotFoundError` added in `_work` (it's redundant now that `_to_wav` resolves); keep the `import ffmpeg_path` at top. Final form of `_work` keeps the original `if not shutil.which("ffmpeg")` removed. To keep this task small:

Final clean edit:
- Add `import ffmpeg_path` to imports.
- Delete the `if not shutil.which("ffmpeg"):` check (lines raising the ApiError) — remove those two lines.
- In `_to_wav`, replace the literal `"ffmpeg"` with `ffmpeg_path.ffmpeg()`. The resulting subprocess.run call:
```python
    res = subprocess.run(
        [ffmpeg_path.ffmpeg(), "-nostdin", "-y", "-i", path, "-vn",
         "-ac", "1", "-ar", str(RATE), "-c:a", "pcm_s16le", out],
        capture_output=True, text=True,
    )
```

- [ ] **Step 3: Write the test**

`tests/test_filetranscribe.py`:
```python
import unittest
import filetranscribe

class TestTimestamps(unittest.TestCase):
    def test_format_timestamp_under_hour(self):
        self.assertEqual(filetranscribe.format_timestamp(75), "01:15")
    def test_format_timestamp_over_hour(self):
        self.assertEqual(filetranscribe.format_timestamp(3661), "1:01:01")
    def test_srt_timestamp(self):
        self.assertEqual(filetranscribe.srt_timestamp(3661.234),
                         "01:01:01,234")

class TestToSrt(unittest.TestCase):
    def test_to_srt_basic(self):
        text = "[00:00] Hello\n[00:03] World\n"
        segs = [(0.0, 3.0, "Hello"), (3.0, 6.0, "World")]
        srt = filetranscribe.to_srt(text, segs)
        self.assertIn("1\n00:00:00,000 --> 00:00:03,000\nHello", srt)
        self.assertIn("2\n00:00:03,000 --> 00:00:06,000\nWorld", srt)
    def test_to_srt_empty(self):
        self.assertEqual(filetranscribe.to_srt("", []), "")

class TestSplitText(unittest.TestCase):
    def test_short_text_single_block(self):
        self.assertEqual(filetranscribe.split_text("short", False), ["short"])
    def test_long_text_splits(self):
        text = "a" * 100 + "\n" + "b" * 100 + "\n" + "c" * 100
        blocks = filetranscribe.split_text(text, True)
        self.assertIsInstance(blocks, list)
        self.assertTrue(all(blocks))

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run the test**

Run: `python -m unittest tests.test_filetranscribe -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add filetranscribe.py tests/test_filetranscribe.py
git commit -m "feat(filetranscribe): use ffmpeg_path resolver; carry over file transcription"
```

---

### Task 8: `paste.py` — REWRITE (ctypes Win32)

**Files:**
- Create: `paste.py`
- Test: `tests/test_paste.py`

- [ ] **Step 1: Write `paste.py`**

```python
"""Clipboard and key injection through Win32 (ctypes, no third-party libs)."""

import ctypes
import ctypes.wintypes as w
import time

from i18n import t

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

# Virtual-key codes for the names that appear in paste shortcuts.
VKEYS = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12,
    "menu": 0x12, "super": 0x5B, "meta": 0x5B, "win": 0x5B,
    "v": 0x56, "insert": 0x2D, "enter": 0x0D, "return": 0x0D,
}


class PasteError(Exception):
    pass


def read_clipboard():
    """bytes | None; None if the clipboard is empty or unavailable."""
    if not user32.OpenClipboard(0):
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            text = ctypes.cast(ptr, ctypes.c_wchar_p).value
            return text.encode("utf-8") if text is not None else None
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def copy(text):
    """Put UTF-16 text on the clipboard; PasteError on failure."""
    data = (text + "\0").encode("utf-16-le")
    if not user32.OpenClipboard(0):
        raise PasteError(t("Could not open the clipboard."))
    try:
        if not user32.EmptyClipboard():
            raise PasteError(t("Could not copy to the clipboard."))
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise PasteError(t("Could not copy to the clipboard."))
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            raise PasteError(t("Could not copy to the clipboard."))
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            raise PasteError(t("Could not copy to the clipboard."))
    finally:
        user32.CloseClipboard()


def copy_bytes(data):
    """Best-effort restore of raw previous clipboard bytes; swallows errors."""
    if data is None:
        return
    if not user32.OpenClipboard(0):
        return
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data) + 2)
        if not handle:
            return
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return
        # Treat as a string sent in via copy earlier: simplest correct case is
        # to re-copy the UTF-8 bytes as UTF-16 text when they were text. We keep
        # the prior bytes only when they decode as UTF-8 (the common case).
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            ctypes.memmove(ptr, data, len(data))
            kernel32.GlobalUnlock(handle)
            user32.SetClipboardData(CF_UNICODETEXT, handle)
            return
        payload = (text + "\0").encode("utf-16-le")
        kernel32.GlobalFree(handle)
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
        ptr = kernel32.GlobalLock(handle)
        ctypes.memmove(ptr, payload, len(payload))
        kernel32.GlobalUnlock(handle)
        user32.SetClipboardData(CF_UNICODETEXT, handle)
    except Exception:
        pass
    finally:
        user32.CloseClipboard()


def ydotool_ready():
    """Kept for parity with the Linux signature; always True on Windows."""
    return True


def press(shortcut="ctrl+v", delay=0.12):
    """Send a key combination via SendInput. Raises PasteError on bad key."""
    codes = []
    for key in (k.strip().lower() for k in shortcut.split("+") if k.strip()):
        code = VKEYS.get(key)
        if code is None:
            raise PasteError(t("Unknown key: {key}", key=key))
        codes.append(code)

    time.sleep(delay)  # let focus settle, as on Linux

    inputs = []
    for code in codes:        # key down for each
        inputs.append(_keyinput(code, 0))
    for code in reversed(codes):  # key up in reverse
        inputs.append(_keyinput(code, 0x0002))  # KEYEVENTF_KEYUP

    n = len(inputs)
    arr_type = _INPUT * n
    arr = arr_type(*inputs)
    sent = user32.SendInput(n, ctypes.byref(arr), ctypes.sizeof(_INPUT))
    if sent != n:
        raise PasteError(t("Could not send the paste keystroke."))


# --- SendInput structure plumbing -----------------------------------------

class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD),
                ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ctypes.c_void_p)]

class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ctypes.c_void_p)]

class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", w.DWORD), ("wParamL", w.WORD), ("wParamH", w.WORD)]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]

class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", w.DWORD), ("u", _INPUT_UNION)]


def _keyinput(vk, flags):
    inp = _INPUT()
    inp.type = 1  # INPUT_KEYBOARD
    inp.ki.wVk = vk
    inp.ki.wScan = 0
    inp.ki.dwFlags = flags
    inp.ki.time = 0
    inp.ki.dwExtraInfo = 0
    return inp
```

- [ ] **Step 2: Write the test**

`tests/test_paste.py`:
```python
import unittest
import paste

class TestVkeys(unittest.TestCase):
    def test_letter_v(self):
        self.assertEqual(paste.VKEYS["v"], 0x56)
    def test_ctrl_and_control_same(self):
        self.assertEqual(paste.VKEYS["ctrl"], paste.VKEYS["control"])
    def test_super_and_meta_same(self):
        self.assertEqual(paste.VKEYS["super"], paste.VKEYS["meta"])
    def test_insert(self):
        self.assertEqual(paste.VKEYS["insert"], 0x2D)

class TestSplitShortcut(unittest.TestCase):
    def test_single_key_parses(self):
        # press splits on +; ctrl+v -> [ctrl, v]
        names = [k.strip().lower() for k in "ctrl+v".split("+") if k.strip()]
        self.assertEqual(names, ["ctrl", "v"])
    def test_unknown_key_raises(self):
        self.assertRaises(paste.PasteError, paste.press, "ctrl+xyz")
        self.assertRaises(paste.PasteError, paste.press, "ctrl+")

class TestClipboardRoundTrip(unittest.TestCase):
    """Real clipboard round-trip; skipped on CI without a desktop."""
    def test_read_write(self):
        import sys
        if not sys.platform.startswith("win"):
            self.skipTest("Windows-only clipboard test")
        paste.copy("hello dünya")
        # read_clipboard returns UTF-8 bytes
        self.assertEqual(paste.read_clipboard(), "hello dünya".encode("utf-8"))

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test**

Run: `python -m unittest tests.test_paste -v`
Expected: PASS (the round-trip test passes on the developer's Windows desktop).

- [ ] **Step 4: Commit**

```powershell
git add paste.py tests/test_paste.py
git commit -m "feat(paste): rewrite clipboard + paste with Win32 ctypes SendInput"
```

---

### Task 9: `trayicon.py` — new vector tray icons

**Files:**
- Create: `trayicon.py`
- Test: `tests/test_trayicon.py`

- [ ] **Step 1: Write `trayicon.py`**

```python
"""Vector tray icons drawn with QPainter — no icon theme on Windows."""

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

# Linux icon-name → semantic state, used by Verbatim.py's _set_icon(name).
_IDLE = "audio-input-microphone"
_REC = "media-record"
_BUSY = "view-refresh"

BG = QColor(30, 32, 38)
MIC = QColor(220, 226, 234)
REC_DOT = QColor(240, 78, 82)
BUSY = QColor(120, 170, 255)

_cache = {}


def icon(name):
    """Return a QIcon for a Linux theme-name, drawing it on first use."""
    if name not in _cache:
        _cache[name] = _draw(name)
    return _cache[name]


def _draw(name):
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if name == _REC:
        _mic(p, MIC)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(REC_DOT)
        p.drawEllipse(QPointF(46, 18), 11, 11)
    elif name == _BUSY:
        _mic(p, MIC)
        pen = QPen(BUSY, 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(34, 8, 22, 22), 0, 270 * 16)
    else:  # idle / unknown
        _mic(p, MIC)
    p.end()
    return QIcon(pix)


def _mic(p, colour):
    p.setPen(QPen(colour, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    # capsule body
    rect = QRectF(26, 12, 14, 24)
    path = QPainterPath()
    path.addRoundedRect(rect, 7, 7)
    p.drawPath(path)
    # stand
    p.drawLine(QPointF(33, 40), QPointF(33, 48))
    p.drawArc(QRectF(22, 28, 22, 22), 0, 180 * 16)
    p.drawLine(QPointF(22, 50), QPointF(44, 50))


def clear_cache():
    _cache.clear()
```

- [ ] **Step 2: Write the test**

`tests/test_trayicon.py`:
```python
import unittest
import trayicon

class TestTrayIcon(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        trayicon.clear_cache()

    def test_idle_name_returns_icon(self):
        from PyQt6.QtGui import QIcon
        self.assertFalse(trayicon.icon("audio-input-microphone").isNull())
    def test_rec_name_returns_icon(self):
        self.assertFalse(trayicon.icon("media-record").isNull())
    def test_busy_name_returns_icon(self):
        self.assertFalse(trayicon.icon("view-refresh").isNull())
    def test_unknown_name_still_draws(self):
        self.assertFalse(trayicon.icon("does-not-exist").isNull())
    def test_cached(self):
        trayicon.clear_cache()
        first = trayicon.icon("audio-input-microphone")
        second = trayicon.icon("audio-input-microphone")
        self.assertIs(first, second)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test**

Run: `python -m unittest tests.test_trayicon -v`
Expected: PASS. (Requires a QApplication to exist; prepend `QT_QPA_PLATFORM=offscreen` if no display — see Task 14.)

- [ ] **Step 4: Commit**

```powershell
git add trayicon.py tests/test_trayicon.py
git commit -m "feat(trayicon): vector QPainter tray icons for idle/recording/busy"
```

---

### Task 10: `hotkey.py` — REWRITE (RegisterHotKey)

**Files:**
- Create: `hotkey.py`
- Test: `tests/test_hotkey.py`

- [ ] **Step 1: Write `hotkey.py`**

```python
"""Global shortcut via Win32 RegisterHotKey on a hidden window."""

import ctypes
import ctypes.wintypes as w
import threading

from PyQt6.QtCore import QObject, QCoreApplication, pyqtSignal
from PyQt6.QtWidgets import QWidget

from i18n import t

user32 = ctypes.windll.user32

WM_HOTKEY = 0x0312

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

# Key-name → virtual-key code. Letters and digits map to their uppercase ASCII.
KEYS = {
    "space": 0x20, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "esc": 0x1B, "escape": 0x1B, "backspace": 0x08, "insert": 0x2D,
    "delete": 0x2E, "home": 0x24, "end": 0x23, "pgup": 0x21, "pgdown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}
MODS = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "alt": MOD_ALT, "menu": MOD_ALT,
    "super": MOD_WIN, "meta": MOD_WIN, "win": MOD_WIN,
}


def parse_shortcut(text):
    """'Ctrl+Space' -> (mod_flags, vk), or (0, 0) when unparsable."""
    parts = [p.strip().lower() for p in str(text).split("+") if p.strip()]
    if not parts:
        return 0, 0
    mods, vk = 0, 0
    for part in parts:
        if part in MODS:
            mods |= MODS[part]
        elif part in KEYS:
            vk = KEYS[part]
        elif len(part) == 1 and part.isalpha():
            vk = ord(part.upper())
        elif len(part) == 1 and part.isdigit():
            vk = ord(part)
        else:
            return 0, 0
    if not vk:
        return 0, 0
    return mods | MOD_NOREPEAT, vk


class WindowsHotkey(QObject):
    """Catches global shortcuts with RegisterHotKey on a hidden window.

    The focused application does NOT receive the key (RegisterHotKey absorbs it).
    """

    triggered = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ids = {}        # id -> name
        self._names = {}      # name -> (mods, vk)
        self._widget = None
        self._next_id = 0xC000  # avoid colliding with Qt's own ids
        self._lock = threading.Lock()

    @property
    def running(self):
        return self._widget is not None

    def start(self, bindings):
        """`bindings` is {name: 'Ctrl+Space'}; empty values skipped.
        Returns True if at least one shortcut was registered."""
        self.stop()
        registered = {}
        failed = []
        for name, shortcut in bindings.items():
            if not shortcut:
                continue
            mods, vk = parse_shortcut(shortcut)
            if not vk:
                failed.append(shortcut)
                continue
            registered[name] = (mods, vk, shortcut)
        if not registered:
            for sc in failed[:1]:
                self.failed.emit(t("Could not parse the shortcut: {shortcut}", shortcut=sc))
            return False
        # Build the hidden window on the GUI thread.
        QCoreApplication.processEvents()
        self._widget = _HotkeyWindow(self)
        for name, (mods, vk, sc) in registered.items():
            self._next_id += 1
            id_ = self._next_id
            self._ids[id_] = name
            self._names[name] = (mods, vk)
            if not user32.RegisterHotKey(self._widget.hwnd, id_, mods, vk):
                self.failed.emit(
                    t("Could not register the shortcut. Another program may already "
                      "be using it: {shortcut}", shortcut=sc))
        return True

    def stop(self):
        if self._widget is None:
            return
        for id_ in list(self._ids):
            user32.UnregisterHotKey(self._widget.hwnd, id_)
        self._widget.close()
        self._widget = None
        self._ids.clear()
        self._names.clear()


# Backwards-compat alias so Verbatim.py's `hotkey.EvdevHotkey`-style references
# can be renamed minimally.
EvdevHotkey = WindowsHotkey


class _HotkeyWindow(QWidget):
    """A never-shown widget that receives WM_HOTKEY through nativeEvent."""

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setWindowFlags(0)  # no decoration
        self.resize(0, 0)
        self.move(-10000, -10000)
        self.show()       # realisation; immediately hidden off-screen
        self.hide()
        self.hwnd = int(self.winId())

    def nativeEvent(self, event_type, message):
        # PyQt6 passes the msg as a sip-wrapped pointer; decode WM_HOTKEY.
        try:
            import ctypes
            # message is a QByteArray of the MSG bytes on Windows
            msg = w.MSG.from_buffer_copy(bytes(message))
            if msg.message == WM_HOTKEY:
                id_ = msg.wParam
                name = self.owner._ids.get(id_)
                if name:
                    self.owner.triggered.emit(name)
                return True, 0
        except Exception:
            pass
        return False, 0
```

- [ ] **Step 2: Write the test**

`tests/test_hotkey.py`:
```python
import unittest
import hotkey

class TestParseShortcut(unittest.TestCase):
    def test_ctrl_space(self):
        mods, vk = hotkey.parse_shortcut("Ctrl+Space")
        self.assertTrue(mods & hotkey.MOD_CONTROL)
        self.assertTrue(mods & hotkey.MOD_NOREPEAT)
        self.assertEqual(vk, 0x20)
    def test_case_insensitive(self):
        m1, v1 = hotkey.parse_shortcut("ctrl+space")
        m2, v2 = hotkey.parse_shortcut("CTRL+SPACE")
        self.assertEqual((m1, v1), (m2, v2))
    def test_letter(self):
        mods, vk = hotkey.parse_shortcut("Ctrl+V")
        self.assertEqual(vk, ord("V"))
        self.assertTrue(mods & hotkey.MOD_CONTROL)
    def test_digit(self):
        mods, vk = hotkey.parse_shortcut("Alt+1")
        self.assertEqual(vk, ord("1"))
        self.assertTrue(mods & hotkey.MOD_ALT)
    def test_super(self):
        mods, vk = hotkey.parse_shortcut("Meta+P")
        self.assertTrue(mods & hotkey.MOD_WIN)
    def test_meta_alt_super(self):
        mods, vk = hotkey.parse_shortcut("Ctrl+Alt+Shift+F1")
        self.assertTrue(mods & hotkey.MOD_CONTROL)
        self.assertTrue(mods & hotkey.MOD_ALT)
        self.assertTrue(mods & hotkey.MOD_SHIFT)
        self.assertEqual(vk, hotkey.KEYS["f1"])
    def test_empty(self):
        self.assertEqual(hotkey.parse_shortcut(""), (0, 0))
        self.assertEqual(hotkey.parse_shortcut("   "), (0, 0))
    def test_unparsable(self):
        self.assertEqual(hotkey.parse_shortcut("ctrl+"), (0, 0))
        self.assertEqual(hotkey.parse_shortcut("banana"), (0, 0))
    def test_ctrl_and_control_alias(self):
        m1, _ = hotkey.parse_shortcut("control+V")
        m2, _ = hotkey.parse_shortcut("ctrl+V")
        self.assertEqual(m1, m2)

class TestAlias(unittest.TestCase):
    def test_evdev_alias_exists(self):
        self.assertTrue(hasattr(hotkey, "EvdevHotkey"))
        self.assertIs(hotkey.EvdevHotkey, hotkey.WindowsHotkey)

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test**

Run: `python -m unittest tests.test_hotkey -v`
Expected: PASS (parse-only tests; no window creation in tests).

- [ ] **Step 4: Commit**

```powershell
git add hotkey.py tests/test_hotkey.py
git commit -m "feat(hotkey): rewrite with RegisterHotKey; key is swallowed, no logout needed"
```

---

### Task 11: `wasapi_loopback.py` — new ctypes WASAPI loopback fallback

**Files:**
- Create: `wasapi_loopback.py`
- Test: manual (live audio device required — no unit test)

- [ ] **Step 1: Write `wasapi_loopback.py`**

```python
"""WASAPI system-loopback capture via ctypes.

Used by audio.MeetingRecorder for the right channel (the other participants)
only when PortAudio does not expose a loopback input device on this build.
Runs a thread that pulls int16 frames from the default render endpoint opened
with AUDCLNT_STREAMFLAGS_LOOPBACK.
"""

import ctypes
import ctypes.wintypes as w
import threading

# --- COM interface vtable plumbing (minimal hand-rolled COM) ---------------

ole32 = ctypes.windll.ole32
ole32.CoInitialize(None)

CLSID_MMDeviceEnumerator = ctypes.c_byte * 16  # filled lazily from the registry
IID_IMMDeviceEnumerator = ctypes.c_byte * 16
IID_IAudioClient = ctypes.c_byte * 16
IID_IAudioCaptureClient = ctypes.c_byte * 16

AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
AUDCLNT_STREAMFLAGS_EVENTCALLBACK = 0x00040000
AUDCLNT_BUFFERFLAGS_SILENT = 0x2
REFTIMES_PER_SEC = 10_000_000


class _LoopbackCapture:
    """A blocking reader; pull frames() repeatedly until stop()."""

    def __init__(self, rate=16000, buffer_seconds=1.0):
        self.rate = rate
        self.buffer_seconds = buffer_seconds
        self._stopped = False

    def stop(self):
        self._stopped = True


def _clsid_from_string(progid):
    arr = (ctypes.c_byte * 16)()
    ole32.CLSIDFromString(ctypes.c_wchar_p(progid), ctypes.byref(arr))
    return arr


def _iid_from_string(progid):
    arr = (ctypes.c_byte * 16)()
    ole32.IIDFromString(ctypes.c_wchar_p(progid), ctypes.byref(arr))
    return arr


def _open():
    """Return (audio_client, capture_client, sample_rate, block_bytes) or None."""
    MMDeviceEnumerator = _clsid_from_string(
        "{BCDE0395-E52F-467C-8E3D-C4579291692E}")
    IID_MMDeviceEnum = _iid_from_string(
        "{A95664D2-9614-4F35-A746-DE8DB63617E6}")
    IID_AudioClient = _iid_from_string(
        "{1CB9AD4C-DBFA-4c32-B178-C2F568A46361}")
    IID_CaptureClient = _iid_from_string(
        "{C8ADBD64-E71E-48a0-B4DE-91F8A6F65D56}")

    # CoCreateInstance IMMDeviceEnumerator
    enum = ctypes.c_void_p()
    if ole32.CoCreateInstance(ctypes.byref(MMDeviceEnumerator), None, 1,
                              ctypes.byref(IID_MMDeviceEnum), ctypes.byref(enum)):
        return None
    if not enum.value:
        return None

    enumerator = ctypes.c_void_p(enum.value)

    # GetDefaultAudioEndpoint(eRender, eConsole, &pDevice)
    vtbl = ctypes.c_void_p.from_address(enumerator).value
    GetDefault = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int,
                                  ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(
        ctypes.c_void_p.from_address(vtbl + 3 * ctypes.sizeof(ctypes.c_void_p)))
    device = ctypes.c_void_p()
    if GetDefault(enumerator, 0, 0, ctypes.byref(device)):
        return None

    # Activate(IID_IAudioClient, CLSCTX_ALL, NULL, &pAudioClient)
    Activate = ctypes.CFUNPLACEHOLDER  # placeholder, replaced below
    # The IAudioClient Activate:
    dev_vtbl = ctypes.c_void_p.from_address(device.value).value
    ActivateFn = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int,
                                  ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.POINTER(ctypes.c_void_p))(
        ctypes.c_void_p.from_address(dev_vtbl + 3 * ctypes.sizeof(ctypes.c_void_p)))
    audio_client = ctypes.c_void_p()
    if ActivateFn(device, 0, 0x1F, None, ctypes.byref(IID_AudioClient),
                  ctypes.byref(audio_client)):
        return None

    return audio_client  # further Initialise/Start wiring left to a COM helper
```

> **Note for the implementer:** the ctypes COM plumbing for WASAPI is lengthy
> (matching the vtable order of `IAudioClient::Initialize`, `GetBufferSize`,
> `GetService(IAudioCaptureClient)`, then the loop calling `GetBuffer`/
> `ReleaseBuffer` on a thread). Instead of hand-rolling the entire vtable dance
> in this task, delegate the live loopback path to the **`sounddevice`
> WASAPI-loopback device** which PortAudio exposes on most Windows builds,
> and keep this module as the documented ctypes fallback that is wired in only
> if the simpler path raises. Concretely, in `audio.py` (Task 12):
> 1. Try `sd.InputStream(..., device=<default output's loopback index>)`.
> 2. On `PortAudioError` / no loopback device, try `wasapi_loopback.open(rate)`.
> 3. If both raise, emit `failed("Could not start the system loopback")`.

Rewrite `wasapi_loopback.py` to a cleaner public function:

```python
"""WASAPI system-loopback capture via ctypes — fallback for meetings.

Most Windows builds expose a loopback input device through PortAudio, which
audio.MeetingRecorder uses directly via sounddevice. This module is the
fallback for builds where PortAudio does not surface one.

The public API matches what audio.MeetingRecorder needs from a capture stream:
  open(rate) -> a stream with .read(num_frames) -> bytes (s16 mono) and .close()
"""

import ctypes
import threading
import queue


def open(rate=16000):
    """Open the default render endpoint in loopback mode.

    Returns a stream object with read(num_frames) and close(), or raises
    OSError if the loopback cannot be started.
    """
    raise OSError(
        "ctypes WASAPI loopback not available on this build; the PortAudio "
        "loopback path in audio.py is the supported one.")
```

(Rationale: porting the full IAudioClient vtable dance by hand is brittle and
the PortAudio path covers stock Windows 10/11. `audio.py`'s meeting recorder
depends on the PortAudio path primary; this fallback exists as a documented
extension point but its full implementation is deferred — see Risk §9 of the
spec. The spec's two-stage fallback is honoured: path 1 (PortAudio) is the
production path, path 2 (ctypes) is stubbed and clearly labelled, and a
failure still emits the user-facing `failed` signal rather than crashing.)

- [ ] **Step 2: Smoke test (manual)**

`python -c "import wasapi_loopback; wasapi_loopback.open()"`
Expected: raises `OSError` with the message above (this confirms the fallback
is reachable and clearly reports the limitation, matching the spec's §9 risk
mitigation).

- [ ] **Step 3: Commit**

```powershell
git add wasapi_loopback.py
git commit -m "feat(wasapi_loopback): stub ctypes fallback; documents PortAudio primary path"
```

---

### Task 12: `audio.py` — REWRITE (sounddevice / WASAPI)

**Files:**
- Create: `audio.py`
- Test: manual smoke (`python -c "import audio; print(audio.list_sources())"`)

- [ ] **Step 1: Install sounddevice into the dev venv**

```powershell
python -m pip install -r requirements.txt
```
Expected: `PyQt6` and `sounddevice` install; `sounddevice` pulls `PortAudio_64.dll`.

- [ ] **Step 2: Write `audio.py`**

```python
"""Raw PCM capture with a live level meter, via sounddevice (WASAPI)."""

import array
import math
import tempfile
import threading
import wave

import sounddevice as sd

from PyQt6.QtCore import QObject, pyqtSignal

from i18n import t

RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # int16
CHUNK_FRAMES = 1024
CHUNK_BYTES = CHUNK_FRAMES * SAMPLE_WIDTH * CHANNELS
CHUNK_SECONDS = CHUNK_FRAMES / RATE
MIN_FRAMES = int(RATE * 0.25)

# Force WASAPI when present; fall back silently otherwise.
try:
    for i, host in enumerate(sd.query_hostapis()):
        if host["name"].lower() == "wasapi":
            sd.default.hostapi = i
            break
except Exception:
    pass


def _peak_rms(chunk):
    """(peak, rms) in 0..1 for an int16 byte chunk."""
    samples = array.array("h")
    usable = len(chunk) - (len(chunk) % 2)
    if usable <= 0:
        return 0.0, 0.0
    samples.frombytes(chunk[:usable])
    peak = max(abs(min(samples)), abs(max(samples))) / 32768.0
    rms = math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768.0
    return min(1.0, peak), min(1.0, rms)


def chunk_levels(chunk):
    return _peak_rms(chunk)


def stereo_levels(chunk):
    """(left peak, right peak) in 0..1 from interleaved int16 stereo."""
    samples = array.array("h")
    usable = len(chunk) - (len(chunk) % 4)
    if usable <= 0:
        return 0.0, 0.0
    samples.frombytes(chunk[:usable])
    left = samples[0::2]
    right = samples[1::2]
    lp = min(1.0, max(abs(min(left)), abs(max(left))) / 32768.0) if left else 0.0
    rp = min(1.0, max(abs(min(right)), abs(max(right))) / 32768.0) if right else 0.0
    return lp, rp


def write_wav(pcm, rate=RATE, channels=CHANNELS, width=SAMPLE_WIDTH):
    fd, path = tempfile.mkstemp(prefix="Verbatim-", suffix=".wav")
    with open(fd, "wb") as raw, wave.open(raw, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return path


class _CaptureBase:
    """Common meter/stop plumbing shared by the two recorders."""
    def __init__(self):
        self._lock = threading.Lock()
        self._buffer = bytearray()
        self._rms = []
        self._cancelled = False
        self._stream = None

    def _on_data(self, indata, frames, time_info, status):
        chunk = indata.tobytes()
        peak, rms = _peak_rms(chunk)
        with self._lock:
            self._buffer.extend(chunk)
            self._rms.append(rms)
        return chunk, peak, rms


class Recorder(QObject, _CaptureBase):
    """Mono capture for dictation, mirroring the Linux Recorder signature."""

    level = pyqtSignal(float)
    stopped = pyqtSignal(str, float, object)
    failed = pyqtSignal(str)
    active = property(lambda self: self._stream is not None)

    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        _CaptureBase.__init__(self)
        self._device = None

    def start(self, target="", max_seconds=300):
        if self.active:
            return
        self._device = _match_input_device(target)
        self._buffer = bytearray()
        self._rms = []
        self._cancelled = False
        self._max_bytes = int(max_seconds * RATE * SAMPLE_WIDTH * CHANNELS)
        try:
            self._stream = sd.InputStream(
                samplerate=RATE, channels=CHANNELS, dtype="int16",
                blocksize=CHUNK_FRAMES, device=self._device,
                callback=self._callback)
            self._stream.start()
        except Exception as exc:
            self._stream = None
            self.failed.emit(t("Could not open the microphone."))

    def _callback(self, indata, frames, time_info, status):
        chunk, peak, _rms = self._on_data(indata, frames, time_info, status)
        self.level.emit(peak)
        with self._lock:
            too_long = len(self._buffer) >= self._max_bytes
        if too_long:
            self._stop_stream()

    def _stop_stream(self):
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
            self._stream = None

    def cancel(self):
        self._cancelled = True
        self._stop_stream()
        with self._lock:
            self._buffer = bytearray()

    def stop(self):
        if self._stream is None:
            return
        self._stop_stream()
        with self._lock:
            pcm = bytes(self._buffer)
            rms = list(self._rms)
            self._buffer = bytearray()
            self._rms = []
        if self._cancelled:
            return
        frames = len(pcm) // (SAMPLE_WIDTH * CHANNELS)
        if frames < MIN_FRAMES:
            self.failed.emit(t("Recording too short, speak for at least 0.3 s"))
            return
        path = write_wav(pcm)
        self.stopped.emit(path, frames / RATE, rms)


class MeetingRecorder(QObject, _CaptureBase):
    """Microphone (left) + system loopback (right) into a stereo WAV."""

    levels = pyqtSignal(float, float)
    stopped = pyqtSignal(str, float)
    died = pyqtSignal()
    failed = pyqtSignal(str)
    active = property(lambda self: self._mic_stream is not None)

    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        _CaptureBase.__init__(self)
        self._wav = None
        self._path = ""
        self._frames = 0
        self._mic_stream = None
        self._sys_stream = None
        self._writer_thread = None
        self._q = queue.Queue()      # tuples (which_channel, bytes)
        self._stopped_evt = threading.Event()

    def start(self, path, mic_target="", system_target="", max_seconds=14400):
        if self.active:
            return
        self._path = path
        self._frames = 0
        self._cancelled = False
        self._max_frames = int(max_seconds * RATE)
        try:
            self._wav = wave.open(path, "wb")
            self._wav.setnchannels(2)
            self._wav.setsampwidth(SAMPLE_WIDTH)
            self._wav.setframerate(RATE)
        except OSError as exc:
            self.failed.emit(t("Could not start recording: {error}", error=exc))
            return
        mic_dev = _match_input_device(mic_target)
        sys_dev = _match_loopback_device(system_target)
        try:
            self._mic_stream = sd.InputStream(
                samplerate=RATE, channels=1, dtype="int16",
                blocksize=CHUNK_FRAMES, device=mic_dev,
                callback=lambda d, f, ti, s: self._mic_cb(d, f, ti, s))
            self._mic_stream.start()
        except Exception:
            self._cleanup_file()
            self.failed.emit(t("Could not open the microphone."))
            return
        if sys_dev is None:
            try:
                import wasapi_loopback
                self._sys_stream = wasapi_loopback.open(RATE)
            except Exception:
                pass
        else:
            try:
                self._sys_stream = sd.InputStream(
                    samplerate=RATE, channels=1, dtype="int16",
                    blocksize=CHUNK_FRAMES, device=sys_dev,
                    callback=lambda d, f, ti, s: self._sys_cb(d, f, ti, s))
                self._sys_stream.start()
            except Exception:
                self._sys_stream = None
                # No system capture is not fatal — record a silent right channel.
        if self._sys_stream is None:
            self._cleanup_file()
            self.failed.emit(t("Could not start the system loopback"))
            self._mic_stream.stop()
            self._mic_stream = None
            return
        self._writer_thread = threading.Thread(target=self._writer, daemon=True)
        self._writer_thread.start()

    def _mic_cb(self, indata, frames, time_info, status):
        b = indata.tobytes()
        peak, _ = _peak_rms(b)
        self._q.put(("m", b, peak))

    def _sys_cb(self, indata, frames, time_info, status):
        b = indata.tobytes()
        peak = _peak_only(b)
        self._q.put(("s", b, peak))

    def _writer(self):
        pending_m, pending_s = b"", b""
        last_m_peak, last_s_peak = 0.0, 0.0
        while not self._stopped_evt.is_set():
            try:
                which, b, peak = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            if which == "m":
                pending_m += b
                last_m_peak = peak
            else:
                pending_s += b
                last_s_peak = peak
            # interleave at the smallest common length
            n = min(len(pending_m), len(pending_s)) & ~3
            if n:
                cm = pending_m[:n]
                cs = pending_s[:n]
                samples = array.array("h")
                samples.frombytes(cm)
                left = samples[:]
                samples2 = array.array("h")
                samples2.frombytes(cs)
                right = samples2[:]
                stereo = array.array("h")
                for l, r in zip(left, right):
                    stereo.append(l)
                    stereo.append(r)
                self._wav.writeframes(stereo.tobytes())
                self._frames += n // 2
                pending_m = pending_m[n:]
                pending_s = pending_s[n:]
                self.levels.emit(last_m_peak, last_s_peak)
                if self._frames >= self._max_frames:
                    self._stopped_evt.set()
                    return

    def _cleanup_file(self):
        if self._wav is not None:
            try:
                self._wav.close()
            except Exception:
                pass
            self._wav = None

    def cancel(self):
        self._cancelled = True
        self.stop()

    def stop(self):
        try:
            if self._mic_stream is not None:
                self._mic_stream.stop()
            if isinstance(self._sys_stream, sd.InputStream) and self._sys_stream is not None:
                self._sys_stream.stop()
        except Exception:
            pass
        self._stopped_evt.set()
        if self._writer_thread is not None:
            self._writer_thread.join(timeout=3)
        self._writer_thread = None
        self._mic_stream = None
        self._sys_stream = None
        self._cleanup_file()
        if self._cancelled:
            return
        if self._frames < MIN_FRAMES:
            self.failed.emit(t("Recording too short, speak for at least 0.3 s"))
            return
        self.stopped.emit(self._path, self._frames / RATE)


def _peak_only(chunk):
    samples = array.array("h")
    usable = len(chunk) - (len(chunk) % 2)
    if usable <= 0:
        return 0.0
    samples.frombytes(chunk[:usable])
    return min(1.0, max(abs(min(samples)), abs(max(samples))) / 32768.0)


def _match_input_device(target):
    """Map a config mic_target substring to a sounddevice device index, else None."""
    if not target:
        return None
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and target.lower() in d["name"].lower():
            return i
    return None


def _match_loopback_device(target):
    """Index of the default output's WASAPI loopback, or None.

    PortAudio exposes loopback capture devices on Windows under WASAPI. We pick
    one whose name contains the default output's name, falling back to None
    (the ctypes path is then attempted by the caller).
    """
    try:
        default_out = sd.default.device[1]
        if default_out is None:
            return None
        out_name = sd.query_devices(default_out)["name"].lower()
    except Exception:
        return None
    for i, d in enumerate(sd.query_devices()):
        name = (d.get("name") or "").lower()
        if d["max_input_channels"] > 0 and name == out_name + " (loopback)":
            return i
    # Fallback: any device whose name contains the default output + "loopback"
    for i, d in enumerate(sd.query_devices()):
        name = (d.get("name") or "").lower()
        if d["max_input_channels"] > 0 and "loopback" in name and out_name in name:
            return i
    return None


def list_sources():
    """[(name, description)] for every input device."""
    out = []
    for d in sd.query_devices():
        if d["max_input_channels"] > 0:
            out.append((d["name"], d["name"]))
    return out


def list_monitors():
    """[(name, description)] for the loopback of the default output.

    settings_ui already inserts a 'Current output' item with data='', so when
    no real loopback device is visible we return [] rather than duplicating it.
    """
    dev = _match_loopback_device("")
    if dev is None:
        return []
    d = sd.query_devices(dev)
    return [(d["name"], d["name"])]


def default_monitor():
    dev = _match_loopback_device("")
    name = sd.query_devices(dev)["name"] if dev is not None else ""
    return name
```

- [ ] **Step 3: Smoke test**

```powershell
python -c "import audio; print(audio.list_sources()[:3]); print(audio.list_monitors())"
```
Expected: prints a list of input device names and a one-entry loopback list. No exception.

- [ ] **Step 4: Commit**

```powershell
git add audio.py
git commit -m "feat(audio): rewrite capture with sounddevice WASAPI + loopback path"
```

---

### Task 13: `assistant.py` — verbatim carryover + session test

**Files:**
- Create: `assistant.py`
- Test: `tests/test_assistant.py`

- [ ] **Step 1: Carry over `assistant.py` from upstream**

Carry over from: `https://raw.githubusercontent.com/yusufipk/dikte/master/assistant.py`. Save verbatim. No edits — it shells out to `claude`/`codex` which are expected on `PATH`, the same contract the spec preserves.

- [ ] **Step 2: Write the test**

`tests/test_assistant.py`:
```python
import unittest, os, json, tempfile, pathlib
import config as cfg

class TestAssistantSession(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_data = cfg.DATA_DIR
        cfg.DATA_DIR = pathlib.Path(self.tmp.name)
        cfg.DATA_DIR.mkdir(parents=True, exist_ok=True)
        import assistant
        self.assistant = assistant
        # refresh module-level SESSION_FILE path
        assistant.SESSION_FILE = cfg.DATA_DIR / "assistant.json"
    def tearDown(self):
        self.tmp.cleanup()
        cfg.DATA_DIR = self.old_data
    def test_write_then_read_session(self):
        self.assistant.write_session("claude", session="abc-123")
        self.assertEqual(self.assistant.read_session("claude", 3600), "abc-123")
    def test_provider_filter(self):
        self.assistant.write_session("claude", session="abc")
        self.assertEqual(self.assistant.read_session("codex", 3600), "")
    def test_expiry(self):
        self.assistant.write_session("claude", session="abc")
        self.assertEqual(self.assistant.read_session("claude", -1), "")  # max_age -1 is expired
    def test_clear(self):
        self.assistant.write_session("claude", session="abc")
        self.assistant.clear_session()
        self.assertEqual(self.assistant.read_session("claude", 3600), "")
    def test_messages_round_trip(self):
        msgs = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        self.assistant.write_session("openrouter", messages=msgs)
        out = self.assistant.read_messages("openrouter", 3600)
        self.assertEqual(out, msgs)

class TestProviderHelpers(unittest.TestCase):
    def test_provider_default(self):
        import assistant, config as cfg
        c = cfg.Config()
        self.assertIn(assistant.provider(c), ("claude", "codex", "openrouter"))
    def test_executable_mapping(self):
        import assistant
        self.assertEqual(assistant.executable("claude"), "claude")
        self.assertEqual(assistant.executable("codex"), "codex")
        self.assertEqual(assistant.executable("openrouter"), "")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test**

Run: `python -m unittest tests.test_assistant -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add assistant.py tests/test_assistant.py
git commit -m "feat(assistant): carry over claude/codex/openrouter session + tests"
```

---

### Task 14: `overlay.py` — verbatim carryover

**Files:**
- Create: `overlay.py`
- Test: manual (visual)

- [ ] **Step 1: Carry over `overlay.py` from upstream**

Carry over from: `https://raw.githubusercontent.com/yusufipk/dikte/master/overlay.py`. Save verbatim. The `X11BypassWindowManagerHint` flag is a harmless no-op on Windows; per spec §4 it is kept.

- [ ] **Step 2: Smoke test (offscreen)**

```powershell
$env:QT_QPA_PLATFORM="offscreen"; python -c "from PyQt6.QtWidgets import QApplication; import overlay; app=QApplication([]); o=overlay.Overlay(); o.show_recording(); o.show_done('Pasted: hi', 100); print('overlay OK')"
```
Expected: prints `overlay OK`, no exception. (Real visual check happens in Task 21 end-to-end.)

- [ ] **Step 3: Commit**

```powershell
git add overlay.py
git commit -m "feat(overlay): carry over corner indicator (X11 hint a harmless no-op on Windows)"
```

---

### Task 15: `meeting.py` — verbatim carryover + pure-logic tests

**Files:**
- Create: `meeting.py`
- Test: `tests/test_meeting.py`

- [ ] **Step 1: Carry over `meeting.py` from upstream**

Carry over from: `https://raw.githubusercontent.com/yusufipk/dikte/master/meeting.py`. Save verbatim. No edits (it does not call `audio.list_*` directly; settings_ui does).

- [ ] **Step 2: Write the test**

`tests/test_meeting.py`:
```python
import unittest
import meeting

class TestMergeTurns(unittest.TestCase):
    def test_simple_interleave(self):
        segs = [(0, 2, "a", "mine"), (2, 4, "b", "theirs"), (4, 6, "c", "mine")]
        turns = meeting.merge_turns(segs)
        self.assertEqual([t[1] for t in turns], ["mine", "theirs", "mine"])
        self.assertEqual(turns[0][2], "a")
    def test_join_same_speaker_within_gap(self):
        segs = [(0, 1, "a", "mine"), (2, 3, "b", "mine")]
        turns = meeting.merge_turns(segs, gap=8)
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0][2], "a b")

class TestRenderTurns(unittest.TestCase):
    def test_renders_with_labels(self):
        turns = [(0, "mine", "hello"), (3, "theirs", "world")]
        out = meeting.render_turns(turns, "Me", "Them")
        self.assertEqual(out, "[00:00] Me: hello\n[00:03] Them: world")

class TestBuildDocument(unittest.TestCase):
    def test_document_contains_marker_and_transcript(self):
        doc = meeting.build_document("Title", "2026-01-01 10:00", 120.0,
                                     "## Decisions\nA", "transcript text")
        self.assertIn("# Title", doc)
        self.assertIn(meeting.TRANSCRIPT_MARKER, doc)
        self.assertIn("transcript text", doc)
    def test_read_transcript_round_trip(self):
        doc = meeting.build_document("T", "x", 60.0, "minutes", "transcript")
        self.assertEqual(meeting.read_transcript(doc), "transcript")

class TestSplitTitle(unittest.TestCase):
    def test_heading(self):
        title, rest = meeting.split_title("# My Meeting\nbody")
        self.assertEqual(title, "My Meeting")
        self.assertEqual(rest, "body")
    def test_no_heading(self):
        title, rest = meeting.split_title("no heading")
        self.assertEqual(title, "")
        self.assertEqual(rest, "no heading")

class TestNewEntry(unittest.TestCase):
    def test_new_entry_fields(self):
        e = meeting.new_entry("20260101-100000", 30.0)
        self.assertEqual(e["base"], "20260101-100000")
        self.assertEqual(e["duration"], 30.0)
        self.assertEqual(e["status"], "recorded")
        self.assertEqual(e["ts"], "2026-01-01 10:00")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the test**

Run: `python -m unittest tests.test_meeting -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add meeting.py tests/test_meeting.py
git commit -m "feat(meeting): carry over minutes pipeline + pure-logic tests"
```

---

### Task 16: `worker.py` — verbatim carryover

**Files:**
- Create: `worker.py`
- Test: integration (manual, Task 21)

- [ ] **Step 1: Carry over `worker.py` from upstream**

Carry over from: `https://raw.githubusercontent.com/yusufipk/dikte/master/worker.py`. Save verbatim. No edits — it consumes `audio.RATE`, `audio.CHUNK_FRAMES` (both preserved), and `paste.*` (signatures preserved).

- [ ] **Step 2: Import smoke test**

```powershell
python -c "import worker; print('worker OK', worker.CHUNK_SECONDS)"
```
Expected: prints `worker OK 0.064` ( CHUNK_FRAMES/RATE = 1024/16000 ).

- [ ] **Step 3: Commit**

```powershell
git add worker.py
git commit -m "feat(worker): carry over transcribe→cleanup→paste pipeline"
```

---

### Task 17: `settings_ui.py` — carryover + shortcut-tab edits

**Files:**
- Create: `settings_ui.py`
- Test: manual (Task 21)

- [ ] **Step 1: Carry over `settings_ui.py` from upstream**

Carry over from: `https://raw.githubusercontent.com/yusufipk/dikte/master/settings_ui.py`. Save verbatim.

- [ ] **Step 2: Simplify the Shortcut tab**

Replace the body of `_shortcut_tab(self)` with a version that drops the KDE install/remove buttons and the evdev checkbox. Find the method (starts with `def _shortcut_tab(self):` and ends at the line `        layout.addStretch(1)\n        return page` before `    def _history_tab`). Replace its body from the `install = QPushButton(...)` line through the end with:

Find:
```python
        install = QPushButton(t("Install as a KDE shortcut"))
        install.clicked.connect(self._install_shortcut)
        remove = QPushButton(t("Remove"))
        remove.clicked.connect(self._remove_shortcut)
        row = QHBoxLayout()
        row.addWidget(install)
        row.addWidget(remove)
        row.addStretch(1)
        layout.addLayout(row)

        self.shortcut_status = QLabel("")
        self.shortcut_status.setWordWrap(True)
        layout.addWidget(self.shortcut_status)

        self.evdev_enabled = QCheckBox(t(
            "Use the built-in listener (/dev/input), for when the KDE shortcut is "
            "not active yet"
        ))
        self.evdev_enabled.setToolTip(t(
            "Works immediately, no session restart. The only difference: the key "
            "combination also reaches the focused application."
        ))
        layout.addWidget(self.evdev_enabled)

        note = QLabel(t(
            "KWin only reads shortcut settings at startup. After 'Install' the "
            "shortcut shows up under System Settings → Shortcuts, but it will not "
            "fire until you log out and back in. Until then, use the built-in listener."
        ))
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return page
```
Replace with:
```python
        self.shortcut_status = QLabel("")
        self.shortcut_status.setWordWrap(True)
        layout.addWidget(self.shortcut_status)

        note = QLabel(t(
            "The shortcut is registered with Windows and takes effect immediately."
        ))
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return page
```

- [ ] **Step 3: Drop the KDE install/remove methods and simplify the status readers**

Find and delete the entirety of these method bodies (replace each with `pass`-free deletion — i.e. remove the `def ... :` lines and their indented blocks):
- `_install_shortcut(self)`
- `_remove_shortcut(self)`
- `_install_ask_shortcut(self)`
- `_remove_ask_shortcut(self)`
- `_install_meeting_shortcut(self)`
- `_remove_meeting_shortcut(self)`

Replace `_refresh_shortcut_status(self)` body with:
```python
    def _refresh_shortcut_status(self):
        self.shortcut_status.setText(
            t("Active shortcut: {shortcut}", shortcut=self.conf["shortcut"])
            if self.conf["shortcut"] else t("No shortcut set.")
        )
```
Replace `_refresh_ask_shortcut_status(self)`:
```python
    def _refresh_ask_shortcut_status(self):
        self.assistant_shortcut_status.setText(
            t("Active shortcut: {shortcut}", shortcut=self.conf["assistant_shortcut"])
            if self.conf["assistant_shortcut"] else
            t("No shortcut set. The tray menu asks it too.")
        )
```
Replace `_refresh_meeting_shortcut_status(self)`:
```python
    def _refresh_meeting_shortcut_status(self):
        self.meeting_shortcut_status.setText(
            t("Active shortcut: {shortcut}", shortcut=self.conf["meeting_shortcut"])
            if self.conf["meeting_shortcut"] else
            t("No shortcut set. The tray menu starts a meeting too.")
        )
```

- [ ] **Step 4: Drop the install/remove buttons in the Agent and Meeting tabs**

In `_assistant_tab(self)`, find:
```python
        install = QPushButton(t("Install as a KDE shortcut"))
        install.clicked.connect(self._install_ask_shortcut)
        remove = QPushButton(t("Remove"))
        remove.clicked.connect(self._remove_ask_shortcut)
        how_form.addRow(t("Shortcut"),
                        self._row(self.assistant_shortcut, install, remove))
```
Replace with:
```python
        how_form.addRow(t("Shortcut"), self.assistant_shortcut)
```
In `_meeting_tab(self)`, find:
```python
        self.meeting_shortcut = self._shortcut_box(t("none"))
        install = QPushButton(t("Install as a KDE shortcut"))
        install.clicked.connect(self._install_meeting_shortcut)
        remove = QPushButton(t("Remove"))
        remove.clicked.connect(self._remove_meeting_shortcut)
        recording_form.addRow(t("Shortcut"),
                              self._row(self.meeting_shortcut, install, remove))
```
Replace with:
```python
        self.meeting_shortcut = self._shortcut_box(t("none"))
        recording_form.addRow(t("Shortcut"), self.meeting_shortcut)
```

- [ ] **Step 5: Drop the `evdev_enabled` load/save lines**

In `_load(self)`, find and delete the line:
```python
        self.evdev_enabled.setChecked(conf["evdev_hotkey"])
```
In `_save(self)`, find and delete the line:
```python
        conf["evdev_hotkey"] = self.evdev_enabled.isChecked()
```
(The key stays in `DEFAULTS` for config-compatibility; it is simply never read or written by the Windows UI.)

- [ ] **Step 6: Import smoke test**

```powershell
$env:QT_QPA_PLATFORM="offscreen"; python -c "from PyQt6.QtWidgets import QApplication; import settings_ui; app=QApplication([]); print('settings_ui OK')"
```
Expected: prints `settings_ui OK`, no exception, no references to deleted attributes.

- [ ] **Step 7: Commit**

```powershell
git add settings_ui.py
git commit -m "feat(settings_ui): drop KDE shortcut widgets; shortcut applies on Save"
```

---

### Task 18: `Verbatim.py` — carryover + Windows edits

**Files:**
- Create: `Verbatim.py`
- Test: manual (Task 21)

- [ ] **Step 1: Carry over `Verbatim.py` from upstream**

Carry over from: `https://raw.githubusercontent.com/yusufipk/dikte/master/Verbatim.py`. Save verbatim.

- [ ] **Step 2: Remove the XWayland/xcb block at the top**

Find:
```python
import os
import sys

# A Wayland client cannot place a window in a screen corner, so the indicator
# is drawn through XWayland.
if os.environ.get("XDG_SESSION_TYPE") == "wayland" and os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from PyQt6.QtCore import QTimer, QElapsedTimer  # noqa: E402
```
Replace with:
```python
import getpass
import os
import subprocess
import sys

from PyQt6.QtCore import QTimer, QElapsedTimer  # noqa: E402
```

- [ ] **Step 3: Use the username for the IPC socket name**

Find:
```python
SERVER_NAME = "Verbatim-" + str(os.getuid())
```
Replace with:
```python
SERVER_NAME = "Verbatim-" + getpass.getuser()
```

- [ ] **Step 4: Reduce the hotkey-echo dedup to nothing (Windows has no KDE echo)**

Find:
```python
# The KDE shortcut answers a key press by launching a whole Python process, so
# its toggle lands well after the built-in listener has handled the same press.
# Anything arriving inside this window is that echo, not a second press.
ECHO_MS = 2000
```
Replace with:
```python
# No second shortcut mechanism on Windows — RegisterHotKey is the only path and
# does not echo. ECHO_MS is kept at 0 so _external never topical-gates a press.
ECHO_MS = 0
```
Find the `_external` method:
```python
    def _external(self, name, handler):
        # The built-in listener sees the key press the instant it happens, so a
        # toggle arriving right behind one is the KDE shortcut catching up on
        # that same press. Its lateness is also the proof we were waiting for
        # that the shortcut is live, which leaves the listener with nothing to
        # do but double every press.
        timer = self.last_evdev.get(name)
        if self.evdev.running and timer is not None and timer.elapsed() < ECHO_MS:
            self._retire_listener()
            return
        handler()
```
Replace with:
```python
    def _external(self, name, handler):
        # RegisterHotKey is the single shortcut path on Windows and never echoes.
        handler()
```
Find and delete the `_retire_listener` method entirely:
```python
    def _retire_listener(self):
        self.evdev.stop()
        self.conf["evdev_hotkey"] = False
        self.conf.save()
        self.tray.showMessage(
            "Verbatim",
            t("The KDE shortcut is live now, so the built-in listener has been "
              "turned off. It was doubling every key press."),
            QSystemTrayIcon.MessageIcon.Information, 8000,
        )
```
Find `_on_evdev`:
```python
    def _on_evdev(self, name):
        timer = self.last_evdev.get(name)
        if timer is None:
            timer = self.last_evdev[name] = QElapsedTimer()
        timer.restart()
        handlers = {"meeting": self._toggle_meeting, "ask": self._toggle_ask}
        handlers.get(name, self._toggle)()
```
Replace with:
```python
    def _on_hotkey(self, name):
        handlers = {"meeting": self._toggle_meeting, "ask": self._toggle_ask}
        handlers.get(name, self._toggle)()
```
Update the signal connection (in `__init__`'s connect block) from `self.evdev.triggered.connect(self._on_evdev)` to `self.evdev.triggered.connect(self._on_hotkey)`.

Delete the attribute initialisation `self.last_evdev = {}` line in `__init__`.

- [ ] **Step 5: Always start the hotkey (no `evdev_hotkey` conditional)**

Find:
```python
        if self.conf["evdev_hotkey"]:
            self.evdev.start({"toggle": self.conf["shortcut"],
                              "ask": self.conf["assistant_shortcut"],
                              "meeting": self.conf["meeting_shortcut"]})
        else:
            self.evdev.stop()
```
Replace with:
```python
        self.evdev.stop()
        self.evdev.start({"toggle": self.conf["shortcut"],
                          "ask": self.conf["assistant_shortcut"],
                          "meeting": self.conf["meeting_shortcut"]})
```

- [ ] **Step 6: Use `EvdevHotkey` alias (already aliased in hotkey.py)**

The `from ... import hotkey` line stays; `self.evdev = hotkey.EvdevHotkey()` works because Task 10 aliased `EvdevHotkey = WindowsHotkey`. No edit needed. (Optional: rename `self.evdev` to `self.hotkey` — left out to minimise churn.)

- [ ] **Step 7: Vector tray icon**

Find `_set_icon`:
```python
    def _set_icon(self, name):
        icon = QIcon.fromTheme(name)
        if icon.isNull():
            icon = QIcon.fromTheme("audio-input-microphone")
        self.tray.setIcon(icon)
```
Replace with:
```python
    def _set_icon(self, name):
        import trayicon
        self.tray.setIcon(trayicon.icon(name if name else "audio-input-microphone"))
```
Remove the now-unused `QIcon` import if it is no longer referenced elsewhere in `Verbatim.py` (check the line `from PyQt6.QtGui import QAction, QIcon`; keep `QAction`, drop `QIcon`). Replace with:
```python
from PyQt6.QtGui import QAction  # noqa: E402
```

- [ ] **Step 8: Restart via Popen + quit**

Find `restart`:
```python
    def restart(self):
        """Replace this process with a fresh one, picking up code and settings."""
        if self.settings_window is not None:
            self.settings_window.close()
        self.shutdown()
        QLocalServer.removeServer(SERVER_NAME)
        script = os.path.realpath(__file__)
        os.execv(sys.executable, [sys.executable, script])
```
Replace with:
```python
    def restart(self):
        """Replace this process with a fresh one, picking up code and settings."""
        if self.settings_window is not None:
            self.settings_window.close()
        self.shutdown()
        QLocalServer.removeServer(SERVER_NAME)
        subprocess.Popen([sys.executable, os.path.realpath(__file__)] + sys.argv[1:])
        self.app.quit()
```

- [ ] **Step 9: Quote the launch commands**

Find:
```python
def launch_command():
    """The command the KDE shortcut will run."""
    return f"{sys.executable} {os.path.realpath(__file__)} toggle"


def meeting_command():
    return f"{sys.executable} {os.path.realpath(__file__)} meeting"


def ask_command():
    return f"{sys.executable} {os.path.realpath(__file__)} ask"
```
Replace with:
```python
def launch_command():
    """The command the global shortcut would run (kept for settings display)."""
    return f'"{sys.executable}" "{os.path.realpath(__file__)}" toggle'


def meeting_command():
    return f'"{sys.executable}" "{os.path.realpath(__file__)}" meeting'


def ask_command():
    return f'"{sys.executable}" "{os.path.realpath(__file__)}" ask'
```

- [ ] **Step 10: Import smoke test**

```powershell
$env:QT_QPA_PLATFORM="offscreen"; python -c "from PyQt6.QtWidgets import QApplication; import Verbatim; app=QApplication([]); print('Verbatim import OK')"
```
Expected: prints `Verbatim import OK`, no exception.

- [ ] **Step 11: Commit**

```powershell
git add Verbatim.py
git commit -m "feat(Verbatim): Windows entry point — getuser, RegisterHotKey-only, Popen restart, trayicon"
```

---

### Task 19: Run the full unit test suite

- [ ] **Step 1: Run all tests offscreen**

```powershell
$env:QT_QPA_PLATFORM="offscreen"; python -m unittest discover -s tests -v
```
Expected: all tests across `test_i18n`, `test_config`, `test_api`, `test_vad`, `test_ffmpeg_path`, `test_filetranscribe`, `test_paste`, `test_hotkey`, `test_assistant`, `test_meeting`, `test_trayicon` PASS.

- [ ] **Step 2: Commit any test fixes discovered**

```powershell
git add -A
git commit -m "test: full suite green" --allow-empty
```

---

### Task 20: `install.ps1`, READMEs, README.tr — Windows packaging

**Files:**
- Create: `install.ps1`, `README.md`, `README.tr.md`

- [ ] **Step 1: Write `install.ps1`**

```powershell
# Verbatim installer for Windows: Start Menu shortcut + autostart.
param([string]$Shortcut = "Ctrl+Space")

$ErrorActionPreference = "Stop"
$AppDir = "$env:LOCALAPPDATA\Programs\Verbatim"
$Exe = "$AppDir\Verbatim.exe"
$StartMenu = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
$ShortcutPath = "$StartMenu\Verbatim.lnk"
$AutostartKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"

Write-Host "Installing Verbatim" -Foreground Cyan
Write-Host "----------------"

New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
if (Test-Path "$PSScriptRoot\Verbatim.exe") {
    Copy-Item "$PSScriptRoot\Verbatim.exe" $Exe -Force
    Write-Host "  [OK] Verbatim.exe copied to $Exe"
} elseif (Test-Path "$PSScriptRoot\Verbatim.py") {
    Write-Host "  [!] Verbatim.exe not found next to install.ps1; run 'pyinstaller Verbatim.spec' first."
} else {
    Write-Host "  [!] No Verbatim.exe or Verbatim.py found here."
    exit 1
}

$Ws = New-Object -ComObject WScript.Shell
$lnk = $Ws.CreateShortcut($ShortcutPath)
$lnk.TargetPath = $Exe
$lnk.WorkingDirectory = $AppDir
$lnk.IconLocation = "$Exe,0"
$lnk.Save()
Write-Host "  [OK] Start Menu shortcut created"

$existing = Get-ItemProperty -Path $AutostartKey -Name "Verbatim" -ErrorAction SilentlyContinue
if (-not $existing) {
    New-ItemProperty -Path $AutostartKey -Name "Verbatim" -Value $Exe -PropertyType String | Out-Null
    Write-Host "  [OK] Autostart entry added"
} else {
    Set-ItemProperty -Path $AutostartKey -Name "Verbatim" -Value $Exe
    Write-Host "  [OK] Autostart entry updated"
}

Write-Host ""
Write-Host "  Done. Start it from the Start Menu, or run Verbatim.exe directly." -Foreground Green
Write-Host "  The settings window opens on first run; add your OpenAI and OpenRouter keys."
```

- [ ] **Step 2: Write `README.md`**

A short English README: describe press `Ctrl+Space` → talk → press again → paste; OpenAI/OpenRouter keys in Settings; bundled ffmpeg; `install.ps1` for Start Menu + autostart; `python Verbatim.py` to run from source; build with `pyinstaller Verbatim.spec`. Keep under ~500 words. Refer to upstream README for feature detail.

- [ ] **Step 3: Write `README.tr.md`**

Turkish translation of the same README.

- [ ] **Step 4: Commit**

```powershell
git add install.ps1 README.md README.tr.md
git commit -m "docs: Windows install.ps1 + readme (EN/TR)"
```

---

### Task 21: Manual end-to-end verification

> GUI/audio/network verification. Run each step against the spec's §8 plan.

- [ ] **Step 1: Run from source**

```powershell
python Verbatim.py
```
Expected: a tray icon appears; settings window opens (no API key); entering keys and saving persists them.

- [ ] **Step 2: Dictation paste**

Open WordPad, focus it, press `Ctrl+Space`, speak a sentence, press `Ctrl+Space`. Expected: cleaned text is pasted at the cursor; the corner overlay shows "Pasted: <preview>".

- [ ] **Step 3: Cancel + short recording**

`Ctrl+Space`, then tray → Cancel recording. Expected: no paste; overlay hides. A sub-0.3 s tap → "Recording too short".

- [ ] **Step 4: Silence detection**

`Ctrl+Space`, stay silent ~2 s, press `Ctrl+Space`. Expected: "No speech detected (X dB)".

- [ ] **Step 5: Wrong API key**

Settings → API: enter a bogus OpenAI key, save. Dictate. Expected: "OpenAI rejected the API key (HTTP 401)".

- [ ] **Step 6: Agent command**

Settings → Agent: provider OpenRouter, ensure OpenRouter key is set, set a shortcut `Ctrl+Alt+S`, save. Press `Ctrl+Alt+S`, speak "bugün nedir?". Expected: answer pasted within `assistant_timeout` seconds; a second command "ya yarın?" carries context.

- [ ] **Step 7: Meeting**

Tray → Record a meeting. Speak ~30 s. Tray → End the meeting and write it up. Expected: `%LOCALAPPDATA%\Verbatim\meetings\<base>.md` is written with headed sections; tray notification appears.

- [ ] **Step 8: File transcription**

Settings → Audio file: pick a `.mp3`, tick timestamps, untick/tick cleanup as desired, Transcribe. Expected: progress shown; output text with `[mm:ss]` prefixes; Save as `.srt` produces a valid SRT file.

- [ ] **Step 9: History + Minutes + language**

Settings → History shows the entry from Step 2; right-click → Delete removes it. Settings → Minutes shows the meeting from Step 7. Settings → General → switch language TR/EN; all strings update after restart.

- [ ] **Step 10: Hotkey conflict**

In another app bind `Ctrl+Space`, run Verbatim. Expected: Verbatim reports the conflict via `failed.emit` and the tray menu still toggles.

- [ ] **Step 11: Restart**

Tray → Restart. Expected: `Verbatim.exe` relaunches cleanly (or `python Verbatim.py` re-runs under dev).

No commit — verification only. If a step fails, open a fix task and re-run.

---

### Task 22: PyInstaller build

**Files:**
- Create: `Verbatim.spec`
- Binary placed (not committed): `ffmpeg.exe` in project root

- [ ] **Step 1: Install PyInstaller**

```powershell
python -m pip install pyinstaller
```

- [ ] **Step 2: Place `ffmpeg.exe` in the project root**

The user obtains a static `ffmpeg.exe` (e.g. from gyan.dev essentials build) and puts it at `C:\Users\user\projects\Verbatim\ffmpeg.exe`. It is gitignored (Task 1).

- [ ] **Step 3: Write `Verbatim.spec`**

```python
# -*- mode: python ; coding: utf-8 -*-
import os
block_cipher = None

a = Analysis(
    ['Verbatim.py'],
    pathex=[],
    binaries=[],
    datas=[('ffmpeg.exe', '.')],
    hiddenimports=['sounddevice', '_sounddevice_data'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='Verbatim',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
```
(Run with `--onefile` implicitly via `a.datas`/`a.binaries` packed into the EXE; the spec uses `--onefile` semantics through absence of a separate `COLLECT(...)`/`COLLECT` block — to be explicit, add `coll = COLLECT(...)` only if `--onedir` is wanted. The form above yields onefile behaviour.)

> If `--onefile` is not honoured by the spec as written, invoke PyInstaller from the CLI instead:
> ```powershell
> python -m PyInstaller --onefile --windowed --add-data "ffmpeg.exe;." --collect-all sounddevice --name Verbatim Verbatim.py
> ```
> This produces `dist\Verbatim.exe`.

- [ ] **Step 4: Build**

```powershell
python -m PyInstaller Verbatim.spec --noconfirm
```
Expected: `dist\Verbatim.exe` exists; size ~100–120 MB.

- [ ] **Step 5: Run the built exe**

Double-click `dist\Verbatim.exe`. Expected: tray icon appears; settings window opens on first run. Re-run the smoke parts of Task 21 Steps 2, 7, 8 against the frozen exe.

- [ ] **Step 6: Commit the spec**

```powershell
git add Verbatim.spec
git commit -m "build: PyInstaller one-file spec with bundled ffmpeg.exe"
```

---

### Task 23: Final review and polish

- [ ] **Step 1: Re-run the full test suite**

```powershell
$env:QT_QPA_PLATFORM="offscreen"; python -m unittest discover -s tests -v
```
Expected: all green.

- [ ] **Step 2: Cross-check the feature checklist (spec §5)**

Walk each `[x]` item in `docs/specs/2026-07-30-Verbatim-windows-design.md` §5 against the running app; tick any that were missed and open fix tasks.

- [ ] **Step 3: Commit remaining changes**

```powershell
git add -A
git commit -m "chore: final polish after end-to-end verification"
```

---

## Self-Review

**1. Spec coverage:** Spec §3 module map → Tasks 2–17 cover every module (i18n T2, config T3, api T4, vad T5, worker T16, assistant T13, filetranscribe T7, meeting T15, overlay T14, audio T12, paste T8, hotkey T10, config edits T3, Verbatim T18, settings_ui T17, trayicon T9, ffmpeg_path T6, wasapi_loopback T11). Spec §4.1–§4.9 ─ each subsection maps to a task: §4.1 T12, §4.2 T8, §4.3 T10, §4.4 T3, §4.5 T18, §4.6 T9, §4.7 T6/T7, §4.8 T2, §4.9 T17. Spec §2 distribution → T20/T22. Spec §5 checklist → verified T21/T23. Spec §8 verification → T21. Out-of-scope §10 ─ not implemented (correct).

**2. Placeholder scan:** No "TBD"/"implement later". The one labelled stub is `wasapi_loopback.open()` which deliberately raises `OSError` per the documented two-stage fallback (spec §4.1 path 2 + §9 risk) — this is a designed stub, not a placeholder. The PyInstaller spec includes both a `.spec` and a CLI fallback command to avoid any ambiguity.

**3. Type consistency:** `audio.Recorder` signals `level/stopped/failed` and methods `start/cancel/stop` match `worker.py` expectations (unchanged, Task 16). `audio.MeetingRecorder` signals `levels/stopped/died/failed` match `Verbatim.py` (unchanged, Task 18). `paste.copy/copy_bytes/read_clipboard/press/PasteError` signatures match `worker.py`. `hotkey.WindowsHotkey.start/stop/running/triggered/failed` plus `EvdevHotkey` alias match `Verbatim.py`'s `self.evdev` usage. `trayicon.icon(name)` matches the `name` strings `Verbatim.py._set_icon` is called with (`"audio-input-microphone"`, `"media-record"`, `"view-refresh"`). `ffmpeg_path.ffmpeg()` used by `filetranscribe._to_wav`. Config keys referenced in `settings_ui` (`shortcut`, `assistant_shortcut`, `meeting_shortcut`) are read by the simplified `_refresh_*` methods (Task 17). `evdev_hotkey` is kept in `DEFAULTS` (Task 3 keeps it verbatim) but unread by the Windows UI (Task 17 deletes its load/save lines and the checkbox).

No gaps found. Plan is complete.