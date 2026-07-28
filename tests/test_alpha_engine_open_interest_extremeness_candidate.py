"""Verification tests for the open_interest_extremeness_rule candidate
(Research Campaign 01). Synthetic inputs throughout."""

import unittest
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.candidates import (
    CandidateError,
    OpenInterestExtremenessRuleCandidate,
    SignalDirection,
    get_candidate_type,
    open_interest_extremeness_candidate_specification,
)
from alpha_engine.features import PCTRANK_NAME, PCTRANK_VERSION, ZSCORE_NAME, ZSCORE_VERSION, FeatureValue

_EVAL = OpenInterestExtremenessRuleCandidate.evaluate


def _spec(direction_convention="contrarian", threshold="0.49",
          feature_name=PCTRANK_NAME, feature_version=PCTRANK_VERSION, version="v1"):
    return open_interest_extremeness_candidate_specification(
        version=version, universe=(Symbol("BTC"),),
        feature_name=feature_name, feature_version=feature_version,
        cadence_seconds=86400,
        parameters={"threshold": threshold, "direction_convention": direction_convention},
        acceptance_criteria={"min_hit_rate": 0.55},
    )


def _fv(value, feature_name=PCTRANK_NAME, feature_version=PCTRANK_VERSION, available=True, reason=None):
    if available:
        return FeatureValue(
            feature_name=feature_name, feature_version=feature_version, symbol=Symbol("BTC"),
            computed_at_utc="2024-01-01T00:00:00+00:00", available=True, value=Decimal(value),
        )
    return FeatureValue(
        feature_name=feature_name, feature_version=feature_version, symbol=Symbol("BTC"),
        computed_at_utc="2024-01-01T00:00:00+00:00", available=False, reason=reason or "no data",
    )


class TestSpecFactory(unittest.TestCase):
    def test_accepts_pctrank_feature(self):
        spec = _spec()
        self.assertEqual(spec.name, "open_interest_extremeness_rule")
        self.assertEqual(spec.feature_name, PCTRANK_NAME)

    def test_accepts_zscore_feature(self):
        spec = _spec(feature_name=ZSCORE_NAME, feature_version=ZSCORE_VERSION, threshold="2.0")
        self.assertEqual(spec.feature_name, ZSCORE_NAME)

    def test_rejects_unrecognized_feature(self):
        with self.assertRaises(CandidateError):
            _spec(feature_name="open_interest_raw", feature_version="v1")


class TestContrarianConvention(unittest.TestCase):
    def test_upper_tail_shorts(self):
        sig = _EVAL(_fv("0.5"), _spec("contrarian"))  # score > 0.49
        self.assertTrue(sig.available)
        self.assertIs(sig.direction, SignalDirection.SHORT)

    def test_lower_tail_longs(self):
        sig = _EVAL(_fv("-0.5"), _spec("contrarian"))  # score < -0.49
        self.assertIs(sig.direction, SignalDirection.LONG)

    def test_middle_is_flat(self):
        sig = _EVAL(_fv("0.1"), _spec("contrarian"))
        self.assertIs(sig.direction, SignalDirection.FLAT)


class TestMomentumConvention(unittest.TestCase):
    def test_upper_tail_longs(self):
        sig = _EVAL(_fv("0.5"), _spec("momentum"))
        self.assertIs(sig.direction, SignalDirection.LONG)

    def test_lower_tail_shorts(self):
        sig = _EVAL(_fv("-0.5"), _spec("momentum"))
        self.assertIs(sig.direction, SignalDirection.SHORT)


class TestThresholdBoundary(unittest.TestCase):
    def test_exactly_at_threshold_is_flat(self):
        # score == threshold is NOT > threshold -> FLAT (strict inequality)
        sig = _EVAL(_fv("0.49"), _spec("contrarian", threshold="0.49"))
        self.assertIs(sig.direction, SignalDirection.FLAT)


class TestFailModes(unittest.TestCase):
    def test_unavailable_feature_degrades(self):
        sig = _EVAL(_fv(None, available=False, reason="empty window"), _spec())
        self.assertFalse(sig.available)
        self.assertIn("empty window", sig.reason)

    def test_mismatched_feature_raises(self):
        # spec declares pctrank; feed a zscore-named feature value
        with self.assertRaises(CandidateError):
            _EVAL(_fv("0.5", feature_name=ZSCORE_NAME, feature_version=ZSCORE_VERSION), _spec())

    def test_wrong_family_spec_raises(self):
        from alpha_engine.candidates import funding_rate_candidate_specification
        wrong = funding_rate_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "0.01"}, acceptance_criteria={"min_hit_rate": 0.5},
        )
        with self.assertRaises(CandidateError):
            _EVAL(_fv("0.5"), wrong)

    def test_missing_threshold_raises(self):
        spec = open_interest_extremeness_candidate_specification(
            version="v1", universe=(Symbol("BTC"),),
            feature_name=PCTRANK_NAME, feature_version=PCTRANK_VERSION, cadence_seconds=86400,
            parameters={"direction_convention": "contrarian"},  # no threshold
            acceptance_criteria={"min_hit_rate": 0.55},
        )
        with self.assertRaises(CandidateError):
            _EVAL(_fv("0.5"), spec)


class TestCatalogWiring(unittest.TestCase):
    def test_registered_in_catalog(self):
        entry = get_candidate_type("open_interest_extremeness_rule")
        self.assertIs(entry.evaluate_fn, OpenInterestExtremenessRuleCandidate.evaluate)


if __name__ == "__main__":
    unittest.main()
