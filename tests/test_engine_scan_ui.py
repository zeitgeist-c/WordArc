"""Exercise selection, progress, cancellation, and stale worker responses."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading
import time
from unittest import mock

import pytest
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtWidgets import QApplication

import engine_discovery as discovery
from engine_scan_ui import EngineScanDialog
from tests import test_settings_smoke as smoke


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(app):
    window = EngineScanDialog()
    window.show()
    app.processEvents()
    yield window
    window.reject()
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def inventory():
    return discovery.Inventory(
        models=[discovery.Model("large-v3-turbo", "ct2", "C:/Hermes/models/faster-whisper-large-v3-turbo", 1624555275)],
        backends={"cpu": dict(ready=True, status="ready", detail="int8"),
                  "cuda": dict(ready=False, status="unavailable", detail="No NVIDIA GPU")})


def wait(app, condition):
    deadline = time.monotonic() + 3
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert condition()


def test_progress_then_explicit_selection_and_activation(dialog, app, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def scan(**kwargs):
        entered.set()
        release.wait(2)
        return inventory()
    monkeypatch.setattr(discovery, "scan", scan)
    chosen = []
    activated = mock.Mock()
    monkeypatch.setattr(discovery, "activate", activated)
    dialog.selected.connect(chosen.append)
    dialog.start()
    assert entered.wait(1)
    assert dialog.bar.minimum() == dialog.bar.maximum() == 0
    assert not dialog.use.isEnabled()
    # The UI remains responsive while search waits on the worker.
    dialog._on_progress(dialog._generation, dict(phase="probe", done=1, total=3, path="CUDA"))
    assert dialog.bar.value() == 1 and dialog.bar.maximum() == 3
    release.set()
    wait(app, lambda: not dialog._busy)
    assert dialog.results.count() == 1
    assert not dialog.use.isEnabled() and not chosen
    dialog.results.setCurrentRow(0)
    assert dialog.use.isEnabled()
    dialog.use.click()
    wait(app, lambda: bool(chosen))
    activated.assert_called_once()
    assert chosen[0]["model"].name == "large-v3-turbo"
    assert chosen[0]["device"] == "cpu"


def test_empty_scan_shows_download_card_and_engine_chips(dialog, app):
    found = discovery.Inventory(
        models=[],
        runtimes=[dict(path="C:/engines/whisper-vulkan", compatible=True,
                        status="ready", detail="")],
        backends={"cpu": dict(ready=True, status="ready", detail="int8"),
                  "cuda": dict(ready=False, status="unavailable",
                               detail="No NVIDIA GPU")})
    dialog._on_finished(dialog._generation, found, "")
    assert dialog.empty.isVisibleTo(dialog)
    assert not dialog.results.isVisibleTo(dialog)
    chips = dialog.backends.text()
    assert "CPU" in chips and "CUDA" in chips and "Vulkan" in chips
    assert not dialog.use.isEnabled()


def test_download_button_requests_settings_download(dialog, app):
    found = discovery.Inventory(models=[], backends={
        "cpu": dict(ready=True, status="ready", detail="int8"),
        "cuda": dict(ready=False, status="unavailable",
                     detail="No NVIDIA GPU")})
    dialog._on_finished(dialog._generation, found, "")
    asked = []
    dialog.download_requested.connect(lambda: asked.append(True))
    dialog.download.click()
    assert asked == [True]


def test_old_results_cannot_replace_new_scan(dialog):
    dialog._generation = 4
    dialog._busy = True
    dialog._on_finished(3, inventory(), "")
    assert dialog.inventory is None and dialog._busy
    dialog._on_finished(4, inventory(), "")
    assert dialog.inventory is not None


def test_new_scan_hides_empty_card_again(dialog, app, monkeypatch):
    dialog._on_finished(dialog._generation, discovery.Inventory(models=[]), "")
    assert dialog.empty.isVisibleTo(dialog)
    entered = threading.Event()
    def scan(**kwargs):
        entered.set()
        while not kwargs["stop"]():
            time.sleep(0.005)
        raise discovery.ScanCancelled()
    monkeypatch.setattr(discovery, "scan", scan)
    dialog.start()
    assert entered.wait(1)
    assert not dialog.empty.isVisibleTo(dialog)
    assert dialog.results.isVisibleTo(dialog)
    dialog.cancel.click()
    wait(app, lambda: not dialog._busy)


def test_cancel_terminates_worker_and_window_close_ignores_late_results(dialog, app, monkeypatch):
    entered = threading.Event()
    def scan(**kwargs):
        entered.set()
        while not kwargs["stop"]():
            time.sleep(0.005)
        raise discovery.ScanCancelled()
    monkeypatch.setattr(discovery, "scan", scan)
    dialog.start()
    assert entered.wait(1)
    dialog.cancel.click()
    wait(app, lambda: not dialog._busy)
    assert dialog.results.count() == 0
    old = dialog._generation
    dialog.reject()
    dialog._on_finished(old, inventory(), "")
    assert dialog.inventory is None


def test_partial_scan_and_unavailable_backend_remain_visible(dialog):
    found = inventory()
    found.partial = True
    found.backends["cpu"]["ready"] = False
    dialog._on_finished(dialog._generation, found, "")
    assert dialog.results.count() == 1
    assert not dialog.results.item(0).flags() & Qt.ItemFlag.ItemIsSelectable
    assert dialog.details.toPlainText()
    assert not dialog.use.isEnabled()


def test_selected_source_updates_settings_and_stale_device_inspection_is_dropped():
    smoke.TestSettingsSmoke.setUpClass()
    fixture = smoke.TestSettingsSmoke()
    fixture.setUp()
    window = fixture.window
    try:
        window._on_engine_source_selected(dict(model=inventory().models[0], device="cpu", runtime=""))
        fixture.wait_local_inspection()
        assert window.conf["local_stt_device"] == "cpu"
        assert window.conf["local_stt_model"] == "large-v3-turbo"
        assert window.local_stt_device.currentData() == "cpu"
        window._on_local_inspected("cpu", window._local_generation - 1, "stale")
        assert window._local_snapshots["cpu"] != "stale"
    finally:
        fixture.tearDown()
