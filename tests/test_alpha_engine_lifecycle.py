"""Verification tests for the experiment lifecycle state machine (Alpha
Engine R2)."""

import json
import tempfile
import unittest
from pathlib import Path

from alpha_engine.registry import (
    ALLOWED_TRANSITIONS,
    GOVERNANCE_DECISION_STATES,
    TERMINAL_STATES,
    ExperimentNotFoundError,
    ExperimentRegistry,
    FileRegistryStorage,
    GovernanceRequiredError,
    IllegalLifecycleTransitionError,
    LifecycleGuardError,
    LifecycleState,
    MalformedRegistryLogError,
    RegistryStorage,
    is_legal_transition,
)


class _InMemoryStorage(RegistryStorage):
    def __init__(self):
        self._entries = []

    def append(self, entry):
        self._entries.append(dict(entry))

    def read_all(self):
        return list(self._entries)


def _registry_with(eid="exp-1", sealed=False, evidence=False):
    registry = ExperimentRegistry(_InMemoryStorage())
    registry.create(eid, {"a": 1})
    if sealed:
        registry.seal(eid)
    if evidence:
        registry.attach_evidence(eid, {"stage": {"x": 1}}, "fp-1")
    return registry


class TestTransitionTable(unittest.TestCase):
    def test_every_state_has_a_transition_entry(self):
        self.assertEqual(set(ALLOWED_TRANSITIONS.keys()), set(LifecycleState))

    def test_terminal_states_have_no_outgoing_edges(self):
        for state in TERMINAL_STATES:
            self.assertEqual(ALLOWED_TRANSITIONS[state], frozenset(), state)

    def test_governance_states_only_reachable_from_in_review(self):
        for target in GOVERNANCE_DECISION_STATES:
            sources = {s for s in LifecycleState if is_legal_transition(s, target)}
            self.assertEqual(sources, {LifecycleState.IN_REVIEW}, target)

    def test_no_edge_reenters_proposed(self):
        for state in LifecycleState:
            self.assertFalse(is_legal_transition(state, LifecycleState.PROPOSED), state)


class TestTransitions(unittest.TestCase):
    def test_initial_state_is_proposed(self):
        registry = _registry_with()
        self.assertEqual(registry.get("exp-1").lifecycle_state, LifecycleState.PROPOSED)

    def test_proposed_to_validating(self):
        registry = _registry_with()
        record = registry.transition("exp-1", LifecycleState.VALIDATING)
        self.assertEqual(record.lifecycle_state, LifecycleState.VALIDATING)

    def test_illegal_edge_raises(self):
        registry = _registry_with()
        with self.assertRaises(IllegalLifecycleTransitionError):
            registry.transition("exp-1", LifecycleState.RETIRED)

    def test_unknown_experiment_raises(self):
        registry = _registry_with()
        with self.assertRaises(ExperimentNotFoundError):
            registry.transition("ghost", LifecycleState.VALIDATING)

    def test_non_state_argument_raises(self):
        registry = _registry_with()
        with self.assertRaises(ValueError):
            registry.transition("exp-1", "validating")

    def test_governance_states_refused_via_direct_transition(self):
        registry = _registry_with(sealed=True, evidence=True)
        registry.transition("exp-1", LifecycleState.VALIDATING)
        registry.transition("exp-1", LifecycleState.EVIDENCE_SEALED)
        registry.transition("exp-1", LifecycleState.IN_REVIEW)
        for target in GOVERNANCE_DECISION_STATES:
            with self.assertRaises(GovernanceRequiredError):
                registry.transition("exp-1", target)

    def test_evidence_sealed_requires_evidence(self):
        registry = _registry_with(sealed=True, evidence=False)
        registry.transition("exp-1", LifecycleState.VALIDATING)
        with self.assertRaises(LifecycleGuardError):
            registry.transition("exp-1", LifecycleState.EVIDENCE_SEALED)

    def test_evidence_sealed_with_evidence_succeeds(self):
        registry = _registry_with(sealed=True, evidence=True)
        registry.transition("exp-1", LifecycleState.VALIDATING)
        record = registry.transition("exp-1", LifecycleState.EVIDENCE_SEALED)
        self.assertEqual(record.lifecycle_state, LifecycleState.EVIDENCE_SEALED)

    def test_withdraw_from_proposed_is_terminal(self):
        registry = _registry_with()
        registry.transition("exp-1", LifecycleState.WITHDRAWN)
        with self.assertRaises(IllegalLifecycleTransitionError):
            registry.transition("exp-1", LifecycleState.VALIDATING)

    def test_list_experiments_filters_by_state(self):
        registry = _registry_with("exp-1")
        registry.create("exp-2", {"b": 2})
        registry.transition("exp-2", LifecycleState.VALIDATING)
        proposed = registry.list_experiments(state=LifecycleState.PROPOSED)
        validating = registry.list_experiments(state=LifecycleState.VALIDATING)
        self.assertEqual([r.experiment_id for r in proposed], ["exp-1"])
        self.assertEqual([r.experiment_id for r in validating], ["exp-2"])


class TestReplayDurability(unittest.TestCase):
    def test_state_survives_restart_and_guards_still_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.jsonl"
            first = ExperimentRegistry(FileRegistryStorage(path))
            first.create("exp-1", {"a": 1})
            first.seal("exp-1")
            first.attach_evidence("exp-1", {"stage": {"x": 1}}, "fp-1")
            first.transition("exp-1", LifecycleState.VALIDATING)
            first.transition("exp-1", LifecycleState.EVIDENCE_SEALED)

            second = ExperimentRegistry(FileRegistryStorage(path))
            self.assertEqual(second.get("exp-1").lifecycle_state, LifecycleState.EVIDENCE_SEALED)
            record = second.transition("exp-1", LifecycleState.IN_REVIEW)
            self.assertEqual(record.lifecycle_state, LifecycleState.IN_REVIEW)


class TestCorruptLogHandling(unittest.TestCase):
    def _write_raw(self, path, entries):
        with open(path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    def _created(self, eid="exp-1"):
        return {"type": "experiment_created", "experiment_id": eid, "fingerprint": "f",
                "parent_id": None, "specification": {"a": 1}, "created_at_utc": "t"}

    def _load(self, path):
        return ExperimentRegistry(FileRegistryStorage(path))

    def test_state_entry_for_unknown_experiment_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.jsonl"
            self._write_raw(path, [
                {"type": "state_changed", "experiment_id": "ghost",
                 "from_state": "proposed", "to_state": "validating", "changed_at_utc": "t"},
            ])
            with self.assertRaises(MalformedRegistryLogError):
                self._load(path)

    def test_state_entry_with_wrong_from_state_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.jsonl"
            self._write_raw(path, [
                self._created(),
                {"type": "state_changed", "experiment_id": "exp-1",
                 "from_state": "validating", "to_state": "evidence_sealed", "changed_at_utc": "t"},
            ])
            with self.assertRaises(MalformedRegistryLogError):
                self._load(path)

    def test_state_entry_with_illegal_edge_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.jsonl"
            self._write_raw(path, [
                self._created(),
                {"type": "state_changed", "experiment_id": "exp-1",
                 "from_state": "proposed", "to_state": "retired", "changed_at_utc": "t"},
            ])
            with self.assertRaises(MalformedRegistryLogError):
                self._load(path)

    def test_state_entry_with_unrecognized_state_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.jsonl"
            self._write_raw(path, [
                self._created(),
                {"type": "state_changed", "experiment_id": "exp-1",
                 "from_state": "proposed", "to_state": "ascended", "changed_at_utc": "t"},
            ])
            with self.assertRaises(MalformedRegistryLogError):
                self._load(path)

    def test_governance_state_entry_without_decision_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.jsonl"
            self._write_raw(path, [
                self._created(),
                {"type": "experiment_sealed", "experiment_id": "exp-1", "sealed_at_utc": "t"},
                {"type": "evidence_attached", "experiment_id": "exp-1",
                 "evidence": {"x": 1}, "evidence_fingerprint": "fp"},
                {"type": "state_changed", "experiment_id": "exp-1",
                 "from_state": "proposed", "to_state": "validating", "changed_at_utc": "t"},
                {"type": "state_changed", "experiment_id": "exp-1",
                 "from_state": "validating", "to_state": "evidence_sealed", "changed_at_utc": "t"},
                {"type": "state_changed", "experiment_id": "exp-1",
                 "from_state": "evidence_sealed", "to_state": "in_review", "changed_at_utc": "t"},
                {"type": "state_changed", "experiment_id": "exp-1",
                 "from_state": "in_review", "to_state": "approved", "changed_at_utc": "t"},
            ])
            with self.assertRaises(MalformedRegistryLogError):
                self._load(path)


if __name__ == "__main__":
    unittest.main()
