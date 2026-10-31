"""Engine list popup: short plain lists open as a menu, long ones as a picker.

A user saw a scroll bar and bottom overflow in the three-row engine list in
0.7.0: the height was computed assuming a fixed 34 px row while the rows were
really drawn taller. Short lists now skip the picker entirely and open as a
native menu (like the language menu), which sizes itself to its items, so the
blank band cannot happen there.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest import mock

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
    app.processEvents()
    return app, combo


def _close(combo):
    combo.hidePopup()
    combo.close()
    combo.deleteLater()


class _Menu:
    """Stand-in for QMenu: records actions, answers exec() on script."""
    instances = []
    script = None

    def __init__(self, *args):
        self.actions = []
        self.instances.append(self)

    def addAction(self, text):
        action = mock.Mock()
        action.text.return_value = text
        action.data.return_value = len(self.actions)
        self.actions.append(action)
        return action

    def exec(self, *args):
        return self.script


def _popup(combo, script):
    _Menu.instances.clear()
    _Menu.script = script
    with mock.patch.object(settings_ui, "QMenu", _Menu):
        combo.showPopup()
    return _Menu.instances[-1]


def test_engine_list_opens_as_menu_with_current_checked():
    app, combo = _combo([(label, value) for label, value in localspeech.ENGINES])
    try:
        menu = _popup(combo, None)
        assert [a.text() for a in menu.actions] == [
            label for label, _value in localspeech.ENGINES]
        assert combo.currentIndex() == 0, "cancelling keeps the choice"
        combo.setCurrentIndex(1)
        menu = _popup(combo, None)
        assert menu.actions[1].setChecked.call_args == mock.call(True)
    finally:
        _close(combo)


def test_menu_choice_moves_the_combo():
    app, combo = _combo([(f"Option {i}", i) for i in range(3)])
    try:
        menu = _popup(combo, None)
        picked = menu.actions[2]
        _popup(combo, picked)
        assert combo.currentIndex() == 2
    finally:
        _close(combo)


@pytest.mark.parametrize("count", [2, 3])
def test_short_list_builds_no_picker(count):
    """No picker, no picker geometry: nothing that could leave a blank band."""
    items = [(f"Option {i}", i) for i in range(count)]
    app, combo = _combo(items)
    try:
        with mock.patch.object(settings_ui, "QMenu", _Menu):
            _Menu.instances.clear()
            _Menu.script = None
            combo.showPopup()
        assert not hasattr(combo, "_picker_rows")
    finally:
        _close(combo)


@pytest.mark.parametrize("kind", ["long", "editable", "searchable", "cards"])
def test_picker_still_serves_search_edit_and_cards(kind):
    app = QApplication.instance() or QApplication([])
    combo = settings_ui.FitsOnScreenCombo()
    delegate = None
    if kind == "long":
        for i in range(9):
            combo.addItem(f"Option {i}", i)
    elif kind == "editable":
        combo.setEditable(True)
        combo.addItem("Option", 1)
    elif kind == "searchable":
        combo.addItem("Option", 1)
        combo.setProperty("searchable", True)
    elif kind == "cards":
        for i in range(3):
            combo.addItem(f"Option {i}", i)
        delegate = settings_ui.DeviceCardDelegate(combo)
        combo.view().setItemDelegate(delegate)
    try:
        assert not combo._menu_serves(), kind
    finally:
        combo.close()
        combo.deleteLater()


@pytest.mark.parametrize("count", [9, 40])
def test_a_scrolling_list_reaches_its_last_row(count):
    """A long list must be able to scroll to the end.

    Half a row at the bottom edge of a scrolling list is normal. What is not
    normal is a list that needs scrolling to show the row the user came for.
    """
    items = [(f"Option {i}", i) for i in range(count)]
    app, combo = _combo(items)
    QTest.mouseClick(combo, Qt.MouseButton.LeftButton)
    app.processEvents()
    QTest.qWait(30)
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
