"""Settings window."""

import os
import logging
import threading

from PyQt6.QtCore import QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import (QDesktopServices, QFont, QGuiApplication, QIcon,
                         QKeySequence, QShortcut)
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QStyle,
    QTabWidget, QVBoxLayout, QWidget,
)

import api
import audio
import config as cfg
import filetranscribe
import hotkey
import i18n
import meeting
import startup
import theme
from brand import BRAND, brand_asset
from filetranscribe import FileTranscriber
from i18n import t

UI_LANGUAGES = [("Automatic (system)", "auto"), ("Turkish", "tr"), ("English", "en")]
LANGUAGES = [
    ("Detect automatically", "auto"), ("Turkish", "tr"), ("English", "en"),
    ("German", "de"), ("French", "fr"), ("Spanish", "es"), ("Arabic", "ar"),
]
CORNERS = ["bottom-left", "bottom-right", "top-left", "top-right"]
# Starting points for the model box; "Fetch model list" replaces them with
# whatever Gemini offers today.
TRANSCRIBE_MODELS = ["gemini-3.5-flash-lite", "gemini-3.6-flash"]
CLEANUP_MODELS = [
    "gemini-3.5-flash-lite", "gemini-3.6-flash",
]
# Minutes are a harder job than cleanup: an hour of talk has to be read whole
# and turned into decisions, so the starting points are the larger models.
MEETING_MODELS = [
    "gemini-3.6-flash", "gemini-3.5-flash-lite",
]
MEETING_STATUS = {
    "recorded": "waiting to be written up",
    "transcribed": "transcript ready, minutes missing",
    "failed": "failed",
}
# How hard the cleanup model may think before it answers.
# A model that ignores the field simply answers as it always did.
REASONING_LEVELS = [
    ("Model's own default", ""), ("Off", "none"), ("Minimal", "minimal"),
    ("Low", "low"), ("Medium", "medium"), ("High", "high"),
    ("Very high", "xhigh"), ("Maximum", "max"),
]
PASTE_SHORTCUTS = ["ctrl+v", "ctrl+shift+v", "shift+insert"]
# Offered for all three global shortcuts, which keeps them one kind of field
# rather than three. The boxes stay editable: this is a shortlist of
# combinations that are usually free, not the set of ones that work.
SHORTCUTS = [
    "Ctrl+Space", "Ctrl+Alt+Space", "Ctrl+Shift+Space", "Meta+Space",
    "Ctrl+Alt+A", "Ctrl+Alt+D", "Ctrl+Alt+M", "Ctrl+Alt+Q",
    "Meta+A", "Meta+D", "Meta+M",
    "Ctrl+Alt+F1", "Ctrl+Alt+F2", "Ctrl+Alt+F3",
]
AUDIO_FILTER = ("*.mp3 *.wav *.m4a *.ogg *.opus *.flac *.aac *.wma "
                "*.mp4 *.mkv *.webm *.mov *.avi")


class SettingsWindow(QDialog):
    applied = pyqtSignal()
    language_changed = pyqtSignal()

    _models_loaded = pyqtSignal(list, str)
    _transcribe_models_loaded = pyqtSignal(list, str)
    _test_done = pyqtSignal(bool, str)

    def __init__(self, conf, launch_command, meeting_command=None,
                 meetings=None, ask_command=None, parent=None):
        super().__init__(parent)
        self.conf = conf
        self.launch_command = launch_command
        self.meeting_command = meeting_command or launch_command
        self.meetings = meetings
        # Each provider keeps its own transcription model, so switching the
        # provider back and forth never overwrites the other one's.
        # No parent on purpose: the worker thread may still emit after this
        # window is closed, and a signal emitted on a deleted child crashes
        # the whole app. Without a parent the object outlives the window and
        # Qt drops signals to dead slots safely.
        self.transcriber = FileTranscriber(conf)
        self.setObjectName("settingsRoot")
        self.setWindowTitle(t("WordArc Settings"))
        self.setWindowIcon(QIcon(str(brand_asset("wordarc.ico"))))
        self.resize(920, 700)
        self.setMinimumSize(760, 560)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(2, 0, 2, 8)
        logo = QLabel()
        logo.setPixmap(QIcon(str(brand_asset("wordarc-app.svg"))).pixmap(44, 44))
        logo.setFixedSize(48, 48)
        header_layout.addWidget(logo)
        identity = QVBoxLayout()
        name = QLabel(f"{BRAND.name} v{BRAND.version}")
        name.setObjectName("brandName")
        identity.addWidget(name)
        subtitle = QLabel(t("Dictation and meetings — in one flow."))
        subtitle.setObjectName("muted")
        identity.addWidget(subtitle)
        header_layout.addLayout(identity)
        header_layout.addStretch()
        header_layout.addWidget(QLabel(t("Language")))
        self.header_lang = QPushButton()
        self.header_lang.setMinimumWidth(110)
        self.header_lang.clicked.connect(self._toggle_lang)
        header_layout.addWidget(self.header_lang)
        header_layout.addWidget(QLabel(t("Theme")))
        self.header_theme = QPushButton()
        self.header_theme.setMinimumWidth(110)
        self.header_theme.clicked.connect(self._cycle_theme)
        # The application tab never had its own theme control; the alias stays
        # so external code keeps working.
        self.general_theme = self.header_theme
        header_layout.addWidget(self.header_theme)

        content = self._build_navigation()

        # Save keeps the window open, so the window is closed with the titlebar
        # cross (or Escape) instead. A "Cancel" next to it would be a lie: the
        # settings are already on disk by then.
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(t("Save"))
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primaryButton")
        buttons.accepted.connect(self._save)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(8)
        layout.addWidget(header)
        layout.addWidget(content, 1)
        layout.addWidget(buttons)

        self._models_loaded.connect(self._on_models_loaded)
        self._transcribe_models_loaded.connect(self._on_transcribe_models_loaded)
        self._test_done.connect(self._on_test_done)
        self.transcriber.progress.connect(self._on_file_progress)
        self.transcriber.finished.connect(self._on_file_finished)
        self.transcriber.failed.connect(self._on_file_failed)
        if self.meetings is not None:
            self.meetings.progress.connect(self._on_minutes_progress)
            self.meetings.finished.connect(self._on_minutes_finished)
            self.meetings.failed.connect(self._on_minutes_failed)
        self._load()
        self._refresh_shared_ai_summaries()
        self.transcribe_model.currentTextChanged.connect(self._refresh_shared_ai_summaries)
        self.cleanup_model.currentTextChanged.connect(self._refresh_shared_ai_summaries)
        self.navigate_to("dictation")

    def _build_navigation(self):
        self._shared_ai_labels = []
        self.tabs = QTabWidget()
        self.tabs.setObjectName("settingsTabs")
        tab_font = QFont()
        tab_font.setPointSize(11)
        self.tabs.setFont(tab_font)
        self.tabs.tabBar().setIconSize(QSize(22, 22))
        # Old logical page ids keep working: aliases point at the tab that
        # absorbed them (history lives in dictation, minutes in meeting).
        self._tab_index = {}
        style = self.style()
        specs = [
            ("dictation", ("history",), "Dictation",
             "Record, transcribe and paste spoken text.",
             style.standardIcon(QStyle.StandardPixmap.SP_MediaVolume),
             self._dictation_tab(), True),
            ("meeting", ("minutes",), "Meeting",
             "Capture microphone and system audio reliably.",
             style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay),
             self._meeting_tab(), True),
            ("audio_file", (), "Audio file",
             "Transcribe an existing recording.",
             style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton),
             self._file_tab(), False),
            ("settings", ("shared_ai", "application"), "Settings",
             "Models, language, startup and appearance.",
             style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon),
             self._settings_tab(), True),
        ]
        for main_id, aliases, title, description, icon, body, scroll in specs:
            wrapped, _scroller = self._wrap_page(body, title, description, scroll)
            index = self.tabs.addTab(wrapped, icon, t(title))
            self._tab_index[main_id] = index
            for alias in aliases:
                self._tab_index[alias] = index
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self.tabs)
        return content

    def _wrap_page(self, page, title, description, scroll=True):
        page.setObjectName("pageCard")
        page.setMinimumWidth(0)
        page.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        container = QWidget()
        container.setObjectName("page")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 16, 4, 4)
        heading = QLabel(t(title))
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        detail = QLabel(t(description))
        detail.setObjectName("pageDescription")
        detail.setWordWrap(True)
        layout.addWidget(detail)
        scroller = None
        if scroll:
            scroller = QScrollArea()
            scroller.setFrameShape(QFrame.Shape.NoFrame)
            scroller.setWidgetResizable(True)
            scroller.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            scroller.setWidget(page)
            layout.addWidget(scroller, 1)
        else:
            layout.addWidget(page, 1)
        return container, scroller

    def _show_page(self, page_id):
        index = self._tab_index.get(page_id)
        if index is None:
            return
        self.tabs.setCurrentIndex(index)

    def navigate_to(self, page_id):
        """Open the tab holding one logical page."""
        if page_id not in self._tab_index:
            return False
        self._show_page(page_id)
        return True

    def _shared_ai_note(self):
        holder = QWidget()
        holder.setObjectName("sharedAiNote")
        row = QHBoxLayout(holder)
        row.setContentsMargins(12, 8, 8, 8)
        label = QLabel("")
        label.setObjectName("muted")
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._shared_ai_labels.append(label)
        row.addWidget(label, 1)
        open_ai = QPushButton(t("Open shared AI settings"))
        open_ai.clicked.connect(lambda: self.navigate_to("shared_ai"))
        row.addWidget(open_ai)
        return holder

    def _refresh_shared_ai_summaries(self, *_):
        if not hasattr(self, "transcribe_model"):
            return
        summary = t(
            "Transcription: {transcribe} · Cleanup: {cleanup}",
            transcribe=self.transcribe_model.currentText(),
            cleanup=self.cleanup_model.currentText(),
        )
        for label in self._shared_ai_labels:
            label.setText(summary)

    THEME_ORDER = ("dark", "light", "system")
    THEME_LABELS = {"dark": "Dark", "light": "Light", "system": "System"}

    def _refresh_header_lang(self):
        code = self.conf["ui_language"]
        self.header_lang.setText("English" if code == "en" else "Türkçe")

    def _refresh_header_theme(self):
        mode = self.conf["theme_mode"]
        if mode not in self.THEME_ORDER:
            mode = "dark"
        self.header_theme.setText(t(self.THEME_LABELS[mode]))

    def _toggle_lang(self):
        """Flip the language at once by rebuilding this window."""
        code = "en" if self.conf["ui_language"] != "en" else "tr"
        if code == self.conf["ui_language"]:
            return
        self.conf["ui_language"] = code
        self._select_data(self.ui_language, code)
        try:
            self.conf.save()
        except OSError:
            logging.getLogger("wordarc.ui").warning(
                "language changed but could not be persisted")
        i18n.set_language(code)
        self._refresh_header_lang()
        self.language_changed.emit()

    def _cycle_theme(self):
        """Step to the next theme; each click applies immediately."""
        try:
            mode = self.THEME_ORDER[
                (self.THEME_ORDER.index(self.conf["theme_mode"]) + 1)
                % len(self.THEME_ORDER)
            ]
        except ValueError:
            mode = "dark"
        self.conf["theme_mode"] = mode
        self._refresh_header_theme()
        theme.ThemeManager.apply(mode, QGuiApplication.instance())
        try:
            self.conf.save()
        except OSError:
            logging.getLogger("wordarc.ui").warning(
                "theme changed but could not be persisted")

    # ---- pages ---------------------------------------------------------

    def _dictation_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        start, body = self._section_card(
            "Start", "The key that starts and stops dictation.")
        self.shortcut = self._shortcut_box("Ctrl+Space")
        body.addWidget(self._label_row("Shortcut", self.shortcut))
        self.shortcut_status = QLabel("")
        self.shortcut_status.setObjectName("muted")
        self.shortcut_status.setWordWrap(True)
        body.addWidget(self.shortcut_status)
        layout.addWidget(start)

        sound, body = self._section_card(
            "Sound", "Where your voice comes in.")
        self.mic = QComboBox()
        self.refresh_audio_devices = QPushButton(t("Reload"))
        self.refresh_audio_devices.clicked.connect(self._refresh_audio_devices)
        body.addWidget(self._label_row(
            "Microphone", self._row(self.mic, self.refresh_audio_devices)))
        self.language = QComboBox()
        for label, code in LANGUAGES:
            self.language.addItem(t(label), code)
        body.addWidget(self._label_row("Speech language", self.language))
        layout.addWidget(sound)

        output, body = self._section_card(
            "Output", "Where the finished text goes.")
        self.auto_paste = QCheckBox(t("Paste the text into the focused window"))
        body.addWidget(self.auto_paste)
        self.paste_shortcut = QComboBox()
        self.paste_shortcut.addItems(PASTE_SHORTCUTS)
        self.paste_shortcut.setToolTip(
            t("Terminals usually want ctrl+shift+v. Change this if pasting does nothing.")
        )
        body.addWidget(self._label_row("Paste key", self.paste_shortcut))
        self.restore_clipboard = QCheckBox(t("Restore the previous clipboard after pasting"))
        body.addWidget(self.restore_clipboard)
        layout.addWidget(output)

        recording, body = self._section_card(
            "Recording", "How long a recording may run, and what is kept.")
        self.max_seconds = QSpinBox()
        self.max_seconds.setRange(10, 3600)
        self.max_seconds.setSuffix(t(" s"))
        body.addWidget(self._label_row("Longest recording", self.max_seconds))
        self.skip_silent = QCheckBox(t("Skip silent recordings (don't call the API)"))
        body.addWidget(self.skip_silent)
        self.keep_audio = QCheckBox(t("Keep audio files (%LOCALAPPDATA%\\WordArc\\recordings)"))
        body.addWidget(self.keep_audio)

        advanced = QGroupBox(t("Advanced"))
        advanced_form = QFormLayout(advanced)
        self.silence_db = QSpinBox()
        self.silence_db.setRange(-80, -20)
        self.silence_db.setSuffix(" dB")
        self.silence_db.setToolTip(t(
            "Speech also has to rise {margin} dB above the recording's own noise "
            "floor, so this absolute floor rarely needs touching. Lower it if quiet "
            "speech gets dropped; raise it if noise still gets through.",
            margin=10,
        ))
        advanced_form.addRow(t("Silence threshold"), self.silence_db)
        self.filter_hallucinations = QCheckBox(
            t("Discard stock phrases models invent for near-silent audio")
        )
        self.filter_hallucinations.setToolTip(
            t("Whisper answers silence with things like “Thanks for watching”.")
        )
        advanced_form.addRow("", self.filter_hallucinations)
        body.addWidget(advanced)
        layout.addWidget(recording)

        cleanup, body = self._section_card(
            "Cleanup", "An optional second pass that tidies the transcript.")
        self.cleanup_enabled = QCheckBox(t("Clean the transcript with a model"))
        body.addWidget(self.cleanup_enabled)
        body.addWidget(self._shared_ai_note())
        layout.addWidget(cleanup)
        layout.addWidget(self._history_box())
        layout.addStretch(1)
        return page

    def _general_tab(self, page=None, embedded=False):
        page = page if page is not None else QWidget()
        layout = QVBoxLayout(page)
        interface, body = self._section_card(
            "Interface", "Language and appearance.")
        self.ui_language = QComboBox()
        for label, code in UI_LANGUAGES:
            self.ui_language.addItem(t(label), code)
        self.ui_language.setToolTip(
            t("Restart WordArc for the language change to reach every window.")
        )
        body.addWidget(self._label_row("Interface language", self.ui_language))

        self.corner = QComboBox()
        for value in CORNERS:
            self.corner.addItem(t(value), value)
        body.addWidget(self._label_row("Indicator corner", self.corner))
        layout.addWidget(interface)

        startup_box, body = self._section_card(
            "Startup", "What happens when Windows and WordArc start.")
        self.start_with_windows = QCheckBox(
            t("Start WordArc when Windows starts")
        )
        self.start_with_windows.setToolTip(t(
            "Starts WordArc for this Windows user without administrator permission."
        ))
        body.addWidget(self.start_with_windows)
        self.close_to_tray = QCheckBox(t(
            "Keep running in the system tray when the window is closed"
        ))
        self.close_to_tray.setToolTip(t(
            "When disabled, the title-bar close button, Escape and Alt+F4 quit WordArc."
        ))
        body.addWidget(self.close_to_tray)
        layout.addWidget(startup_box)

        support, body = self._section_card(
            "Support", "When something breaks.")
        diagnostics = QPushButton(t("Open diagnostics folder"))
        diagnostics.clicked.connect(self._open_diagnostics)
        diag_row = QHBoxLayout()
        diag_row.addWidget(diagnostics)
        diag_row.addStretch(1)
        body.addLayout(diag_row)
        layout.addWidget(support)
        if not embedded:
            layout.addStretch(1)
        return page

    def _shared_ai_tab(self, page=None, embedded=False):
        page = page if page is not None else QWidget()
        outer = QVBoxLayout(page)

        # API keys first, then model selection.
        keys, keys_body = self._section_card(
            "Keys", "Your Gemini API keys, tried from top to bottom.")
        key_help = QLabel(t(
            "Keys are tried from top to bottom and stored only in Windows Credential Manager."
        ))
        key_help.setWordWrap(True)
        key_help.setObjectName("muted")
        keys_body.addWidget(key_help)
        self.gemini_keys_list = QListWidget()
        self.gemini_keys_list.setMinimumHeight(116)
        self.gemini_keys_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        keys_body.addWidget(self.gemini_keys_list)
        self.gemini_add_button = QPushButton(t("Add API"))
        self.gemini_edit_button = QPushButton(t("Edit"))
        self.gemini_remove_button = QPushButton(t("Remove"))
        self.gemini_up_button = QPushButton(t("Move up"))
        self.gemini_down_button = QPushButton(t("Move down"))
        self.gemini_test_button = QPushButton(t("Test"))
        self.gemini_add_button.clicked.connect(self._add_gemini_key)
        self.gemini_edit_button.clicked.connect(self._edit_gemini_key)
        self.gemini_remove_button.clicked.connect(self._remove_gemini_key)
        self.gemini_up_button.clicked.connect(lambda: self._move_gemini_key(-1))
        self.gemini_down_button.clicked.connect(lambda: self._move_gemini_key(1))
        self.gemini_test_button.clicked.connect(self._test_gemini)
        self.gemini_keys_list.currentRowChanged.connect(
            self._refresh_gemini_key_buttons
        )
        key_buttons = QHBoxLayout()
        for button in (
            self.gemini_add_button, self.gemini_edit_button,
            self.gemini_remove_button, self.gemini_up_button,
            self.gemini_down_button, self.gemini_test_button,
        ):
            key_buttons.addWidget(button)
        key_buttons.addStretch(1)
        keys_body.addLayout(key_buttons)
        self.gemini_test_label = QLabel("")
        self.gemini_test_label.setWordWrap(True)
        keys_body.addWidget(self.gemini_test_label)
        outer.addWidget(keys)

        stt, stt_body = self._section_card(
            "Speech to text", "The model that turns speech into text.")

        self.transcribe_model = QComboBox()
        self.transcribe_model.setEditable(True)
        self.transcribe_model.addItems(TRANSCRIBE_MODELS)
        self.refresh_transcribe_models = QPushButton(t("Fetch model list"))
        self.refresh_transcribe_models.clicked.connect(self._load_transcribe_models)
        stt_body.addWidget(self._label_row(
            "Model", self._row(self.transcribe_model, self.refresh_transcribe_models)))
        self.transcribe_status = QLabel("")
        self.transcribe_status.setObjectName("muted")
        self.transcribe_status.setWordWrap(True)
        stt_body.addWidget(self.transcribe_status)
        outer.addWidget(stt)

        orr, orr_body = self._section_card(
            "Transcript cleanup", "The model that tidies transcripts.")
        self.cleanup_model = QComboBox()
        self.cleanup_model.setEditable(True)
        self.cleanup_model.addItems(CLEANUP_MODELS)
        self.refresh_models = QPushButton(t("Fetch model list"))
        self.refresh_models.clicked.connect(self._load_models)
        orr_body.addWidget(self._label_row(
            "Model", self._row(self.cleanup_model, self.refresh_models)))

        self.cleanup_reasoning = QComboBox()
        for label, value in REASONING_LEVELS:
            self.cleanup_reasoning.addItem(t(label), value)
        self.cleanup_reasoning.setToolTip(
            t("How long a thinking model may reason before it answers. Cleanup is "
              "a light job, so more thinking mostly costs time and tokens. Models "
              "that cannot think ignore this.")
        )
        orr_body.addWidget(self._label_row("Thinking", self.cleanup_reasoning))

        self.models_label = QLabel("")
        self.models_label.setObjectName("muted")
        self.models_label.setWordWrap(True)
        orr_body.addWidget(self.models_label)

        cleanup_intro = QLabel(t(
            "System instruction shared by dictation and optional meeting cleanup."
        ))
        cleanup_intro.setObjectName("muted")
        cleanup_intro.setWordWrap(True)
        orr_body.addWidget(cleanup_intro)
        self.cleanup_prompt = QPlainTextEdit()
        self.cleanup_prompt.setMinimumHeight(180)
        orr_body.addWidget(self.cleanup_prompt)
        reset_cleanup = QPushButton(t("Reset to default"))
        reset_cleanup.clicked.connect(
            lambda: self.cleanup_prompt.setPlainText(cfg.default_cleanup_prompt())
        )
        reset_row = QHBoxLayout()
        reset_row.addStretch(1)
        reset_row.addWidget(reset_cleanup)
        orr_body.addLayout(reset_row)
        outer.addWidget(orr)

        glossary, glossary_body = self._section_card(
            "Names and terms", "Words the models should spell right.")
        glossary_hint = QLabel(t(
            "Names and terms you say often (optional). They go to the transcription "
            "model as a hint, and to the cleanup model as a glossary, so it can repair "
            "the ones that still come out wrong."
        ))
        glossary_hint.setObjectName("muted")
        glossary_hint.setWordWrap(True)
        glossary_body.addWidget(glossary_hint)
        self.transcribe_prompt = QPlainTextEdit()
        self.transcribe_prompt.setMaximumHeight(100)
        glossary_body.addWidget(self.transcribe_prompt)
        outer.addWidget(glossary)
        if not embedded:
            outer.addStretch(1)
        return page

    def _meeting_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        sound, body = self._section_card(
            "Sound", "Your microphone plus whatever comes out of your speakers.")
        self.meeting_mic = QComboBox()
        body.addWidget(self._label_row("Microphone", self.meeting_mic))

        self.meeting_system = QComboBox()
        self.meeting_system.addItem(t("Current output"), "")
        for name, desc in audio.list_monitors():
            self.meeting_system.addItem(desc, name)
        body.addWidget(self._label_row("The other participants", self.meeting_system))

        self._refresh_audio_devices()

        note = QLabel(t(
            "Wear headphones if you can. Through speakers your microphone hears "
            "the other side as well, and although a line that lands on both "
            "channels at once is dropped again, the repair is never as clean as "
            "not needing it."
        ))
        note.setObjectName("muted")
        note.setWordWrap(True)
        body.addWidget(note)
        layout.addWidget(sound)

        people, body = self._section_card(
            "Who is talking", "Labels for the two sides of the conversation.")
        self.meeting_self_name = QLineEdit()
        self.meeting_self_name.setPlaceholderText(t("Me"))
        body.addWidget(self._label_row("You", self.meeting_self_name))
        self.meeting_other_name = QLineEdit()
        self.meeting_other_name.setPlaceholderText(t("Other side"))
        body.addWidget(self._label_row("The other end", self.meeting_other_name))
        self.meeting_participants = QPlainTextEdit()
        self.meeting_participants.setMaximumHeight(70)
        self.meeting_participants.setPlaceholderText(t("One name per line"))
        body.addWidget(self._label_row("Expected", self.meeting_participants))
        people_note = QLabel(t(
            "Everyone on the far end shares one label: they reach you as a single "
            "mixed signal. The names go to the transcription model so they come "
            "out spelled right, and to the minutes, which may use one for a line "
            "only when the conversation itself makes clear who was speaking."
        ))
        people_note.setObjectName("muted")
        people_note.setWordWrap(True)
        body.addWidget(people_note)
        layout.addWidget(people)

        models, body = self._section_card(
            "Minutes", "The model that turns the transcript into minutes.")
        self.meeting_model = QComboBox()
        self.meeting_model.setEditable(True)
        self.meeting_model.addItems(MEETING_MODELS)
        body.addWidget(self._label_row("Model", self.meeting_model))
        self.meeting_reasoning = QComboBox()
        for label, value in REASONING_LEVELS:
            self.meeting_reasoning.addItem(t(label), value)
        self.meeting_reasoning.setToolTip(t(
            "Unlike cleanup, this one is worth some thinking: it has to hold a "
            "whole meeting in its head and work out what was actually decided."
        ))
        body.addWidget(self._label_row("Thinking", self.meeting_reasoning))
        self.meeting_language = QComboBox()
        self.meeting_language.addItem(t("Same as dictation"), "")
        for label, code in LANGUAGES:
            self.meeting_language.addItem(t(label), code)
        body.addWidget(self._label_row("Speech language", self.meeting_language))
        self.meeting_cleanup = QCheckBox(t("Clean the transcript up first"))
        self.meeting_cleanup.setToolTip(t(
            "Runs the cleanup model over the transcript before the minutes are "
            "written, keeping the timestamps and the speaker labels."
        ))
        body.addWidget(self.meeting_cleanup)
        layout.addWidget(models)

        recording, body = self._section_card(
            "Recording", "How long a meeting may run, and what is kept.")
        self.meeting_max_minutes = QSpinBox()
        self.meeting_max_minutes.setRange(5, 600)
        self.meeting_max_minutes.setSuffix(t(" min"))
        body.addWidget(self._label_row("Longest meeting", self.meeting_max_minutes))
        self.meeting_keep_audio = QCheckBox(
            t("Keep the recording after the minutes are written")
        )
        self.meeting_keep_audio.setToolTip(t(
            "A run that fails keeps its recording either way, so it can be tried "
            "again from the Meeting tab. This is about the ones that worked."
        ))
        body.addWidget(self.meeting_keep_audio)
        privacy = QLabel(t(
            "Meeting minutes and transcripts are stored as readable text files "
            "under %LOCALAPPDATA%\\WordArc\\meetings."))
        privacy.setObjectName("muted")
        privacy.setWordWrap(True)
        body.addWidget(privacy)
        self.meeting_shortcut = self._shortcut_box(t("none"))
        body.addWidget(self._label_row("Shortcut", self.meeting_shortcut))
        self.meeting_shortcut_status = QLabel("")
        self.meeting_shortcut_status.setObjectName("muted")
        self.meeting_shortcut_status.setWordWrap(True)
        body.addWidget(self.meeting_shortcut_status)
        layout.addWidget(recording)

        prompt_card, prompt_body = self._section_card(
            "Minutes instruction", "System instruction given to the minutes model.")
        self.meeting_prompt = QPlainTextEdit()
        self.meeting_prompt.setMinimumHeight(200)
        prompt_body.addWidget(self.meeting_prompt)
        reset = QPushButton(t("Reset to default"))
        reset.clicked.connect(
            lambda: self.meeting_prompt.setPlainText(cfg.default_meeting_prompt())
        )
        reset_row = QHBoxLayout()
        reset_row.addStretch(1)
        reset_row.addWidget(reset)
        prompt_body.addLayout(reset_row)
        layout.addWidget(prompt_card)
        layout.addWidget(self._minutes_box())

        # Everything above is more than one screenful; let it scroll rather than
        # squeezing the prompt box down to nothing.
        return page

    def _settings_tab(self):
        """Shared AI and application sections built straight into one tab.

        (An earlier version built two throwaway pages and moved their rows
        over; that dance crashed Qt on tab switches, so it is gone.)
        """
        page = QWidget()
        self._shared_ai_tab(page, embedded=True)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        page.layout().addWidget(line)
        self._general_tab(page, embedded=True)
        page.layout().addStretch(1)
        return page

    def _minutes_box(self):
        box = QGroupBox(t("Minutes"))
        layout = QVBoxLayout(box)

        self.minutes_list = QListWidget()
        self.minutes_list.setWordWrap(True)
        self.minutes_list.setMaximumHeight(170)
        self.minutes_list.currentItemChanged.connect(self._show_minutes)
        layout.addWidget(self.minutes_list)

        self.minutes_status = QLabel("")
        self.minutes_status.setWordWrap(True)
        layout.addWidget(self.minutes_status)

        self.minutes_view = QPlainTextEdit()
        self.minutes_view.setReadOnly(True)
        self.minutes_view.setMinimumHeight(200)
        self.minutes_view.setPlaceholderText(t("Pick a meeting to read it."))
        layout.addWidget(self.minutes_view)

        copy = QPushButton(t("Copy"))
        copy.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(self.minutes_view.toPlainText())
        )
        self.minutes_retry = QPushButton(t("Write it up"))
        self.minutes_retry.clicked.connect(self._retry_minutes)
        self.minutes_retry.setEnabled(False)
        folder = QPushButton(t("Open the folder"))
        folder.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(cfg.MEETINGS_DIR))
            )
        )
        delete = QPushButton(t("Delete selected"))
        delete.clicked.connect(self._delete_minutes)
        reload_ = QPushButton(t("Reload"))
        reload_.clicked.connect(self._load_minutes)
        row = QHBoxLayout()
        row.addWidget(copy)
        row.addWidget(self.minutes_retry)
        row.addStretch(1)
        row.addWidget(folder)
        row.addWidget(delete)
        row.addWidget(reload_)
        layout.addLayout(row)
        return box

    def _file_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        intro = QLabel(t("Transcribe an existing audio or video file with the same models."))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addWidget(self._shared_ai_note())

        file_card, body = self._section_card(
            "File", "Pick an audio or video file to transcribe.")
        pick = QPushButton(t("Choose file…"))
        pick.clicked.connect(self._choose_file)
        self.file_label = QLabel(t("No file selected"))
        self.file_label.setWordWrap(True)
        row = QHBoxLayout()
        row.addWidget(pick)
        row.addWidget(self.file_label, 1)
        body.addLayout(row)
        layout.addWidget(file_card)

        options, body = self._section_card(
            "Options", "How the transcript should look.")
        self.file_timestamps = QCheckBox(t("Add timestamps"))
        self.file_timestamps.setToolTip(
            t("Prefixes every chunk with [mm:ss], so the transcript can be "
              "saved as subtitles (.srt).")
        )
        body.addWidget(self.file_timestamps)

        self.file_cleanup = QCheckBox(t("Run the cleanup model afterwards"))
        self.file_cleanup.setToolTip(
            t("With its own rules, under Cleanup rules: written for subtitles, so "
              "the lines keep their place and nothing is shortened.")
        )
        body.addWidget(self.file_cleanup)

        self.file_cleanup_prompt = QPlainTextEdit()
        self.file_cleanup_prompt.setMaximumHeight(110)
        body.addWidget(self._label_row(
            "Audio file cleanup instruction", self.file_cleanup_prompt))
        reset_file_prompt = QPushButton(t("Reset to default"))
        reset_file_prompt.clicked.connect(
            lambda: self.file_cleanup_prompt.setPlainText(cfg.default_file_cleanup_prompt())
        )
        reset_row = QHBoxLayout()
        reset_row.addStretch(1)
        reset_row.addWidget(reset_file_prompt)
        body.addLayout(reset_row)
        layout.addWidget(options)

        transcript, body = self._section_card(
            "Transcript", "The finished text.")
        self.file_run = QPushButton(t("Transcribe"))
        self.file_run.clicked.connect(self._run_file)
        self.file_stop = QPushButton(t("Stop"))
        self.file_stop.clicked.connect(self.transcriber.stop)
        self.file_stop.setEnabled(False)
        run_row = QHBoxLayout()
        run_row.addWidget(self.file_run)
        run_row.addWidget(self.file_stop)
        run_row.addStretch(1)
        body.addLayout(run_row)

        self.file_status = QLabel("")
        self.file_status.setWordWrap(True)
        body.addWidget(self.file_status)

        self.file_output = QPlainTextEdit()
        self.file_output.setPlaceholderText("…")
        self.file_output.setMinimumHeight(200)
        body.addWidget(self.file_output)

        copy = QPushButton(t("Copy"))
        copy.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(self.file_output.toPlainText())
        )
        save = QPushButton(t("Save as .txt"))
        save.clicked.connect(self._save_transcript)
        self.file_save_srt = QPushButton(t("Save as .srt"))
        self.file_save_srt.setToolTip(
            t("Subtitles, timed from the segments. Needs the timestamps option.")
        )
        self.file_save_srt.setEnabled(False)
        self.file_save_srt.clicked.connect(self._save_subtitles)
        out_row = QHBoxLayout()
        out_row.addWidget(copy)
        out_row.addWidget(save)
        out_row.addWidget(self.file_save_srt)
        out_row.addStretch(1)
        body.addLayout(out_row)
        layout.addWidget(transcript)
        return page

    def _history_box(self):
        box = QGroupBox(t("History"))
        layout = QVBoxLayout(box)
        self.history_enabled = QCheckBox(
            t("Store dictation history on this computer")
        )
        layout.addWidget(self.history_enabled)
        self.history = QListWidget()
        self.history.setWordWrap(True)
        self.history.setMinimumHeight(220)
        self.history.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.history.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history.customContextMenuRequested.connect(self._history_menu)
        delete_key = QShortcut(QKeySequence.StandardKey.Delete, self.history)
        delete_key.setContext(Qt.ShortcutContext.WidgetShortcut)
        delete_key.activated.connect(self._delete_history)
        layout.addWidget(self.history)

        self.history_limit = QSpinBox()
        self.history_limit.setRange(0, 10000)
        self.history_limit.setSpecialValueText(t("no limit"))
        self.history_limit.setSuffix(t(" entries"))
        self.history_limit.setToolTip(t(
            "Once the history passes this many entries, the oldest one is dropped "
            "every time a new one arrives. Set it to 0 to keep everything."
        ))
        self.history_enabled.toggled.connect(self.history_limit.setEnabled)
        limit_row = QHBoxLayout()
        limit_row.addWidget(QLabel(t("Keep at most")))
        limit_row.addWidget(self.history_limit)
        limit_row.addStretch(1)
        layout.addLayout(limit_row)

        copy = QPushButton(t("Copy selected to clipboard"))
        copy.clicked.connect(self._copy_history)
        delete = QPushButton(t("Delete selected"))
        delete.clicked.connect(self._delete_history)
        clear = QPushButton(t("Clear history"))
        clear.clicked.connect(self._clear_history)
        reload_ = QPushButton(t("Reload"))
        reload_.clicked.connect(self._load_history)
        row = QHBoxLayout()
        row.addWidget(copy)
        row.addWidget(delete)
        row.addWidget(clear)
        row.addWidget(reload_)
        row.addStretch(1)
        layout.addLayout(row)
        return box

    @staticmethod
    def _shortcut_box(placeholder=""):
        """The field a global shortcut is typed or picked in."""
        box = QComboBox()
        box.setEditable(True)
        box.addItems(SHORTCUTS)
        box.setCurrentText("")
        if placeholder:
            box.lineEdit().setPlaceholderText(placeholder)
        return box

    @staticmethod
    def _row(*widgets):
        """Widgets side by side in one form row; the first one takes the space."""
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        for index, widget in enumerate(widgets):
            layout.addWidget(widget, 1 if index == 0 else 0)
        holder = QWidget()
        holder.setLayout(layout)
        return holder

    @staticmethod
    def _label_row(label, widget):
        """A labelled row: muted label on top, control below it."""
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        caption = QLabel(t(label))
        caption.setObjectName("muted")
        layout.addWidget(caption)
        layout.addWidget(widget)
        return holder

    @staticmethod
    def _section_card(title, description):
        """A roomy card: bold title, one muted description line, content."""
        box = QGroupBox(t(title))
        outer = QVBoxLayout(box)
        detail = QLabel(t(description))
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        outer.addWidget(detail)
        inner = QVBoxLayout()
        inner.setSpacing(10)
        outer.addLayout(inner)
        return box, inner

    # ---- load / save ----------------------------------------------------

    def _load(self):
        conf = self.conf
        self._refresh_header_theme()
        self._refresh_header_lang()
        try:
            starts_with_windows = startup.is_enabled()
        except startup.StartupError:
            starts_with_windows = bool(conf["start_with_windows"])
        self.start_with_windows.setChecked(starts_with_windows)
        self.close_to_tray.setChecked(bool(conf["close_to_tray"]))
        self._select_data(self.ui_language, conf["ui_language"])
        self._refresh_header_lang()
        self._select_data(self.mic, conf["mic_target"])
        self._select_data(self.language, conf["language"])
        self.auto_paste.setChecked(conf["auto_paste"])
        self.paste_shortcut.setCurrentText(conf["paste_shortcut"])
        self.restore_clipboard.setChecked(conf["restore_clipboard"])
        self._select_data(self.corner, conf["overlay_corner"])
        self.max_seconds.setValue(conf["max_seconds"])
        self.skip_silent.setChecked(conf["skip_silent"])
        self.silence_db.setValue(int(conf["silence_db"]))
        self.filter_hallucinations.setChecked(conf["filter_hallucinations"])
        self.keep_audio.setChecked(conf["keep_audio"])

        self._gemini_keys = conf.stored_gemini_keys()
        self._refresh_gemini_keys()
        self.transcribe_model.setCurrentText(conf["gemini_transcribe_model"])
        self.cleanup_enabled.setChecked(conf["cleanup_enabled"])
        self.cleanup_model.setCurrentText(conf["cleanup_model"])
        self._select_data(self.cleanup_reasoning, conf["cleanup_reasoning"])
        self.cleanup_prompt.setPlainText(conf["cleanup_prompt"] or cfg.default_cleanup_prompt())
        self.file_cleanup_prompt.setPlainText(
            conf["file_cleanup_prompt"] or cfg.default_file_cleanup_prompt()
        )
        self.transcribe_prompt.setPlainText(conf["transcribe_prompt"])

        self._select_data(self.meeting_mic, conf["meeting_mic_target"])
        self._select_data(self.meeting_system, conf["meeting_system_target"])
        self.meeting_self_name.setText(conf["meeting_self_name"])
        self.meeting_other_name.setText(conf["meeting_other_name"])
        self.meeting_participants.setPlainText(conf["meeting_participants"])
        self.meeting_model.setCurrentText(conf["meeting_model"])
        self._select_data(self.meeting_reasoning, conf["meeting_reasoning"])
        self._select_data(self.meeting_language, conf["meeting_language"])
        self.meeting_cleanup.setChecked(conf["meeting_cleanup"])
        self.meeting_max_minutes.setValue(max(5, int(conf["meeting_max_seconds"]) // 60))
        self.meeting_keep_audio.setChecked(conf["meeting_keep_audio"])
        self.meeting_shortcut.setCurrentText(conf["meeting_shortcut"])
        self.meeting_prompt.setPlainText(
            conf["meeting_prompt"] or cfg.default_meeting_prompt()
        )

        self.file_timestamps.setChecked(conf["file_timestamps"])
        self.file_cleanup.setChecked(conf["file_cleanup"])
        self.file_path = ""

        self.shortcut.setCurrentText(conf["shortcut"])

        self.history_enabled.setChecked(bool(conf["history_enabled"]))
        self.history_limit.setEnabled(self.history_enabled.isChecked())
        self.history_limit.setValue(max(0, int(conf["history_limit"])))

        self._refresh_shortcut_status()
        self._refresh_meeting_shortcut_status()
        self._load_history()
        self._load_minutes()

    def _save(self):
        conf = self.conf
        # Theme and header language apply on click and persist at once;
        # Save keeps them, it does not read them back from the buttons.
        conf["start_with_windows"] = self.start_with_windows.isChecked()
        conf["close_to_tray"] = self.close_to_tray.isChecked()
        conf["ui_language"] = self.ui_language.currentData() or "auto"
        conf["mic_target"] = self.mic.currentData() or ""
        conf["language"] = self.language.currentData() or "auto"
        conf["auto_paste"] = self.auto_paste.isChecked()
        conf["paste_shortcut"] = self.paste_shortcut.currentText().strip()
        conf["restore_clipboard"] = self.restore_clipboard.isChecked()
        conf["overlay_corner"] = self.corner.currentData() or "bottom-left"
        conf["max_seconds"] = self.max_seconds.value()
        conf["skip_silent"] = self.skip_silent.isChecked()
        conf["silence_db"] = float(self.silence_db.value())
        conf["filter_hallucinations"] = self.filter_hallucinations.isChecked()
        conf["keep_audio"] = self.keep_audio.isChecked()

        conf["gemini_api_key"] = ""
        conf["gemini_transcribe_model"] = (self.transcribe_model.currentText().strip()
                                           or cfg.DEFAULTS["gemini_transcribe_model"])

        conf["cleanup_enabled"] = self.cleanup_enabled.isChecked()
        conf["cleanup_model"] = self.cleanup_model.currentText().strip()
        conf["cleanup_reasoning"] = self.cleanup_reasoning.currentData() or ""

        # Store an empty prompt when it matches the default, so switching the
        # interface language also switches the prompt language.
        prompt = self.cleanup_prompt.toPlainText().strip()
        conf["cleanup_prompt"] = "" if prompt == cfg.default_cleanup_prompt() else prompt
        file_prompt = self.file_cleanup_prompt.toPlainText().strip()
        conf["file_cleanup_prompt"] = ("" if file_prompt == cfg.default_file_cleanup_prompt()
                                       else file_prompt)
        conf["transcribe_prompt"] = self.transcribe_prompt.toPlainText().strip()

        conf["meeting_mic_target"] = self.meeting_mic.currentData() or ""
        conf["meeting_system_target"] = self.meeting_system.currentData() or ""
        conf["meeting_self_name"] = self.meeting_self_name.text().strip()
        conf["meeting_other_name"] = self.meeting_other_name.text().strip()
        conf["meeting_participants"] = self.meeting_participants.toPlainText().strip()
        conf["meeting_model"] = (self.meeting_model.currentText().strip()
                                 or cfg.DEFAULTS["meeting_model"])
        conf["meeting_reasoning"] = self.meeting_reasoning.currentData() or ""
        conf["meeting_language"] = self.meeting_language.currentData() or ""
        conf["meeting_cleanup"] = self.meeting_cleanup.isChecked()
        conf["meeting_max_seconds"] = self.meeting_max_minutes.value() * 60
        conf["meeting_keep_audio"] = self.meeting_keep_audio.isChecked()
        conf["meeting_shortcut"] = self.meeting_shortcut.currentText().strip()
        meeting_prompt = self.meeting_prompt.toPlainText().strip()
        conf["meeting_prompt"] = ("" if meeting_prompt == cfg.default_meeting_prompt()
                                  else meeting_prompt)

        conf["file_timestamps"] = self.file_timestamps.isChecked()
        conf["file_cleanup"] = self.file_cleanup.isChecked()

        conf["shortcut"] = self.shortcut.currentText().strip() or "Ctrl+Space"
        conf["history_enabled"] = self.history_enabled.isChecked()
        conf["history_limit"] = self.history_limit.value()
        try:
            startup.set_enabled(conf["start_with_windows"])
        except startup.StartupError as exc:
            QMessageBox.warning(self, t("Error"), str(exc))
            return
        previous_keys = conf.stored_gemini_keys()
        try:
            cfg.credential_store.write_all(self._gemini_keys)
        except cfg.credential_store.CredentialError as exc:
            QMessageBox.warning(self, t("Error"), str(exc))
            return
        try:
            conf.save()
        except OSError as exc:
            try:
                cfg.credential_store.write_all(previous_keys)
            except cfg.credential_store.CredentialError:
                pass
            QMessageBox.warning(self, t("Error"), str(exc))
            return
        # A lowered limit should bite now, not on the next dictation.
        try:
            cfg.trim_history(conf["history_limit"])
        except OSError as exc:
            print(f"wordarc: could not trim the history ({exc})")
        self._load_history()  # the trim may just have dropped rows from the list
        self.applied.emit()
        QMessageBox.information(self, t("WordArc Settings"), t("Saved successfully."))

    @staticmethod
    def _select_data(combo, value):
        index = combo.findData(value)
        # Migrate the old plain-name setting to the new host-aware target.
        if index < 0 and value and not str(value).startswith(audio.DEVICE_TARGET_PREFIX):
            suffix = f":{value}".casefold()
            for candidate in range(combo.count()):
                data = str(combo.itemData(candidate) or "")
                if data.casefold().endswith(suffix):
                    index = candidate
                    break
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _refresh_audio_devices(self, *_):
        """Rescan hot-plugged inputs while preserving both current selections."""
        sources = audio.list_sources()
        for combo, default_label in (
                (getattr(self, "mic", None), t("Default microphone")),
                (getattr(self, "meeting_mic", None), t("Same as dictation"))):
            if combo is None:
                continue
            selected = combo.currentData() if combo.count() else ""
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(default_label, "")
            for target, label in sources:
                combo.addItem(label, target)
            self._select_data(combo, selected)
            combo.blockSignals(False)

    # ---- api helpers -----------------------------------------------------

    @staticmethod
    def _masked_key(key):
        suffix = key[-4:] if len(key) >= 4 else "••••"
        return f"••••••••{suffix}"

    def _refresh_gemini_keys(self, selected=None):
        if selected is None:
            selected = self.gemini_keys_list.currentRow()
        self.gemini_keys_list.clear()
        for index, key in enumerate(self._gemini_keys, start=1):
            label = t("Default API") if index == 1 else t("Backup API {number}", number=index)
            self.gemini_keys_list.addItem(f"{label} — {self._masked_key(key)}")
        if self._gemini_keys:
            self.gemini_keys_list.setCurrentRow(
                min(max(selected, 0), len(self._gemini_keys) - 1)
            )
        self._refresh_gemini_key_buttons()

    def _refresh_gemini_key_buttons(self, *_):
        row = self.gemini_keys_list.currentRow()
        selected = 0 <= row < len(self._gemini_keys)
        self.gemini_add_button.setEnabled(
            len(self._gemini_keys) < cfg.credential_store.MAX_GEMINI_KEYS
            if hasattr(cfg.credential_store, "MAX_GEMINI_KEYS") else
            len(self._gemini_keys) < 5
        )
        self.gemini_edit_button.setEnabled(selected)
        self.gemini_remove_button.setEnabled(selected)
        self.gemini_up_button.setEnabled(selected and row > 0)
        self.gemini_down_button.setEnabled(
            selected and row + 1 < len(self._gemini_keys)
        )
        self.gemini_test_button.setEnabled(selected or bool(self.conf.gemini_keys()))

    def _prompt_gemini_key(self, title, value=""):
        key, ok = QInputDialog.getText(
            self, t(title), t("Gemini API key"),
            QLineEdit.EchoMode.Password, value,
        )
        return key.strip() if ok else ""

    def _add_gemini_key(self):
        if len(self._gemini_keys) >= 5:
            return
        key = self._prompt_gemini_key("Add API")
        if not key:
            return
        if key in self._gemini_keys:
            QMessageBox.warning(self, t("Error"), t("This API key is already listed."))
            return
        self._gemini_keys.append(key)
        self._refresh_gemini_keys(len(self._gemini_keys) - 1)

    def _edit_gemini_key(self):
        row = self.gemini_keys_list.currentRow()
        if not 0 <= row < len(self._gemini_keys):
            return
        key = self._prompt_gemini_key("Edit API", self._gemini_keys[row])
        if not key:
            return
        if key in self._gemini_keys and key != self._gemini_keys[row]:
            QMessageBox.warning(self, t("Error"), t("This API key is already listed."))
            return
        self._gemini_keys[row] = key
        self._refresh_gemini_keys(row)

    def _remove_gemini_key(self):
        row = self.gemini_keys_list.currentRow()
        if 0 <= row < len(self._gemini_keys):
            self._gemini_keys.pop(row)
            self._refresh_gemini_keys(min(row, len(self._gemini_keys) - 1))

    def _move_gemini_key(self, offset):
        row = self.gemini_keys_list.currentRow()
        target = row + offset
        if not (0 <= row < len(self._gemini_keys)
                and 0 <= target < len(self._gemini_keys)):
            return
        self._gemini_keys[row], self._gemini_keys[target] = (
            self._gemini_keys[target], self._gemini_keys[row]
        )
        self._refresh_gemini_keys(target)

    def _gemini_runtime_keys(self):
        return list(self._gemini_keys) or self.conf.gemini_keys()

    def _load_transcribe_models(self):
        self.refresh_transcribe_models.setEnabled(False)
        self.transcribe_status.setText(t("Fetching model list…"))
        keys = self._gemini_runtime_keys()

        def work():
            try:
                models = api.GeminiClient(keys).list_models()
                self._transcribe_models_loaded.emit(models, "")
            except api.ApiError as exc:
                self._transcribe_models_loaded.emit([], str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _on_transcribe_models_loaded(self, models, error):
        self.refresh_transcribe_models.setEnabled(True)
        if error:
            self.transcribe_status.setText(t("Could not fetch the list: {error}", error=error))
            return
        current = self.transcribe_model.currentText()
        self.transcribe_model.clear()
        self.transcribe_model.addItems(models)
        self.transcribe_model.setCurrentText(current)
        self.transcribe_status.setText(t("{count} models loaded.", count=len(models)))

    def _load_models(self):
        self.refresh_models.setEnabled(False)
        self.models_label.setText(t("Fetching model list…"))
        keys = self._gemini_runtime_keys()

        def work():
            try:
                self._models_loaded.emit(api.GeminiClient(keys).list_models(), "")
            except api.ApiError as exc:
                self._models_loaded.emit([], str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _on_models_loaded(self, models, error):
        self.refresh_models.setEnabled(True)
        if error:
            self.models_label.setText(t("Could not fetch the list: {error}", error=error))
            return
        for combo in (self.cleanup_model, self.meeting_model):
            current = combo.currentText()
            combo.clear()
            combo.addItems(models)
            combo.setCurrentText(current)
        self.models_label.setText(t("{count} models loaded.", count=len(models)))

    def _test_gemini(self):
        self.gemini_test_button.setEnabled(False)
        self.gemini_test_label.setText(t("Trying…"))
        row = self.gemini_keys_list.currentRow()
        if 0 <= row < len(self._gemini_keys):
            key = self._gemini_keys[row]
        else:
            runtime = self.conf.gemini_keys()
            key = runtime[0] if runtime else ""

        def work():
            try:
                models = api.gemini_models(key)
                self._test_done.emit(
                    True, t("Connection works. {count} models visible.", count=len(models))
                )
            except api.ApiError as exc:
                self._test_done.emit(False, str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _on_test_done(self, ok, message):
        self._refresh_gemini_key_buttons()
        self.gemini_test_label.setText(("✓ " if ok else "✗ ") + message)

    # ---- audio file ------------------------------------------------------

    def _choose_file(self):
        start = self.conf["file_last_dir"] or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self, t("Select an audio file"), start,
            f"{t('Audio and video files')} ({AUDIO_FILTER});;{t('All files')} (*)",
        )
        if not path:
            return
        self.file_path = path
        self.file_label.setText(os.path.basename(path))
        self.conf["file_last_dir"] = os.path.dirname(path)

    def _run_file(self):
        if not getattr(self, "file_path", "") or self.transcriber.busy:
            return
        if not os.path.isfile(self.file_path):
            self.file_status.setText(
                t("Failed: {error}", error=t("The selected file no longer exists.")))
            return
        self.file_output.clear()
        self.file_segments = []
        self.file_save_srt.setEnabled(False)
        self.file_run.setEnabled(False)
        self.file_stop.setEnabled(True)
        self.transcriber.start(
            self.file_path,
            self.file_timestamps.isChecked(),
            self.file_cleanup.isChecked(),
        )

    def _on_file_progress(self, message):
        self.file_status.setText(message)
        if message == t("Stopped."):
            self._file_idle()

    def _on_file_finished(self, text, segments):
        self.file_output.setPlainText(text)
        self.file_segments = segments
        self.file_save_srt.setEnabled(self._has_timestamped_lines(text))
        self.file_status.setText(t("Done: {chars} characters.", chars=len(text)))
        self._file_idle()

    def _on_file_failed(self, error):
        self.file_status.setText(t("Failed: {error}", error=error))
        self._file_idle()

    def _file_idle(self):
        self.file_run.setEnabled(True)
        self.file_stop.setEnabled(False)

    @staticmethod
    def _has_timestamped_lines(text):
        return any(
            filetranscribe.STAMP_RE.match(line.strip())
            for line in (text or "").splitlines()
        )

    def closeEvent(self, event):
        # Closing mid-transcription used to kill the whole app: the worker
        # thread kept emitting on the deleted transcriber child. Ask it to
        # stop; the daemon thread dies on its own, the window closes now.
        try:
            if getattr(self, "transcriber", None) is not None and self.transcriber.busy:
                self.transcriber.stop()
        except (RuntimeError, AttributeError):
            pass
        super().closeEvent(event)

    def _save_transcript(self):
        self._write_transcript(self.file_output.toPlainText(), ".txt",
                               f"{t('Text files')} (*.txt)")

    def _save_subtitles(self):
        srt = filetranscribe.to_srt(self.file_output.toPlainText(),
                                    getattr(self, "file_segments", []))
        if not srt:
            self.file_status.setText(t("No timestamped lines to turn into subtitles."))
            return
        self._write_transcript(srt, ".srt", f"{t('Subtitle files')} (*.srt)")

    def _write_transcript(self, text, suffix, file_filter):
        if not text:
            return
        base = os.path.splitext(os.path.basename(getattr(self, "file_path", "")))[0]
        start = os.path.join(self.conf["file_last_dir"] or os.path.expanduser("~"),
                             f"{base or 'transcript'}{suffix}")
        path, _ = QFileDialog.getSaveFileName(
            self, t("Save transcript"), start, file_filter
        )
        if not path:
            return
        if not path.lower().endswith(suffix):
            path += suffix
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            self.file_status.setText(t("Saved: {path}", path=path))
        except OSError as exc:
            self.file_status.setText(t("Failed: {error}", error=exc))

    # ---- shortcut --------------------------------------------------------

    def _refresh_shortcut_status(self):
        self.shortcut_status.setText(
            t("Active shortcut: {shortcut}", shortcut=self.conf["shortcut"])
            if self.conf["shortcut"] else t("No shortcut set.")
        )

    def _refresh_meeting_shortcut_status(self):
        self.meeting_shortcut_status.setText(
            t("Active shortcut: {shortcut}", shortcut=self.conf["meeting_shortcut"])
            if self.conf["meeting_shortcut"] else
            t("No shortcut set. The tray menu starts a meeting too.")
        )

    def _open_diagnostics(self):
        cfg.LOG_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(cfg.LOG_DIR)))

    # ---- minutes ---------------------------------------------------------

    def _load_minutes(self):
        self.minutes_list.clear()
        for row in reversed(cfg.read_meetings()):
            title = row.get("title") or t("Meeting")
            head = f"{row.get('ts', '')}  ·  {meeting.length_label(row.get('duration', 0))}"
            state = MEETING_STATUS.get(row.get("status", ""), "")
            if state:
                head += "  ·  " + t(state)
            item = QListWidgetItem(f"{head}\n{title}")
            item.setData(Qt.ItemDataRole.UserRole, row)
            self.minutes_list.addItem(item)
        if not self.minutes_list.count():
            self.minutes_view.clear()
            self.minutes_retry.setEnabled(False)

    def _selected_meeting(self):
        item = self.minutes_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _show_minutes(self, *_):
        row = self._selected_meeting()
        if not row:
            self.minutes_view.clear()
            self.minutes_retry.setEnabled(False)
            return
        doc_path, _wav = cfg.meeting_paths(row["base"])
        try:
            self.minutes_view.setPlainText(doc_path.read_text(encoding="utf-8"))
        except OSError:
            self.minutes_view.setPlainText(
                row.get("error") or t("Nothing has been written yet.")
            )
        busy = self.meetings is not None and self.meetings.busy
        self.minutes_retry.setEnabled(
            self.meetings is not None and not busy and row.get("status") != "done"
        )

    def _retry_minutes(self):
        row = self._selected_meeting()
        if not row or self.meetings is None or self.meetings.busy:
            return
        # A row that already has its transcript resumes from there; only a run
        # that never got that far goes back to the audio.
        self.meetings.run(row)
        self.minutes_retry.setEnabled(False)
        self.minutes_status.setText(t("Working…"))

    def _delete_minutes(self):
        row = self._selected_meeting()
        if not row:
            return
        if self.meetings is not None and self.meetings.running_base == row["base"]:
            QMessageBox.information(self, t("Minutes"),
                                    t("This one is being written up right now."))
            return
        if not self._confirm(
            t("Delete this meeting, its minutes and its recording?"), t("Minutes")
        ):
            return
        try:
            cfg.delete_meetings([row["base"]])
        except OSError as exc:
            QMessageBox.warning(self, t("Minutes"), t("Failed: {error}", error=exc))
        self._load_minutes()

    def _on_minutes_progress(self, _base, message):
        self.minutes_status.setText(message)

    def _on_minutes_finished(self, _base, title):
        self.minutes_status.setText(t("Done: {title}", title=title))
        self._load_minutes()

    def _on_minutes_failed(self, _base, error):
        self.minutes_status.setText(t("Failed: {error}", error=error))
        self._load_minutes()

    # ---- history ---------------------------------------------------------

    def _load_history(self):
        self.history.clear()
        for row in reversed(cfg.read_history(self.conf["history_limit"])):
            text = (row.get("text") or "").replace("\n", " ")
            preview = text[:110] + ("…" if len(text) > 110 else "")
            header = t("{ts}  ({duration} s)",
                       ts=row.get("ts", ""), duration=row.get("duration", 0))
            if row.get("mode") == "ask":
                # The text of an answer says nothing about what was asked, and
                # out of that context half of them read like non sequiturs.
                asked = (row.get("question") or row.get("raw") or "").replace("\n", " ")
                header += t("  ·  legacy Agent record: {question}",
                            question=asked[:60] + ("…" if len(asked) > 60 else ""))
            item = QListWidgetItem(f"{header}\n{preview}")
            item.setData(Qt.ItemDataRole.UserRole, row)
            self.history.addItem(item)

    def _selected_rows(self):
        """Selected entries, newest first, the order they are listed in."""
        items = sorted(self.history.selectedItems(), key=self.history.row)
        return [item.data(Qt.ItemDataRole.UserRole) for item in items]

    def _copy_history(self):
        rows = self._selected_rows()
        if rows:
            QGuiApplication.clipboard().setText(
                "\n\n".join(row.get("text", "") for row in rows)
            )

    def _delete_history(self):
        rows = self._selected_rows()
        if not rows:
            return
        # One entry goes without asking; a multi-selection is easy to make by
        # accident, and there is no undo.
        if len(rows) > 1 and not self._confirm(
            t("Delete the {count} selected entries?", count=len(rows))
        ):
            return
        self._rewrite_history(lambda: cfg.delete_history(rows))

    def _clear_history(self):
        if not self.history.count():
            return
        if not self._confirm(t("Delete the whole history? This cannot be undone.")):
            return
        self._rewrite_history(cfg.clear_history)

    def _confirm(self, question, title=None):
        answer = QMessageBox.question(
            self, title or t("History"), question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _rewrite_history(self, action):
        try:
            action()
        except OSError as exc:
            QMessageBox.warning(self, t("History"), t("Failed: {error}", error=exc))
        self._load_history()

    def _history_menu(self, pos):
        item = self.history.itemAt(pos)
        if item is not None and not item.isSelected():
            self.history.setCurrentItem(item)
        menu = QMenu(self)
        copy = menu.addAction(t("Copy selected to clipboard"))
        delete = menu.addAction(t("Delete selected"))
        menu.addSeparator()
        clear = menu.addAction(t("Clear history"))
        has_selection = bool(self.history.selectedItems())
        copy.setEnabled(has_selection)
        delete.setEnabled(has_selection)
        clear.setEnabled(self.history.count() > 0)
        chosen = menu.exec(self.history.viewport().mapToGlobal(pos))
        if chosen is copy:
            self._copy_history()
        elif chosen is delete:
            self._delete_history()
        elif chosen is clear:
            self._clear_history()
