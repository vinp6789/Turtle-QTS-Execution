"""trend_momentum_rule (EMA + MACD + ATR) -- feature, candidate, catalog.

Synthetic candles only; no network. Guards the properties the strategy's
correctness actually depends on: determinism, refusal on short history,
the EMA trend gate, ATR scale-invariance, two-tailed direction mapping,
provenance, and the frozen-period constants.
"""

import unittest
from decimal import Decimal

from exchange_adapter import Candle, CandleInterval, Symbol

from alpha_engine.candidates import (
    CANDIDATE_CATALOG,
    TrendMomentumRuleCandidate,
    trend_momentum_candidate_specification,
)
from alpha_engine.candidates.errors import CandidateError
from alpha_engine.candidates.models import SignalDirection
from alpha_engine.features import TrendMomentumFeature
from alpha_engine.features.errors import FeatureError

BTC = Symbol("BTC")
_PARAMS = {"threshold": "0.35", "direction_convention": "momentum"}
_CRITERIA = {"min_hit_rate": 0.55, "min_signaled_samples": 100}


def _series(closes, symbol=BTC, spread=Decimal("1")):
    """Build a candle series from close prices. high/low bracket the
    close so OHLC validation passes and ATR is non-zero."""
    out = []
    for i, close in enumerate(closes):
        c = Decimal(str(close))
        out.append(
            Candle(
                symbol=symbol,
                interval=CandleInterval.H1,
                open_time_utc=f"2026-01-{(i // 24) + 1:02d}T{i % 24:02d}:00:00+00:00",
                open=c,
                high=c + spread,
                low=c - spread,
                close=c,
                volume=Decimal("10"),
            )
        )
    return tuple(out)


def _spec(**over):
    params = dict(_PARAMS)
    params.update(over)
    return trend_momentum_candidate_specification(
        version="test-v1",
        universe=(BTC,),
        cadence_seconds=3600,
        parameters=params,
        acceptance_criteria=_CRITERIA,
    )


class TestFrozenConstants(unittest.TestCase):
    """Periods are constants, not parameters. If one changes, that is a
    NEW feature version and a new pre-registration -- never a silent
    refit. These assertions make that structural."""

    def test_canonical_periods(self):
        self.assertEqual(TrendMomentumFeature.EMA_FAST, 12)
        self.assertEqual(TrendMomentumFeature.EMA_SLOW, 26)
        self.assertEqual(TrendMomentumFeature.MACD_SIGNAL, 9)
        self.assertEqual(TrendMomentumFeature.ATR_PERIOD, 14)

    def test_warmup_declared(self):
        self.assertEqual(TrendMomentumFeature.WARMUP_PERIODS, 200)

    def test_metadata_identity(self):
        md = TrendMomentumFeature.metadata()
        self.assertEqual(md.name, "ema_macd_atr_norm")
        self.assertEqual(md.version, "v1")
        self.assertEqual(md.input_data_sources, ("candles",))


class TestFeatureCompute(unittest.TestCase):
    def test_deterministic(self):
        candles = _series([100 + i * 0.5 for i in range(250)])
        a = TrendMomentumFeature.compute(BTC, "t", candles)
        b = TrendMomentumFeature.compute(BTC, "t", candles)
        self.assertEqual(a.value, b.value)
        self.assertEqual(a.available, b.available)

    def test_short_window_refuses_never_computes(self):
        fv = TrendMomentumFeature.compute(BTC, "t", _series([100] * 50))
        self.assertFalse(fv.available)
        self.assertIn("insufficient history", fv.reason)

    def test_none_candles_requires_reason(self):
        with self.assertRaises(FeatureError):
            TrendMomentumFeature.compute(BTC, "t", None)
        fv = TrendMomentumFeature.compute(BTC, "t", None, unavailable_reason="venue down")
        self.assertFalse(fv.available)
        self.assertEqual(fv.reason, "venue down")

    def test_flat_market_yields_unavailable_not_zero(self):
        """Zero ATR has no volatility scale; a normalised value would be
        meaningless, so the feature must decline rather than emit 0."""
        flat = tuple(
            Candle(
                symbol=BTC, interval=CandleInterval.H1,
                open_time_utc=f"2026-01-{(i // 24) + 1:02d}T{i % 24:02d}:00:00+00:00",
                open=Decimal("100"), high=Decimal("100"), low=Decimal("100"),
                close=Decimal("100"), volume=Decimal("1"),
            )
            for i in range(250)
        )
        fv = TrendMomentumFeature.compute(BTC, "t", flat)
        self.assertFalse(fv.available)
        self.assertIn("ATR", fv.reason)

    def test_unordered_candles_rejected(self):
        candles = _series([100 + i for i in range(250)])
        with self.assertRaises(FeatureError):
            TrendMomentumFeature.compute(BTC, "t", tuple(reversed(candles)))

    def test_duplicate_timestamps_rejected(self):
        candles = _series([100 + i for i in range(250)])
        with self.assertRaises(FeatureError):
            TrendMomentumFeature.compute(BTC, "t", candles + (candles[-1],))

    def test_symbol_mismatch_rejected(self):
        candles = _series([100 + i for i in range(250)], symbol=Symbol("ETH"))
        with self.assertRaises(FeatureError):
            TrendMomentumFeature.compute(BTC, "t", candles)

    def test_uptrend_produces_non_negative_value(self):
        fv = TrendMomentumFeature.compute(BTC, "t", _series([100 + i * 0.8 for i in range(250)]))
        self.assertTrue(fv.available)
        self.assertGreaterEqual(fv.value, 0)

    def test_downtrend_produces_non_positive_value(self):
        fv = TrendMomentumFeature.compute(BTC, "t", _series([500 - i * 0.8 for i in range(250)]))
        self.assertTrue(fv.available)
        self.assertLessEqual(fv.value, 0)

    def test_atr_normalisation_is_scale_invariant(self):
        """The same shape at 1000x the price must give the same value --
        this is what lets ONE threshold serve BTC and SOL alike."""
        shape = [100 + i * 0.5 for i in range(250)]
        small = TrendMomentumFeature.compute(BTC, "t", _series(shape, spread=Decimal("1")))
        big = TrendMomentumFeature.compute(
            BTC, "t", _series([v * 1000 for v in shape], spread=Decimal("1000"))
        )
        self.assertTrue(small.available and big.available)
        self.assertAlmostEqual(float(small.value), float(big.value), places=6)


class TestCandidateEvaluate(unittest.TestCase):
    def _fv(self, value):
        md = TrendMomentumFeature.metadata()
        from alpha_engine.features.models import FeatureValue

        return FeatureValue(
            feature_name=md.name, feature_version=md.version, symbol=BTC,
            computed_at_utc="t", available=True, value=Decimal(str(value)),
        )

    def test_two_tailed_momentum(self):
        spec = _spec(direction_convention="momentum")
        self.assertEqual(
            TrendMomentumRuleCandidate.evaluate(self._fv("0.5"), spec).direction,
            SignalDirection.LONG,
        )
        self.assertEqual(
            TrendMomentumRuleCandidate.evaluate(self._fv("-0.5"), spec).direction,
            SignalDirection.SHORT,
        )

    def test_two_tailed_contrarian_is_the_mirror(self):
        spec = _spec(direction_convention="contrarian")
        self.assertEqual(
            TrendMomentumRuleCandidate.evaluate(self._fv("0.5"), spec).direction,
            SignalDirection.SHORT,
        )
        self.assertEqual(
            TrendMomentumRuleCandidate.evaluate(self._fv("-0.5"), spec).direction,
            SignalDirection.LONG,
        )

    def test_inside_threshold_is_flat(self):
        spec = _spec()
        for v in ("0.34", "0", "-0.34"):
            self.assertEqual(
                TrendMomentumRuleCandidate.evaluate(self._fv(v), spec).direction,
                SignalDirection.FLAT,
            )

    def test_boundary_is_inclusive(self):
        spec = _spec()
        self.assertEqual(
            TrendMomentumRuleCandidate.evaluate(self._fv("0.35"), spec).direction,
            SignalDirection.LONG,
        )

    def test_unavailable_feature_degrades_never_crashes(self):
        from alpha_engine.features.models import FeatureValue

        md = TrendMomentumFeature.metadata()
        fv = FeatureValue(
            feature_name=md.name, feature_version=md.version, symbol=BTC,
            computed_at_utc="t", available=False, reason="short window",
        )
        sig = TrendMomentumRuleCandidate.evaluate(fv, _spec())
        self.assertFalse(sig.available)
        self.assertIn("short window", sig.reason)

    def test_non_positive_threshold_rejected(self):
        with self.assertRaises(CandidateError):
            TrendMomentumRuleCandidate.evaluate(self._fv("1"), _spec(threshold="0"))

    def test_unknown_direction_convention_rejected(self):
        with self.assertRaises(CandidateError):
            TrendMomentumRuleCandidate.evaluate(self._fv("1"), _spec(direction_convention="both"))

    def test_foreign_specification_refused(self):
        from alpha_engine.candidates import funding_rate_candidate_specification

        foreign = funding_rate_candidate_specification(
            version="v1", universe=(BTC,), cadence_seconds=3600,
            parameters={"threshold": "0.001", "direction_convention": "momentum"},
            acceptance_criteria=_CRITERIA,
        )
        with self.assertRaises(CandidateError):
            TrendMomentumRuleCandidate.evaluate(self._fv("1"), foreign)


class TestProvenanceAndCatalog(unittest.TestCase):
    def test_specification_stamps_the_real_feature(self):
        """RD-19: an evidence package must record the feature it actually
        measured -- never one borrowed from another family."""
        spec = _spec()
        self.assertEqual(spec.feature_name, "ema_macd_atr_norm")
        self.assertNotIn("funding", spec.feature_name)
        self.assertEqual(spec.name, "trend_momentum_rule")

    def test_registered_in_catalog(self):
        entry = CANDIDATE_CATALOG["trend_momentum_rule"]
        self.assertEqual(entry.feature_name, TrendMomentumFeature.metadata().name)
        self.assertEqual(entry.feature_version, TrendMomentumFeature.metadata().version)
        self.assertIs(entry.evaluate_fn, TrendMomentumRuleCandidate.evaluate)

    def test_catalog_dispatch_resolves(self):
        from alpha_engine.candidates import get_candidate_type

        self.assertIsNotNone(get_candidate_type("trend_momentum_rule"))


if __name__ == "__main__":
    unittest.main()
