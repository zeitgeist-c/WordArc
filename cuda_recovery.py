"""One GUI consent prompt shared by dictation, meetings and file workers."""
from dataclasses import dataclass, field
import threading

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import QMessageBox
from i18n import t


@dataclass
class Request:
    reason: str
    ready: threading.Event = field(default_factory=threading.Event)
    accepted: bool = False
    cancelled: bool = False


class CudaRecovery(QObject):
    requested = pyqtSignal(object)
    changed = pyqtSignal()

    def __init__(self, conf, parent=None):
        super().__init__(parent)
        self.conf = conf
        self._offered = False
        self.requested.connect(self._answer)
        conf._cuda_recovery = self.request

    def request(self, reason, should_stop=None):
        request = Request(reason)
        if QThread.currentThread() == self.thread():
            self._answer(request)
        else:
            self.requested.emit(request)
        while not request.ready.wait(0.1):
            if should_stop and should_stop():
                request.cancelled = True
                return False
        return request.accepted

    def _answer(self, request):
        try:
            if request.cancelled:
                return
            if self.conf.get('local_stt_device') == 'cpu':
                request.accepted = True
                return
            if self._offered:
                return
            self._offered = True
            answer = QMessageBox.question(
                self.parent(), t('Vulkan could not start') if self.conf.get('local_stt_device') == 'vulkan' else t('CUDA could not start'),
                request.reason + '\n\n' + t('Switch to CPU, save this setting and retry this recording?'),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes or request.cancelled:
                return
            previous = self.conf.get('local_stt_device')
            self.conf['local_stt_device'] = 'cpu'
            try:
                self.conf.save()
            except OSError as exc:
                self.conf['local_stt_device'] = previous
                QMessageBox.warning(self.parent(), t('Could not save settings'), str(exc))
                return
            request.accepted = True
            self.changed.emit()
        finally:
            request.ready.set()
