"""The frozen-build check: prove the exe really runs what it ships.

Two probes, chosen by argv[1], because a source-tree test cannot stand in for
either:

  stt    — load the speech engine from inside the exe and transcribe a real
           recording. The spec once listed faster_whisper as a hidden import
           while the package was absent from the build environment; the exe
           started fine and only failed when a key was pressed.
  cards  — build the device dropdown and paint it. Row heights and text
           eliding are exactly what changes between the source tree and a
           frozen build, so a screenshot taken in the source tree is not
           evidence about the shipped exe.

Run from a console build of the same spec: the shipped one is console=False
and swallows the evidence.
"""
import os
import sys

if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ.pop("QT_QPA_PLATFORM", None)

DEVICES = [
    ("t0", "Varsayılan mikrofon", ""),
    ("t1", "Microsoft Ses Eşleştiricisi - Input", "built-in"),
    ("t2", "Mikrofon (Razer Seiren V3 Mini)", "usb"),
    ("t3", "Mikrofon (3- USBGH8-Plus-7.1-ENC)", "usb"),
    ("t4", "Birincil Ses Yakalama Sürücüsü", "built-in"),
    ("t5", "Kulaklık (REDMI Buds 8 Lite) - Hands-Free", "bluetooth"),
    ("t6", "Yedek mikrofon (USB)", "usb"),
    ("t7", "Karaoke mikrofonu", ""),
]
SHORT = [("t0", "Bulut (Gemini)", ""), ("t1", "Yerel (bu bilgisayar)", "")]


def stt(where, name, audio_path):
    import time

    print("frozen:", getattr(sys, "frozen", False), flush=True)
    print("exe:", sys.executable, flush=True)
    import ctranslate2
    import faster_whisper
    print("faster_whisper:", faster_whisper.__file__, flush=True)
    print("ctranslate2:", ctranslate2.__version__, flush=True)

    import localspeech

    t0 = time.monotonic()
    segments = localspeech.transcribe(name, audio_path, language="tr",
                                      with_segments=True, where=where)
    text = " ".join(part for _, _, part in segments)
    print(f"transcribed {len(segments)} segments in {time.monotonic() - t0:.1f}s")
    print(f"text: {text[:200]!r}")
    assert text.strip(), "the frozen build returned nothing"
    print("FROZEN TRANSCRIPTION OK")


def cards():
    from PyQt6.QtCore import QRect
    from PyQt6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter
    from PyQt6.QtWidgets import QApplication, QStyle, QStyleOptionViewItem

    import settings_ui
    import theme

    print("frozen:", getattr(sys, "frozen", False), flush=True)
    print("exe:", sys.executable, flush=True)

    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(theme.stylesheet(theme.palette(theme.ThemeMode.DARK)))
    app.processEvents()

    out = os.path.join(os.environ.get("TMPDIR", os.getcwd()), "wa-shots")
    os.makedirs(out, exist_ok=True)

    box = settings_ui.FitsOnScreenCombo()
    settings_ui.SettingsWindow._fill_device_combo(
        box, DEVICES, "Varsayılan mikrofon", "t3")
    box.setFixedWidth(560)
    box.show()
    app.processEvents()

    delegate = box.view().itemDelegate()
    print("delegate:", type(delegate).__name__, flush=True)
    print("row 0 second line:", repr(delegate.connection_text(0)), flush=True)
    print("row 3 second line:", repr(delegate.connection_text(3)), flush=True)

    plain = settings_ui.FitsOnScreenCombo()
    settings_ui.SettingsWindow._fill_device_combo(
        plain, SHORT, "Bulut (Gemini)", "t0")
    plain.setFixedWidth(560)
    plain.show()
    app.processEvents()
    print("short list delegate:",
          type(plain.view().itemDelegate()).__name__, flush=True)

    problems = []
    if not isinstance(delegate, settings_ui.DeviceCardDelegate):
        problems.append("a long device list is not drawing as cards")
    if isinstance(plain.view().itemDelegate(),
                  settings_ui.DeviceCardDelegate):
        problems.append("a two-row list is drawing as cards")
    if delegate.connection_text(3) != "USB":
        problems.append(
            f"row 3's second line is {delegate.connection_text(3)!r}, not 'USB'")

    row_h = box._row_height()
    small = QFont(box.font())
    small.setPointSizeF(max(8.0, box.font().pointSizeF() - 1.5))
    needed = (QFontMetrics(box.font()).lineSpacing()
              + QFontMetrics(small).lineSpacing()
              + settings_ui.DeviceCardDelegate.PAINT_PADDING_TOP
              + settings_ui.DeviceCardDelegate.PAINT_PADDING_BOTTOM)
    print(f"card row is {row_h}px, needs {needed}px", flush=True)
    if row_h < needed:
        problems.append(f"a card row is {row_h}px but needs {needed}px")

    view = box.view()
    width = 560
    # The popup's own frame is around the rows: a popup sized to the rows
    # alone draws its 1px border over the first and last row.
    height = row_h * box.count() + view.frameWidth() * 2 + 8
    colors = theme.palette()
    img = QImage(width, height, QImage.Format.Format_ARGB32)
    img.fill(QColor(colors.surface_alt))
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    model = view.model()
    for row in range(box.count()):
        index = model.index(row, 0)
        opt = QStyleOptionViewItem()
        opt.rect = QRect(0, row * row_h, width, row_h)
        opt.font = view.font()
        opt.fontMetrics = view.fontMetrics()
        opt.palette = view.palette()
        opt.state = (QStyle.StateFlag.State_Selected
                     if row == box.currentIndex()
                     else QStyle.StateFlag.State_Enabled)
        delegate.paint(painter, opt, index)
    painter.end()
    path = os.path.join(out, "frozen-cards.png")
    img.save(path)
    print("shot:", path, f"({width}x{height})", flush=True)

    for problem in problems:
        print("PROBLEM:", problem, flush=True)
    assert not problems, "the frozen build's device list is wrong"
    print("FROZEN CARDS OK")


def workspace():
    """Exercise bundled settings with fully isolated storage and credentials."""
    import tempfile
    from pathlib import Path
    from unittest import mock
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    import config as cfg
    import settings_ui
    import startup
    import theme
    from brand import BRAND
    app = QApplication.instance() or QApplication([])
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="wordarc-release-check-") as scratch:
        root = Path(scratch)
        with mock.patch.object(cfg, "CONFIG_DIR", root / "config"), \
             mock.patch.object(cfg, "CONFIG_FILE", root / "config" / "config.json"), \
             mock.patch.object(cfg, "HISTORY_FILE", root / "history.jsonl"), \
             mock.patch.object(cfg, "MEETINGS_DIR", root / "meetings"), \
             mock.patch.object(cfg, "MEETINGS_FILE", root / "meetings.jsonl"), \
             mock.patch.object(cfg.credential_store, "read_all", return_value=[]), \
             mock.patch.object(cfg.credential_store, "read", return_value=""), \
             mock.patch.object(settings_ui.audio, "list_sources", return_value=[]), \
             mock.patch.object(settings_ui.audio, "list_monitors", return_value=[]), \
             mock.patch.object(settings_ui.audio, "refresh_devices"), \
             mock.patch.object(startup, "is_enabled", return_value=False):
            conf = cfg.Config()
            window = settings_ui.SettingsWindow(conf, "isolated toggle")
            window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            theme.ThemeManager.apply("dark", app)
            window.show()
            window.resize(1040, 760)
            assert window.tabs.count() == 4
            combos = window.findChildren(settings_ui.FitsOnScreenCombo)
            assert len(combos) >= 15
            for combo in combos:
                with mock.patch.object(combo, "_search_picker") as picker, \
                     mock.patch.object(settings_ui.QComboBox, "showPopup") as native:
                    combo.showPopup()
                searchable = combo.isEditable() or combo.property("searchable") or combo.count() > 8
                assert picker.call_count == int(bool(searchable))
                assert native.call_count == int(not searchable)
            assert window.transcribe_model.lineEdit().isReadOnly()
            assert window.dictation_record_button.isEnabled()
            window.set_recording_state("dictation", "busy", "release probe")
            assert not window.dictation_record_button.isEnabled()
            window.set_dictation_result("Isolated release verification")
            for index in range(4):
                window.tabs.setCurrentIndex(index)
                app.processEvents()
                assert window.grab().save(str(out / f"workspace-{index}.png"))
            window.close()
            assert not cfg.CONFIG_FILE.exists()
            assert not cfg.HISTORY_FILE.exists()
    print(f"FROZEN WORKSPACE OK version={BRAND.version} frozen={getattr(sys, 'frozen', False)}", flush=True)


def download():
    """Verify HTTPS, checksums and engine loading in the frozen runtime."""
    import localspeech
    name, output = sys.argv[2:4]
    last_phase = None
    def progress(value):
        nonlocal last_phase
        if value.phase != last_phase:
            print(value.phase, value.filename, value.completed, value.total, flush=True)
            last_phase = value.phase
    size = localspeech.download(name, where=output, on_progress=progress)
    assert localspeech.state(name, where=output).installed
    instance = localspeech.engine(name, where=output)
    print(f"FROZEN DOWNLOAD OK name={name} bytes={size} engine={type(instance).__name__}", flush=True)


def main():
    probe = sys.argv[1] if len(sys.argv) > 1 else "stt"
    if probe == "runtime":
        import tempfile
        import wave
        import unicodedata
        import localspeech
        assert unicodedata.normalize('NFC', 'e\u0301') == '\u00e9'
        where, name = sys.argv[2:4]
        with tempfile.TemporaryDirectory(prefix='wordarc-runtime-') as scratch:
            recording = os.path.join(scratch, 'silence.wav')
            with wave.open(recording, 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b'\0' * 32000)
            result = localspeech.transcribe(name, recording, language='en',
                                           where=where, device_preference='cpu')
            assert isinstance(result, str)
        print(f'FROZEN RUNTIME OK version={__import__("brand").BRAND.version} device=cpu unicode=ok decode=ok', flush=True)
    elif probe == "workspace":
        workspace()
    elif probe == "download":
        download()
    elif probe == "cards":
        cards()
    else:
        stt(sys.argv[2], sys.argv[3], sys.argv[4])


if __name__ == "__main__":
    main()
