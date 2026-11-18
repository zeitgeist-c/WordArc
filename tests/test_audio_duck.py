"""Dictation background ducking: device-bound lower-then-restore.

Finding-driven coverage:
- read/duck/restore are bound to the device id captured at start(); a
  default change in between must never write the new device.
- a manual edit on the original device wins even after it stops being
  the default (small changes included, tolerance boundary tested).
- a temporarily unreachable device keeps the saved level; the next
  stop() retries, so only a replugged-unchanged device gets restored.
- dictation never ducks while a meeting records; starting a meeting
  restores an active duck first without disturbing either recording.
"""

import inspect

import pytest

import audio_duck
from audio_duck import AudioDucker, clamp_reduction, ducked_level


class FakeBackend:
    """Per-device in-memory stand-in for the Windows endpoint volumes."""

    def __init__(self, devices=None, default="dev-1", quantum=None):
        self.devices = dict(devices if devices is not None
                            else {default: 0.6})
        self.default = default
        # quantum: the device rounds every written level to a multiple of
        # this (models slider quantisation on real endpoints).
        self.quantum = quantum
        self.unreachable = set()
        self.writes = []  # (device_id, level), in order
        self.fail_on_get = False
        self.fail_on_write = False
        self.no_id = False  # get() reports a level but no reliable id
        self.switch_to_after_get = None  # race injector: flip default in get()

    # -- default-addressed (legacy surface) --
    def get(self):
        if self.fail_on_get:
            raise OSError("no audio control")
        # Capture first, THEN flip: models a default change landing between
        # the read and the duck-write inside start().
        level, did = self.devices[self.default], self.default
        if self.switch_to_after_get is not None:
            self.default, self.switch_to_after_get = self.switch_to_after_get, None
        if did in self.unreachable:
            raise OSError("default device unreachable")
        if self.no_id:
            return level, ""
        return level, did

    def set(self, level):
        if self.default in self.unreachable:
            raise OSError("default device unreachable")
        self.devices[self.default] = level

    # -- id-addressed (device-bound surface) --
    def _check(self, device_id):
        if device_id in self.unreachable or device_id not in self.devices:
            raise OSError("device %r gone or unreachable" % (device_id,))

    def read(self, device_id):
        self._check(device_id)
        return self.devices[device_id]

    def write(self, device_id, level):
        if self.fail_on_write:
            raise OSError("no audio control")
        self._check(device_id)
        if self.quantum:
            level = round(level / self.quantum) * self.quantum
        self.devices[device_id] = level
        self.writes.append((device_id, level))

    # -- test scenario helpers --
    def unplug(self, device_id):
        self.unreachable.add(device_id)

    def replug(self, device_id):
        self.unreachable.discard(device_id)

    @property
    def level(self):
        return self.devices[self.default]

    @level.setter
    def level(self, value):
        self.devices[self.default] = value


def test_ducked_level_math():
    assert ducked_level(1.0, 80) == pytest.approx(0.2)
    assert ducked_level(0.5, 80) == pytest.approx(0.1)
    assert ducked_level(0.0, 80) == pytest.approx(0.0)


def test_clamp_reduction_bounds():
    assert clamp_reduction(80) == 80
    assert clamp_reduction(0) == audio_duck.MIN_REDUCTION
    assert clamp_reduction(100) == audio_duck.MAX_REDUCTION
    assert clamp_reduction("bozuk") == audio_duck.DEFAULT_REDUCTION
    assert clamp_reduction(None) == audio_duck.DEFAULT_REDUCTION


def test_start_lowers_and_stop_restores_same_device():
    backend = FakeBackend()
    ducker = AudioDucker(backend=backend)
    assert ducker.start(80) is True
    assert backend.level == pytest.approx(0.12)
    assert ducker.active
    assert ducker.stop() is True
    assert backend.level == pytest.approx(0.6)
    assert not ducker.active


def test_start_is_idempotent_and_stop_without_start_is_noop():
    backend = FakeBackend()
    ducker = AudioDucker(backend=backend)
    assert ducker.start(80) is True
    assert ducker.start(80) is True  # second start keeps the first level
    assert backend.writes == [("dev-1", pytest.approx(0.12))]
    assert ducker.stop() is True
    assert ducker.stop() is True
    assert backend.level == pytest.approx(0.6)


def test_user_adjustment_mid_recording_wins():
    backend = FakeBackend()
    ducker = AudioDucker(backend=backend)
    ducker.start(80)
    backend.level = 0.9  # user moved the slider while ducked
    assert ducker.stop() is True
    assert backend.level == pytest.approx(0.9)


def test_small_manual_nudge_is_preserved_not_restored():
    # Regression: a small deliberate move (0.12 -> 0.14) used to fall inside
    # the old tolerance band and get clobbered by the restore.
    backend = FakeBackend()
    ducker = AudioDucker(backend=backend)
    ducker.start(80)
    target = ducked_level(0.6, 80)
    backend.level = target + 0.02  # user nudged the slider up a little
    assert ducker.stop() is True
    assert backend.level == pytest.approx(target + 0.02)
    assert not ducker.active


def test_float_noise_still_restores():
    backend = FakeBackend()
    ducker = AudioDucker(backend=backend)
    ducker.start(80)
    target = ducked_level(0.6, 80)
    backend.level = target + 1e-7  # read noise, not a user edit
    assert ducker.stop() is True
    assert backend.level == pytest.approx(0.6)


def test_tolerance_boundary():
    tol = audio_duck.USER_CHANGED_TOLERANCE
    backend = FakeBackend()
    at = AudioDucker(backend=backend)
    at.start(80)
    actual = backend.level  # read-back baseline, not the computed target
    backend.level = actual + tol / 2
    assert at.stop() is True  # inside the noise band: still ours
    assert backend.level == pytest.approx(0.6)

    backend2 = FakeBackend()
    past = AudioDucker(backend=backend2)
    past.start(80)
    actual2 = backend2.level
    backend2.level = actual2 + tol * 2 + 0.001
    assert past.stop() is True  # clearly past tolerance: user's choice wins
    assert backend2.level == pytest.approx(actual2 + tol * 2 + 0.001)


def test_duck_baseline_is_the_read_back_level():
    # The slider quantises: 0.6 ducked by 80% computes 0.12 but the device
    # settles at 0.10. The baseline must be 0.10, so the quantisation gap
    # itself is never mistaken for a user edit.
    backend = FakeBackend(quantum=0.05)
    ducker = AudioDucker(backend=backend)
    assert ducker.start(80) is True
    assert backend.level == pytest.approx(0.10)
    assert ducker._ducked["dev-1"] == (pytest.approx(0.6), pytest.approx(0.10))
    assert ducker.stop() is True  # untouched quantised level restores
    assert backend.level == pytest.approx(0.6)


def test_small_nudge_on_quantised_device_is_preserved():
    # Regression: with a computed baseline of 0.12, moving 0.10 -> 0.12
    # measured as "no change" and the restore wiped the user's edit.
    backend = FakeBackend(quantum=0.05)
    ducker = AudioDucker(backend=backend)
    ducker.start(80)  # device settles at 0.10
    backend.level = 0.12  # user nudged up while ducked
    assert ducker.stop() is True
    assert backend.level == pytest.approx(0.12)
    assert not ducker.active


def test_duck_skipped_without_reliable_device_id():
    backend = FakeBackend()
    backend.no_id = True
    ducker = AudioDucker(backend=backend)
    assert ducker.start(80) is False
    assert not ducker.active
    assert backend.writes == []  # nothing lowered anywhere
    assert backend.level == pytest.approx(0.6)
    assert ducker.stop() is True


def test_unplug_dictate_on_new_output_replug_sequence():
    # Unplug mid-duck, dictate on the new output, replug: the pending
    # restore must neither block the new dictation nor clobber edits.
    backend = FakeBackend(devices={"spk": 0.5, "usb": 0.8}, default="spk")
    ducker = AudioDucker(backend=backend)
    assert ducker.start(80) is True  # dictation 1 on speakers
    assert backend.devices["spk"] == pytest.approx(0.1)

    backend.unplug("spk")
    backend.default = "usb"  # OS moves the default to the headset
    assert ducker.stop() is False  # speakers pending, nothing clobbered
    assert ducker.active

    assert ducker.start(80) is True  # dictation 2 on the headset: not blocked
    assert backend.devices["usb"] == pytest.approx(0.16)
    assert backend.devices["spk"] == pytest.approx(0.1)  # still lowered
    assert ducker.stop() is False  # headset restored, speakers still pending
    assert backend.devices["usb"] == pytest.approx(0.8)
    assert ducker.active

    backend.replug("spk")
    backend.default = "spk"  # OS moves the default back
    assert ducker.stop() is True  # pending restore retried, edits intact
    assert backend.devices["spk"] == pytest.approx(0.5)
    assert backend.devices["usb"] == pytest.approx(0.8)
    assert not ducker.active


def test_default_change_between_read_and_write_lowers_original_only():
    # The old get()-then-set() pair could lower the NEW default when the
    # default flipped in between; the write is now bound to the read id.
    backend = FakeBackend(devices={"old": 0.5, "new": 0.9}, default="old")
    backend.switch_to_after_get = "new"  # default flips mid-start()
    ducker = AudioDucker(backend=backend)
    assert ducker.start(80) is True
    assert backend.devices["old"] == pytest.approx(0.1)
    assert backend.devices["new"] == pytest.approx(0.9)  # never touched


def test_default_change_mid_recording_restores_old_never_new():
    backend = FakeBackend(devices={"old": 0.5, "new": 0.9}, default="old")
    ducker = AudioDucker(backend=backend)
    ducker.start(80)
    backend.default = "new"  # headphones plugged in mid-recording
    assert ducker.stop() is True
    assert backend.devices["old"] == pytest.approx(0.5)  # restored by id
    assert backend.devices["new"] == pytest.approx(0.9)  # never written
    assert [d for d, _ in backend.writes] == ["old", "old"]


def test_manual_edit_on_old_device_wins_after_default_switch():
    # Finding: the old code restored blindly on this path and would have
    # clobbered the user's own edit of the previous device.
    backend = FakeBackend(devices={"old": 0.5, "new": 0.9}, default="old")
    ducker = AudioDucker(backend=backend)
    ducker.start(80)
    backend.default = "new"
    backend.devices["old"] = 0.7  # user edited the old device via mixer
    assert ducker.stop() is True
    assert backend.devices["old"] == pytest.approx(0.7)
    assert backend.devices["new"] == pytest.approx(0.9)
    assert not ducker.active


def test_unreachable_device_keeps_state_and_restores_after_replug():
    backend = FakeBackend()
    ducker = AudioDucker(backend=backend)
    ducker.start(80)
    backend.unplug("dev-1")  # USB headset pulled mid-recording
    assert ducker.stop() is False  # nothing clobbered, state kept
    assert ducker.active
    assert ducker.stop() is False  # still gone: still pending, never raises
    backend.replug("dev-1")  # same id comes back with the ducked level
    assert ducker.stop() is True
    assert backend.level == pytest.approx(0.6)
    assert not ducker.active


def test_replug_with_user_changed_level_keeps_user_level():
    backend = FakeBackend()
    ducker = AudioDucker(backend=backend)
    ducker.start(80)
    backend.unplug("dev-1")
    assert ducker.stop() is False
    backend.replug("dev-1")
    backend.devices["dev-1"] = 0.8  # level moved while we could not see it
    assert ducker.stop() is True
    assert backend.level == pytest.approx(0.8)


def test_device_vanishing_between_read_and_write_aborts_start():
    backend = FakeBackend()
    backend.fail_on_write = True  # device gone right after the read
    ducker = AudioDucker(backend=backend)
    assert ducker.start(80) is False
    assert not ducker.active
    assert backend.level == pytest.approx(0.6)  # nothing lowered


def test_audio_failures_never_raise_and_leave_dictation_alone():
    backend = FakeBackend()
    backend.fail_on_get = True
    assert AudioDucker(backend=backend).start(80) is False


def test_config_defaults_enable_ducking_at_80_percent():
    import config as cfg

    assert cfg.DEFAULTS["duck_background_audio"] is True
    assert cfg.DEFAULTS["duck_reduction_percent"] == 80


# --- meeting interplay (dictation and meeting can record together) ---

def _dictation_controller(meeting_state):
    from unittest import mock

    import wordarc as wa

    controller = wa.WordArc.__new__(wa.WordArc)
    controller.conf = {"duck_background_audio": True,
                       "duck_reduction_percent": 80}
    controller.meeting_state = meeting_state
    controller._ducker = mock.Mock()
    return controller


def test_duck_start_skipped_while_meeting_records():
    import wordarc as wa

    controller = _dictation_controller(wa.M_RECORDING)
    controller._duck_start()
    controller._ducker.start.assert_not_called()


def test_duck_start_runs_while_meeting_idle():
    import wordarc as wa

    controller = _dictation_controller(wa.M_IDLE)
    controller._duck_start()
    controller._ducker.start.assert_called_once_with(80)


def test_start_meeting_restores_duck_first_and_keeps_dictation():
    from unittest import mock

    import wordarc as wa

    controller = _dictation_controller(wa.M_IDLE)
    order = []
    controller._ducker.stop.side_effect = lambda: order.append("restore")
    controller.meeting_operation = mock.Mock()
    controller.meeting_operation.state = mock.Mock()
    controller.meeting_recorder = mock.Mock()
    controller.meeting_recorder.active = True

    def _rec_start(*args):
        order.append("meeting-record-start")

    controller.meeting_recorder.start.side_effect = _rec_start
    controller.recorder = mock.Mock()  # dictation, still recording
    controller.overlay = mock.Mock()
    controller.meeting_ticker = mock.Mock()
    controller.meeting_elapsed = mock.Mock()
    controller.conf = {"duck_background_audio": True,
                       "duck_reduction_percent": 80,
                       "meeting_mic_target": "", "mic_target": "",
                       "meeting_system_target": "", "meeting_max_seconds": 60}
    controller._set_meeting_state = mock.Mock()
    with mock.patch.object(wa.meeting, "new_base", return_value="base"), \
         mock.patch.object(wa.cfg, "meeting_paths",
                           return_value=("doc", "wav")):
        controller.start_meeting()
    assert order == ["restore", "meeting-record-start"]
    controller.recorder.cancel.assert_not_called()
    controller.recorder.stop.assert_not_called()


def test_meeting_stop_paths_never_duck_and_start_restores_only():
    import wordarc

    for name in ("stop_meeting", "cancel_meeting",
                 "_on_meeting_error", "_on_meeting_finished",
                 "_on_meeting_recorded"):
        fn = getattr(wordarc.WordArc, name)
        assert "_duck_" not in inspect.getsource(fn), name
    start_source = inspect.getsource(wordarc.WordArc.start_meeting)
    assert "_duck_stop" in start_source
    assert "_duck_start" not in start_source
