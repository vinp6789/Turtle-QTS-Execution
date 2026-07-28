"""Verification tests for the Candidate specification scaffold (Alpha
Engine Milestone 3.1).

Covers CandidateSpecification's own validation/determinism/immutability,
the funding_rate_candidate_specification() factory's cross-reference to
FundingRateFeature.metadata(), and -- the key integration proof this
milestone requires -- that a candidate specification's
to_specification_dict() plugs directly into ExperimentRegistry (Milestone
0.2/0.3) with no adaptation: registration, seal, content-derived
fingerprinting, and specification-field querying all work exactly as
they do for any other opaque specification.
"""

import json
import unittest
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.candidates import CandidateError, CandidateSpecification, funding_rate_candidate_specification
from alpha_engine.features import FundingRateFeature
from alpha_engine.registry import ExperimentRegistry, RegistryStorage


class _InMemoryStorage(RegistryStorage):
    """Mirrors the in-memory test double already used in
    test_alpha_engine_registry.py / test_alpha_engine_registry_queries.py
    rather than importing a test-only class across test files."""

    def __init__(self):
        self._entries = []

    def append(self, entry):
        self._entries.append(dict(entry))

    def read_all(self):
        return list(self._entries)


def _spec(**overrides):
    fields = dict(
        name="x", version="v1", candidate_type="rule_based",
        universe=(Symbol("BTC"),), feature_name="funding_rate_raw", feature_version="v1",
        cadence_seconds=60, acceptance_criteria={"min_sharpe": 0.5}, parameters={"threshold": "0.0005"},
    )
    fields.update(overrides)
    return CandidateSpecification(**fields)


class TestCandidateSpecificationValidation(unittest.TestCase):
    def test_valid_specification_constructs(self):
        spec = _spec()
        self.assertEqual(spec.name, "x")

    def test_blank_name_raises(self):
        with self.assertRaises(CandidateError):
            _spec(name="  ")

    def test_blank_version_raises(self):
        with self.assertRaises(CandidateError):
            _spec(version="")

    def test_blank_candidate_type_raises(self):
        with self.assertRaises(CandidateError):
            _spec(candidate_type=" ")

    def test_blank_feature_name_raises(self):
        with self.assertRaises(CandidateError):
            _spec(feature_name="")

    def test_blank_feature_version_raises(self):
        with self.assertRaises(CandidateError):
            _spec(feature_version="")

    def test_empty_universe_raises(self):
        with self.assertRaises(CandidateError):
            _spec(universe=())

    def test_non_symbol_in_universe_raises(self):
        with self.assertRaises(CandidateError):
            _spec(universe=("BTC",))  # str, not Symbol

    def test_non_tuple_universe_raises(self):
        with self.assertRaises(CandidateError):
            _spec(universe=[Symbol("BTC")])

    def test_zero_cadence_raises(self):
        with self.assertRaises(CandidateError):
            _spec(cadence_seconds=0)

    def test_negative_cadence_raises(self):
        with self.assertRaises(CandidateError):
            _spec(cadence_seconds=-60)

    def test_bool_cadence_raises(self):
        with self.assertRaises(CandidateError):
            _spec(cadence_seconds=True)

    def test_non_mapping_acceptance_criteria_raises(self):
        with self.assertRaises(CandidateError):
            _spec(acceptance_criteria=["min_sharpe", 0.5])

    def test_empty_acceptance_criteria_raises(self):
        with self.assertRaises(CandidateError):
            _spec(acceptance_criteria={})

    def test_non_json_native_acceptance_criteria_raises(self):
        with self.assertRaises(CandidateError):
            _spec(acceptance_criteria={"min_sharpe": Decimal("0.5")})

    def test_non_mapping_parameters_raises(self):
        with self.assertRaises(CandidateError):
            _spec(parameters=["threshold", "0.0005"])

    def test_empty_parameters_is_allowed(self):
        spec = _spec(parameters={})
        self.assertEqual(spec.parameters, {})

    def test_non_json_native_parameters_raises(self):
        with self.assertRaises(CandidateError):
            _spec(parameters={"threshold": Decimal("0.0005")})


class TestCandidateSpecificationImmutability(unittest.TestCase):
    def test_cannot_reassign_a_field(self):
        spec = _spec()
        with self.assertRaises(Exception):
            spec.name = "y"


class TestToSpecificationDict(unittest.TestCase):
    def test_produces_expected_shape(self):
        spec = _spec()
        d = spec.to_specification_dict()
        self.assertEqual(d["candidate_name"], "x")
        self.assertEqual(d["candidate_version"], "v1")
        self.assertEqual(d["candidate_type"], "rule_based")
        self.assertEqual(d["universe"], ["BTC"])
        self.assertEqual(d["feature_name"], "funding_rate_raw")
        self.assertEqual(d["feature_version"], "v1")
        self.assertEqual(d["cadence_seconds"], 60)
        self.assertEqual(d["acceptance_criteria"], {"min_sharpe": 0.5})
        self.assertEqual(d["parameters"], {"threshold": "0.0005"})

    def test_is_json_serializable(self):
        d = _spec().to_specification_dict()
        json.dumps(d)  # must not raise

    def test_multi_symbol_universe_encoded_as_list_of_values(self):
        spec = _spec(universe=(Symbol("BTC"), Symbol("ETH")))
        d = spec.to_specification_dict()
        self.assertEqual(d["universe"], ["BTC", "ETH"])

    def test_deterministic_across_identical_construction(self):
        spec_1 = _spec()
        spec_2 = _spec()
        d1, d2 = spec_1.to_specification_dict(), spec_2.to_specification_dict()
        self.assertEqual(d1, d2)
        self.assertEqual(json.dumps(d1, sort_keys=True), json.dumps(d2, sort_keys=True))

    def test_different_parameters_produce_different_dict(self):
        d1 = _spec(parameters={"threshold": "0.0005"}).to_specification_dict()
        d2 = _spec(parameters={"threshold": "0.0009"}).to_specification_dict()
        self.assertNotEqual(d1, d2)


class TestFundingRateCandidateFactory(unittest.TestCase):
    def test_name_and_type_are_fixed(self):
        spec = funding_rate_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "0.0005"}, acceptance_criteria={"min_sharpe": 0.5},
        )
        self.assertEqual(spec.name, "funding_rate_threshold_rule")
        self.assertEqual(spec.candidate_type, "rule_based")

    def test_feature_reference_matches_funding_rate_feature_metadata_exactly(self):
        feature_meta = FundingRateFeature.metadata()
        spec = funding_rate_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={}, acceptance_criteria={"min_sharpe": 0.5},
        )
        self.assertEqual(spec.feature_name, feature_meta.name)
        self.assertEqual(spec.feature_version, feature_meta.version)

    def test_parameters_and_acceptance_criteria_pass_through_untouched(self):
        spec = funding_rate_candidate_specification(
            version="v2", universe=(Symbol("ETH"),), cadence_seconds=120,
            parameters={"threshold": "0.001", "direction": "short_on_positive"},
            acceptance_criteria={"min_sharpe": 1.0, "max_drawdown_pct": 0.2},
        )
        self.assertEqual(spec.parameters, {"threshold": "0.001", "direction": "short_on_positive"})
        self.assertEqual(spec.acceptance_criteria, {"min_sharpe": 1.0, "max_drawdown_pct": 0.2})
        self.assertEqual(spec.version, "v2")
        self.assertEqual(spec.universe, (Symbol("ETH"),))
        self.assertEqual(spec.cadence_seconds, 120)


class TestRegistryIntegration(unittest.TestCase):
    """The concrete proof this milestone requires: a candidate
    specification's to_specification_dict() integrates with
    ExperimentRegistry with zero adaptation."""

    def setUp(self):
        self.registry = ExperimentRegistry(_InMemoryStorage())

    def test_specification_registers_and_round_trips(self):
        spec = funding_rate_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "0.0005"}, acceptance_criteria={"min_sharpe": 0.5},
        )
        record = self.registry.create("exp-1", spec.to_specification_dict())
        self.assertEqual(record.specification["candidate_name"], "funding_rate_threshold_rule")
        self.assertEqual(record.specification["feature_name"], "funding_rate_raw")

    def test_seal_works_normally_on_a_candidate_specification_experiment(self):
        spec = funding_rate_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={}, acceptance_criteria={"min_sharpe": 0.5},
        )
        self.registry.create("exp-1", spec.to_specification_dict())
        sealed = self.registry.seal("exp-1")
        self.assertTrue(sealed.sealed)

    def test_find_by_specification_field_locates_by_feature_name(self):
        spec_a = funding_rate_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "0.0005"}, acceptance_criteria={"min_sharpe": 0.5},
        )
        spec_b = funding_rate_candidate_specification(
            version="v2", universe=(Symbol("ETH"),), cadence_seconds=120,
            parameters={"threshold": "0.001"}, acceptance_criteria={"min_sharpe": 1.0},
        )
        self.registry.create("exp-a", spec_a.to_specification_dict())
        self.registry.create("exp-b", spec_b.to_specification_dict())

        found = self.registry.find_by_specification_field("feature_name", "funding_rate_raw")
        self.assertEqual({r.experiment_id for r in found}, {"exp-a", "exp-b"})

    def test_find_by_specification_field_locates_by_candidate_type(self):
        spec = funding_rate_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={}, acceptance_criteria={"min_sharpe": 0.5},
        )
        self.registry.create("exp-1", spec.to_specification_dict())
        found = self.registry.find_by_specification_field("candidate_type", "rule_based")
        self.assertEqual({r.experiment_id for r in found}, {"exp-1"})

    def test_identical_specifications_under_different_ids_share_a_fingerprint(self):
        spec_1 = funding_rate_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "0.0005"}, acceptance_criteria={"min_sharpe": 0.5},
        )
        spec_2 = funding_rate_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "0.0005"}, acceptance_criteria={"min_sharpe": 0.5},
        )
        r1 = self.registry.create("exp-1", spec_1.to_specification_dict())
        r2 = self.registry.create("exp-2", spec_2.to_specification_dict())
        self.assertEqual(r1.fingerprint, r2.fingerprint)

    def test_specification_differing_only_in_a_parameter_gets_a_different_fingerprint(self):
        spec_1 = funding_rate_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "0.0005"}, acceptance_criteria={"min_sharpe": 0.5},
        )
        spec_2 = funding_rate_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "0.0009"}, acceptance_criteria={"min_sharpe": 0.5},
        )
        r1 = self.registry.create("exp-1", spec_1.to_specification_dict())
        r2 = self.registry.create("exp-2", spec_2.to_specification_dict())
        self.assertNotEqual(r1.fingerprint, r2.fingerprint)

    def test_lineage_works_with_a_refined_candidate_specification(self):
        spec_v1 = funding_rate_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "0.0005"}, acceptance_criteria={"min_sharpe": 0.5},
        )
        spec_v2 = funding_rate_candidate_specification(
            version="v2", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "0.0007"}, acceptance_criteria={"min_sharpe": 0.6},
        )
        self.registry.create("exp-v1", spec_v1.to_specification_dict())
        self.registry.seal("exp-v1")
        child = self.registry.create("exp-v2", spec_v2.to_specification_dict(), parent_id="exp-v1")
        self.assertEqual(child.parent_id, "exp-v1")
        ancestors = self.registry.get_ancestors("exp-v2")
        self.assertEqual([a.experiment_id for a in ancestors], ["exp-v1"])


if __name__ == "__main__":
    unittest.main()
