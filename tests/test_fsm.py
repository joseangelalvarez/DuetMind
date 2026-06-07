import unittest

from duetmind.fsm import FsmEvent, CollisionInputs, FsmState, resolve_collision_priority, resolve_phase_transition


class TestFSM(unittest.TestCase):
    def test_freeze_to_init_transition_defined(self) -> None:
        next_state = resolve_phase_transition(FsmState.FREEZE, FsmEvent.PHASE_END)
        self.assertEqual(next_state, FsmState.INIT)

    def test_timeout_has_priority(self) -> None:
        decision = resolve_collision_priority(CollisionInputs(timeout_or_oom=True))
        self.assertIsNotNone(decision)
        self.assertEqual(decision.next_state, FsmState.CLOUD_ESC)

    def test_integrity_violation_has_priority_over_ds(self) -> None:
        decision = resolve_collision_priority(
            CollisionInputs(timeout_or_oom=False, integrity_violation=True, ds_critical=True)
        )
        self.assertIsNotNone(decision)
        self.assertEqual(decision.next_state, FsmState.ABORT)

    def test_ds_has_priority_over_loop(self) -> None:
        decision = resolve_collision_priority(CollisionInputs(ds_critical=True, loop_flag=True))
        self.assertIsNotNone(decision)
        self.assertEqual(decision.next_state, FsmState.RESET)


if __name__ == "__main__":
    unittest.main()
