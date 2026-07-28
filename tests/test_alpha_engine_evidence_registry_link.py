"""Verification tests for Evidence-Registry integration (Alpha Engine
R1). Synthetic fixture data throughout."""

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from exchange_adapter import Symbol

from alpha_engine.candidates import FundingRateThresholdRuleCandidate, funding_rate_candidate_specification
from alpha_engine.features import FeatureValue
from alpha_engine.registry import (
    EvidenceAlreadyAttachedError,
    ExperimentNotFoundError,
    ExperimentNotSealedError,
    ExperimentRegistry,
    FileRegistryStorage,
    InvalidSpecificationError,
    MalformedRegistryLogError,
    RegistryStorage,
)
from alpha_engine.validation import (
    ValidationError,
    ValidationSample,
    attach_evidence_package,
    evidence_package_from_validation_result,
    run_validation,
)


class _InMemoryStorage(RegistryStorage):
    def __init__(self):
        self._entries = []

    def append(self, entry):
        self._entries.append(dict(entry))

    def read_all(self):
        return list(self._entries)


def _spec(threshold="0.0005"):
    return funding_rate_candidate_specification(
        version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
        parameters={"threshold": threshold}, acceptance_criteria={"min_hit_rate": 0.5},
    )


def _package(spec):
    samples = (
        ValidationSample(
            feature_value=FeatureValue(
                feature_name="funding_rate_raw", feature_version="v1", symbol=Symbol("BTC"),
                computed_at_utc="2026-01-01T00:00:00+00:00", available=True, value=Decimal("0.0010"),
            ),
            realized_outcome=Decimal("-0.02"),
        ),
    )
    result = run_validation(FundingRateThresholdRuleCandidate.evaluate, spec, samples)
    return evidence_package_from_validation_result(spec, "single_pass", result)


class TestAttachEvidenceRawPath(unittest.TestCase):
    def setUp(self):
        self.registry = ExperimentRegistry(_InMemoryStorage())
        self.registry.create("exp-1", {"a": 1})

    def test_attach_requires_sealed_experiment(self):
        with self.assertRaises(ExperimentNotSealedError):
            self.registry.attach_evidence("exp-1", {"stage": {"x": 1}}, "fp-1")

    def test_attach_after_seal_succeeds_and_sets_fingerprint(self):
        self.registry.seal("exp-1")
        record = self.registry.attach_evidence("exp-1", {"stage": {"x": 1}}, "fp-1")
        self.assertEqual(record.evidence_fingerprint, "fp-1")
        self.assertTrue(record.has_evidence)

    def test_unknown_experiment_raises(self):
        with self.assertRaises(ExperimentNotFoundError):
            self.registry.attach_evidence("ghost", {"stage": {"x": 1}}, "fp-1")

    def test_second_attach_raises(self):
        self.registry.seal("exp-1")
        self.registry.attach_evidence("exp-1", {"stage": {"x": 1}}, "fp-1")
        with self.assertRaises(EvidenceAlreadyAttachedError):
            self.registry.attach_evidence("exp-1", {"stage": {"x": 2}}, "fp-2")

    def test_non_json_native_evidence_raises(self):
        self.registry.seal("exp-1")
        with self.assertRaises(InvalidSpecificationError):
            self.registry.attach_evidence("exp-1", {"v": Decimal("1")}, "fp-1")

    def test_empty_evidence_raises(self):
        self.registry.seal("exp-1")
        with self.assertRaises(InvalidSpecificationError):
            self.registry.attach_evidence("exp-1", {}, "fp-1")

    def test_get_evidence_none_before_attach_and_read_only_after(self):
        self.assertIsNone(self.registry.get_evidence("exp-1"))
        self.registry.seal("exp-1")
        self.registry.attach_evidence("exp-1", {"stage": {"x": 1}}, "fp-1")
        evidence = self.registry.get_evidence("exp-1")
        self.assertEqual(dict(evidence), {"stage": {"x": 1}})
        with self.assertRaises(TypeError):
            evidence["new"] = 1

    def test_get_evidence_unknown_experiment_raises(self):
        with self.assertRaises(ExperimentNotFoundError):
            self.registry.get_evidence("ghost")

    def test_records_without_evidence_report_none_fingerprint(self):
        self.assertIsNone(self.registry.get("exp-1").evidence_fingerprint)
        self.assertFalse(self.registry.get("exp-1").has_evidence)


class TestReplayDurability(unittest.TestCase):
    def test_evidence_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.jsonl"
            first = ExperimentRegistry(FileRegistryStorage(path))
            first.create("exp-1", {"a": 1})
            first.seal("exp-1")
            first.attach_evidence("exp-1", {"stage": {"x": 1}}, "fp-1")

            second = ExperimentRegistry(FileRegistryStorage(path))
            self.assertEqual(second.get("exp-1").evidence_fingerprint, "fp-1")
            self.assertEqual(dict(second.get_evidence("exp-1")), {"stage": {"x": 1}})
            with self.assertRaises(EvidenceAlreadyAttachedError):
                second.attach_evidence("exp-1", {"stage": {"x": 2}}, "fp-2")


class TestCorruptLogHandling(unittest.TestCase):
    def _write_raw(self, path, entries):
        with open(path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    def _created(self, eid="exp-1"):
        return {"type": "experiment_created", "experiment_id": eid, "fingerprint": "f",
                "parent_id": None, "specification": {"a": 1}, "created_at_utc": "t"}

    def test_evidence_for_unknown_experiment_raises_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.jsonl"
            self._write_raw(path, [
                {"type": "evidence_attached", "experiment_id": "ghost", "evidence": {"x": 1},
                 "evidence_fingerprint": "fp"},
            ])
            with self.assertRaises(MalformedRegistryLogError):
                ExperimentRegistry(FileRegistryStorage(path))

    def test_evidence_for_unsealed_experiment_raises_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.jsonl"
            self._write_raw(path, [
                self._created(),
                {"type": "evidence_attached", "experiment_id": "exp-1", "evidence": {"x": 1},
                 "evidence_fingerprint": "fp"},
            ])
            with self.assertRaises(MalformedRegistryLogError):
                ExperimentRegistry(FileRegistryStorage(path))

    def test_duplicate_evidence_entry_raises_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.jsonl"
            self._write_raw(path, [
                self._created(),
                {"type": "experiment_sealed", "experiment_id": "exp-1", "sealed_at_utc": "t1"},
                {"type": "evidence_attached", "experiment_id": "exp-1", "evidence": {"x": 1},
                 "evidence_fingerprint": "fp1"},
                {"type": "evidence_attached", "experiment_id": "exp-1", "evidence": {"x": 2},
                 "evidence_fingerprint": "fp2"},
            ])
            with self.assertRaises(MalformedRegistryLogError):
                ExperimentRegistry(FileRegistryStorage(path))


class TestTypedAttachHelper(unittest.TestCase):
    def setUp(self):
        self.registry = ExperimentRegistry(_InMemoryStorage())

    def test_happy_path_attaches_package_with_matching_spec(self):
        spec = _spec()
        package = _package(spec)
        self.registry.create("exp-1", spec.to_specification_dict())
        self.registry.seal("exp-1")

        record = attach_evidence_package(self.registry, "exp-1", package)

        self.assertEqual(record.evidence_fingerprint, package.fingerprint)
        self.assertEqual(dict(self.registry.get_evidence("exp-1")), package.to_dict())

    def test_mismatched_specification_refused(self):
        spec_registered = _spec(threshold="0.0005")
        spec_validated = _spec(threshold="0.0009")  # different hypothesis
        package = _package(spec_validated)
        self.registry.create("exp-1", spec_registered.to_specification_dict())
        self.registry.seal("exp-1")

        with self.assertRaises(ValidationError):
            attach_evidence_package(self.registry, "exp-1", package)
        self.assertIsNone(self.registry.get_evidence("exp-1"))  # nothing attached

    def test_rejects_wrong_types(self):
        with self.assertRaises(ValidationError):
            attach_evidence_package("not-a-registry", "exp-1", _package(_spec()))
        with self.assertRaises(ValidationError):
            attach_evidence_package(self.registry, "exp-1", "not-a-package")


if __name__ == "__main__":
    unittest.main()
