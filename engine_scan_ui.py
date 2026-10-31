"""Responsive discovery and explicit selection of existing local speech models."""
import threading

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget,
                            QListWidgetItem, QPushButton, QProgressBar,
                            QPlainTextEdit, QVBoxLayout, QFileDialog)

import engine_discovery as discovery
from i18n import t


class EngineScanDialog(QDialog):
    selected = pyqtSignal(object)
    _progress = pyqtSignal(int, object)
    _finished = pyqtSignal(int, object, str)
    _activated = pyqtSignal(int, object, str)

    def __init__(self, parent=None, *, scan_options=None):
        super().__init__(parent)
        self.setWindowTitle(t("Find local speech models"))
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(820, 640)
        self.setMinimumSize(580, 440)
        self._generation = 0
        self._stop = threading.Event()
        self._extra = []
        self._scan_options = dict(scan_options or {})
        self._busy = False
        self._applying = False
        self.inventory = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        title = QLabel(t("Your models, already on this computer"))
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        title.setWordWrap(True)
        layout.addWidget(title)
        subtitle = QLabel(t("Search WordArc and model caches first, then user folders and local drives. Choose a model; shared files stay in place."))
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        self.status = QLabel(t("Preparing scan…"))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        self.bar.setStyleSheet("QProgressBar { min-height: 8px; max-height: 8px; border: 0; border-radius: 4px; } QProgressBar::chunk { border-radius: 4px; }")
        self.bar.setAccessibleName(t("Scan progress"))
        layout.addWidget(self.bar)
        self.location = QLabel("")
        self.location.setObjectName("muted")
        self.location.setWordWrap(True)
        self.location.setMaximumHeight(52)
        layout.addWidget(self.location)
        self.backends = QLabel("")
        self.backends.setWordWrap(True)
        layout.addWidget(self.backends)
        self.results = QListWidget()
        self.results.setSpacing(5)
        self.results.setWordWrap(True)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.setAccessibleName(t("Discovered models"))
        self.results.currentRowChanged.connect(self._selection_changed)
        layout.addWidget(self.results, 1)
        self.coverage = QLabel("")
        self.coverage.setWordWrap(True)
        self.coverage.setObjectName("muted")
        self.coverage.hide()
        layout.addWidget(self.coverage)
        self.detail_toggle = QPushButton(t("Show scan details"))
        self.detail_toggle.setCheckable(True)
        self.detail_toggle.setObjectName("disclosure")
        layout.addWidget(self.detail_toggle)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(110)
        self.details.setPlaceholderText(t("Scan details and inaccessible locations appear here."))
        layout.addWidget(self.details)
        self.details.hide()
        self.detail_toggle.toggled.connect(self.details.setVisible)
        actions = QHBoxLayout()
        self.folder = QPushButton(t("Search another folder…"))
        self.folder.clicked.connect(self._add_folder)
        self.rescan = QPushButton(t("Scan again"))
        self.rescan.clicked.connect(self.start)
        self.cancel = QPushButton(t("Stop scan"))
        self.cancel.clicked.connect(self._cancel)
        self.use = QPushButton(t("Use this model"))
        self.use.setObjectName("primaryButton")
        self.use.setEnabled(False)
        self.use.clicked.connect(self._use)
        for button in (self.folder, self.rescan, self.cancel):
            actions.addWidget(button)
        actions.addStretch(1)
        actions.addWidget(self.use)
        layout.addLayout(actions)
        self._progress.connect(self._on_progress)
        self._finished.connect(self._on_finished)
        self._activated.connect(self._on_activated)

    def _emit(self, signal, *args):
        try:
            signal.emit(*args)
        except RuntimeError:
            pass  # Qt has already deleted the closed window.

    def start(self):
        self._stop.set()
        self._generation += 1
        generation = self._generation
        stop = self._stop = threading.Event()
        extra = tuple(self._extra)
        self._busy = True
        self.inventory = None
        self.results.clear()
        self.details.clear()
        self.coverage.hide()
        self.backends.clear()
        self.bar.setRange(0, 0)
        self.status.setText(t("Searching for existing engines and models…"))
        self.location.clear()
        self.location.show()
        self._buttons()

        def work():
            try:
                result = discovery.scan(extra=extra, stop=stop.is_set,
                                        progress=lambda value: self._emit(self._progress, generation, value),
                                        **self._scan_options)
                self._emit(self._finished, generation, result, "")
            except discovery.ScanCancelled:
                self._emit(self._finished, generation, None, t("Scan stopped. You can scan again or choose another folder."))
            except Exception as exc:
                self._emit(self._finished, generation, None, f"{type(exc).__name__}: {exc}")
        threading.Thread(target=work, daemon=True).start()

    def _buttons(self):
        busy = self._busy or self._applying
        self.folder.setEnabled(not busy)
        self.rescan.setEnabled(not busy)
        self.cancel.setEnabled(not self._applying)
        self.cancel.setText(t("Stop scan") if self._busy else t("Close"))
        self.use.setEnabled(not busy and self.results.currentItem() is not None
                            and self.results.currentItem().data(Qt.ItemDataRole.UserRole) is not None)

    def _selection_changed(self, *_):
        self._buttons()

    def _on_progress(self, generation, value):
        if generation != self._generation or not self._busy:
            return
        if value["phase"] == "search":
            self.status.setText(t("Searching… {count} models found · {files} entries checked",
                                  count=value["models"], files=value["visited"]))
        elif value["phase"] == "probe":
            self.bar.setRange(0, value["total"])
            self.bar.setValue(value["done"])
            self.status.setText(t("Checking CPU, CUDA and Vulkan… {done}/{total}",
                                  done=value["done"], total=value["total"]))
        self.location.setText(value["path"])

    def _on_finished(self, generation, inventory, error):
        if generation != self._generation:
            return
        self._busy = False
        self.bar.setRange(0, 1)
        self.bar.setValue(1 if inventory else 0)
        self.location.clear()
        self.location.hide()
        self.inventory = inventory
        if error:
            self.status.setText(error)
            self._buttons()
            return
        rows = discovery.choices(inventory)
        self.status.setText(t("{models} models found · {choices} choices available",
                              models=len(inventory.models), choices=len(rows)))
        notes = []
        for kind in ("cpu", "cuda"):
            result = inventory.backends[kind]
            notes.append(f"{kind.upper()}: {t('Ready') if result['ready'] else t('Unavailable')}")
        native = sum(row["compatible"] for row in inventory.runtimes)
        notes.append(t("Native engines: {count}", count=native))
        self.backends.setText("   ·   ".join(notes))
        for choice in rows:
            model = choice["model"]
            suffix = t("Validate on selection") if choice["unverified"] else t("Files found")
            lower = model.path.lower()
            origin = ("Hugging Face" if "huggingface" in lower else "Hermes" if "hermes" in lower
                      else "WordArc" if "wordarc" in lower else t("This computer"))
            item = QListWidgetItem(
                f"Whisper {model.name}  ·  {choice['device'].upper()}\n"
                f"{origin}  ·  {model.size / (1024 ** 2):.0f} MB  ·  {suffix}\n{model.path}")
            item.setData(Qt.ItemDataRole.UserRole, choice)
            item.setToolTip(model.path + ("\n" + choice["runtime"] if choice["runtime"] else ""))
            self.results.addItem(item)
        available = {row["model"] for row in rows}
        for model in inventory.models:
            if model not in available:
                item = QListWidgetItem(f"Whisper {model.name} · {t('Backend unavailable')}\n{model.path}")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                self.results.addItem(item)
        messages = []
        if inventory.partial:
            message = t("Search limit reached. Some locations were not checked; select a specific folder to continue.")
            messages.append(message)
            self.coverage.setText(message)
            self.coverage.show()
        for kind, value in inventory.backends.items():
            messages.append(f"{kind.upper()}: {t(value['status'])} — {value['detail']}")
        for runtime in inventory.runtimes:
            messages.append(f"{runtime['path']} — {t(runtime['status'])} {runtime['detail']}")
        for path, status, detail in inventory.issues[:100]:
            messages.append(f"{path} — {t(status)} {detail}")
        if not inventory.models:
            messages.insert(0, t("No compatible models found. Search another folder or download a model in Settings."))
        self.details.setPlainText("\n".join(messages))
        self.results.setCurrentRow(-1)
        self._buttons()

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, t("Choose a folder to search"))
        if folder:
            self._extra.insert(0, folder)
            self.start()

    def _cancel(self):
        if self._busy:
            self._stop.set()
            self.cancel.setEnabled(False)
            self.status.setText(t("Stopping scan…"))
        else:
            self.reject()

    def _use(self):
        item = self.results.currentItem()
        choice = item.data(Qt.ItemDataRole.UserRole) if item else None
        if choice is None or self._busy or self._applying:
            return
        self._applying = True
        self._buttons()
        self.status.setText(t("Validating the selected model and engine…"))
        self.bar.setRange(0, 0)
        generation = self._generation
        stop = self._stop

        def work():
            try:
                discovery.activate(choice, stop.is_set)
                self._emit(self._activated, generation, choice, "")
            except Exception as exc:
                self._emit(self._activated, generation, choice, str(exc))
        threading.Thread(target=work, daemon=True).start()

    def _on_activated(self, generation, choice, error):
        if generation != self._generation:
            return
        self._applying = False
        self.bar.setRange(0, 1)
        self.bar.setValue(1)
        if error:
            self.status.setText(t("Could not use this model: {error}", error=error))
            self._buttons()
            return
        self.selected.emit(choice)
        self.accept()

    def reject(self):
        self._stop.set()
        self._generation += 1
        super().reject()

    def closeEvent(self, event):
        self._stop.set()
        self._generation += 1
        super().closeEvent(event)
