"""Ayarlar > Arayüz: ses dalgası biçimi seçimi ve canlı önizlemeler.

Kullanıcı dört biçimi de programda istedi ve seçilenin neye benzediğini
görmek istedi. Önizleme, üretim çizimiyle aynı fonksiyondan geçer; seçili
biçimin önizlemesi çerçeveli durur. Bu dosya o sözleşmeyi korur.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pathlib
import tempfile
import unittest
from unittest import mock

from PyQt6.QtWidgets import QApplication

import config as cfg
import localspeech
import overlay
import settings_ui


class TestMeterSettings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.patchers = [
            mock.patch.object(cfg, "CONFIG_DIR", root / "cfg"),
            mock.patch.object(cfg, "CONFIG_FILE", root / "cfg" / "config.json"),
            mock.patch.object(cfg, "DATA_DIR", root / "data"),
            mock.patch.object(cfg, "HISTORY_FILE", root / "data" / "history.jsonl"),
            mock.patch.object(cfg, "MEETINGS_DIR", root / "data" / "meetings"),
            mock.patch.object(cfg, "MEETINGS_FILE", root / "data" / "meetings.jsonl"),
            mock.patch.object(cfg.credential_store, "read", return_value=""),
            mock.patch.object(cfg.credential_store, "read_all", return_value=[]),
            mock.patch.object(cfg.credential_store, "write_all"),
            mock.patch.object(settings_ui.audio, "list_sources", return_value=[]),
            mock.patch.object(settings_ui.audio, "refresh_devices"),
            mock.patch.object(settings_ui.audio, "list_monitors", return_value=[]),
            mock.patch.object(settings_ui.startup, "is_enabled", return_value=False),
            mock.patch.object(localspeech.vulkan_speech, "available",
                              return_value=False),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self._stop_patchers)
        self.window = self._open()

    def _stop_patchers(self):
        for patcher in self.patchers:
            patcher.stop()

    def _open(self):
        window = settings_ui.SettingsWindow(cfg.Config(), "wordarc toggle")
        window.show()
        self.app.processEvents()
        return window

    def _framed(self, window):
        return [widget.style for widget in window.meter_previews
                if widget._selected]

    def test_combo_offers_every_style(self):
        values = [self.window.meter_style.itemData(i)
                  for i in range(self.window.meter_style.count())]
        self.assertEqual(values, ["bars", "spectrum", "wave", "capsule"])

    def test_one_preview_per_style(self):
        self.assertEqual([widget.style for widget in self.window.meter_previews],
                         ["bars", "spectrum", "wave", "capsule"])

    def test_saved_style_is_framed_on_open(self):
        self.window.meter_style.setCurrentIndex(
            self.window.meter_style.findData("capsule"))
        self.window._save()
        self.assertEqual(self.window.conf["overlay_meter"], "capsule")
        fresh = self._open()
        self.assertEqual(fresh.meter_style.currentData(), "capsule")
        self.assertEqual(self._framed(fresh), ["capsule"])
        fresh.close()

    def test_framed_style_survives_the_first_item(self):
        """Kayıtlı biçim listenin ilk maddesi olsa da çerçeve çizilmeli.

        Açılışta indeks zaten 0 ise açılır kutu sinyal yaymaz; çerçeveleme
        yalnız sinyale bağlı olsaydı kullanıcı hiçbirinin seçili olmadığını
        görürdü.
        """
        self.window.meter_style.setCurrentIndex(
            self.window.meter_style.findData("bars"))
        self.window._save()
        fresh = self._open()
        self.assertEqual(fresh.meter_style.currentIndex(), 0)
        self.assertEqual(self._framed(fresh), ["bars"])
        fresh.close()

    def test_changing_the_combo_moves_the_frame(self):
        for style in ("wave", "capsule", "bars", "spectrum"):
            self.window.meter_style.setCurrentIndex(
                self.window.meter_style.findData(style))
            self.app.processEvents()
            self.assertEqual(self._framed(self.window), [style], style)

    def test_previews_are_drawn_with_their_own_style(self):
        """Her önizleme kendi biçimini çizer: piksel imzaları ayrışmalı.

        Önizleme üretim çizimini çağırdığı için bu, şeritte göreceği şeyin
        aynısıdır; imzalar eşitse önizleme yalan söylüyor demektir.
        """
        from PyQt6.QtGui import QImage, QPainter
        signatures = {}
        for widget in self.window.meter_previews:
            image = QImage(widget.width(), widget.height(),
                           QImage.Format.Format_ARGB32)
            image.fill(0)
            painter = QPainter(image)
            widget.render(painter)
            painter.end()
            columns = {}
            for y in range(image.height()):
                for x in range(image.width()):
                    colour = image.pixelColor(x, y)
                    if colour.alpha() < 40:
                        continue
                    r, g, b = colour.red(), colour.green(), colour.blue()
                    if r > 60 and r > g + 25 and r > b + 25:
                        columns[x] = columns.get(x, 0) + 1
            runs = []
            previous = None
            for x in sorted(columns):
                if previous is None or x > previous + 1:
                    runs.append(1)
                else:
                    runs[-1] += 1
                previous = x
            signatures[widget.style] = (len(runs), max(runs) if runs else 0)
        self.assertEqual(len(set(signatures.values())), 4, signatures)

    def test_unknown_saved_style_falls_back(self):
        self.window.conf["overlay_meter"] = "bilinmeyen"
        self.window._load()
        self.assertEqual(self.window.meter_style.currentData(), "bars")
        overlay.set_meter("spectrum")

    def tearDown(self):
        self.window.close()
