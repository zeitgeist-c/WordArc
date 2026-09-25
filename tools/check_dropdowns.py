"""The dropdown as the user sees it, in the real settings window.

The measurements so far walked a bare QComboBox down the screen, which proves
where the overshoot starts but not that the settings window is what puts it
there. This opens the actual SettingsWindow with the real stylesheet, moves it
where a user's window sits, opens the "Where it runs" popup, and measures the
popup against the screen — which is the claim the screenshots make.
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

os.environ.pop("QT_QPA_PLATFORM", None)
sys.path.insert(0, r"C:\Users\user\projects\WordArc")

from PyQt6.QtWidgets import QApplication  # noqa: E402

import config as cfg  # noqa: E402
import localspeech  # noqa: E402
import settings_ui  # noqa: E402
from PyQt6.QtCore import QSize  # noqa: E402


def main():
    app = QApplication([])
    tmp = Path(tempfile.mkdtemp())
    with mock.patch.object(cfg, "CONFIG_DIR", tmp / "c"), \
         mock.patch.object(cfg, "CONFIG_FILE", tmp / "c" / "config.json"), \
         mock.patch.object(cfg, "DATA_DIR", tmp / "d"), \
         mock.patch.object(cfg, "HISTORY_FILE", tmp / "d" / "h.jsonl"), \
         mock.patch.object(cfg, "MEETINGS_DIR", tmp / "d" / "m"), \
         mock.patch.object(cfg, "MEETINGS_FILE", tmp / "d" / "m.jsonl"), \
         mock.patch.object(cfg.credential_store, "read", return_value=""), \
         mock.patch.object(cfg.credential_store, "read_all", return_value=[]), \
         mock.patch.object(cfg.credential_store, "write_all"), \
         mock.patch.object(settings_ui.audio, "list_sources", return_value=[]), \
         mock.patch.object(settings_ui.audio, "refresh_devices"), \
         mock.patch.object(settings_ui.audio, "list_monitors", return_value=[]), \
         mock.patch.object(settings_ui.startup, "is_enabled", return_value=False), \
         mock.patch.object(localspeech, "models_dir", return_value=tmp / "none"):
        window = settings_ui.SettingsWindow(cfg.Config(), "wordarc toggle")
        window.resize(980, 900)
        window.show()
        app.processEvents()

        # The monitor this session has is taller than the one the screenshots
        # came from, and QScreen cannot be resized — so instead of pretending,
        # the window is pushed down until its bottom hangs past the screen edge
        # by the amount that broke it before. If the fix holds here, it holds
        # on a short screen too, because the popup has nowhere to go.
        avail = window.screen().availableGeometry()
        window.setGeometry(avail.x() + 60, avail.y() + 20, 980, 900)
        window._fit_on_screen(avail)
        app.processEvents()
        print(f"screen: {avail.getRect()}  bottom={avail.bottom()}")
        print(f"window: {window.geometry().getRect()}  "
              f"bottom past screen: {window.geometry().bottom() - avail.bottom():+d}px\n")

        # Every combo in the dialog, on the tab it lives on: the one that was
        # cut off in the screenshot is whichever sits lowest on the screen.
        seen = set()
        for tab in list(window._tab_index):
            try:
                window.navigate_to(tab)
            except Exception:
                continue
            app.processEvents()
            # Put the window where a user's window sits: centred, near the top.
            window.move(avail.x() + (avail.width() - 980) // 2, avail.top() + 20)
            app.processEvents()

        # The two the screenshots actually show: the engine box on the settings
        # tab, and the microphone list on the dictation tab. Both are the ones a
        # user opens, so those are the ones that have to fit.
        print("after moving the window up, the boxes a user can see:")
        cut = 0
        for tab in list(window._tab_index):
            window.navigate_to(tab)
            app.processEvents()
            window.move(avail.x() + (avail.width() - 980) // 2, avail.top() + 20)
            app.processEvents()
            for box in window.findChildren(type(window.transcribe_engine)):
                if id(box) in seen or not box.isVisible() or box.count() < 2:
                    continue
                seen.add(id(box))
                glob = box.mapToGlobal(box.rect().topLeft())
                if glob.y() > avail.bottom():
                    continue          # below the fold: the user cannot click it
                box.showPopup()
                app.processEvents()
                # Ask the combo itself where it put the popup, and check that
                # against the screen: this is the claim under test, not a
                # re-derivation of it in the test.
                rect = box.view().window().geometry()
                over = rect.bottom() - avail.bottom()
                over_top = avail.top() - rect.top()
                if over > 0 or over_top > 0:
                    cut += 1
                why = ("upward" if rect.bottom() < box.frameGeometry().bottom()
                       else "downward")
                print(f"  [{tab:9}] {box.currentText()[:24]:26} "
                      f"items={box.count():2d} box_y={box.frameGeometry().top():5d} "
                      f"popup=({rect.y()},{rect.height()}) {why:9} "
                      f"past_bottom={over:+4d} past_top={over_top:+4d}px"
                      f"{'   <-- CUT OFF' if over > 0 or over_top > 0 else '   ok'}")
                box.hidePopup()
                app.processEvents()
        print(f"\nvisible dropdowns cut off: {cut}")

        # The last box is the one that breaks: it sits in the final row of the
        # window, so a popup below it has nowhere to go. The window fits the
        # screen but not the screen *and* the popup under its last combo, which
        # is what the screenshot shows. Shrinking the window by the tallest
        # popup is the honest fix — the tabs scroll, so nothing is lost.
        if cut:
            tallest = 0
            for tab in list(window._tab_index):
                window.navigate_to(tab)
                app.processEvents()
                for box in window.findChildren(type(window.transcribe_engine)):
                    if not box.isVisible() or box.count() < 2:
                        continue
                    if box.mapToGlobal(box.rect().topLeft()).y() > avail.bottom():
                        continue
                    box.showPopup()
                    app.processEvents()
                    h = box.view().window().geometry().height()
                    box.hidePopup()
                    tallest = max(tallest, h)
            print(f"tallest popup among visible boxes: {tallest}px")
            need = window.height() + tallest
            print(f"window {window.height()}px + popup {tallest}px = {need}px "
                  f"vs screen {avail.height()}px "
                  f"-> {'too tall' if need > avail.height() else 'fits'}")
            if need > avail.height():
                new_h = max(400, avail.height() - tallest)
                window.resize(window.width(), new_h)
                app.processEvents()
                window._fit_on_screen(avail)
                app.processEvents()
                print(f"window shrunk to {window.height()}px, now re-measuring:")
                cut = 0
                seen.clear()
                for tab in list(window._tab_index):
                    window.navigate_to(tab)
                    app.processEvents()
                    window.move(avail.x() + (avail.width() - window.width()) // 2,
                                avail.top() + 20)
                    app.processEvents()
                    for box in window.findChildren(type(window.transcribe_engine)):
                        if id(box) in seen or not box.isVisible() or box.count() < 2:
                            continue
                        seen.add(id(box))
                        if box.mapToGlobal(box.rect().topLeft()).y() > avail.bottom():
                            continue
                        box.showPopup()
                        app.processEvents()
                        rect = box.view().window().geometry()
                        over = rect.bottom() - avail.bottom()
                        if over > 0:
                            cut += 1
                            print(f"  [{tab:9}] {box.currentText()[:24]:26} "
                                  f"past_bottom={over:+4d}px   <-- STILL CUT OFF")
                        box.hidePopup()
                        app.processEvents()
                print(f"visible dropdowns cut off after shrinking: {cut}")


if __name__ == "__main__":
    main()
