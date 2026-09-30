"""Late CUDA DLL failures must not lose a recording or duplicate partial text."""
import types
from unittest import mock

import pytest
import localspeech as stt
import cuda_runtime


@pytest.fixture(autouse=True)
def isolate_engine():
    with mock.patch.object(stt, '_model', None), \
         mock.patch.object(stt, '_model_name', ''), \
         mock.patch.object(stt, '_model_device', ('', '')), \
         mock.patch.object(stt, '_cuda_failed', False), \
         mock.patch.object(stt, '_last_fallback_note', ''):
        yield


@pytest.mark.parametrize('segments', [False, True])
@pytest.mark.parametrize('late', [False, True])
def test_late_dll_error_retries_entire_recording_on_cpu(segments, late):
    gpu, cpu = mock.Mock(), mock.Mock()
    gpu.model.device = 'cuda'
    cpu.model.device = 'cpu'
    error = RuntimeError('Library cublas64_12.dll is not found or cannot be loaded')
    if late:
        def broken():
            yield types.SimpleNamespace(start=0, end=1, text='partial GPU output')
            raise error
        gpu.transcribe.return_value = (broken(), None)
    else:
        gpu.transcribe.side_effect = error
    cpu.transcribe.return_value = (iter([types.SimpleNamespace(start=0, end=2, text=' final text ')]), None)
    with mock.patch.object(stt, 'engine', side_effect=[gpu, cpu]) as engine, \
         mock.patch.object(stt, '_read_wav', return_value=[0.1]):
        result = stt.transcribe('base', 'recording.wav', 'tr', with_segments=segments,
                                where='isolated-models', device_preference='auto')
    assert result == ([(0, 2, 'final text')] if segments else 'final text')
    assert engine.call_args.args == ('base', 'isolated-models', 'cpu')
    assert stt._cuda_failed
    assert 'cublas64_12.dll' in stt.last_fallback_note()
    assert cpu.transcribe.call_args.kwargs['language'] == 'tr'


@pytest.mark.parametrize('message', ['CUDA out of memory', 'CUBLAS_STATUS_ALLOC_FAILED',
                                     'failed to load vocabulary', 'invalid model'])
def test_execution_errors_are_not_hidden(message):
    gpu = mock.Mock()
    gpu.model.device = 'cuda'
    gpu.transcribe.side_effect = RuntimeError(message)
    with mock.patch.object(stt, 'engine', return_value=gpu) as engine, \
         mock.patch.object(stt, '_read_wav', return_value=[0.1]):
        with pytest.raises(stt.LocalSpeechError, match=message):
            stt.transcribe('base', 'recording.wav')
    assert engine.call_count == 1


def test_auto_keeps_cpu_after_dll_failure():
    stt._cuda_failed = True
    cpu = object()
    with mock.patch.object(stt, 'cuda_available', return_value=True), \
         mock.patch.object(stt, '_is_installed', return_value=True), \
         mock.patch.object(stt, '_load_model', return_value=cpu) as load:
        assert stt.engine('base', 'isolated-models', 'auto') is cpu
        assert stt.engine('base', 'isolated-models', 'auto') is cpu
    assert load.call_count == 1
    assert load.call_args.args[1:] == ('cpu', 'int8')


def test_windows_load_checks_find_dependency_failures():
    with mock.patch.object(cuda_runtime.sys, 'platform', 'win32'), \
         mock.patch.object(cuda_runtime, 'prepare'), \
         mock.patch.object(cuda_runtime, '_libraries', {}), \
         mock.patch.object(cuda_runtime.ctypes, 'WinDLL', side_effect=OSError('missing dependency')):
        assert 'cublas64_12.dll' in cuda_runtime.missing_libraries()


def test_inaccessible_search_path_does_not_break_detection():
    with mock.patch.object(cuda_runtime.Path, 'is_dir', side_effect=PermissionError):
        assert cuda_runtime.search_directories() == []
