"""Settings window."""

from datetime import datetime
import os
import logging
import sys
import threading
import weakref

from PyQt6.QtCore import (QEasingCurve, QLibraryInfo, QPoint, QPropertyAnimation,
                          QRect, QSize, Qt, QTimer, QEvent, QTranslator, QUrl, pyqtSignal)
from PyQt6.QtGui import (QColor, QDesktopServices, QFont, QFontMetrics,
                         QGuiApplication, QIcon, QKeySequence, QShortcut, QPainter)
from PyQt6 import sip
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QFrame, QGraphicsOpacityEffect, QGroupBox,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox, QStyle, QProgressBar,
    QStyledItemDelegate, QStyleOptionViewItem, QTabWidget, QTabBar, QVBoxLayout, QWidget, QBoxLayout, QStackedWidget,
)

import api
import audio
import config as cfg
import filetranscribe
import i18n
import hotkey
import livespeech
import localspeech
import overlay
import meeting
import sounds
import startup
import theme
from screenshot_capture import default_save_folder
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
    ("Model's own default", ""), ("Minimal", "minimal"),
    ("Low", "low"), ("Medium", "medium"), ("High", "high"),
]
AUDIO_FILTER = ("*.mp3 *.wav *.m4a *.ogg *.opus *.flac *.aac *.wma "
                "*.mp4 *.mkv *.webm *.mov *.avi")


def _box_button_texts(box):
    """Qt's standard buttons in the user's language.

    QMessageBox ships English button texts (Yes/No/OK) unless the Qt
    translator catalogs are installed, which they are not here, so every
    dialog built below gets its buttons relabelled through t().
    """
    for standard, key in (
        (QMessageBox.StandardButton.Ok, "OK"),
        (QMessageBox.StandardButton.Yes, "Yes"),
        (QMessageBox.StandardButton.No, "No"),
        (QMessageBox.StandardButton.Cancel, "Cancel"),
    ):
        button = box.button(standard)
        if button is not None:
            button.setText(t(key))


def warn_box(parent, title, text):
    box = QMessageBox(QMessageBox.Icon.Warning, title, text,
                      QMessageBox.StandardButton.Ok, parent)
    _box_button_texts(box)
    box.exec()


def info_box(parent, title, text):
    box = QMessageBox(QMessageBox.Icon.Information, title, text,
                      QMessageBox.StandardButton.Ok, parent)
    _box_button_texts(box)
    box.exec()


def confirm_box(parent, title, text):
    box = QMessageBox(
        QMessageBox.Icon.Question, title, text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        parent,
    )
    box.setDefaultButton(QMessageBox.StandardButton.No)
    _box_button_texts(box)
    return box.exec() == QMessageBox.StandardButton.Yes


_qt_translator = None


def install_qt_translator(app, code):
    """Qt's own strings (context menus, dialog buttons) in the UI language.

    Qt ships the Turkish catalogue next to the PyQt6 package; a frozen build
    carries the same file under its own bundle directory.
    """
    global _qt_translator
    if _qt_translator is not None:
        app.removeTranslator(_qt_translator)
        _qt_translator = None
    if code != "tr":
        return False
    translator = QTranslator(app)
    for folder in (
        os.path.join(getattr(sys, "_MEIPASS", ""), "PyQt6", "Qt6", "translations"),
        QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath),
    ):
        if folder and translator.load("qtbase_tr", folder):
            app.installTranslator(translator)
            _qt_translator = translator
            return True
    return False


class EmptyListWidget(QListWidget):
    """An empty hint without a fake selectable record."""
    def __init__(self, hint):
        super().__init__()
        self.hint = hint
        self.setAccessibleName(hint)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.count():
            painter = QPainter(self.viewport())
            painter.setPen(QColor(theme.palette().muted))
            painter.drawText(self.viewport().rect().adjusted(12, 8, -12, -8),
                             Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                             self.hint)


class Disclosure(QWidget):
    """A compact section that does not occupy space until requested."""
    def __init__(self, title, widgets, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.toggle = QPushButton(t(title))
        self.toggle.setObjectName("disclosure")
        self.toggle.setCheckable(True)
        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 8, 0, 8)
        for widget in widgets:
            body.addWidget(widget)
        self.body.hide()
        self.toggle.toggled.connect(self._expand)
        layout.addWidget(self.toggle)
        layout.addWidget(self.body)

    def _expand(self, expanded):
        self.body.setVisible(expanded)
        self.body.setMinimumHeight(self.body.layout().minimumSize().height() if expanded else 0)
        self.body.updateGeometry()
        self.updateGeometry()
        QTimer.singleShot(0, self._refresh_scroll_extent)

    def _refresh_scroll_extent(self):
        parent = self.parentWidget()
        while parent is not None:
            if parent.layout() is not None:
                parent.layout().invalidate()
                parent.layout().activate()
            parent.updateGeometry()
            if isinstance(parent, QScrollArea):
                content = parent.widget()
                content.setMinimumHeight(content.layout().minimumSize().height())
                if self.toggle.isChecked():
                    parent.ensureWidgetVisible(self.toggle, 0, 16)
                break
            parent = parent.parentWidget()


class ActionRow(QWidget):
    def __init__(self, source):
        super().__init__()
        self.actions = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self.actions.setContentsMargins(0, 0, 0, 0)
        while source.count():
            item = source.takeAt(0)
            if item.widget():
                self.actions.addWidget(item.widget())
    def resizeEvent(self, event):
        needed = sum(self.actions.itemAt(i).widget().sizeHint().width()
                     for i in range(self.actions.count())) + max(0, self.actions.count()-1) * 8
        self.actions.setDirection(QBoxLayout.Direction.TopToBottom if self.width() < needed
                                  else QBoxLayout.Direction.LeftToRight)
        super().resizeEvent(event)


class Workspace(QWidget):
    """Two panes on desktop; one selectable pane on small windows."""
    def __init__(self, left, right):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.selector = QTabBar()
        self.selector.addTab(t("Controls"))
        self.selector.addTab(t("Details"))
        self.selector.setExpanding(False)
        self.selector.hide()
        layout.addWidget(self.selector)
        self.columns = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.columns.setContentsMargins(0, 0, 0, 0)
        self.columns.setSpacing(16)
        self.panes = []
        for panel in (left, right):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            panel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            scroll.setWidget(panel)
            self.columns.addWidget(scroll, 1)
            self.panes.append(scroll)
        layout.addLayout(self.columns, 1)
        self.selector.currentChanged.connect(self._reflow)

    def _reflow(self, *_):
        narrow = self.width() < 780
        self.selector.setVisible(narrow)
        for index, pane in enumerate(self.panes):
            pane.setVisible(not narrow or self.selector.currentIndex() == index)

    def resizeEvent(self, event):
        self._reflow()
        super().resizeEvent(event)


class PanelTabs(QTabWidget):
    """Local pages reserve their own space rather than growing the main page.

    Scroll areas are a fallback for genuinely short windows. At desktop sizes
    each selected form fits; only transcript editors and lists need scrolling.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panelTabs")
        self.setDocumentMode(True)
        # A hidden page's minimum height must not force its whole pane to
        # scroll. The selected page owns the available space and its fallback.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

    def add_panel(self, title, widget):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        widget.setMinimumWidth(0)
        widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        scroll.setWidget(widget)
        return self.addTab(scroll, t(title))


class SaveBanner(QFrame):
    """The strip a save shows under the header rule, then takes away itself.

    A save does not need an answer from anyone: the settings are already on
    disk, so the window keeps working and the confirmation leaves on its own.
    Nothing here accepts a click, and nothing has to be dismissed.
    """

    HEIGHT = 46
    HOLD_MS = 2400
    FADE_IN_MS = 150
    FADE_OUT_MS = 320

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("saveBanner")
        self.setFixedHeight(self.HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row = QHBoxLayout(self)
        row.setContentsMargins(13, 0, 13, 0)
        row.setSpacing(10)
        self.mark = QLabel("✓")
        self.mark.setObjectName("saveBannerMark")
        self.mark.setFixedSize(26, 26)
        self.mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.mark)
        self.label = QLabel("")
        self.label.setObjectName("saveBannerText")
        row.addWidget(self.label)
        row.addStretch(1)
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self._animation = QPropertyAnimation(self._opacity, b"opacity", self)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._animation.finished.connect(self._after_animation)
        self._hold = QTimer(self)
        self._hold.setSingleShot(True)
        self._hold.timeout.connect(self.fade_out)
        self.hide()

    def show_saved(self, text):
        self.label.setText(text)
        self.place()
        self.show()
        self.raise_()
        self._hold.stop()
        self._animate(1.0, self.FADE_IN_MS)
        self._hold.start(self.FADE_IN_MS + self.HOLD_MS)

    def fade_out(self):
        self._animate(0.0, self.FADE_OUT_MS)

    def place(self):
        """Sit under the header rule, as wide as the window's own margins."""
        window = self.parentWidget()
        if window is None:
            return
        margin = window.layout().contentsMargins().left()
        rule = getattr(window, "_header_rule", None)
        top = 8
        if rule is not None:
            top = rule.mapTo(window, QPoint(0, 0)).y() + 5
        self.setGeometry(margin, top,
                         max(160, window.width() - 2 * margin), self.HEIGHT)

    # ---- internals -----------------------------------------------------

    def _animate(self, target, msec):
        self._animation.stop()
        self._animation.setDuration(msec)
        self._animation.setStartValue(self._opacity.opacity())
        self._animation.setEndValue(target)
        self._animation.start()

    def _after_animation(self):
        if self._opacity.opacity() <= 0.01:
            self.hide()


# What a device card says under the name. The keys are what audio.py guesses
# and the values are the text handed to t(), so the guess itself stays out of
# the translation table and only the one word that changes is in it.
CONNECTION_LABELS = {
    "bluetooth": "Bluetooth",
    "usb": "USB",
    "built-in": "Built-in",
}


class DeviceCardDelegate(QStyledItemDelegate):
    """Draws a device row as a card: the name, and under it how it is connected.

    One line per device was not enough to tell two rows apart — a machine with a
    headset, a USB interface and a laptop array shows three near-identical
    names, and the user has to open each one to find out. The second line says
    what the first one leaves out.

    The card only appears when there are enough rows to need it. A two-item
    box (Cloud/Local, a language) would spend twice the height saying less.
    """

    # Below this, the plain single-line row is the better look: there is no
    # scrolling to do and nothing to disambiguate.
    MIN_ROWS_FOR_CARDS = 5

    # The air around a card's two lines. sizeHint() and paint() both use these,
    # so the height promised and the height drawn can never drift apart.
    PAINT_PADDING_TOP = 5
    PAINT_PADDING_BOTTOM = 6
    PAINT_PADDING_X = 10
    BAR_WIDTH = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._connection_text = {}

    def set_connection_text(self, index, text):
        """The second line for one row, or "" for none."""
        self._connection_text[index] = text or ""
        view = self.parent()
        if isinstance(view, QAbstractItemView):
            view.viewport().update()

    def set_connection_text_map(self, mapping):
        """Replace every row's second line at once."""
        self._connection_text = {int(i): (text or "")
                                 for i, text in mapping.items()}

    def connection_text(self, index):
        return self._connection_text.get(index, "")

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        sub = self.connection_text(index.row())
        if not sub:
            return hint
        metrics = option.fontMetrics
        small = QFont(option.font)
        small.setPointSizeF(max(8.0, option.font.pointSizeF() - 1.5))
        small_metrics = QFontMetrics(small)
        # Both lines at their own leading, plus the padding paint() draws
        # around them, plus a few pixels so the last row is never the one that
        # gets clipped: metrics.lineSpacing() alone measured 5px short per card
        # and every second line sat on the row below it.
        height = (metrics.lineSpacing() + small_metrics.lineSpacing()
                  + self.PAINT_PADDING_TOP + self.PAINT_PADDING_BOTTOM + 2)
        return QSize(hint.width(), max(hint.height(), height))

    def paint(self, painter, option, index):
        sub = self.connection_text(index.row())
        if not sub:
            super().paint(painter, option, index)
            return

        painter.save()
        # The theme can be switched with the window open, so the palette is
        # read here rather than captured when the delegate was built.
        colors = theme.palette()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            painter.fillRect(option.rect, QColor(colors.selected))
            # The bar is what makes the chosen row findable at a glance in a
            # list this tall; without it the card is just another dark row.
            painter.fillRect(QRect(option.rect.left(), option.rect.top(),
                                   self.BAR_WIDTH, option.rect.height()),
                             QColor(colors.violet))
        elif hovered:
            painter.fillRect(option.rect, QColor(colors.hover))

        rect = option.rect.adjusted(
            self.PAINT_PADDING_X + self.BAR_WIDTH, self.PAINT_PADDING_TOP,
            -self.PAINT_PADDING_X, -self.PAINT_PADDING_BOTTOM)
        # Measured with the font that is about to be used, not the option's:
        # the name is drawn bold, and eliding against the unbolded metrics
        # leaves a name a few pixels too wide to fit (measured: a 233px name
        # elided for 240px and then drawn 246px wide, so it ran off the row).
        font = QFont(option.font)
        font.setBold(True)
        metrics = QFontMetrics(font)
        name_color = QColor(colors.text if (selected or hovered)
                            else colors.muted)
        sub_color = QColor(colors.violet if selected else colors.muted)
        painter.setFont(font)
        painter.setPen(name_color)
        name = metrics.elidedText(
            index.data(Qt.ItemDataRole.DisplayRole) or "",
            Qt.TextElideMode.ElideMiddle, rect.width())
        flags = (Qt.AlignmentFlag.AlignLeft
                 | Qt.AlignmentFlag.AlignVCenter)
        # The two lines share the row, split at the midpoint of the text area
        # rather than at metrics.lineSpacing(), so the card looks the same
        # whatever font is in use and the second line can never land on the
        # row below it.
        half = rect.height() // 2
        painter.drawText(QRect(rect.left(), rect.top(), rect.width(), half),
                         int(flags), name)
        small = QFont(option.font)
        small.setPointSizeF(max(8.0, option.font.pointSizeF() - 1.5))
        painter.setFont(small)
        painter.setPen(sub_color)
        painter.drawText(
            QRect(rect.left(), rect.top() + half, rect.width(), half),
            int(flags), sub)
        painter.restore()


class FitsOnScreenCombo(QComboBox):
    """One anchored picker for every choice, with search for long/model lists.

    Mouse release opens it after the originating click has finished. Children
    belong to the popup before being shown, so no temporary top-level control
    can steal Windows focus and immediately close the list.
    """


    def _cards_if_long(self, subs):
        """Turn on card rows when the list is long enough to need them.

        The threshold is the row count, because that is what the card is for:
        telling similar devices apart. A two-item box has nothing to
        disambiguate, and doubling its height to say the same thing less is
        worse than the plain row it replaces.
        """
        view = self.view()
        delegate = view.itemDelegate()
        if self.count() < DeviceCardDelegate.MIN_ROWS_FOR_CARDS:
            if isinstance(delegate, DeviceCardDelegate):
                view.setItemDelegate(None)
            return
        if not isinstance(delegate, DeviceCardDelegate):
            # Parented to the combo, not to the view. A view is itself parented
            # inside the combo's container, so a delegate parented there is
            # thrown away the moment setItemDelegate() returns (measured: the
            # view reporting None straight after). Parented to the combo it
            # lives exactly as long as the list does.
            delegate = DeviceCardDelegate(self)
            view.setItemDelegate(delegate)
        # subs is already (row, text) pairs, straight from the caller. Taking
        # them apart with enumerate() stored the whole pair as the text, and
        # the card then drew "(3, 'USB')" where a USB label belonged.
        for row, text in subs:
            delegate.set_connection_text(row, text)

    def _row_height(self):
        """The height of one row as it will actually be drawn.

        Read from the delegate rather than from the view: sizeHintForRow()
        reports the single-line height whatever delegate is installed, so a
        card list measured with it opens at half the height its rows need and
        the last card is exactly the one that gets cut. sizeHintForIndex() is
        no use either — it returns a whole QSize, not a height.

        Row 0 is the "default" entry, which carries no second line and so stays
        a plain row; measuring that one reports the plain height and halves
        the whole popup. The tallest row is asked for instead, because the
        popup has to fit the cards.
        """
        view = self.view()
        delegate = view.itemDelegate()
        opt = QStyleOptionViewItem()
        opt.font = view.font()
        opt.fontMetrics = view.fontMetrics()
        opt.palette = view.palette()
        opt.rect = QRect(0, 0, 100, 100)
        tallest = 0
        for row in range(self.count()):
            index = view.model().index(row, 0)
            if not index.isValid():
                continue
            hint = delegate.sizeHint(opt, index)
            if hint.isValid():
                tallest = max(tallest, hint.height())
        return tallest or view.sizeHintForRow(0) or 24

    def setEditable(self, editable):
        super().setEditable(editable)
        if editable:
            # Custom values are entered in the picker. The entire closed field
            # is a selection target, including the embedded line edit.
            self.lineEdit().setReadOnly(True)
            self.lineEdit().installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is getattr(self, "_picker_search", None) and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self._picker_rows.setFocus()
                return True
        if watched is self.lineEdit() and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space, Qt.Key.Key_Down):
                self.showPopup()
                return True
        if watched is self.lineEdit() and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                return True
        if watched is self.lineEdit() and event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                QTimer.singleShot(0, self.showPopup)
                return True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.rect().contains(event.position().toPoint()):
                QTimer.singleShot(0, self.showPopup)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def showPopup(self):
        if self.isEnabled() and (self.count() or self.isEditable()):
            self._search_picker()

    def hidePopup(self):
        self._close_picker()
        super().hidePopup()

    def _close_picker(self):
        """Close and forget the live picker; safe when it is already gone.

        The picker is a Qt.Popup: Qt destroys it on its own when it closes
        (WA_DeleteOnClose) or when its owner window goes away, and the stale
        Python reference then points at a deleted C++ object. Every touch of
        that reference has to pass through here, or the process dies with an
        access violation instead of an exception.
        """
        picker, self._picker = getattr(self, "_picker", None), None
        if picker is not None and not sip.isdeleted(picker):
            picker.close()

    def _live_picker(self):
        picker = getattr(self, "_picker", None)
        if picker is None or sip.isdeleted(picker):
            self._picker = None
            return None
        return picker

    def _search_picker(self):
        existing = self._live_picker()
        if existing is not None:
            existing.close()
        dialog = QFrame(self.window(), Qt.WindowType.Popup)
        self._picker = dialog
        dialog.setObjectName("selectionPopup")
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle(t("Select"))
        screen = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        layout = QVBoxLayout(dialog)
        search = QLineEdit(dialog)
        search.setPlaceholderText(t("Search…"))
        search.setClearButtonEnabled(True)
        searchable = self.isEditable() or bool(self.property('searchable')) or self.count() > 8
        search.setVisible(searchable)
        rows = QListWidget(dialog)
        self._picker_search = search
        self._picker_rows = rows
        search.installEventFilter(self)
        rows.setWordWrap(True)
        source_delegate = self.view().itemDelegate()
        if isinstance(source_delegate, DeviceCardDelegate):
            delegate = DeviceCardDelegate(rows)
            delegate.set_connection_text_map({i: source_delegate.connection_text(i) for i in range(self.count())})
            rows.setItemDelegate(delegate)
        for index in range(self.count()):
            item = QListWidgetItem(self.itemText(index))
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(self.itemText(index))
            rows.addItem(item)
        rows.setCurrentRow(self.currentIndex())
        def filter_rows(query):
            for index in range(rows.count()):
                connection = source_delegate.connection_text(index) if isinstance(source_delegate, DeviceCardDelegate) else ""
                rows.item(index).setHidden(query.casefold() not in (rows.item(index).text() + " " + connection).casefold())
            visible = [rows.item(i) for i in range(rows.count()) if not rows.item(i).isHidden()]
            if visible:
                rows.setCurrentItem(visible[0])
        search.textChanged.connect(filter_rows)
        def choose():
            item = rows.currentItem()
            if item is not None and not item.isHidden():
                self.setCurrentIndex(item.data(Qt.ItemDataRole.UserRole))
                self._picker = None   # closed by its own click; the reference goes with it
                dialog.close()
        custom = QPushButton(t("Use typed value"), dialog)
        custom.setVisible(self.isEditable())
        def use_custom():
            if search.text().strip():
                self.setEditText(search.text().strip())
                self._picker = None
                dialog.close()
        custom.clicked.connect(use_custom)
        def accept_search():
            if self.isEditable() and not any(not rows.item(i).isHidden() for i in range(rows.count())):
                use_custom()
            else:
                choose()
        rows.itemDoubleClicked.connect(lambda _: choose())
        rows.itemClicked.connect(lambda _: choose())
        rows.itemActivated.connect(lambda _: choose())
        search.returnPressed.connect(accept_search)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), dialog,
                  activated=lambda: (setattr(self, "_picker", None), dialog.close()))
        enter = QShortcut(QKeySequence(Qt.Key.Key_Return), rows, activated=choose)
        enter.setContext(Qt.ShortcutContext.WidgetShortcut)
        layout.addWidget(search)
        layout.addWidget(rows, 1)
        layout.addWidget(custom)
        # The rows' own heights, not a guess: the stylesheet padding and the
        # installed delegate both decide how tall a row draws, and a hardcoded
        # 34 let a 150% display push the last row past the popup edge where it
        # could only be reached by scrolling.
        row_height = max(rows.fontMetrics().height() + 18,
                         *(rows.sizeHintForRow(i) for i in range(rows.count())),
                         34)
        width = min(max(self.width(), 320), screen.width() - 16)
        visible_rows = min(self.count(), 6 if searchable else 8)
        # Space the layout itself takes: its margins, plus whatever visible
        # widget shares the column. The row count only gets the rest.
        # isVisible() cannot be asked here: the dialog has not been shown yet,
        # so every child reports False and the rows would be given a window
        # that is too short for them — the last one ends up under the edge.
        margins = layout.contentsMargins()
        chrome = margins.top() + margins.bottom() + rows.frameWidth() * 2
        if searchable:
            chrome += layout.spacing() + search.sizeHint().height()
        if self.isEditable():
            chrome += layout.spacing() + custom.sizeHint().height()
        height = min(440, row_height * visible_rows + chrome)
        if self.count() > visible_rows:
            # A list that scrolls draws the bar over its rows; without the
            # extra width the widest row is elided for no reason.
            width = min(screen.width() - 16,
                        width + rows.verticalScrollBar().sizeHint().width())
        anchor = self.mapToGlobal(QPoint(0, self.height()))
        above = self.mapToGlobal(QPoint(0, 0)).y() - screen.top()
        below = screen.bottom() - anchor.y() + 1
        upwards = below < height and above > below
        height = min(height, max(80, above if upwards else below), screen.height() - 16)
        x = max(screen.left() + 8, min(anchor.x(), screen.right() - width - 7))
        y = self.mapToGlobal(QPoint(0, 0)).y() - height if upwards else anchor.y()
        y = max(screen.top() + 8, min(y, screen.bottom() - height - 7))
        dialog.setGeometry(x, y, width, height)
        dialog.show()
        if searchable:
            search.setFocus()
        else:
            rows.setFocus()

    def _open_where_it_fits(self):
        """Move the popup so the whole list is on the screen, shrinking it to
        the room that exists when the full list fits neither below nor above.

        The view is not resized directly. A combo's view is wrapped in a QFrame
        that Qt lays out itself, so anything set on the view is undone on the
        next event. Only the popup window is placed here; Qt lays the rows out
        inside it and scrolls what does not fit.
        """
        popup = self.view().window()
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        box = self.mapToGlobal(self.rect().topLeft())
        row_h = self._row_height()
        frame = self.view().frameWidth() * 2 + 8
        full = max(1, self.count()) * row_h + frame
        placed = self._choose_placement(
            box.y(), box.y() + self.height(), full, row_h, frame,
            avail.top(), avail.bottom(),
            popup.geometry().top(), popup.geometry().bottom())
        if placed is None:
            return                              # Qt's placement fits; leave it
        top, height = placed
        rect = popup.geometry()
        popup.setGeometry(rect.x(), top, rect.width(), height)

    @staticmethod
    def _choose_placement(box_top, box_bottom, full, row_h, frame,
                          screen_top, screen_bottom, qt_top, qt_bottom):
        """Where the popup goes, as (top, height) — or None to keep Qt's.

        Qt lines the selected row up with the box, so its first choice can
        hang off the top even when the whole list would fit below — that is a
        real placement too, not only the bottom clipping. Cases in order: what
        Qt opened is fully visible; opens below at full height; opens above at
        full height; neither way fits, so the roomier side is taken and the
        list shrinks to it and scrolls — a full-height popup pushed off-screen
        reads as a list that shows nothing at all. Never shorter than three
        rows unless the screen itself is that short.
        """
        avail_h = screen_bottom - screen_top + 1
        full = min(full, avail_h - 24)
        # The floor, not a second full: at least three rows stay visible so a
        # shrunk list is still a list, unless the screen itself is shorter.
        min_h = min(3 * row_h + frame, avail_h - 24)
        below = screen_bottom - box_bottom
        above = box_top - screen_top
        if qt_top >= screen_top and qt_bottom <= screen_bottom:
            return None
        if below >= full:
            return box_bottom, full
        if above >= full:
            return box_top - full, full
        if below >= above:
            height = min(full, max(below, min_h))
            top = min(box_bottom, screen_bottom - height + 1)
            return max(top, screen_top), height
        height = min(full, max(above, min_h))
        return max(box_top - height, screen_top), height

    def keyPressEvent(self, event):
        # Qt decides this one for itself and does not consult the screen, so a
        # keyboard-opened list lands in the same clipped place the mouse-opened
        # one did. Routed through the same placement for the same reason.
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space,
                           Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_F4):
            self.showPopup()
            event.accept()
        else:
            super().keyPressEvent(event)

    def _reposition_popup(self):
        """Slide an already-open popup back onto the screen.

        Separate from _open_where_it_fits because by the time a key arrives the
        list has scrolled, so the height is Qt's to decide and only the
        position is ours to fix.
        """
        popup = self.view().window()
        if not popup.isVisible():
            return
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        rect = popup.geometry()
        if rect.bottom() <= avail.bottom() and rect.top() >= avail.top():
            return
        if rect.height() <= avail.height():
            y = min(max(rect.y(), avail.top()),
                    avail.bottom() - rect.height() + 1)
            popup.setGeometry(rect.x(), y, rect.width(), rect.height())


class HotkeyEdit(QWidget):
    """Press-to-assign shortcut field, game-style.

    Click the field and it starts listening — the box highlights; the next
    combination pressed lands in it right away. Escape cancels the take,
    Backspace or Delete clears the shortcut, and nothing is applied until the
    settings window's Save button is pressed.
    """

    capture_started = pyqtSignal()
    capture_finished = pyqtSignal()

    # Windows owns these; RegisterHotKey can never take them.
    RESERVED = ("ctrl+alt+del", "ctrl+alt+delete")

    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self._placeholder = placeholder or t("Press shortcut keys…")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.line = QLineEdit(self)
        self.line.setReadOnly(True)
        self.line.setCursor(Qt.CursorShape.PointingHandCursor)
        self.line.setPlaceholderText(self._placeholder)
        self.line.installEventFilter(self)
        layout.addWidget(self.line)
        self.hint = QLabel("")
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        self.hint.hide()
        layout.addWidget(self.hint)
        self.setFocusProxy(self.line)
        self._listening = False
        self._value_before_listen = ""

    def currentText(self):
        return self.line.text()

    def setCurrentText(self, text):
        self.line.setText(text or "")
        self._clear_hint()

    def clear(self):
        self.line.clear()
        self._clear_hint()

    def mousePressEvent(self, event):
        self._start_listen()
        self.line.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)

    def _clear_hint(self):
        if self.hint.isVisible():
            self.hint.hide()

    def _note(self, message):
        self.hint.setText(message)
        self.hint.show()

    def _start_listen(self):
        """A click starts the capture; one combination ends it again."""
        if self._listening:
            return
        self._listening = True
        self._capture_assigned = False
        self._value_before_listen = self.line.text()
        self._clear_hint()
        self.line.clear()
        self.line.setPlaceholderText(t("Press the keys now…"))
        self.line.setStyleSheet("border: 1px solid #9475EC;")
        self.capture_started.emit()

    def _stop_listen(self):
        if not self._listening:
            return
        if not self._capture_assigned:
            self.line.setText(self._value_before_listen)
        self._listening = False
        self.line.setPlaceholderText(self._placeholder)
        self.line.setStyleSheet("")
        self.capture_finished.emit()

    def eventFilter(self, obj, event):
        if obj is not self.line:
            return super().eventFilter(obj, event)
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress:
            self._start_listen()
        elif kind in (QEvent.Type.FocusOut, QEvent.Type.Hide):
            self._stop_listen()
        elif kind == QEvent.Type.ShortcutOverride:
            if not self._listening:
                return super().eventFilter(obj, event)
            # Reserve the event here; assign only on KeyPress. Qt sends both
            # events for one press, so assigning here used to capture twice.
            event.accept()
            return True
        elif kind == QEvent.Type.KeyPress:
            if (not self._listening and not event.isAutoRepeat() and event.key() in
                    (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space)):
                self._start_listen()
                return True
            if self._listening:
                try:
                    if self._capture(event):
                        return True
                except Exception:
                    logging.getLogger("wordarc.shortcut").exception(
                        "could not capture the pressed keys")
        return super().eventFilter(obj, event)

    def _assign(self, text):
        self._capture_assigned = True
        self.line.setText(text)
        self._clear_hint()
        self._note(t("Press Save to apply."))
        self._stop_listen()

    def _capture(self, event):
        if event.isAutoRepeat():
            return True
        key = event.key()
        mods = (event.modifiers() & (Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.AltModifier
                | Qt.KeyboardModifier.MetaModifier
                | Qt.KeyboardModifier.ShiftModifier)).value
        if key == Qt.Key.Key_Escape:
            self.line.setText(self._value_before_listen)
            self._clear_hint()
            self._stop_listen()
            return True
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt,
                   Qt.Key.Key_Meta, Qt.Key.Key_unknown):
            return True
        if not mods and key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self._assign("")
            return True
        text = QKeySequence(mods | int(key)).toString(
            QKeySequence.SequenceFormat.PortableText)
        if event.modifiers() & Qt.KeyboardModifier.KeypadModifier:
            key_text = QKeySequence(int(key)).toString(
                QKeySequence.SequenceFormat.PortableText)
            if key_text in "0123456789*+-./" and len(key_text) == 1:
                prefix = text[:-len(key_text)]
                text = prefix + ("NumPlus" if key_text == "+"
                                 else "Num" + key_text)
        if text == "Print":
            text = "PrintScreen"
        elif text.endswith("+Print"):
            text = text[:-len("+Print")] + "+PrintScreen"
        if not text:
            return True
        if text.strip().lower().replace(" ", "") in self.RESERVED:
            self._note(t("Windows reserves this combination: {shortcut}",
                         shortcut=text))
            return True
        if hotkey.parse_shortcut(text) == (0, 0):
            self._note(t("This key combination cannot be assigned."))
            return True
        self._assign(text)
        return True


class WindowView:
    """Where a settings window sits and which page it shows.

    The language change rebuilds the window instead of retranslating every
    widget, and the rebuild used to hand back a window at its opening size, on
    the first tab, wherever Qt felt like placing it — which is what the change
    looked like from the outside: the window rearranging itself. This is the
    little that has to survive for the new window to land where the old one
    was.

    The screen is carried along with the rectangle: the new window is placed by
    its own geometry, and without the screen Qt would answer "which monitor is
    this on" from wherever it put the window by default, which can be the other
    one — and then the placement check slides a window from the second monitor
    onto the first.
    """

    PAGES = ("dictation", "meeting", "audio_file", "screenshot", "settings")

    def __init__(self, window):
        self.maximized = window.isMaximized()
        rect = window.normalGeometry() if self.maximized else window.geometry()
        self.rect = QRect(rect)
        # A monitor that has gone away leaves this None, and the window is
        # placed by Qt instead of being pushed onto a screen it was not on.
        self.screen = next(
            (screen for screen in QGuiApplication.screens()
             if screen.availableGeometry().intersects(self.rect)), None)
        self.page = next((name for name in self.PAGES
                          if window._tab_index.get(name) == window.tabs.currentIndex()),
                         "dictation")
        menu = getattr(window, "settings_section_menu", None)
        self.section = menu.currentRow() if menu is not None else 0
        self.panels = {name: getattr(window, name).currentIndex() for name in (
            "dictation_details", "dictation_advanced", "meeting_details",
            "meeting_advanced", "file_options", "model_setup")}

    def apply(self, window):
        """Put `window` back where the old one was."""
        if self.screen is not None:
            window.setScreen(self.screen)
            window.setGeometry(self.rect)
        window.navigate_to(self.page)
        menu = getattr(window, "settings_section_menu", None)
        if menu is not None:
            menu.setCurrentRow(max(0, min(self.section, menu.count() - 1)))
        for name, index in self.panels.items():
            getattr(window, name).setCurrentIndex(index)
        if self.maximized:
            window.setWindowState(Qt.WindowState.WindowMaximized)


class SettingsWindow(QDialog):
    recording_requested = pyqtSignal(str)
    screenshot_requested = pyqtSignal(str)
    screenshot_failed = pyqtSignal(str)
    cancel_requested = pyqtSignal(str)
    applied = pyqtSignal()
    language_changed = pyqtSignal()
    # True while a shortcut field is listening for keys: the global shortcuts
    # have to be parked, or RegisterHotKey swallows the combination first.
    shortcut_capture = pyqtSignal(bool)

    _models_loaded = pyqtSignal(list, str)
    _transcribe_models_loaded = pyqtSignal(list, str)
    _local_download_done = pyqtSignal(str, str)
    _local_download_progress = pyqtSignal(object)
    _test_done = pyqtSignal(bool, str)
    _local_inspected = pyqtSignal(str, object)

    def __init__(self, conf, launch_command, meeting_command=None,
                 meetings=None, ask_command=None, parent=None):
        super().__init__(parent)
        self.conf = conf
        if not hasattr(conf, '_cuda_recovery'):
            from cuda_recovery import CudaRecovery
            self.cuda_recovery = CudaRecovery(conf)
        else:
            self.cuda_recovery = conf._cuda_recovery.__self__
        self.cuda_recovery.changed.connect(self._cuda_changed)
        self._download_stop = threading.Event()
        self._download_name = None
        self._local_snapshots = {}
        self._local_pending = set()
        self._local_inspected.connect(self._on_local_inspected)
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
        # Damgalar işlemler tarafından pencereden bağımsız yazılır; açık
        # kalan liste 5 saniyede bir tazelenir, gizlenince durur.
        self._usage_timer = QTimer(self)
        self._usage_timer.timeout.connect(self._on_usage_tick)
        self.setObjectName("settingsRoot")
        self.setWindowTitle(t("WordArc Settings"))
        self.setWindowIcon(QIcon(str(brand_asset("wordarc.ico"))))
        self.resize(1040, 760)
        # Small screens must be able to shrink the window: the floor sits
        # well below the opening size and every tab scrolls vertically.
        self.setMinimumSize(520, 400)
        # A bare QDialog offers only the cross on Windows. The window is a
        # full workspace with scrollable tabs: it minimises and maximises
        # like any other window, so ask for the standard title-bar buttons.
        self.setWindowFlags(self.windowFlags()
                            | Qt.WindowType.WindowMinimizeButtonHint
                            | Qt.WindowType.WindowMaximizeButtonHint)
        if os.environ.get("QT_QPA_PLATFORM", "") != "offscreen":
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                avail = screen.availableGeometry()
                self.resize(min(1040, max(520, avail.width() - 40)),
                            min(760, max(400, avail.height() - 80)))
                # Size is not position. A window sized to fit can still sit
                # where it was restored to — partly off the bottom of the
                # screen — and a dropdown near its last row then opens past
                # the screen edge with its final item cut in half, because Qt
                # places the popup inside the combo's own rectangle. Put the
                # window on the screen it opened on, fully inside it.
                self._fit_on_screen(avail)

        header = QWidget()
        header_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, header)
        self.header_layout = header_layout
        header_layout.setContentsMargins(2, 0, 2, 4)
        logo = QLabel()
        logo.setPixmap(QIcon(str(brand_asset("wordarc-app.svg"))).pixmap(44, 44))
        logo.setFixedSize(48, 48)
        header_layout.addWidget(logo)
        identity = QVBoxLayout()
        identity.setSpacing(0)
        name = QLabel(f"{BRAND.name} v{BRAND.version}")
        name.setObjectName("brandName")
        name.setWordWrap(True)
        self.brand_name_label = name
        identity.addWidget(name)
        header_layout.addLayout(identity)
        header_layout.addStretch()
        header_layout.addWidget(QLabel(t("Language")))
        self.header_lang = QPushButton()
        self.header_lang.setMinimumWidth(96)
        self.header_lang.clicked.connect(self._toggle_lang)
        header_layout.addWidget(self.header_lang)
        header_layout.addWidget(QLabel(t("Theme")))
        self.header_theme = QPushButton()
        self.header_theme.setMinimumWidth(96)
        self.header_theme.clicked.connect(self._cycle_theme)
        # The application tab never had its own theme control; the alias stays
        # so external code keeps working.
        self.general_theme = self.header_theme
        header_layout.addWidget(self.header_theme)

        rule = QFrame()
        rule.setObjectName("headerRule")
        rule.setFixedHeight(1)
        self._header_rule = rule

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
        layout.setSpacing(12)
        layout.addWidget(header)
        layout.addWidget(rule)
        layout.addWidget(content, 1)
        layout.addWidget(buttons)

        # Floats over the tab strip rather than taking a row of its own: a
        # confirmation that shoves the window around costs more than it says.
        self.save_banner = SaveBanner(self)

        self._models_loaded.connect(self._on_models_loaded)
        self._transcribe_models_loaded.connect(self._on_transcribe_models_loaded)
        self._local_download_done.connect(self._on_local_download_done)
        self._local_download_progress.connect(self._on_local_download_progress)
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
        self.transcribe_engine.currentIndexChanged.connect(self._refresh_local_controls)
        self.local_stt_model.currentIndexChanged.connect(self._refresh_local_controls)
        self.transcribe_model.currentTextChanged.connect(self._refresh_shared_ai_summaries)
        self.cleanup_model.currentTextChanged.connect(self._refresh_shared_ai_summaries)
        self.cleanup_enabled.toggled.connect(self._refresh_local_controls)
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
             self._file_tab(), True),
            ("screenshot", (), "Screenshot",
             "Capture and save a screenshot from the active screen.",
             style.standardIcon(QStyle.StandardPixmap.SP_DesktopIcon),
             self._screenshot_tab(), True),
            ("settings", ("shared_ai", "application"), "Settings",
             "Models, language, startup and appearance.",
             style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon),
             self._settings_tab(), False),
        ]
        for main_id, aliases, title, description, icon, body, scroll in specs:
            body = self._workspace_page(main_id, body)
            wrapped, _scroller = self._wrap_page(body, description, False)
            index = self.tabs.addTab(wrapped, t(title))
            self._tab_index[main_id] = index
            for alias in aliases:
                self._tab_index[alias] = index
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self.tabs)
        return content

    @staticmethod
    def _column(widgets):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        expands = False
        for widget in widgets:
            expanding = widget.sizePolicy().verticalPolicy() in (QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
            layout.addWidget(widget, int(expanding))
            expands |= expanding
        if not expands:
            layout.addStretch()
        return panel

    def _record_controls(self, kind):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton(t("Start recording"))
        button.setObjectName("primaryButton")
        cancel = QPushButton(t("Cancel recording"))
        cancel.hide()
        status = QLabel(t("Ready"))
        status.setObjectName("muted")
        status.setWordWrap(True)
        button.clicked.connect(lambda: self._request_recording(kind))
        cancel.clicked.connect(lambda: self.cancel_requested.emit(kind))
        layout.addWidget(status)
        layout.addWidget(button)
        layout.addWidget(cancel)
        setattr(self, kind + "_record_button", button)
        setattr(self, kind + "_cancel_button", cancel)
        setattr(self, kind + "_record_status", status)
        setattr(self, kind + "_runtime_state", "idle")
        return panel

    def _request_recording(self, kind):
        state = getattr(self, kind + "_runtime_state")
        if state in ("busy", "working"):
            return
        # The settings still go to disk first (the take must use what is on
        # screen), but quietly: the "saved" banner belongs to the Save
        # button, not to every press of "start recording".
        if state == "idle" and not self._save(quiet=True):
            return
        self.recording_requested.emit(kind)

    def set_recording_state(self, kind, state, message=""):
        setattr(self, kind + "_runtime_state", state)
        busy = state in ("busy", "working")
        recording = state == "recording"
        button = getattr(self, kind + "_record_button")
        button.setText(t("Working…") if busy else
                       t("Stop and transcribe") if recording else t("Start recording"))
        button.setEnabled(not busy)
        getattr(self, kind + "_cancel_button").setVisible(recording)
        getattr(self, kind + "_record_status").setText(
            message or t("Recording…" if recording else "Working…" if busy else "Ready"))

    def set_dictation_result(self, text):
        self.dictation_output.setPlainText(text)
        self._load_history()

    def _workspace_page(self, kind, original):
        """Move existing controls into fixed local pages, preserving callbacks."""
        if kind == "screenshot":
            return original
        old = original.layout()
        widgets = []
        while old.count():
            item = old.takeAt(0)
            if item.widget():
                widget = item.widget()
                widget.setParent(None)
                widgets.append(widget)

        def card(title, controls):
            box, body = self._section_card(title, title)
            for control in controls:
                if isinstance(control, tuple):
                    body.addWidget(self._label_row(*control))
                else:
                    body.addWidget(control)
            return box

        def book(groups):
            tabs = PanelTabs()
            for title, items in groups:
                tabs.add_panel(title, self._column(items))
            return tabs

        def editor(widget, minimum=90):
            widget.setMinimumHeight(minimum)
            widget.setMaximumHeight(16777215)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            return widget

        # Long explanations belong in help, not between every form control.
        for widget in widgets:
            for label in widget.findChildren(QLabel):
                if len(label.text()) > 150:
                    widget.setToolTip(widget.toolTip() + "\n" + label.text())
                    label.hide()
            for row in widget.findChildren(QHBoxLayout):
                children = [row.itemAt(i).widget() for i in range(row.count()) if row.itemAt(i).widget()]
                if len(children) > 1 and all(isinstance(child, QPushButton) for child in children):
                    parent = row.parent()
                    if isinstance(parent, QVBoxLayout):
                        index = parent.indexOf(row)
                        parent.removeItem(row)
                        parent.insertWidget(index, ActionRow(row))

        if kind == "settings":
            # The model card stays compact; its large instruction editor gets
            # a dedicated text page. Default-reset uses the existing callback.
            cleanup_card = widgets[2]
            body = cleanup_card.layout().itemAt(0).layout()
            body.removeWidget(self.cleanup_prompt)
            reset_item = body.takeAt(body.count() - 1)
            reset_holder = QWidget()
            reset_holder.setLayout(reset_item.layout())
            rules = card("Cleanup rules", [editor(self.cleanup_prompt, 180), reset_holder])
            # Speech glossary has its own editor; it does not compete vertically
            # with cleanup instructions.
            editor(self.transcribe_prompt, 140)
            editor(self.gemini_keys_list, 120)
            widgets[1].layout().itemAt(0).layout().removeWidget(self.download_panel)
            self.model_setup = book([
                ("Model", [widgets[1]]), ("Download", [self.download_panel]),
            ])
            widgets[1].layout().itemAt(0).layout().setSpacing(6)
            self.model_setup.tabBar().setAutoHide(True)
            self.model_setup.setTabVisible(1, False)
            models = Workspace(self.model_setup, self._column([cleanup_card]))
            text = Workspace(self._column([rules]), self._column([widgets[3]]))
            application = Workspace(self._column([widgets[5]]), self._column(widgets[6:]))
            self.settings_section_stack = book([
                ("Audio and models", [models]),
                ("Text and terms", [text]),
                ("API keys", [widgets[0]]),
                ("Application", [application]),
            ])
            # Compatibility for navigation and language-rebuild state, while
            # visible navigation is now the horizontal category strip.
            menu = QListWidget(self.settings_section_stack)
            menu.addItems([t(name) for name in ("Audio and models", "Text and terms", "API keys", "Application")])
            menu.hide()
            menu.currentRowChanged.connect(self.settings_section_stack.setCurrentIndex)
            self.settings_section_stack.currentChanged.connect(menu.setCurrentRow)
            menu.setCurrentRow(0)
            self.settings_section_menu = menu
            widgets[4].deleteLater()
            original.deleteLater()
            return self.settings_section_stack

        if kind == "dictation":
            controls = card("Dictation", [
                ("Microphone", self._row(self.mic, self.refresh_audio_devices)),
                ("Speech language", self.language), ("Shortcut", self.shortcut),
                self.shortcut_status, self.cleanup_enabled, self.auto_paste,
            ])
            left = self._column([self._record_controls(kind), controls])
            recording = card("Recording", [
                ("Longest recording", self.max_seconds),
                ("Silence threshold", self.silence_db), self.skip_silent,
                self.filter_hallucinations, self.keep_audio,
            ])
            output = card("Output", [("Paste key", self.paste_shortcut), self.restore_clipboard])
            text = card("Cleanup", [self.translate_enabled, self.translate_mode, self._shared_ai_note()])
            self.dictation_advanced = book([
                ("Recording", [recording]), ("Output", [output]), ("Text", [text]),
            ])
            self.dictation_output = QPlainTextEdit()
            self.dictation_output.setReadOnly(True)
            editor(self.dictation_output, 160)
            self.dictation_output.setPlaceholderText(t("Your next dictation appears here."))
            copy = QPushButton(t("Copy"))
            copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.dictation_output.toPlainText()))
            result = card("Latest dictation", [self.dictation_output, copy])
            result.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
            self.history.setMinimumHeight(80)
            self.history.setMaximumHeight(150)
            self.dictation_details = book([
                ("Advanced", [self.dictation_advanced]),
                ("Latest dictation", [result]), ("History", [widgets[5]]),
            ])
            self.dictation_details.setCurrentIndex(1)
            for stale in widgets[:5]:
                stale.deleteLater()
            right = self.dictation_details
        elif kind == "meeting":
            # Sound sources remain visible. People, recording limits, model
            # and the long minutes instruction each have a bounded local page.
            left = self._column([self._record_controls(kind), widgets[0]])
            editor(self.meeting_prompt, 180)
            editor(self.meeting_participants, 60)
            self.meeting_participants.setMaximumHeight(100)
            self.meeting_advanced = book([
                ("Recording", [widgets[3]]), ("Who is talking", [widgets[1]]),
                ("Minutes", [widgets[2]]), ("Minutes instruction", [widgets[4]]),
            ])
            self.minutes_list.setMinimumHeight(70)
            self.minutes_list.setMaximumHeight(110)
            editor(self.minutes_view, 100)
            widgets[5].setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
            self.meeting_details = book([
                ("Minutes", [widgets[5]]), ("Advanced", [self.meeting_advanced]),
            ])
            right = self.meeting_details
        else:
            # File options and prompt are peers; opening the prompt cannot push
            # timestamps, the result or the run button below the window.
            options = widgets[3]
            prompt_row = self.file_cleanup_prompt.parentWidget()
            body = options.layout().itemAt(0).layout()
            body.removeWidget(prompt_row)
            reset = body.takeAt(body.count() - 1)
            reset_holder = QWidget()
            reset_holder.setLayout(reset.layout())
            editor(self.file_cleanup_prompt, 160)
            rules = card("Cleanup rules", [prompt_row, reset_holder])
            self.file_options = book([
                ("Options", [widgets[2], options]), ("Cleanup rules", [rules]),
            ])
            widgets[4].setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
            left = self._column([widgets[1], self.file_options])
            right = self._column(widgets[4:])
            editor(self.file_output, 140)
            widgets[0].deleteLater()
        original.deleteLater()
        return Workspace(left, right)

    def _wrap_page(self, page, description, scroll=True):
        page.setObjectName("pageCard")
        page.setMinimumWidth(0)
        page.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        container = QWidget()
        container.setObjectName("page")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 18, 4, 8)
        layout.setSpacing(12)
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
        # A tab is a different amount of content: the one that was open may
        # have left the window where it fit, and the one now open may be the
        # one whose last dropdown has no room. Re-fitting on every switch costs
        # nothing and keeps a later click from opening a list off the screen.
        self._fit_on_screen()

    def _fit_on_screen(self, avail=None):
        """Slide the window fully onto the screen it is on, and shrink the
        window to that screen if it is taller.

        A dropdown opens inside the rectangle its combo occupies, so a combo in
        the last row of a window whose bottom hangs below the screen edge opens
        a popup whose bottom is that far below the screen too — and the last
        item is cut in half rather than scrolled, which is what a user sees as
        a list they cannot finish reading. The window is the cheapest place to
        fix it: nothing else has to know whether a given screen is short.
        """
        # A maximized window already fills the screen it is on, and moving it
        # here would only take the state away — setGeometry clears it — so a
        # user who maximized the window and then switched tabs watched it fall
        # back to its old size.
        if self.isMaximized() or self.isFullScreen():
            return
        if avail is None:
            # Which monitor the window is on is read from where it stands, not
            # from what Qt reports for it: a window that is open has a handle
            # and Qt's answer is right, but a window being placed before it is
            # shown has none yet, and Qt then guesses the screen the cursor is
            # on — which slid a window restored onto the second monitor over to
            # the first one.
            screen = (QGuiApplication.screenAt(self.frameGeometry().center())
                      or self.screen() or QGuiApplication.primaryScreen())
            if screen is None:
                return
            avail = screen.availableGeometry()
        # setGeometry() positions the window frame but sizes the client area,
        # and for a decorated window those are different rectangles. Measured
        # on the frame and compared against width()/x(), which leave the frame
        # out, a window never looked like it was already in place: every tab
        # switch called setGeometry() with the frame's size as the client size
        # and grew the window by its title bar and borders.
        frame = self.frameGeometry()
        rect = self.geometry()
        chrome = frame.height() - rect.height()  # title bar plus borders
        # Only the height is capped. The width is the user's: narrowing it to
        # the screen would fight the minimum width the window already sets,
        # and a window that is too wide just gets a horizontal scrollbar.
        # Tall content: let the window use the whole screen height. Every tab
        # scrolls, so this costs nothing and saves a clipped popup.
        height = min(rect.height(), max(0, avail.height() - chrome))
        x = min(max(frame.x(), avail.left()),
                max(avail.left(), avail.right() - rect.width() + 1))
        y = min(max(frame.y(), avail.top()),
                max(avail.top(), avail.bottom() - height - chrome + 1))
        if (height, x, y) == (rect.height(), frame.x(), frame.y()):
            return
        self.setGeometry(x, y, rect.width(), height)

    def navigate_to(self, page_id):
        """Open the tab holding one logical page."""
        if page_id not in self._tab_index:
            return False
        self._show_page(page_id)
        if page_id == "history":
            self.dictation_details.setCurrentIndex(2)
        elif page_id == "minutes":
            self.meeting_details.setCurrentIndex(0)
        if page_id in ("shared_ai", "application"):
            self.settings_section_menu.setCurrentRow(3 if page_id == "application" else 0)
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
            transcribe=self._engine_summary(),
            cleanup=self.cleanup_model.currentText(),
        )
        for label in list(getattr(self, "_shared_ai_labels", [])):
            try:
                label.setText(summary)
            except RuntimeError:
                # The note was rebuilt under this list (a language change
                # swaps the pages out): a deleted label is dropped instead
                # of taking the update down with it.
                self._shared_ai_labels.remove(label)

    def _engine_summary(self):
        """One short phrase naming the engine that would answer now."""
        if self.transcribe_engine.currentData() == "local":
            return f"Whisper {self.local_stt_model.currentData()}"
        if self.transcribe_engine.currentData() == "live":
            return "Live Gemini"
        return self.transcribe_model.currentText()

    def _refresh_local_controls(self, *_):
        """Show the rows that belong to the chosen engine, and the state of the
        model it names. Called on every engine or model change: this is the one
        place the user can tell a model they have from one they don't."""
        if not hasattr(self, "transcribe_engine"):
            return
        local = self.transcribe_engine.currentData() == "local"
        live = self.transcribe_engine.currentData() == "live"
        self.cloud_row.setVisible(not local and not live)
        self.transcribe_status.setVisible(not local and not live)
        if hasattr(self, "live_row"):
            self.live_row.setVisible(live)
            self.live_model_note.setVisible(live)
        self.local_row.setVisible(local)
        self.local_status.setVisible(local)
        if hasattr(self, "local_privacy_note"):
            self.local_privacy_note.setVisible(local)
            enabled = hasattr(self, "cleanup_enabled") and self.cleanup_enabled.isChecked()
            self.local_privacy_note.setText(t("Audio stays on this computer. Cleanup sends the text to Gemini when enabled." if enabled else "Audio stays on this computer. Cleanup is off; the raw transcript is used."))
        if hasattr(self, "device_row"):
            self.device_row.setVisible(local)
            self.local_device_note.setVisible(local)
            if local and hasattr(self, "local_stt_device"):
                preference = self.local_stt_device.currentData() or "auto"
                snapshot = self._local_snapshots.get(preference)
                if snapshot is None:
                    self.local_device_note.setText(t("Checking local speech device…"))
                    self.local_status.setText(t("Checking local speech device…"))
                    self.local_download_button.setEnabled(False)
                    self.local_remove_button.setEnabled(False)
                    if preference not in self._local_pending:
                        self._local_pending.add(preference)
                        threading.Thread(target=self._inspect_local,
                                         args=(preference,), daemon=True).start()
                    return
                if isinstance(snapshot, str):
                    self.local_device_note.setText(snapshot)
                    self.local_status.setText(snapshot)
                    self.local_download_button.setEnabled(False)
                    self.local_remove_button.setEnabled(False)
                    return
                note = snapshot["note"]
                fallback = localspeech.last_fallback_note()
                if fallback:
                    note = f"{note} — {fallback}"
                self.local_device_note.setText(note)
        if self._download_name:
            self.local_download_button.setEnabled(False)
            self.local_remove_button.setEnabled(False)
            return
        if not local:
            self.local_download_button.setEnabled(False)
            self.local_remove_button.setEnabled(False)
            return
        name = self.local_stt_model.currentData()
        preference = self.local_stt_device.currentData() or "auto"
        if snapshot["backend"] == "vulkan":
            for index in range(self.local_stt_model.count()):
                model = self.local_stt_model.itemData(index)
                size = localspeech.human_size(snapshot["states"][model].expected)
                self.local_stt_model.setItemText(index, f"Whisper {model} — {size} (Vulkan)")
            if name in snapshot["cpu_only"]:
                self.local_device_note.setText(t("Vulkan model needs downloading; the existing CPU model remains available in Automatic mode."))
        else:
            for index in range(self.local_stt_model.count()):
                model = self.local_stt_model.itemData(index)
                label, note = localspeech.model_label(model)
                current_model = snapshot["states"][model]
                if current_model.path.endswith(".bin"):
                    note = localspeech.human_size(current_model.expected)
                self.local_stt_model.setItemText(index, f"{label} — {t(note)}")
        current = snapshot["states"][name]
        if (snapshot["backend"] != "vulkan" or
                preference == "auto" and localspeech.vulkan_speech._failed) and current.path.endswith(".bin"):
            self.local_device_note.setText(t("CPU (whisper.cpp model)"))
        if current.installed:
            self.local_status.setText(t(
                "{name} is installed ({size}) and ready.",
                name=name, size=localspeech.human_size(current.size)))
            self.local_download_button.setEnabled(False)
            self.local_remove_button.setEnabled(True)
            return
        self.local_status.setText(t(
            "{name} is not downloaded yet — {size}. Downloaded once, it "
            "works offline after that.", name=name,
            size=localspeech.human_size(current.expected)))
        self.local_download_button.setEnabled(True)
        self.local_remove_button.setEnabled(False)

    def _inspect_local(self, preference):
        """No widgets here: driver probes and filesystem inspection may block."""
        try:
            names = localspeech.model_names()
            try:
                resolved = localspeech.get_best_device(preference)
                note = localspeech.describe_device(preference, resolved=resolved)
                storage_preference = resolved[0]
            except localspeech.LocalSpeechError as exc:
                note = str(exc)
                storage_preference = preference if preference != "auto" else "cpu"
            # Failed auto Vulkan sessions still keep GGML models visible.
            if preference == "auto" and localspeech.vulkan_speech._failed:
                storage_preference = "vulkan"
            snapshot = dict(
                note=note,
                backend="vulkan" if storage_preference == "vulkan" else "cpu",
                states={name: localspeech.state(name, device_preference=storage_preference)
                        for name in names},
                cpu_only={name for name in names
                          if not localspeech.vulkan_speech.installed(name)
                          and localspeech._is_installed(name)})
        except Exception as exc:
            logging.getLogger("wordarc.settings").warning(
                "local device inspection failed: %s", type(exc).__name__)
            snapshot = t("Could not check the local speech device.")
        try:
            self._local_inspected.emit(preference, snapshot)
        except RuntimeError:
            pass  # window was deleted while the driver was answering

    def _on_local_inspected(self, preference, snapshot):
        self._local_pending.discard(preference)
        self._local_snapshots[preference] = snapshot
        self._refresh_local_controls()
        if getattr(self, "_local_status_error", ""):
            self.local_status.setText(self._local_status_error)

    def _download_local_model(self):
        self._local_status_error = ""
        name = self.local_stt_model.currentData()
        preference = self.local_stt_device.currentData() or "auto"
        if self._download_name or not name or localspeech.state(name, device_preference=preference).installed:
            return
        # Install-time system check: missing Python packages are offered for
        # automatic install; a driver without a working CUDA runtime only
        # changes where the model will run. Nothing missing -> straight on.
        status = (dict(packages_missing=[], driver=False, gpu_ready=True)
                  if localspeech.model_backend(preference) == "vulkan" else localspeech.prerequisite_status())
        missing = list(status["packages_missing"])
        if missing:
            if not confirm_box(self, t("Install"), t(
                    "The local engine needs {packages}. Install them "
                    "automatically and continue with the setup?",
                    packages=", ".join(missing))):
                return
        elif status["driver"] and not status["gpu_ready"]:
            if not confirm_box(self, t("Download"), t(
                    "An Nvidia driver is present, but the CUDA runtime does "
                    "not answer (cuBLAS/cuDNN may be missing). Setup continues "
                    "and the model runs on the CPU. Continue?")):
                return
        self._download_name = name
        self._download_stop.clear()
        self.local_stt_model.setEnabled(False)
        self.local_stt_device.setEnabled(False)
        self.local_download_button.setEnabled(False)
        self.local_remove_button.setEnabled(False)
        self.download_cancel.setEnabled(True)
        self.download_panel.show()
        self.model_setup.setTabVisible(1, True)
        self.model_setup.setCurrentIndex(1)
        self.download_title.setText(t("Downloading {name}…", name=name))
        self.download_details.setText(t("Connecting…"))
        self.download_bar.setRange(0, 0)
        self.local_status.setText(t("Downloading {name}…", name=name))
        def work():
            try:
                if missing:
                    self._deliver("_local_download_progress",
                                  localspeech.DownloadProgress(
                                      name, 0, 0, 0.0, None,
                                      t("Installing…"), "installing"))
                    localspeech.install_missing_packages(missing)
                localspeech.download(
                    name, should_stop=self._download_stop.is_set,
                    device_preference=preference,
                    on_progress=lambda progress: self._deliver(
                        "_local_download_progress", progress))
                self._deliver("_local_download_done", name, "")
            except Exception as exc:
                self._deliver("_local_download_done", name, str(exc))
        threading.Thread(target=work, daemon=True).start()

    def _on_local_download_progress(self, progress):
        if progress.name != self._download_name:
            return
        self.download_title.setText(t("Downloading {name}…", name=progress.name))
        if progress.total:
            self.download_bar.setRange(0, 1000)
            self.download_bar.setValue(min(1000, int(progress.completed * 1000 / progress.total)))
            eta = t("Calculating…") if progress.remaining is None else t("{seconds} s", seconds=round(progress.remaining))
            self.download_details.setText(t(
                "{done} / {total} · {speed}/s · Remaining: {eta}",
                done=localspeech.human_size(progress.completed) or "0 MB",
                total=localspeech.human_size(progress.total),
                speed=localspeech.human_size(progress.speed) or "0 KB", eta=eta))
        self.download_file.setText(t("Verifying files…") if progress.phase == "verifying" else
                                   t("Retrying connection…") if progress.phase == "retrying" else progress.filename)

    def _on_local_download_done(self, name, error):
        if name != self._download_name:
            return
        cancelled = self._download_stop.is_set()
        self._download_name = None
        self.local_stt_model.setEnabled(True)
        self.local_stt_device.setEnabled(True)
        self.download_cancel.setEnabled(False)
        self._local_snapshots.clear()
        self._refresh_local_controls()
        if error:
            message = t("Download stopped. Press Download to resume.") if cancelled else t("Could not download {name}: {error}", name=name, error=error)
            self._local_status_error = message
            self.local_status.setText(message)
            self.download_title.setText(message)
            self.download_title.setToolTip(message)
            self.download_bar.setRange(0, 1000)
        else:
            self.download_bar.setRange(0, 1000)
            self.download_bar.setValue(1000)
            self.download_title.setText(t("Model ready: {name}", name=name))
            self.download_file.setText("")
            self.save_banner.show_saved(t("Model ready: {name}", name=name))

    def _remove_local_model(self):
        name = self.local_stt_model.currentData()
        if not name:
            return
        preference = self.local_stt_device.currentData() or "auto"
        if not confirm_box(self, t("Remove"), t(
                "Delete the downloaded {name} model? {size} goes back to the "
                "disk. Nothing else is touched.", name=name,
                size=localspeech.human_size(localspeech.state(name, device_preference=preference).size))):
            return
        localspeech.remove(name, device_preference=preference)
        self._local_snapshots.clear()
        self._refresh_local_controls()

    THEME_ORDER = ("dark", "light")
    THEME_LABELS = {"dark": "Dark", "light": "Light"}

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
        # The window rebuilds itself on the signal, and the app installs Qt's
        # translator before it does, so both languages change together.
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
        layout.setSpacing(14)

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
        self.mic = FitsOnScreenCombo()
        self.mic.setProperty("searchable", True)
        self.refresh_audio_devices = QPushButton(t("Reload"))
        self.refresh_audio_devices.clicked.connect(self._refresh_audio_devices)
        body.addWidget(self._label_row(
            "Microphone", self._row(self.mic, self.refresh_audio_devices)))
        self.language = FitsOnScreenCombo()
        for label, code in LANGUAGES:
            self.language.addItem(t(label), code)
        body.addWidget(self._label_row("Speech language", self.language))
        layout.addWidget(sound)

        output, body = self._section_card(
            "Output", "Where the finished text goes.")
        self.auto_paste = QCheckBox(t("Paste the text into the focused window"))
        body.addWidget(self.auto_paste)
        self.paste_shortcut = self._shortcut_box()
        self.paste_shortcut.setToolTip(
            t("Terminals usually want Ctrl+Shift+V. Change this if pasting does nothing.")
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
        self.translate_enabled = QCheckBox(t("Translate dictation to English"))
        body.addWidget(self.translate_enabled)
        self.translate_mode = FitsOnScreenCombo()
        self.translate_mode.addItem(t("Academic English"), "academic")
        self.translate_mode.addItem(t("Game English"), "game")
        body.addWidget(self.translate_mode)
        body.addWidget(self._shared_ai_note())
        layout.addWidget(cleanup)
        layout.addWidget(self._history_box())
        layout.addStretch(1)
        return page

    def _general_tab(self, page=None, embedded=False):
        page = page if page is not None else QWidget()
        # A page that already carries the shared AI sections keeps its layout:
        # Qt refuses a second one and these rows would never appear.
        layout = page.layout() or QVBoxLayout(page)
        layout.setSpacing(14)
        interface, body = self._section_card(
            "Interface", "Language and appearance.")
        self.ui_language = FitsOnScreenCombo()
        for label, code in UI_LANGUAGES:
            self.ui_language.addItem(t(label), code)
        self.ui_language.setToolTip(
            t("Applies as soon as you save: the window is rebuilt in that language.")
        )
        body.addWidget(self._label_row("Interface language", self.ui_language))

        self.corner = FitsOnScreenCombo()
        for value in CORNERS:
            self.corner.addItem(t(value), value)
        body.addWidget(self._label_row("Indicator corner", self.corner))

        self.meter_style = FitsOnScreenCombo()
        for label, value in overlay.meter_styles():
            self.meter_style.addItem(t(label), value)
        self.meter_style.setToolTip(t(
            "How the sound wave is drawn on the recording indicator. "
            "Spectrum and Capsules glow as you speak louder; Wave is a single "
            "flowing line."))
        body.addWidget(self._label_row("Sound wave style", self.meter_style))
        # Every style shown as it actually draws: the names alone ("Wave",
        # "Capsules") cannot say what the difference looks like, and a user
        # who picks blind ends up thinking the setting does nothing.
        self.meter_previews = []
        previews_row = QWidget()
        previews = QHBoxLayout(previews_row)
        previews.setContentsMargins(0, 0, 0, 0)
        previews.setSpacing(8)
        for label, value in overlay.meter_styles():
            column = QVBoxLayout()
            column.setSpacing(3)
            caption = QLabel(t(label))
            caption.setObjectName("muted")
            caption.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            widget = overlay.MeterPreview(value)
            self.meter_previews.append(widget)
            column.addWidget(widget)
            column.addWidget(caption)
            holder = QWidget()
            holder.setLayout(column)
            previews.addWidget(holder)
        previews.addStretch(1)
        body.addWidget(previews_row)
        layout.addWidget(interface)

        def highlight_preview():
            """Seçili biçimin önizlemesi belirgin dursun."""
            chosen = self.meter_style.currentData()
            for widget in self.meter_previews:
                widget.set_selected(widget.style == chosen)
        self.meter_style.currentIndexChanged.connect(highlight_preview)
        self._highlight_meter_preview = highlight_preview

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
        outer.setSpacing(14)

        # API keys first, then model selection. Two rows: the list with its two
        # main actions on top, the row actions underneath.
        keys, keys_body = self._section_card(
            "Keys", "Your Gemini API keys, used one after another.")
        key_help = QLabel(t("Stored only in Windows Credential Manager."))
        key_help.setWordWrap(True)
        key_help.setObjectName("muted")
        keys_body.addWidget(key_help)

        self.gemini_keys_list = EmptyListWidget(t("Add an API key to use cloud models."))
        self.gemini_keys_list.setMinimumHeight(150)
        self.gemini_keys_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.gemini_keys_list.currentRowChanged.connect(
            self._refresh_gemini_key_buttons
        )
        keys_body.addWidget(self.gemini_keys_list)

        self.gemini_add_button = QPushButton(t("Add API"))
        self.gemini_add_button.setObjectName("accentButton")
        self.gemini_add_button.clicked.connect(self._add_gemini_key)
        self.gemini_test_button = QPushButton(t("Test"))
        self.gemini_test_button.clicked.connect(self._test_gemini)
        top_row = QHBoxLayout()
        top_row.addWidget(self.gemini_add_button)
        top_row.addWidget(self.gemini_test_button)
        top_row.addStretch(1)
        keys_body.addLayout(top_row)

        self.gemini_test_label = QLabel("")
        self.gemini_test_label.setObjectName("muted")
        self.gemini_test_label.setWordWrap(True)
        keys_body.addWidget(self.gemini_test_label)

        self.gemini_edit_button = QPushButton(t("Edit"))
        self.gemini_edit_button.clicked.connect(self._edit_gemini_key)
        self.gemini_remove_button = QPushButton(t("Remove"))
        self.gemini_remove_button.setObjectName("dangerButton")
        self.gemini_remove_button.clicked.connect(self._remove_gemini_key)
        self.gemini_up_button = QPushButton(t("Move up"))
        self.gemini_up_button.clicked.connect(lambda: self._move_gemini_key(-1))
        self.gemini_down_button = QPushButton(t("Move down"))
        self.gemini_down_button.clicked.connect(lambda: self._move_gemini_key(1))
        item_row = QHBoxLayout()
        for button in (self.gemini_edit_button, self.gemini_remove_button,
                       self.gemini_up_button, self.gemini_down_button):
            item_row.addWidget(button)
        item_row.addStretch(1)
        keys_body.addLayout(item_row)
        outer.addWidget(keys)

        stt, stt_body = self._section_card(
            "Speech to text", "The model that turns speech into text.")

        self.transcribe_engine = FitsOnScreenCombo()
        for label, value in localspeech.ENGINES:
            self.transcribe_engine.addItem(t(label), value)
        self.transcribe_engine.setToolTip(t(
            "Local transcribes on this computer and sends no audio anywhere. "
            "Cloud and Live use Gemini and need an API key: Cloud types up a "
            "recording after it ends, Live streams your speech as you speak "
            "and shows the words while you are still talking."))
        self.local_stt_model = FitsOnScreenCombo()
        self.local_stt_model.setProperty("searchable", True)
        for name in localspeech.model_names():
            label, note = localspeech.model_label(name)
            # The model name is the same in both languages; the note beside it
            # is what the user is choosing between, so that one is translated.
            self.local_stt_model.addItem(f"{label} — {t(note)}", name)
        self.local_stt_model.setToolTip(t(
            "Measured on Turkish dictation. base is quick and the smallest "
            "download; small is in between; large-v3-turbo reads hardest audio "
            "most reliably and never invents a closing sentence."))
        self.local_stt_device = FitsOnScreenCombo()
        for label, value in localspeech.DEVICE_CHOICES:
            self.local_stt_device.addItem(t(label), value)
        self.local_stt_device.setToolTip(t(
            "Automatic uses NVIDIA CUDA, then AMD Vulkan, then CPU. "
            "AMD Vulkan needs a separate model download. An explicit GPU "
            "choice asks before switching to CPU after a failure."))
        self.local_stt_device.currentIndexChanged.connect(
            self._refresh_local_controls)
        self.local_download_button = QPushButton(t("Download"))
        self.local_download_button.clicked.connect(self._download_local_model)
        self.local_remove_button = QPushButton(t("Remove"))
        self.local_remove_button.clicked.connect(self._remove_local_model)
        self.local_status = QLabel("")
        self.local_status.setObjectName("muted")
        self.local_status.setWordWrap(True)
        self.transcribe_model = FitsOnScreenCombo()
        self.transcribe_model.setEditable(True)
        self.transcribe_model.addItems(TRANSCRIBE_MODELS)
        self.refresh_transcribe_models = QPushButton(t("Fetch model list"))
        self.refresh_transcribe_models.clicked.connect(self._load_transcribe_models)

        stt_body.addWidget(self._label_row(
            "Where it runs", self.transcribe_engine))
        # Both model rows go away in the other mode, not just their buttons: a
        # model box the chosen engine ignores is a control that does nothing.
        self.local_row = self._label_row(
            "Local model", self._row(self.local_stt_model,
                                     self.local_download_button,
                                     self.local_remove_button))
        stt_body.addWidget(self.local_row)
        self.device_row = self._label_row("Device", self.local_stt_device)
        stt_body.addWidget(self.device_row)
        self.local_device_note = QLabel("")
        self.local_device_note.setObjectName("muted")
        self.local_device_note.setWordWrap(True)
        stt_body.addWidget(self.local_device_note)
        self.local_status = QLabel("")
        self.local_status.setObjectName("muted")
        self.local_status.setWordWrap(True)
        stt_body.addWidget(self.local_status)
        self.local_privacy_note = QLabel()
        self.local_privacy_note.setObjectName("muted")
        self.local_privacy_note.setWordWrap(True)
        stt_body.addWidget(self.local_privacy_note)
        self.download_panel = QWidget()
        self.download_panel.setObjectName("sharedAiNote")
        download_layout = QVBoxLayout(self.download_panel)
        self.download_title = QLabel()
        self.download_title.setWordWrap(True)
        self.download_bar = QProgressBar()
        self.download_bar.setTextVisible(True)
        self.download_details = QLabel()
        self.download_details.setObjectName("muted")
        self.download_details.setWordWrap(True)
        self.download_file = QLabel()
        self.download_file.setObjectName("muted")
        self.download_file.setWordWrap(True)
        self.download_cancel = QPushButton(t("Stop"))
        self.download_cancel.clicked.connect(self._download_stop.set)
        for widget in (self.download_title, self.download_bar, self.download_details,
                       self.download_file, self.download_cancel):
            download_layout.addWidget(widget)
        self.download_panel.hide()
        stt_body.addWidget(self.download_panel)
        self.cloud_row = self._label_row(
            "Cloud model", self._row(self.transcribe_model,
                                     self.refresh_transcribe_models))
        stt_body.addWidget(self.cloud_row)
        self.live_transcription_mode = FitsOnScreenCombo()
        self.live_transcription_mode.addItem(t("Smart"), "smart")
        self.live_transcription_mode.addItem(t("Verbatim"), "verbatim")
        self.live_transcription_mode.setToolTip(t(
            "Smart removes filler words while you speak. Verbatim keeps "
            "every word, including fillers."))
        self.live_row = self._label_row(
            "Live transcript mode", self.live_transcription_mode)
        stt_body.addWidget(self.live_row)
        # The live engine speaks through one fixed model, so there is nothing
        # to choose; without saying so, the Cloud model box looks like the
        # setting that applies and the user has no way to tell what answered.
        self.live_model_note = QLabel("")
        self.live_model_note.setObjectName("muted")
        self.live_model_note.setWordWrap(True)
        stt_body.addWidget(self.live_model_note)
        self.live_model_note.setText(t(
            "Live uses {model}; it cannot be changed. The model under "
            "Transcript cleanup tidies the text afterwards.",
            model=livespeech.MODEL.removeprefix("models/")))
        self.transcribe_status = QLabel("")
        self.transcribe_status.setObjectName("muted")
        self.transcribe_status.setWordWrap(True)
        stt_body.addWidget(self.transcribe_status)
        self._refresh_local_controls()
        outer.addWidget(stt)

        orr, orr_body = self._section_card(
            "Transcript cleanup", "The model that tidies transcripts.")
        self.cleanup_model = FitsOnScreenCombo()
        self.cleanup_model.setEditable(True)
        self.cleanup_model.addItems(CLEANUP_MODELS)
        self.refresh_models = QPushButton(t("Fetch model list"))
        self.refresh_models.clicked.connect(self._load_models)
        orr_body.addWidget(self._label_row(
            "Model", self._row(self.cleanup_model, self.refresh_models)))

        self.cleanup_reasoning = FitsOnScreenCombo()
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
        layout.setSpacing(14)

        sound, body = self._section_card(
            "Sound", "Your microphone plus whatever comes out of your speakers.")
        self.meeting_mic = FitsOnScreenCombo()
        self.meeting_mic.setProperty("searchable", True)
        body.addWidget(self._label_row("Microphone", self.meeting_mic))

        self.meeting_system = FitsOnScreenCombo()
        self.meeting_system.setProperty("searchable", True)
        self.meeting_system.addItem(t("Current output"), "")
        for name, desc in audio.list_monitors():
            self.meeting_system.addItem(desc, name)
        body.addWidget(self._label_row("Meeting audio source", self.meeting_system))

        self._refresh_audio_devices()

        note = QLabel(t(
            "Wear headphones if you can. Through speakers your microphone hears "
            "the other side as well, and although a line that lands on both "
            "channels at once is dropped again, the repair is never as clean as "
            "not needing it."
        ))
        note.setObjectName("muted")
        note.setWordWrap(True)
        sound.setToolTip(note.text())
        note.hide()
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
        self.meeting_model = FitsOnScreenCombo()
        self.meeting_model.setEditable(True)
        self.meeting_model.addItems(MEETING_MODELS)
        body.addWidget(self._label_row("Model", self.meeting_model))
        self.meeting_reasoning = FitsOnScreenCombo()
        for label, value in REASONING_LEVELS:
            self.meeting_reasoning.addItem(t(label), value)
        self.meeting_reasoning.setToolTip(t(
            "Unlike cleanup, this one is worth some thinking: it has to hold a "
            "whole meeting in its head and work out what was actually decided."
        ))
        body.addWidget(self._label_row("Thinking", self.meeting_reasoning))
        self.meeting_language = FitsOnScreenCombo()
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

    def _cuda_changed(self):
        self._local_snapshots.clear()
        if hasattr(self, 'local_stt_device'):
            self.local_stt_device.setCurrentIndex(self.local_stt_device.findData('cpu'))

    def _settings_tab(self):
        """Shared AI and application sections built straight into one tab.

        (An earlier version built two throwaway pages and moved their rows
        over; that dance crashed Qt on tab switches, so it is gone.)
        """
        page = QWidget()
        self._shared_ai_tab(page, embedded=True)
        line = QFrame()
        line.setObjectName("headerRule")
        line.setFixedHeight(1)
        page.layout().addWidget(line)
        self._general_tab(page, embedded=True)
        page.layout().addStretch(1)
        return page

    def _minutes_box(self):
        box = QGroupBox(t("Minutes"))
        layout = QVBoxLayout(box)

        self.minutes_list = EmptyListWidget(t("No meetings yet."))
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
        delete.setObjectName("dangerButton")
        delete.clicked.connect(self._delete_minutes)
        reload_ = QPushButton(t("Reload"))
        reload_.clicked.connect(self._load_minutes)
        row = QHBoxLayout()
        row.addWidget(copy)
        row.addWidget(self.minutes_retry)
        row.addStretch(1)
        layout.addLayout(row)
        more = QHBoxLayout()
        more.addWidget(folder)
        more.addWidget(delete)
        more.addWidget(reload_)
        layout.addLayout(more)
        return box

    def _file_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)
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
        self.file_run.setObjectName("primaryButton")
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

    def _screenshot_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(14)
        intro = QLabel(t("Capture a region, write on it, then copy or save it."))
        intro.setWordWrap(True)
        layout.addWidget(intro)

        capture, body = self._section_card(
            "Capture", "Select a region or capture the active screen.")
        region = QPushButton(t("Select area…"))
        region.setObjectName("primaryButton")
        region.clicked.connect(
            lambda _checked=False: self.screenshot_requested.emit("region"))
        full = QPushButton(t("Capture this screen"))
        full.clicked.connect(
            lambda _checked=False: self.screenshot_requested.emit("screen"))
        window = QPushButton(t("Capture active window"))
        window.clicked.connect(
            lambda _checked=False: self.screenshot_requested.emit("window"))
        actions = QHBoxLayout()
        actions.addWidget(region)
        actions.addWidget(full)
        actions.addWidget(window)
        actions.addStretch(1)
        body.addLayout(actions)
        self.screenshot_shortcut = self._shortcut_box()
        body.addWidget(self._label_row("Capture shortcut", self.screenshot_shortcut))
        self.screenshot_status = QLabel("")
        self.screenshot_status.setObjectName("muted")
        self.screenshot_status.setWordWrap(True)
        self.screenshot_status.hide()
        self.screenshot_failed.connect(self._show_screenshot_error)
        body.addWidget(self.screenshot_status)
        layout.addWidget(capture)

        options, body = self._section_card(
            "Screenshot options", "Choose where new screenshots are saved by default.")
        self.screenshot_directory = QLineEdit()
        browse = QPushButton(t("Choose folder…"))
        browse.clicked.connect(self._choose_screenshot_directory)
        body.addWidget(self._label_row(
            "Save folder", self._row(self.screenshot_directory, browse)))
        default_folder = QLabel(t("Leave empty to use the Pictures/WordArc folder."))
        default_folder.setObjectName("muted")
        default_folder.setWordWrap(True)
        body.addWidget(default_folder)
        self.screenshot_format = FitsOnScreenCombo()
        self.screenshot_format.addItem("PNG", "PNG")
        self.screenshot_format.addItem("JPEG", "JPEG")
        body.addWidget(self._label_row("Image format", self.screenshot_format))
        layout.addWidget(options)
        layout.addStretch(1)
        return page

    def _choose_screenshot_directory(self):
        current = self.screenshot_directory.text().strip()
        if not current:
            current = str(default_save_folder())
        folder = QFileDialog.getExistingDirectory(
            self, t("Choose screenshot folder"), current)
        if folder:
            self.screenshot_directory.setText(folder)

    def _show_screenshot_error(self, message):
        self.screenshot_status.setText(t("Screenshot failed: {error}", error=message))
        self.screenshot_status.show()

    def _history_box(self):
        box = QGroupBox(t("History"))
        layout = QVBoxLayout(box)
        self.history_enabled = QCheckBox(
            t("Store dictation history on this computer")
        )
        layout.addWidget(self.history_enabled)
        self.history = EmptyListWidget(t("No dictation history yet."))
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

        copy = QPushButton(t("Copy"))
        copy.clicked.connect(self._copy_history)
        delete = QPushButton(t("Delete selected"))
        delete.setObjectName("dangerButton")
        delete.clicked.connect(self._delete_history)
        clear = QPushButton(t("Clear history"))
        clear.setObjectName("dangerButton")
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

    def _shortcut_box(self, placeholder=""):
        """The field a global shortcut is pressed in."""
        edit = HotkeyEdit(placeholder)
        edit.capture_started.connect(
            lambda: self.shortcut_capture.emit(True))
        edit.capture_finished.connect(
            lambda: self.shortcut_capture.emit(False))
        return edit

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
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        caption = QLabel(t(label))
        caption.setObjectName("muted")
        caption.setWordWrap(True)
        layout.addWidget(caption)
        layout.addWidget(widget)
        return holder

    @staticmethod
    def _section_card(title, description):
        """A roomy card: bold title, one muted description line, content."""
        box = QGroupBox(t(title))
        box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        outer = QVBoxLayout(box)
        # The description is the tooltip: the line itself was built here, never
        # added to a layout and thrown away on the next turn of the loop.
        box.setToolTip(t(description))
        inner = QVBoxLayout()
        inner.setSpacing(8)
        inner.setAlignment(Qt.AlignmentFlag.AlignTop)
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
        self.screenshot_shortcut.setCurrentText(
            conf.get("screenshot_shortcut", "Ctrl+Alt+S") or "")
        self.screenshot_directory.setText(
            conf.get("screenshot_directory", "") or "")
        self._select_data(self.screenshot_format,
                          conf.get("screenshot_format", "PNG") or "PNG")
        self._select_data(self.meter_style,
                          conf.get("overlay_meter") or "spectrum")
        # The combo only fires on a *change*: a saved "Bars" would leave every
        # preview unframed, so the selection is painted once here too.
        self._highlight_meter_preview()
        self.max_seconds.setValue(conf["max_seconds"])
        self.skip_silent.setChecked(conf["skip_silent"])
        self.silence_db.setValue(int(conf["silence_db"]))
        self.filter_hallucinations.setChecked(conf["filter_hallucinations"])
        self.keep_audio.setChecked(conf["keep_audio"])

        self._gemini_keys = conf.stored_gemini_keys()
        self._refresh_gemini_keys()
        self.transcribe_model.setCurrentText(conf["gemini_transcribe_model"])
        self._select_data(self.transcribe_engine, conf["transcribe_engine"])
        self._select_data(self.live_transcription_mode,
                          conf.get("live_transcription_mode") or "smart")
        self._select_data(self.local_stt_model,
                          conf.get("local_stt_model") or localspeech.default_model())
        self._select_data(self.local_stt_device,
                          conf.get("local_stt_device") or "auto")
        self._refresh_local_controls()
        self.cleanup_enabled.setChecked(conf["cleanup_enabled"])
        self.translate_enabled.setChecked(conf.get("translate_enabled", False))
        mode = conf.get("translate_mode", "academic")
        self.translate_mode.setCurrentIndex(1 if mode == "game" else 0)
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

    def _save(self, quiet=False):
        """Write the window to disk; True when the caller may proceed.

        Only the Save button confirms ("Ayarlar kaydedildi" + chime). The
        "start recording" path saves quietly so the take uses what is on
        screen — a failure still blocks it, loudly, through warn_box.
        """
        # Check before mutating settings: aliases such as Ctrl/Control and
        # Print/PrintScreen resolve to the same Windows binding.
        seen = {}
        for label, field, fallback in (
                ("Dictation", self.shortcut, "Ctrl+Space"),
                ("Meeting", self.meeting_shortcut, ""),
                ("Screenshot", self.screenshot_shortcut, "")):
            shortcut = field.currentText().strip() or fallback
            if not shortcut:
                continue
            binding = hotkey.parse_shortcut(shortcut)
            if binding == (0, 0):
                warn_box(self, t("Error"), t(
                    "Could not parse the shortcut: {shortcut}", shortcut=shortcut))
                return False
            if binding in seen:
                warn_box(self, t("Shortcut conflict"), t(
                    "{shortcut} is assigned to both {first} and {second}.",
                    shortcut=shortcut, first=t(seen[binding]), second=t(label)))
                return False
            seen[binding] = label
        conf = self.conf
        language_before = i18n.language()
        # Theme and header language apply on click and persist at once;
        # Save keeps them, it does not read them back from the buttons.
        conf["start_with_windows"] = self.start_with_windows.isChecked()
        conf["close_to_tray"] = self.close_to_tray.isChecked()
        conf["ui_language"] = self.ui_language.currentData() or "auto"
        conf["mic_target"] = self.mic.currentData() or ""
        conf["language"] = self.language.currentData() or "auto"
        conf["auto_paste"] = self.auto_paste.isChecked()
        conf["paste_shortcut"] = (self.paste_shortcut.currentText().strip()
                                      or "ctrl+v")
        conf["restore_clipboard"] = self.restore_clipboard.isChecked()
        conf["overlay_corner"] = self.corner.currentData() or "bottom-left"
        conf["screenshot_shortcut"] = self.screenshot_shortcut.currentText().strip()
        conf["screenshot_directory"] = self.screenshot_directory.text().strip()
        conf["screenshot_format"] = self.screenshot_format.currentData() or "PNG"
        conf["overlay_meter"] = self.meter_style.currentData() or "spectrum"
        conf["max_seconds"] = self.max_seconds.value()
        conf["skip_silent"] = self.skip_silent.isChecked()
        conf["silence_db"] = float(self.silence_db.value())
        conf["filter_hallucinations"] = self.filter_hallucinations.isChecked()
        conf["keep_audio"] = self.keep_audio.isChecked()

        conf["gemini_api_key"] = ""
        conf["transcribe_engine"] = self.transcribe_engine.currentData() or "cloud"
        conf["live_transcription_mode"] = (
            self.live_transcription_mode.currentData() or "smart")
        conf["local_stt_model"] = (self.local_stt_model.currentData()
                                   or localspeech.default_model())
        conf["local_stt_device"] = (self.local_stt_device.currentData()
                                    or "auto")
        conf["gemini_transcribe_model"] = (self.transcribe_model.currentText().strip()
                                           or cfg.DEFAULTS["gemini_transcribe_model"])

        conf["cleanup_enabled"] = self.cleanup_enabled.isChecked()
        conf["translate_enabled"] = self.translate_enabled.isChecked()
        conf["translate_mode"] = self.translate_mode.currentData() or "academic"
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
            warn_box(self, t("Error"), str(exc))
            return
        previous_keys = conf.stored_gemini_keys()
        try:
            cfg.credential_store.write_all(self._gemini_keys)
        except cfg.credential_store.CredentialError as exc:
            warn_box(self, t("Error"), str(exc))
            return
        # Anahtarlık değiştiyse damgalar slotlara göre kırpılır/uzatılır.
        conf["gemini_last_used"] = conf.rotation_stamps(len(self._gemini_keys))
        try:
            conf.save()
        except OSError as exc:
            try:
                cfg.credential_store.write_all(previous_keys)
            except cfg.credential_store.CredentialError:
                pass
            warn_box(self, t("Error"), str(exc))
            return
        # A lowered limit should bite now, not on the next dictation.
        # The trim and the repaint run only when rows were actually
        # dropped, so an unchanged save touches neither disk nor list.
        history_limit = conf["history_limit"]
        if conf["history_enabled"] and history_limit:
            try:
                dropped = cfg.trim_history(history_limit)
            except OSError as exc:
                print(f"wordarc: could not trim the history ({exc})")
            else:
                if dropped:
                    self._load_history()
        self.applied.emit()
        if i18n.language() != language_before:
            # The box on the Settings tab changes the language the same way the
            # header button does: the window is rebuilt in it, so the window is
            # never left standing in one language while the tray menu and the
            # dialogs speak the other. A turn later, because a save can be only
            # the first half of a click — "start recording" saves first — and
            # this window is replaced by the rebuild.
            QTimer.singleShot(0, self.language_changed.emit)
            return True
        if not quiet:
            self._confirm_saved()
        return True

    def _confirm_saved(self):
        """Say the settings are in without taking the window over."""
        self.save_banner.show_saved(t("Settings saved"))
        sounds.play(sounds.SAVED)

    def resizeEvent(self, event):
        if hasattr(self, "brand_name_label"):
            narrow = self.width() < 800
            self.brand_name_label.setText(BRAND.name if narrow else f"{BRAND.name} v{BRAND.version}")
            self.header_lang.setMinimumWidth(70 if narrow else 96)
            self.header_theme.setMinimumWidth(70 if narrow else 96)
        super().resizeEvent(event)
        # The banner is not in the layout, so it has to be told where the
        # window's new edges are. The window is resized once before the banner
        # exists.
        banner = getattr(self, "save_banner", None)
        if banner is not None and banner.isVisible():
            banner.place()

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
        # A saved target can name a copy the list no longer shows: the
        # microphone box keeps one row per device, so the MME/DirectSound
        # copies were merged into the best one.
        if index < 0 and str(value).startswith(audio.DEVICE_TARGET_PREFIX):
            wanted = str(value)[len(audio.DEVICE_TARGET_PREFIX):].split(":", 1)[-1]
            for candidate in range(combo.count()):
                data = str(combo.itemData(candidate) or "")
                if not data.startswith(audio.DEVICE_TARGET_PREFIX):
                    continue
                listed = data[len(audio.DEVICE_TARGET_PREFIX):].split(":", 1)[-1]
                if audio.same_device_name(wanted, listed):
                    index = candidate
                    break
        combo.setCurrentIndex(index if index >= 0 else 0)

    # What the drop-down needs beside the text itself: the item padding, the
    # list's own padding, its frame and the scroll bar.
    DEVICE_POPUP_PADDING = 46

    @staticmethod
    def _device_label(label):
        """One readable line: driver-supplied names can carry line breaks."""
        return " ".join(str(label).split())

    @classmethod
    def _widen_device_popup(cls, combo):
        """Let the drop-down show device names whole instead of clipped.

        The list opens as wide as its longest entry, so no name needs the
        ellipsis a fixed-width list ends them all with. It stays capped to the
        screen: a Bluetooth hands-free entry can run twice the window wide,
        and a list that runs off the screen helps nobody.
        """
        metrics = QFontMetrics(combo.font())
        widest = max((metrics.horizontalAdvance(combo.itemText(index))
                      for index in range(combo.count())), default=0)
        if not widest:
            return
        screen = combo.screen() or QGuiApplication.primaryScreen()
        limit = 900
        if screen is not None:
            limit = max(320, screen.availableGeometry().width() - 80)
        combo.view().setMinimumWidth(
            min(widest + cls.DEVICE_POPUP_PADDING, limit))

    @classmethod
    def _fill_device_combo(cls, combo, items, default_label, selected):
        """Refill a device box with the names as they are, not cut short.

        Items are (target, label) or (target, label, connection). The third
        field, when there is one, is what the card row draws under the name —
        without it a device list says the same thing twice and takes twice the
        room.
        """
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(default_label, "")
        subs = [(0, "")]
        for item in items:
            target, label = item[0], item[1]
            connection = item[2] if len(item) > 2 else ""
            display = cls._device_label(label)
            combo.addItem(display, target)
            combo.setItemData(combo.count() - 1, display,
                              Qt.ItemDataRole.ToolTipRole)
            subs.append((combo.count() - 1,
                         t(CONNECTION_LABELS[connection]) if connection
                         else ""))
        combo._cards_if_long(subs)
        cls._select_data(combo, selected)
        cls._widen_device_popup(combo)
        combo.blockSignals(False)

    def _refresh_audio_devices(self, *_):
        """Rescan hot-plugged devices while preserving current selections."""
        # PortAudio only reports what it saw when it started; restarting the
        # library is what makes a device connected later show up here. The
        # rescan can also fail — a device pulled mid-query, a library left in
        # a bad state — and this runs while the window is being built, so a
        # failure leaves the boxes exactly as they are instead of taking the
        # window down with it.
        try:
            audio.refresh_devices()
            sources = audio.describe_sources()
            monitors = audio.describe_monitors()
        except Exception as exc:
            logging.getLogger("wordarc.ui").warning(
                "audio device rescan failed: %s", exc)
            sources = monitors = None
        for combo, default_label, rows in (
                (getattr(self, "mic", None), t("Default microphone"), sources),
                (getattr(self, "meeting_mic", None), t("Same as dictation"), sources),
                (getattr(self, "meeting_system", None), t("Current output"), monitors)):
            if combo is None:
                continue
            if rows is None:
                # Nothing could be read this time: a box that has not been
                # filled yet still says what it means rather than standing
                # empty, and a filled one keeps the selection it has.
                if not combo.count():
                    combo.addItem(default_label, "")
                continue
            selected = combo.currentData() if combo.count() else ""
            self._fill_device_combo(combo, rows, default_label, selected)

    # ---- api helpers -----------------------------------------------------

    @staticmethod
    def _masked_key(key):
        suffix = key[-4:] if len(key) >= 4 else "••••"
        return f"••••••••{suffix}"

    def showEvent(self, event):
        super().showEvent(event)
        # İşlemler pencereden bağımsız koşar; liste her açılışta kayıtlı
        # damgaları yeniden okur, açık kaldığı sürece de tikle tazelenir.
        if getattr(self, "_gemini_keys", None) is not None:
            self._refresh_gemini_keys()
        self._usage_timer.start(5000)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._usage_timer.stop()

    def _on_usage_tick(self):
        if getattr(self, "_gemini_keys", None) is not None:
            self._refresh_gemini_keys()

    @staticmethod
    def _format_last_used(stamp):
        try:
            when = datetime.fromisoformat(stamp)
        except (TypeError, ValueError):
            return stamp
        return when.strftime("%d.%m.%Y %H:%M:%S")

    def _refresh_gemini_keys(self, selected=None):
        if selected is None:
            selected = self.gemini_keys_list.currentRow()
        self.gemini_keys_list.clear()
        stamps = self.conf.rotation_stamps(len(self._gemini_keys))
        for index, key in enumerate(self._gemini_keys, start=1):
            stamp = stamps[index - 1]
            if stamp:
                usage = t("last used: {when}",
                          when=self._format_last_used(stamp))
            else:
                usage = t("not used yet")
            self.gemini_keys_list.addItem(
                f"API {index} — {self._masked_key(key)} — {usage}")
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

    def _key_dialog(self, title, value=""):
        """The password prompt for one API key, in the interface language."""
        dialog = QInputDialog(self)
        dialog.setWindowTitle(t(title))
        dialog.setLabelText(t("Gemini API key"))
        dialog.setTextEchoMode(QLineEdit.EchoMode.Password)
        dialog.setTextValue(value)
        dialog.setOkButtonText(t("OK"))
        dialog.setCancelButtonText(t("Cancel"))
        return dialog

    def _prompt_gemini_key(self, title, value=""):
        dialog = self._key_dialog(title, value)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return ""
        return dialog.textValue().strip()

    def _add_gemini_key(self):
        if len(self._gemini_keys) >= 5:
            return
        key = self._prompt_gemini_key("Add API")
        if not key:
            return
        if key in self._gemini_keys:
            warn_box(self, t("Error"), t("This API key is already listed."))
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
            warn_box(self, t("Error"), t("This API key is already listed."))
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

    def _deliver(self, name, *args):
        """Hand a worker thread's result back to this window, if it is still here.

        A language change frees the old window a turn later, and a thread it
        started may still be fetching or downloading: reaching for the signal on
        a deleted window raises, the thread dies with a traceback nobody reads,
        and the download it was running is cut off with it.
        """
        try:
            getattr(self, name).emit(*args)
        except RuntimeError:
            pass

    def _load_transcribe_models(self):
        self.refresh_transcribe_models.setEnabled(False)
        self.transcribe_status.setText(t("Fetching model list…"))
        keys = self._gemini_runtime_keys()

        def work():
            try:
                models = api.GeminiClient(keys).list_models()
                self._deliver("_transcribe_models_loaded", models, "")
            except api.ApiError as exc:
                self._deliver("_transcribe_models_loaded", [], str(exc))

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
                self._deliver("_models_loaded", api.GeminiClient(keys).list_models(), "")
            except api.ApiError as exc:
                self._deliver("_models_loaded", [], str(exc))

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
                self._deliver(
                    "_test_done", True,
                    t("Connection works. {count} models visible.", count=len(models)))
            except api.ApiError as exc:
                self._deliver("_test_done", False, str(exc))

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
        self._download_stop.set()
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
            info_box(self, t("Minutes"),
                                    t("This one is being written up right now."))
            return
        if not self._confirm(
            t("Delete this meeting, its minutes and its recording?"), t("Minutes")
        ):
            return
        try:
            cfg.delete_meetings([row["base"]])
        except OSError as exc:
            warn_box(self, t("Minutes"), t("Failed: {error}", error=exc))
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
        # Use custom confirm box to ensure Turkish button texts.
        return confirm_box(self, title or t("History"), question)

    def _rewrite_history(self, action):
        try:
            action()
        except OSError as exc:
            warn_box(self, t("History"), t("Failed: {error}", error=exc))
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
