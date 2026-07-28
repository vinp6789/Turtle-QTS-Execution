"""Verification tests for portfolio signal selection (Alpha Engine R6)."""

import unittest
from decimal import Decimal

from exchange_adapter import Symbol

from alpha_engine.candidates import CandidateSignal, SignalDirection
from alpha_engine.portfolio import PortfolioError, select_signals


def _signal(symbol="BTC", direction=SignalDirection.LONG, candidate="funding_rate_threshold_rule",
            version="v1", available=True, reason=None):
    return CandidateSignal(
        candidate_name=candidate, candidate_version=version, symbol=Symbol(symbol),
        evaluated_at_utc="2026-01-01T00:00:00+00:00", available=available,
        direction=direction if available else None,
        feature_value=Decimal("1") if available else None,
        threshold=Decimal("1") if available else None,
        reason=reason if not available else None,
    )


class TestSelectSignals(unittest.TestCase):
    def test_empty_input_yields_empty_output(self):
        self.assertEqual(select_signals(()), ())

    def test_unavailable_signals_dropped(self):
        self.assertEqual(select_signals((_signal(available=False, reason="stale"),)), ())

    def test_flat_signals_dropped(self):
        self.assertEqual(select_signals((_signal(direction=SignalDirection.FLAT),)), ())

    def test_single_directional_signal_passes_through(self):
        signal = _signal(direction=SignalDirection.SHORT)
        self.assertEqual(select_signals((signal,)), (signal,))

    def test_conflicting_directions_drop_the_whole_symbol(self):
        signals = (
            _signal(direction=SignalDirection.LONG, candidate="a_family"),
            _signal(direction=SignalDirection.SHORT, candidate="b_family"),
        )
        self.assertEqual(select_signals(signals), ())

    def test_conflict_on_one_symbol_does_not_affect_another(self):
        signals = (
            _signal("BTC", SignalDirection.LONG, candidate="a_family"),
            _signal("BTC", SignalDirection.SHORT, candidate="b_family"),
            _signal("ETH", SignalDirection.LONG),
        )
        selected = select_signals(signals)
        self.assertEqual([s.symbol.value for s in selected], ["ETH"])

    def test_same_direction_duplicates_collapse_deterministically(self):
        first = _signal(candidate="a_family")
        second = _signal(candidate="b_family")
        selected = select_signals((second, first))  # input order reversed on purpose
        self.assertEqual(selected, (first,))  # kept by candidate-name sort, not input order

    def test_output_sorted_by_symbol(self):
        signals = (_signal("SOL"), _signal("BTC"), _signal("ETH"))
        self.assertEqual([s.symbol.value for s in select_signals(signals)], ["BTC", "ETH", "SOL"])

    def test_non_tuple_raises(self):
        with self.assertRaises(PortfolioError):
            select_signals([_signal()])

    def test_non_signal_items_raise(self):
        with self.assertRaises(PortfolioError):
            select_signals(("not-a-signal",))


if __name__ == "__main__":
    unittest.main()
