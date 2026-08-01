"""Qt-independent operation state validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import secrets
import threading


class State(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_ALLOWED = {
    State.IDLE: {State.RECORDING},
    State.RECORDING: {State.PROCESSING, State.FAILED, State.CANCELLED},
    State.PROCESSING: {State.COMPLETED, State.FAILED, State.CANCELLED},
    State.COMPLETED: {State.IDLE},
    State.FAILED: {State.IDLE},
    State.CANCELLED: {State.IDLE},
}


@dataclass
class OperationController:
    state: State = State.IDLE
    operation_id: str = ""
    _lock: threading.RLock = field(default_factory=threading.RLock,
                                  init=False, repr=False)

    def transition(self, target, operation_id=None):
        target = State(target)
        with self._lock:
            if operation_id and operation_id != self.operation_id:
                return False
            if target not in _ALLOWED[self.state]:
                raise ValueError(f"invalid operation transition: {self.state} -> {target}")
            self.state = target
            if target == State.RECORDING:
                self.operation_id = secrets.token_hex(8)
            elif target == State.IDLE:
                self.operation_id = ""
            return True

    def begin(self):
        self.transition(State.RECORDING)
        return self.operation_id

    def accepts(self, operation_id):
        with self._lock:
            return bool(operation_id) and operation_id == self.operation_id
