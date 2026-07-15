import os
import tempfile
import unittest
from pathlib import Path

from event_store import EventStore
from execution_state_machine import (
    ExecutionStateMachine,
    IllegalTransitionError,
    ReplayIntegrityError,
    State,
    Trigger,
    UnknownTriggerError,
)
from execution_state_machine.transitions import LEGAL_TRIGGERS_BY_STATE, TRANSITION_TABLE


def _tmp_path() -> Path:
    fd, name = tempfile.mkstemp(suffix=".log")
    os.close(fd)
    os.unlink(name)
    return Path(name)


def _drive_to_ready(sm: ExecutionStateMachine, prefix: str = "r") -> None:
    sm.transition(Trigger.STARTED, f"{prefix}-start")
    sm.transition(Trigger.RECONCILED, f"{prefix}-reconciled")


def _drive_to_position_open(sm: ExecutionStateMachine, prefix: str = "p") -> None:
    _drive_to_ready(sm, prefix)
    sm.transition(Trigger.SIGNAL_RECEIVED, f"{prefix}-signal")
    sm.transition(Trigger.ORDER_PLACED, f"{prefix}-order")
    sm.transition(Trigger.FULLY_FILLED, f"{prefix}-fill")


class TableIntegrity(unittest.TestCase):
    def test_all_required_states_present(self):
        required = {
            "INITIALIZING", "RECONCILING", "READY", "SIGNAL_PENDING", "ORDER_PENDING",
            "PARTIALLY_FILLED", "POSITION_OPEN", "POSITION_CLOSING", "FLAT",
            "SOFT_KILL", "HARD_KILL", "EMERGENCY_KILL", "STOPPED",
        }
        self.assertEqual({s.value for s in State}, required)

    def test_stopped_is_terminal(self):
        self.assertEqual(LEGAL_TRIGGERS_BY_STATE[State.STOPPED], frozenset())

    def test_every_state_other_than_stopped_has_an_emergency_exit_or_is_emergency_kill(self):
        for state in State:
            if state in (State.STOPPED, State.EMERGENCY_KILL):
                continue
            self.assertIn(
                Trigger.EMERGENCY_KILL_TRIGGERED, LEGAL_TRIGGERS_BY_STATE[state],
                f"{state} has no emergency-kill escape",
            )

    def test_emergency_kill_only_exit_is_shutdown(self):
        self.assertEqual(LEGAL_TRIGGERS_BY_STATE[State.EMERGENCY_KILL], frozenset({Trigger.SHUTDOWN}))

    def test_shutdown_not_legal_from_in_flight_states(self):
        in_flight = {
            State.SIGNAL_PENDING, State.ORDER_PENDING, State.PARTIALLY_FILLED,
            State.POSITION_OPEN, State.POSITION_CLOSING,
        }
        for state in in_flight:
            self.assertNotIn(Trigger.SHUTDOWN, LEGAL_TRIGGERS_BY_STATE[state])

    def test_recovery_from_kill_states_routes_through_reconciling(self):
        self.assertEqual(TRANSITION_TABLE[(State.SOFT_KILL, Trigger.RESUME)], State.RECONCILING)
        self.assertEqual(TRANSITION_TABLE[(State.HARD_KILL, Trigger.RESUME)], State.RECONCILING)
        self.assertNotIn((State.SOFT_KILL, Trigger.READY_FOR_NEXT), TRANSITION_TABLE)


class LegalTransitions(unittest.TestCase):
    def test_full_lifecycle_happy_path(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            self.assertEqual(sm.current_state, State.INITIALIZING)

            sm.transition(Trigger.STARTED, "r1")
            self.assertEqual(sm.current_state, State.RECONCILING)

            sm.transition(Trigger.RECONCILED, "r2")
            self.assertEqual(sm.current_state, State.READY)

            sm.transition(Trigger.SIGNAL_RECEIVED, "r3")
            self.assertEqual(sm.current_state, State.SIGNAL_PENDING)

            sm.transition(Trigger.ORDER_PLACED, "r4")
            self.assertEqual(sm.current_state, State.ORDER_PENDING)

            sm.transition(Trigger.PARTIAL_FILL_RECEIVED, "r5")
            self.assertEqual(sm.current_state, State.PARTIALLY_FILLED)

            sm.transition(Trigger.REMAINDER_FILLED, "r6")
            self.assertEqual(sm.current_state, State.POSITION_OPEN)

            sm.transition(Trigger.STOP_ADJUSTED, "r7")
            self.assertEqual(sm.current_state, State.POSITION_OPEN)

            sm.transition(Trigger.CLOSE_INITIATED, "r8")
            self.assertEqual(sm.current_state, State.POSITION_CLOSING)

            sm.transition(Trigger.CLOSE_COMPLETED, "r9")
            self.assertEqual(sm.current_state, State.FLAT)

            sm.transition(Trigger.READY_FOR_NEXT, "r10")
            self.assertEqual(sm.current_state, State.READY)
        finally:
            store.close()

    def test_self_loop_transitions_still_emit_events(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            _drive_to_ready(sm)
            sm.transition(Trigger.SIGNAL_RECEIVED, "s1")
            sm.transition(Trigger.ORDER_PLACED, "o1")
            sm.transition(Trigger.PARTIAL_FILL_RECEIVED, "f1")
            self.assertEqual(sm.current_state, State.PARTIALLY_FILLED)
            before = store.event_count
            sm.transition(Trigger.PARTIAL_FILL_RECEIVED, "f2")  # self-loop
            self.assertEqual(sm.current_state, State.PARTIALLY_FILLED)
            self.assertEqual(store.event_count, before + 1)  # a new event WAS recorded
        finally:
            store.close()

    def test_transition_result_fields(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            result = sm.transition(Trigger.STARTED, "req-1", context={"note": "boot"})
            self.assertEqual(result.trigger, Trigger.STARTED)
            self.assertEqual(result.from_state, State.INITIALIZING)
            self.assertEqual(result.to_state, State.RECONCILING)
            self.assertEqual(result.request_id, "req-1")
            self.assertEqual(result.context["note"], "boot")
            self.assertFalse(result.replayed)
            self.assertIsInstance(result.event_id, int)
            self.assertTrue(result.timestamp_utc)
        finally:
            store.close()

    def test_legal_triggers_introspection(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            self.assertEqual(sm.legal_triggers(), LEGAL_TRIGGERS_BY_STATE[State.INITIALIZING])
        finally:
            store.close()


class IllegalTransitions(unittest.TestCase):
    def test_illegal_transition_rejected_and_state_unchanged(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            with self.assertRaises(IllegalTransitionError):
                sm.transition(Trigger.SIGNAL_RECEIVED, "bad-1")  # not legal from INITIALIZING
            self.assertEqual(sm.current_state, State.INITIALIZING)
            self.assertEqual(store.event_count, 0)  # nothing recorded
        finally:
            store.close()

    def test_illegal_transition_from_terminal_state(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            sm.transition(Trigger.SHUTDOWN, "shutdown-1")
            self.assertEqual(sm.current_state, State.STOPPED)
            with self.assertRaises(IllegalTransitionError):
                sm.transition(Trigger.STARTED, "after-stop")
        finally:
            store.close()

    def test_cannot_shutdown_mid_order(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            _drive_to_ready(sm)
            sm.transition(Trigger.SIGNAL_RECEIVED, "s1")
            sm.transition(Trigger.ORDER_PLACED, "o1")
            with self.assertRaises(IllegalTransitionError):
                sm.transition(Trigger.SHUTDOWN, "sneaky-shutdown")
            self.assertEqual(sm.current_state, State.ORDER_PENDING)
        finally:
            store.close()

    def test_rejects_non_trigger_type(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            with self.assertRaises(UnknownTriggerError):
                sm.transition("STARTED", "bad-type")
        finally:
            store.close()

    def test_rejects_empty_request_id(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            with self.assertRaises(ValueError):
                sm.transition(Trigger.STARTED, "")
        finally:
            store.close()

    def test_rejects_non_dict_context(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            with self.assertRaises(TypeError):
                sm.transition(Trigger.STARTED, "req", context="not-a-dict")
        finally:
            store.close()


class DuplicateRequests(unittest.TestCase):
    def test_duplicate_request_id_is_idempotent_no_op(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            r1 = sm.transition(Trigger.STARTED, "same-id")
            before_count = store.event_count
            r2 = sm.transition(Trigger.STARTED, "same-id")
            self.assertEqual(store.event_count, before_count)  # no new event
            self.assertEqual(r1.event_id, r2.event_id)
            self.assertFalse(r1.replayed)
            self.assertTrue(r2.replayed)
        finally:
            store.close()

    def test_duplicate_request_id_returns_original_even_after_state_moved_on(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            r1 = sm.transition(Trigger.STARTED, "start-id")
            sm.transition(Trigger.RECONCILED, "reconciled-id")
            self.assertEqual(sm.current_state, State.READY)

            # Retrying "start-id" now, from READY, would be illegal if
            # re-validated -- idempotency must return the ORIGINAL result
            # instead of raising or re-evaluating against current state.
            r1_again = sm.transition(Trigger.STARTED, "start-id")
            self.assertEqual(r1_again.event_id, r1.event_id)
            self.assertEqual(r1_again.to_state, State.RECONCILING)
            self.assertTrue(r1_again.replayed)
            self.assertEqual(sm.current_state, State.READY)  # unaffected
        finally:
            store.close()

    def test_request_ids_namespaced_per_machine_id(self):
        path = _tmp_path()
        store = EventStore(path)
        try:
            sm_a = ExecutionStateMachine(store, machine_id="BTC")
            sm_b = ExecutionStateMachine(store, machine_id="ETH")
            ra = sm_a.transition(Trigger.STARTED, "shared-id")
            rb = sm_b.transition(Trigger.STARTED, "shared-id")
            self.assertNotEqual(ra.event_id, rb.event_id)  # independent, no collision
            self.assertEqual(sm_a.current_state, State.RECONCILING)
            self.assertEqual(sm_b.current_state, State.RECONCILING)
        finally:
            store.close()


class ReplayAndRecovery(unittest.TestCase):
    def test_replay_reconstructs_identical_state_after_reopen(self):
        path = _tmp_path()
        store = EventStore(path)
        sm = ExecutionStateMachine(store)
        _drive_to_position_open(sm)
        sm.transition(Trigger.CLOSE_INITIATED, "close-1")
        expected_state = sm.current_state
        store.close()

        store2 = EventStore(path)
        try:
            sm2 = ExecutionStateMachine(store2)
            self.assertEqual(sm2.current_state, expected_state)
            self.assertEqual(sm2.current_state, State.POSITION_CLOSING)
        finally:
            store2.close()

    def test_replay_is_deterministic_across_multiple_reopens(self):
        path = _tmp_path()
        store = EventStore(path)
        sm = ExecutionStateMachine(store)
        _drive_to_position_open(sm)
        store.close()

        states_seen = []
        for _ in range(3):
            s = EventStore(path)
            m = ExecutionStateMachine(s)
            states_seen.append(m.current_state)
            s.close()
        self.assertEqual(len(set(states_seen)), 1)
        self.assertEqual(states_seen[0], State.POSITION_OPEN)

    def test_crash_mid_sequence_recovers_to_last_durable_transition(self):
        path = _tmp_path()
        store = EventStore(path)
        sm = ExecutionStateMachine(store)
        _drive_to_ready(sm)
        sm.transition(Trigger.SIGNAL_RECEIVED, "s1")
        sm.transition(Trigger.ORDER_PLACED, "o1")
        # Simulate a crash right here -- no clean close, no further writes.
        store.close()  # closing releases the OS lock but the file itself
                        # already reflects exactly what was durably fsynced

        store2 = EventStore(path)
        try:
            sm2 = ExecutionStateMachine(store2)
            self.assertEqual(sm2.current_state, State.ORDER_PENDING)
            self.assertFalse(store2.recovery_report.tail_truncated)
        finally:
            store2.close()

    def test_recovered_machine_continues_correctly(self):
        path = _tmp_path()
        store = EventStore(path)
        sm = ExecutionStateMachine(store)
        _drive_to_ready(sm)
        sm.transition(Trigger.SIGNAL_RECEIVED, "s1")
        store.close()

        store2 = EventStore(path)
        try:
            sm2 = ExecutionStateMachine(store2)
            self.assertEqual(sm2.current_state, State.SIGNAL_PENDING)
            sm2.transition(Trigger.ORDER_PLACED, "o1")
            self.assertEqual(sm2.current_state, State.ORDER_PENDING)
        finally:
            store2.close()

    def test_replay_skips_foreign_events_from_other_machine_ids(self):
        path = _tmp_path()
        store = EventStore(path)
        sm_a = ExecutionStateMachine(store, machine_id="A")
        sm_b = ExecutionStateMachine(store, machine_id="B")
        sm_a.transition(Trigger.STARTED, "a1")
        sm_b.transition(Trigger.STARTED, "b1")
        sm_b.transition(Trigger.RECONCILED, "b2")
        store.close()

        store2 = EventStore(path)
        try:
            sm_a2 = ExecutionStateMachine(store2, machine_id="A")
            sm_b2 = ExecutionStateMachine(store2, machine_id="B")
            self.assertEqual(sm_a2.current_state, State.RECONCILING)
            self.assertEqual(sm_b2.current_state, State.READY)
        finally:
            store2.close()

    def test_replay_detects_tampered_history(self):
        path = _tmp_path()
        store = EventStore(path)
        sm = ExecutionStateMachine(store)
        sm.transition(Trigger.STARTED, "s1")
        # Forge an event claiming an illegal transition, bypassing the FSM
        # entirely (directly via the Event Store, as corruption/tampering
        # would look on replay).
        from event_store import EventType
        store.append(
            EventType.POSITION_UPDATED,
            {
                "source": "execution_state_machine",
                "machine_id": "default",
                "trigger": "SIGNAL_RECEIVED",
                "from_state": "RECONCILING",  # SIGNAL_RECEIVED is not legal from RECONCILING
                "to_state": "SIGNAL_PENDING",
                "context": {},
            },
        )
        store.close()

        store2 = EventStore(path)
        try:
            with self.assertRaises(ReplayIntegrityError):
                ExecutionStateMachine(store2)
        finally:
            store2.close()

    def test_replay_detects_unknown_trigger_value(self):
        path = _tmp_path()
        store = EventStore(path)
        from event_store import EventType
        store.append(
            EventType.SYSTEM_STARTED,
            {
                "source": "execution_state_machine",
                "machine_id": "default",
                "trigger": "NOT_A_REAL_TRIGGER",
                "from_state": "INITIALIZING",
                "to_state": "RECONCILING",
                "context": {},
            },
        )
        store.close()

        store2 = EventStore(path)
        try:
            with self.assertRaises(ReplayIntegrityError):
                ExecutionStateMachine(store2)
        finally:
            store2.close()


class KillSwitchBehavior(unittest.TestCase):
    def test_soft_kill_reachable_from_position_open_and_recovers_through_reconciling(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            _drive_to_position_open(sm)
            sm.transition(Trigger.SOFT_KILL_TRIGGERED, "soft-1")
            self.assertEqual(sm.current_state, State.SOFT_KILL)

            sm.transition(Trigger.RESUME, "resume-1")
            self.assertEqual(sm.current_state, State.RECONCILING)  # not READY directly
        finally:
            store.close()

    def test_hard_kill_flatten_fills_stay_in_hard_kill_until_resume(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            _drive_to_position_open(sm)
            sm.transition(Trigger.HARD_KILL_TRIGGERED, "hard-1")
            self.assertEqual(sm.current_state, State.HARD_KILL)

            sm.transition(Trigger.FLATTEN_FILL_RECEIVED, "flatten-1")
            self.assertEqual(sm.current_state, State.HARD_KILL)  # still, self-loop
            sm.transition(Trigger.FLATTEN_FILL_RECEIVED, "flatten-2")
            self.assertEqual(sm.current_state, State.HARD_KILL)

            sm.transition(Trigger.RESUME, "resume-1")
            self.assertEqual(sm.current_state, State.RECONCILING)
        finally:
            store.close()

    def test_emergency_kill_from_deep_in_lifecycle_is_one_way(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            _drive_to_position_open(sm)
            sm.transition(Trigger.EMERGENCY_KILL_TRIGGERED, "emergency-1")
            self.assertEqual(sm.current_state, State.EMERGENCY_KILL)

            with self.assertRaises(IllegalTransitionError):
                sm.transition(Trigger.RESUME, "try-resume")
            with self.assertRaises(IllegalTransitionError):
                sm.transition(Trigger.RECONCILED, "try-reconciled")

            sm.transition(Trigger.SHUTDOWN, "shutdown-1")
            self.assertEqual(sm.current_state, State.STOPPED)
        finally:
            store.close()

    def test_kill_switch_escalation_soft_to_hard_to_emergency(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            _drive_to_ready(sm)
            sm.transition(Trigger.SOFT_KILL_TRIGGERED, "soft-1")
            sm.transition(Trigger.HARD_KILL_TRIGGERED, "hard-1")  # escalate
            self.assertEqual(sm.current_state, State.HARD_KILL)
            sm.transition(Trigger.EMERGENCY_KILL_TRIGGERED, "emergency-1")  # escalate further
            self.assertEqual(sm.current_state, State.EMERGENCY_KILL)
        finally:
            store.close()

    def test_reconciliation_failure_routes_to_soft_kill(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            sm.transition(Trigger.STARTED, "s1")
            sm.transition(Trigger.RECONCILIATION_FAILED, "recon-fail-1")
            self.assertEqual(sm.current_state, State.SOFT_KILL)
        finally:
            store.close()

    def test_kill_switch_persists_and_recovers_correctly(self):
        path = _tmp_path()
        store = EventStore(path)
        sm = ExecutionStateMachine(store)
        _drive_to_position_open(sm)
        sm.transition(Trigger.HARD_KILL_TRIGGERED, "hard-1")
        store.close()

        store2 = EventStore(path)
        try:
            sm2 = ExecutionStateMachine(store2)
            self.assertEqual(sm2.current_state, State.HARD_KILL)
        finally:
            store2.close()


    def test_no_unreachable_states_and_no_dead_ends_except_stopped(self):
        to_states = {to for (_frm, _trig), to in TRANSITION_TABLE.items()}
        unreachable = set(State) - to_states - {State.INITIALIZING}
        self.assertEqual(unreachable, set())

        dead_ends = {s for s in State if s != State.STOPPED and len(LEGAL_TRIGGERS_BY_STATE[s]) == 0}
        self.assertEqual(dead_ends, set())


class ConcurrencySafety(unittest.TestCase):
    def test_concurrent_calls_never_produce_two_events_with_the_same_from_state_illegally(self):
        import threading

        path = _tmp_path()
        store = EventStore(path)
        try:
            sm = ExecutionStateMachine(store)
            results = []
            errors = []
            barrier = threading.Barrier(8)

            def worker(i):
                barrier.wait()
                try:
                    results.append(sm.transition(Trigger.STARTED, f"race-{i}"))
                except IllegalTransitionError as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # Exactly one call could legally consume the single
            # INITIALIZING->RECONCILING edge; every other concurrent
            # caller must have been correctly rejected, not raced through.
            self.assertEqual(len(results), 1)
            self.assertEqual(len(errors), 7)
            self.assertEqual(store.event_count, 1)
            self.assertEqual(sm.current_state, State.RECONCILING)
        finally:
            store.close()

        # And the resulting log must still replay cleanly -- no corrupted
        # from_state chain left behind by the race.
        store2 = EventStore(path)
        try:
            sm2 = ExecutionStateMachine(store2)
            self.assertEqual(sm2.current_state, State.RECONCILING)
        finally:
            store2.close()

    def test_concurrent_calls_with_distinct_ids_after_reaching_a_self_loop_state(self):
        import threading

        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            _drive_to_ready(sm)
            sm.transition(Trigger.SIGNAL_RECEIVED, "s1")
            sm.transition(Trigger.ORDER_PLACED, "o1")
            sm.transition(Trigger.PARTIAL_FILL_RECEIVED, "f1")
            self.assertEqual(sm.current_state, State.PARTIALLY_FILLED)

            results = []
            barrier = threading.Barrier(5)

            def worker(i):
                barrier.wait()
                results.append(sm.transition(Trigger.PARTIAL_FILL_RECEIVED, f"fill-{i}"))

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # PARTIAL_FILL_RECEIVED is a legal self-loop, so ALL concurrent
            # calls are individually legal and must all succeed, each
            # producing its own event, with state remaining consistent.
            self.assertEqual(len(results), 5)
            self.assertEqual(sm.current_state, State.PARTIALLY_FILLED)
            self.assertEqual(store.event_count, 5 + 5)  # 5 to reach PARTIALLY_FILLED, +5 self-loops
        finally:
            store.close()


class NamespaceCollisionSafety(unittest.TestCase):
    def test_machine_id_and_request_id_boundary_cannot_be_confused(self):
        path = _tmp_path()
        store = EventStore(path)
        try:
            # "A:B" + "C" must NOT collide with "A" + "B:C" under naive
            # colon concatenation -- verify both machines can independently
            # use their own request_id space without cross-talk.
            sm1 = ExecutionStateMachine(store, machine_id="A:B")
            sm2 = ExecutionStateMachine(store, machine_id="A")

            r1 = sm1.transition(Trigger.STARTED, "C")
            r2 = sm2.transition(Trigger.STARTED, "B:C")

            self.assertNotEqual(r1.event_id, r2.event_id)
            self.assertEqual(sm1.current_state, State.RECONCILING)
            self.assertEqual(sm2.current_state, State.RECONCILING)
            self.assertEqual(store.event_count, 2)
        finally:
            store.close()

    def test_rejects_overlong_machine_id(self):
        store = EventStore(_tmp_path())
        try:
            with self.assertRaises(ValueError):
                ExecutionStateMachine(store, machine_id="x" * 200)
        finally:
            store.close()

    def test_rejects_overlong_request_id(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            with self.assertRaises(ValueError):
                sm.transition(Trigger.STARTED, "x" * 200)
        finally:
            store.close()


class PayloadInjectionSafety(unittest.TestCase):
    def test_context_cannot_override_from_state_or_to_state(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)
            result = sm.transition(
                Trigger.STARTED,
                "req-1",
                context={"from_state": "STOPPED", "to_state": "STOPPED", "trigger": "SHUTDOWN"},
            )
            # The actual transition is exactly what the real trigger and
            # current state dictate -- injected context values are inert.
            self.assertEqual(result.from_state, State.INITIALIZING)
            self.assertEqual(result.to_state, State.RECONCILING)
            self.assertEqual(sm.current_state, State.RECONCILING)
        finally:
            store.close()

    def test_context_does_not_affect_replay(self):
        path = _tmp_path()
        store = EventStore(path)
        sm = ExecutionStateMachine(store)
        sm.transition(Trigger.STARTED, "req-1", context={"to_state": "EMERGENCY_KILL"})
        store.close()

        store2 = EventStore(path)
        try:
            sm2 = ExecutionStateMachine(store2)
            self.assertEqual(sm2.current_state, State.RECONCILING)  # not EMERGENCY_KILL
        finally:
            store2.close()


class CrashTimingConsistency(unittest.TestCase):
    def test_crash_before_append_leaves_no_trace(self):
        store = EventStore(_tmp_path())
        try:
            sm = ExecutionStateMachine(store)

            import event_store.store as store_module
            real_append = store.append
            store.append = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("simulated crash before append"))
            try:
                with self.assertRaises(RuntimeError):
                    sm.transition(Trigger.STARTED, "req-1")
            finally:
                store.append = real_append

            self.assertEqual(sm.current_state, State.INITIALIZING)  # unchanged
            self.assertEqual(store.event_count, 0)

            # A genuinely new attempt afterward must work normally.
            sm.transition(Trigger.STARTED, "req-1-retry")
            self.assertEqual(sm.current_state, State.RECONCILING)
        finally:
            store.close()

    def test_crash_after_append_before_mutation_recovers_via_replay(self):
        path = _tmp_path()
        store = EventStore(path)
        sm = ExecutionStateMachine(store)

        real_append = store.append

        def append_then_die(*args, **kwargs):
            event = real_append(*args, **kwargs)
            raise RuntimeError("simulated crash: process dies right after durable append")

        store.append = append_then_die
        with self.assertRaises(RuntimeError):
            sm.transition(Trigger.STARTED, "req-1")
        store.append = real_append

        # The crashed instance's in-memory state never advanced...
        self.assertEqual(sm.current_state, State.INITIALIZING)
        store.close()

        # ...but the event WAS durably persisted, so a fresh instance
        # (simulating process restart) correctly recovers to RECONCILING.
        store2 = EventStore(path)
        try:
            sm2 = ExecutionStateMachine(store2)
            self.assertEqual(sm2.current_state, State.RECONCILING)
            self.assertEqual(store2.event_count, 1)
        finally:
            store2.close()


if __name__ == "__main__":
    unittest.main()
