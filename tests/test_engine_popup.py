"""Motor seçimi popup'ı: kısa liste tam sığar, uzun liste kaydırılır.

Kullanıcı 0.7.0'da üç satırlık motor listesinde kaydırma çubuğu ve alttan
taşma gördü: yükseklik 34 px'lik sabit bir satır varsayımıyla hesaplanıyordu
ve satırlar gerçekte daha yüksek çiziliyordu.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

import localspeech
import settings_ui
import theme


def _combo(items):
    app = QApplication.instance() or QApplication([])
    combo = settings_ui.FitsOnScreenCombo()
    combo.setStyleSheet(theme.stylesheet(theme.palette(theme.ThemeMode.DARK)))
    for label, value in items:
        combo.addItem(label, value)
    combo.resize(420, 38)
    combo.show()
    QTest.mouseClick(combo, Qt.MouseButton.LeftButton)
    app.processEvents()
    QTest.qWait(30)
    return app, combo


def _close(combo):
    combo.hidePopup()
    combo.close()
    combo.deleteLater()


def test_engine_list_fits_without_scrolling():
    app, combo = _combo([(label, value) for label, value in localspeech.ENGINES])
    try:
        rows = combo._picker_rows
        assert rows.count() == len(localspeech.ENGINES)
        sb = rows.verticalScrollBar()
        assert sb.maximum() == 0, "üç satırlık liste kaydırmamalı"
        bottom = max(rows.visualRect(rows.model().index(i, 0)).bottom()
                     for i in range(rows.count()))
        assert bottom < rows.viewport().height(), "son satır kırpılmamalı"
    finally:
        _close(combo)


@pytest.mark.parametrize("count", [2, 3, 8, 40])
def test_a_scrolling_list_reaches_its_last_row(count):
    """A short list must fit whole; a long one must be able to scroll to the end.

    Half a row at the bottom edge of a scrolling list is normal. What is not
    normal is a list that needs scrolling to show the row the user came for.
    """
    items = [(f"Seçenek {i}", i) for i in range(count)]
    app, combo = _combo(items)
    try:
        rows = combo._picker_rows
        sb = rows.verticalScrollBar()
        viewport = rows.viewport()
        row_h = rows.sizeHintForRow(0)
        fits = count * row_h <= viewport.height()
        if fits:
            assert sb.maximum() == 0, (count, sb.maximum())
            bottom = max(rows.visualRect(rows.model().index(i, 0)).bottom()
                         for i in range(rows.count()))
            assert bottom < viewport.height(), (count, bottom)
        else:
            assert sb.maximum() > 0
            sb.setValue(sb.maximum())
            app.processEvents()
            last = rows.visualRect(rows.model().index(rows.count() - 1, 0))
            assert last.bottom() <= viewport.height() + 1, (count, last)
    finally:
        _close(combo)
