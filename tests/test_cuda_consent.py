import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest import mock
import threading

import pytest
from PyQt6.QtCore import QThread
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox
import config as cfg
import localspeech as stt
from cuda_recovery import CudaRecovery


@pytest.fixture
def conf(tmp_path):
    with mock.patch.object(cfg, 'CONFIG_FILE', tmp_path / 'config.json'), \
         mock.patch.object(cfg, 'CONFIG_DIR', tmp_path), \
         mock.patch.object(cfg.credential_store, 'read', return_value=''), \
         mock.patch.object(cfg.credential_store, 'read_all', return_value=[]):
        value = cfg.Config()
        value['transcribe_engine'] = 'local'
        value['local_stt_device'] = 'cuda'
        yield value


def test_missing_cublas_is_not_reported_as_absent_gpu():
    with mock.patch.object(stt, 'cuda_available', return_value=False), \
         mock.patch.object(stt.cuda_runtime, 'missing_libraries', return_value=['cublas64_12.dll']):
        with pytest.raises(stt.CudaUnavailable, match='cublas64_12.dll'):
            stt.get_best_device('cuda')


def test_absent_gpu_is_distinct_from_missing_libraries():
    with mock.patch.object(stt, 'cuda_available', return_value=False), \
         mock.patch.object(stt.cuda_runtime, 'missing_libraries', return_value=[]), \
         mock.patch('ctranslate2.get_cuda_device_count', return_value=0):
        with pytest.raises(stt.CudaUnavailable, match='GPU'):
            stt.get_best_device('cuda')


def test_approved_cpu_is_saved_and_same_recording_retried(conf):
    app = QApplication.instance() or QApplication([])
    recovery = CudaRecovery(conf)
    failure = stt.CudaUnavailable('cublas missing')
    with mock.patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes) as question, \
         mock.patch.object(stt, 'transcribe', side_effect=[failure, 'real words']) as transcribe:
        assert stt.transcribe_for(conf, 'same.wav', 'tr') == 'real words'
    assert transcribe.call_args.kwargs['device_preference'] == 'cpu'
    assert transcribe.call_args.args[1] == 'same.wav'
    assert conf['local_stt_device'] == 'cpu'
    assert '"local_stt_device": "cpu"' in cfg.CONFIG_FILE.read_text(encoding='utf-8')
    question.assert_called_once()


def test_denied_cpu_is_not_saved_and_cuda_init_is_not_repeated(conf):
    app = QApplication.instance() or QApplication([])
    recovery = CudaRecovery(conf)
    with mock.patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No) as question, \
         mock.patch.object(stt, 'transcribe', side_effect=stt.CudaUnavailable('driver missing')) as transcribe:
        for _ in range(2):
            with pytest.raises(stt.CudaUnavailable):
                stt.transcribe_for(conf, 'same.wav')
    assert conf['local_stt_device'] == 'cuda'
    assert not cfg.CONFIG_FILE.exists()
    question.assert_called_once()
    transcribe.assert_called_once()


def test_save_failure_rolls_back_device(conf):
    app = QApplication.instance() or QApplication([])
    recovery = CudaRecovery(conf)
    with mock.patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes), \
         mock.patch.object(QMessageBox, 'warning') as warning, \
         mock.patch.object(conf, 'save', side_effect=OSError('disk full')):
        assert not recovery.request('CUDA failed')
    assert conf['local_stt_device'] == 'cuda'
    warning.assert_called_once()


def test_explicit_cuda_late_failure_requires_consent():
    gpu = mock.Mock()
    gpu.model.device = 'cuda'
    gpu.transcribe.side_effect = RuntimeError('Library cublas64_12.dll not found')
    with mock.patch.object(stt, 'engine', return_value=gpu) as engine, \
         mock.patch.object(stt, '_read_wav', return_value=[0.1]):
        with pytest.raises(stt.CudaUnavailable, match='cublas64_12.dll'):
            stt.transcribe('base', 'same.wav', device_preference='cuda')
    engine.assert_called_once()


def test_explicit_cuda_init_failure_does_not_silently_fallback():
    with mock.patch.object(stt, 'cuda_available', return_value=True), \
         mock.patch.object(stt, '_model', None), \
         mock.patch.object(stt, '_is_installed', return_value=True), \
         mock.patch.object(stt, '_load_model', side_effect=RuntimeError('CUDA init failed')) as load:
        with pytest.raises(stt.CudaUnavailable, match='CUDA init failed'):
            stt.engine('base', 'isolated', 'cuda')
    load.assert_called_once()


def test_worker_request_is_answered_on_gui_thread(conf):
    app = QApplication.instance() or QApplication([])
    recovery = CudaRecovery(conf)
    answers = []
    def answer(*args):
        assert QThread.currentThread() == app.thread()
        return QMessageBox.StandardButton.Yes
    thread = threading.Thread(target=lambda: answers.append(recovery.request('GPU init failed')))
    with mock.patch.object(QMessageBox, 'question', side_effect=answer):
        thread.start()
        for _ in range(200):
            app.processEvents()
            if not thread.is_alive():
                break
            QTest.qWait(5)
        thread.join(timeout=1)
    assert not thread.is_alive()
    assert answers == [True]


def test_cancelled_worker_does_not_open_queued_prompt(conf):
    app = QApplication.instance() or QApplication([])
    recovery = CudaRecovery(conf)
    answers = []
    thread = threading.Thread(target=lambda: answers.append(recovery.request('failed', lambda: True)))
    with mock.patch.object(QMessageBox, 'question') as question:
        thread.start()
        thread.join(timeout=1)
        app.processEvents()
        question.assert_not_called()
    assert answers == [False]
