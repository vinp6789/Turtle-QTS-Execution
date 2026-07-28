"""Verification tests for governance decision recording (Alpha Engine
R3)."""

import tempfile
import unittest
from pathlib import Path

from alpha_engine.governance import (
    GovernanceDecision,
    GovernanceDecisionType,
    GovernanceError,
    approved_experiments,
    record_governance_decision,
)
from alpha_engine.registry import (
    ExperimentRegistry,
    FileRegistryStorage,
    GovernanceRequiredError,
    LifecycleGuardError,
    LifecycleState,
    RegistryStorage,
)


class _InMemoryStorage(RegistryStorage):
    def __init__(self):
        self._entries = []

    def append(self, entry):
        self._entries.append(dict(entry))

    def read_all(self):
        return list(self._entries)


def _decision(experiment_id="exp-1", decision=GovernanceDecisionType.APPROVE,
              evidence_fingerprint="fp-1", proposed_by="researcher", reviewed_by="reviewer",
              rationale="criteria met", decided_at="2026-01-05T00:00:00+00:00"):
    return GovernanceDecision(
        experiment_id=experiment_id, decision=decision, evidence_fingerprint=evidence_fingerprint,
        proposed_by=proposed_by, reviewed_by=reviewed_by, rationale=rationale,
        decided_at_utc=decided_at,
    )


def _registry_in_review(storage=None, eid="exp-1", fingerprint="fp-1"):
    registry = ExperimentRegistry(storage or _InMemoryStorage())
    registry.create(eid, {"a": 1})
    registry.seal(eid)
    registry.attach_evidence(eid, {"stage": {"x": 1}}, fingerprint)
    registry.transition(eid, LifecycleState.VALIDATING)
    registry.transition(eid, LifecycleState.EVIDENCE_SEALED)
    registry.transition(eid, LifecycleState.IN_REVIEW)
    return registry


class TestGovernanceDecisionValidation(unittest.TestCase):
    def test_valid_decision_constructs(self):
        self.assertEqual(_decision().resulting_state, LifecycleState.APPROVED)

    def test_reject_and_defer_map_to_their_states(self):
        self.assertEqual(_decision(decision=GovernanceDecisionType.REJECT).resulting_state,
                         LifecycleState.REJECTED)
        self.assertEqual(_decision(decision=GovernanceDecisionType.DEFER).resulting_state,
                         LifecycleState.DEFERRED)

    def test_reviewer_must_differ_from_proposer(self):
        with self.assertRaises(GovernanceError):
            _decision(proposed_by="alice", reviewed_by="alice")

    def test_blank_fields_raise(self):
        for field in ("experiment_id", "evidence_fingerprint", "proposed_by", "reviewed_by", "rationale"):
            with self.subTest(field=field):
                with self.assertRaises(GovernanceError):
                    _decision(**{field: "  "})

    def test_non_enum_decision_raises(self):
        with self.assertRaises(GovernanceError):
            _decision(decision="approve")

    def test_to_dict_shape(self):
        d = _decision().to_dict()
        self.assertEqual(d["decision"], "approve")
        self.assertEqual(d["proposed_by"], "researcher")


class TestRecordDecision(unittest.TestCase):
    def test_approve_moves_to_approved_and_records_decision(self):
        registry = _registry_in_review()
        record = record_governance_decision(registry, _decision())
        self.assertEqual(record.lifecycle_state, LifecycleState.APPROVED)
        stored = registry.get_governance_decision("exp-1")
        self.assertEqual(stored["decision"], "approve")
        self.assertEqual(stored["reviewed_by"], "reviewer")

    def test_reject_moves_to_rejected(self):
        registry = _registry_in_review()
        record = record_governance_decision(registry, _decision(decision=GovernanceDecisionType.REJECT))
        self.assertEqual(record.lifecycle_state, LifecycleState.REJECTED)

    def test_decision_outside_in_review_raises(self):
        registry = ExperimentRegistry(_InMemoryStorage())
        registry.create("exp-1", {"a": 1})
        with self.assertRaises(GovernanceError):
            record_governance_decision(registry, _decision())

    def test_evidence_fingerprint_mismatch_raises(self):
        registry = _registry_in_review(fingerprint="fp-real")
        with self.assertRaises(GovernanceError):
            record_governance_decision(registry, _decision(evidence_fingerprint="fp-stale"))
        # Nothing recorded, state unchanged.
        self.assertIsNone(registry.get_governance_decision("exp-1"))
        self.assertEqual(registry.get("exp-1").lifecycle_state, LifecycleState.IN_REVIEW)

    def test_second_decision_raises(self):
        registry = _registry_in_review()
        record_governance_decision(registry, _decision())
        with self.assertRaises(GovernanceError):
            record_governance_decision(registry, _decision(decision=GovernanceDecisionType.REJECT))

    def test_direct_transition_into_governance_states_still_refused(self):
        registry = _registry_in_review()
        with self.assertRaises(GovernanceRequiredError):
            registry.transition("exp-1", LifecycleState.APPROVED)

    def test_registry_guard_rejects_decision_dict_outside_in_review(self):
        registry = ExperimentRegistry(_InMemoryStorage())
        registry.create("exp-1", {"a": 1})
        with self.assertRaises(LifecycleGuardError):
            registry.apply_governance_decision("exp-1", {"decision": "approve"}, LifecycleState.APPROVED)

    def test_wrong_types_raise(self):
        registry = _registry_in_review()
        with self.assertRaises(GovernanceError):
            record_governance_decision("not-a-registry", _decision())
        with self.assertRaises(GovernanceError):
            record_governance_decision(registry, "not-a-decision")


class TestReplayDurability(unittest.TestCase):
    def test_decision_and_state_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.jsonl"
            registry = _registry_in_review(storage=FileRegistryStorage(path))
            record_governance_decision(registry, _decision())

            reloaded = ExperimentRegistry(FileRegistryStorage(path))
            self.assertEqual(reloaded.get("exp-1").lifecycle_state, LifecycleState.APPROVED)
            self.assertEqual(reloaded.get_governance_decision("exp-1")["decision"], "approve")
            record = reloaded.transition("exp-1", LifecycleState.SHAKEDOWN)
            self.assertEqual(record.lifecycle_state, LifecycleState.SHAKEDOWN)


class TestApprovedExperiments(unittest.TestCase):
    def test_approved_set_includes_approved_and_live_states_only(self):
        registry = _registry_in_review(eid="exp-approved")
        record_governance_decision(registry, _decision(experiment_id="exp-approved"))

        registry.create("exp-proposed", {"b": 2})  # stays PROPOSED

        approved = approved_experiments(registry)
        self.assertEqual([r.experiment_id for r in approved], ["exp-approved"])

        registry.transition("exp-approved", LifecycleState.SHAKEDOWN)
        self.assertEqual([r.experiment_id for r in approved_experiments(registry)], ["exp-approved"])

        registry.transition("exp-approved", LifecycleState.RETIRING)
        self.assertEqual(approved_experiments(registry), ())


if __name__ == "__main__":
    unittest.main()
