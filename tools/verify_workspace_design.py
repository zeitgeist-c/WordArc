"""Render isolated UI fixtures. No production configuration or credentials."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_settings_smoke import TestSettingsSmoke
os.environ.pop("QT_QPA_PLATFORM", None)
from PyQt6.QtWidgets import QApplication, QListWidgetItem
from PyQt6.QtCore import Qt
import theme
import i18n
import config as cfg
from unittest import mock

def main():
    app = QApplication.instance() or QApplication([])
    TestSettingsSmoke.app = app
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    for lang in ("tr", "en"):
        i18n.set_language(lang)
        case = TestSettingsSmoke()
        original_config = cfg.Config
        def language_config():
            conf = original_config()
            conf["ui_language"] = lang
            i18n.set_language(lang)
            return conf
        with mock.patch.object(cfg, "Config", side_effect=language_config):
            case.setUp()
        window = case.window
        window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        window.show()
        window.set_dictation_result("WordArc tasarımı için örnek dikte. Bu metin yalnız görsel kontrol verisidir.")
        for index in range(30):
            window.history.addItem(f"26.09.2026 · 14:{index:02d}\nÖrnek dikte kaydı {index + 1}")
        for index in range(15):
            item = QListWidgetItem(f"26.09.2026 · Toplantı {index + 1}")
            window.minutes_list.addItem(item)
        window.minutes_view.setPlainText("Örnek toplantı tutanağı\n\nKararlar\n• Yeni tasarım dört sekmede kullanılacak.\n• Sık seçimler doğrudan erişilebilir olacak.")
        window.file_output.setPlainText("[00:00] Örnek ses dosyasının yazıya çevrilmiş metni.\n[00:12] Bu içerik yalnız görsel kontrol içindir.")
        for mode in ("dark", "light"):
            window.conf["theme_mode"] = mode
            theme.ThemeManager.apply(mode, app)
            window._refresh_header_theme()
            for width, height in ((1040, 760), (520, 400)):
                window.resize(width, height)
                for tab in range(window.tabs.count()):
                    window.tabs.setCurrentIndex(tab)
                    app.processEvents()
                    window.grab().save(str(output / f"{lang}-{mode}-{width}-{tab}.png"))
        case.tearDown()
    print(f"scale={app.primaryScreen().devicePixelRatio()} output={output}")

if __name__ == "__main__":
    main()
