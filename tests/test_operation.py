import unittest

from operation import OperationController, State


class TestOperationController(unittest.TestCase):
    def test_normal_lifecycle(self):
        controller = OperationController()
        operation_id = controller.begin()
        controller.transition(State.PROCESSING, operation_id)
        controller.transition(State.COMPLETED, operation_id)
        controller.transition(State.IDLE, operation_id)
        self.assertEqual(controller.state, State.IDLE)

    def test_stale_operation_is_ignored(self):
        controller = OperationController()
        controller.begin()
        self.assertFalse(controller.transition(State.PROCESSING, "stale"))
        self.assertEqual(controller.state, State.RECORDING)

    def test_invalid_transition_fails(self):
        with self.assertRaises(ValueError):
            OperationController().transition(State.COMPLETED)
