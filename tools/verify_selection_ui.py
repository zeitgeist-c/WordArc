"""Native Qt visual checks for every selector and expanded advanced section."""
import os
import sys
import json
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_settings_smoke import TestSettingsSmoke
os.environ.pop("QT_QPA_PLATFORM", None)
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog, QListWidget
import settings_ui
import theme

def main():
    app = QApplication.instance() or QApplication([])
    TestSettingsSmoke.app = app
    fixture = TestSettingsSmoke()
    fixture.setUp()
    window = fixture.window
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.show()
    window.resize(1040, 760)
    window.transcribe_model.clear()
    window.transcribe_model.addItems([f"gemini-test-model-{i:02d}" for i in range(44)])
    def snapshot(dialog):
        dialog.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        dialog.show()
        app.processEvents()
        rows = dialog.findChild(QListWidget)
        assert rows.count() == current.count()
        assert rows.count() > 0
        assert dialog.grab().save(str(output / f"{mode}-picker-{index:02d}.png"))
        dialog.hide()
        return QDialog.DialogCode.Rejected
    combos = window.findChildren(settings_ui.FitsOnScreenCombo)
    manifest = [{"index": index, "field": next((name for name, value in vars(window).items() if value is combo), "selector"), "rows": combo.count()} for index, combo in enumerate(combos)]
    (output / "selectors.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    for mode in ("dark", "light"):
        theme.ThemeManager.apply(mode, app)
        for index, current in enumerate(combos):
            with mock.patch.object(QDialog, "exec", snapshot):
                current.showPopup()
        for tab in (0, 1, 2):
            window.tabs.setCurrentIndex(tab)
            app.processEvents()
            disclosure = window.tabs.widget(tab).findChild(settings_ui.Disclosure)
            disclosure.toggle.setChecked(True)
            for _ in range(3):
                app.processEvents()
            scroll = window.tabs.widget(tab).findChild(settings_ui.QScrollArea)
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
            app.processEvents()
            window.grab().save(str(output / f"{mode}-advanced-{tab}.png"))
            disclosure.toggle.setChecked(False)
            app.processEvents()
    print(f"SELECTORS OK: {len(combos)} selectors, 44 model rows, dark/light, advanced sections")
    fixture.tearDown()

if __name__ == "__main__":
    main()
