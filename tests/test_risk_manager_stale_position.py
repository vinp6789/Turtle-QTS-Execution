"""§9 fix, 2026-08-08: an AGED POSITION is not STALE DATA.

THE DEFECT THIS REPRODUCES. PositionSnapshot.updated_at_utc is written only
from event.timestamp_utc, so it records the last position-state MUTATION.
Nothing refreshes it between open and close -- AccountingSync.update_marks()
pushes fresh marks to the PORTFOLIO, never to the position. RiskManager
included it in its stale-observation set, so every position became
permanently "stale" max_stale_data_seconds after opening, and RiskManager
then FAIL_SAFE-rejected every later intent for it INCLUDING ITS OWN
REDUCE-ONLY CLOSE.

Measured on Hyperliquid testnet 2026-08-08: a real 0.00025 BTC position was
unclosable through the canonical path at age 344.576899s
(position:pm:default:1:position:stale) and had to be closed by hand at the
venue.

WHAT THESE TESTS ARE NOT. They do not assert that a list no longer contains
an element. Every test below drives the real RiskManager.evaluate() with the
exact failure condition -- an old position alongside FRESH portfolio,
funding and correlation observations -- and each one fails against the
pre-fix implementation with ReasonCode.STALE_DATA.

THE OTHER HALF MATTERS MORE. Removing a check is only safe if it removed
nothing real, so TestGenuineFreshnessStillEnforced proves every observation
that DOES decay still FAIL_SAFEs -- including while an open position is
present, which is the exact combination the fix touches.
"""

import unittest
from decimal import Decimal

from exchange_adapter import OrderSide, Symbol
from position_manager import PositionLifecycleState, PositionSnapshot
from risk_manager import CorrelationEntry, Decision, ReasonCode, RiskManager

from tests.test_risk_manager import (
    FRESH, FUTURE, NOW, STALE, _correlation, _full_eval_kwargs, _funding,
    _limits, _portfolio, _trade,
)

# NOW is 12:00:00; the limit under test is 60s. 10:00:00 is 2 hours old --
# far past any threshold, exactly like the 344s seen on the live venue.
AGED = STALE


def _aged_position(position_id="pm:default:1:position", symbol="BTC",
                   side=OrderSide.BUY, updated_at_utc=AGED):
    """A position whose data is EXACT but whose stamp is old, because
    nothing has happened to it since it opened. This is the real-world
    state of every position that has been held for a while."""
    return PositionSnapshot(
        position_id=position_id, lifecycle_state=PositionLifecycleState.FULLY_FILLED,
        symbol=Symbol(symbol), side=side, intended_quantity=Decimal("1"),
        filled_quantity=Decimal("1"), remaining_quantity=Decimal("1"),
        avg_entry_price=Decimal("2000"), stop_price=Decimal("1800"),
        stop_d=Decimal("0.1"), t1_price=Decimal("2300"), t2_price=Decimal("2600"),
        conviction=None, realized_pnl=Decimal("0"), realized_r=Decimal("0"),
        fees_paid=Decimal("0"), funding_paid=Decimal("0"),
        created_at_utc=updated_at_utc, updated_at_utc=updated_at_utc,
    )


class TestAgedPositionDoesNotBlockItsOwnClose(unittest.TestCase):
    """The defect, reproduced: old position + FRESH observations."""

    def test_reduce_only_close_of_an_aged_position_is_not_stale(self):
        rm = RiskManager(_limits(max_stale_data_seconds=60))
        decision = rm.evaluate(**_full_eval_kwargs(
            trade_request=_trade(reduce_only=True),
            open_positions=(_aged_position(symbol="ETH"),),
            correlation_info=_correlation((CorrelationEntry(Symbol("ETH"), Decimal("0.3")),)),
        ))
        self.assertNotIn(
            ReasonCode.STALE_DATA, decision.reason_codes,
            "an aged position must not make its own reduce-only close stale -- "
            "this is the exact condition that stranded a real testnet position")
        self.assertNotIn("stale", " ".join(decision.violated_limits))

    def test_the_exact_live_failure_no_longer_fail_safes(self):
        """Named for the measured incident: position:pm:default:1:position."""
        rm = RiskManager(_limits(max_stale_data_seconds=150))
        decision = rm.evaluate(**_full_eval_kwargs(
            trade_request=_trade(reduce_only=True),
            open_positions=(_aged_position(symbol="ETH"),),
            correlation_info=_correlation((CorrelationEntry(Symbol("ETH"), Decimal("0.3")),)),
        ))
        self.assertNotEqual(
            decision.decision, Decision.FAIL_SAFE,
            f"FAIL_SAFE returned for an aged position: {decision.violated_limits}")

    def test_an_aged_position_does_not_block_an_ENTRY_either(self):
        """The defect was never exit-specific: an aged position blocked
        every later intent, which is why reduce_only was not special-cased."""
        rm = RiskManager(_limits(max_stale_data_seconds=60))
        decision = rm.evaluate(**_full_eval_kwargs(
            open_positions=(_aged_position(symbol="ETH"),),
            correlation_info=_correlation((CorrelationEntry(Symbol("ETH"), Decimal("0.3")),)),
        ))
        self.assertNotIn(ReasonCode.STALE_DATA, decision.reason_codes)

    def test_many_aged_positions_contribute_no_stale_reasons(self):
        rm = RiskManager(_limits(max_stale_data_seconds=60, max_correlated_positions=5))
        positions = tuple(_aged_position(position_id=f"p{i}", symbol=f"SYM{i}") for i in range(4))
        decision = rm.evaluate(**_full_eval_kwargs(open_positions=positions))
        self.assertNotIn(ReasonCode.STALE_DATA, decision.reason_codes)

    def test_a_position_stamped_in_the_future_is_also_ignored(self):
        """Symmetry: position stamps are not observations in EITHER
        direction, so a future stamp is not a future-observation error."""
        rm = RiskManager(_limits(max_stale_data_seconds=60))
        decision = rm.evaluate(**_full_eval_kwargs(
            open_positions=(_aged_position(symbol="ETH", updated_at_utc=FUTURE),),
            correlation_info=_correlation((CorrelationEntry(Symbol("ETH"), Decimal("0.3")),)),
        ))
        self.assertNotIn(ReasonCode.STALE_DATA, decision.reason_codes)


class TestGenuineFreshnessStillEnforced(unittest.TestCase):
    """Removing a check is only safe if it removed nothing real. Every
    observation that genuinely decays must still FAIL_SAFE -- and must do
    so WHILE AN OPEN POSITION IS PRESENT, the combination the fix touches."""

    def _decide(self, **over):
        rm = RiskManager(_limits(max_stale_data_seconds=60))
        return rm.evaluate(**_full_eval_kwargs(
            open_positions=(_aged_position(symbol="ETH"),),
            correlation_info=_correlation((CorrelationEntry(Symbol("ETH"), Decimal("0.3")),)),
            **over))

    def test_stale_portfolio_still_fail_safes_with_a_position_open(self):
        d = self._decide(portfolio_snapshot=_portfolio(updated_at_utc=STALE))
        self.assertEqual(d.decision, Decision.FAIL_SAFE)
        self.assertIn(ReasonCode.STALE_DATA, d.reason_codes)
        self.assertTrue(any("portfolio_snapshot" in v for v in d.violated_limits))

    def test_stale_funding_still_fail_safes_with_a_position_open(self):
        d = self._decide(funding_info=_funding(as_of_utc=STALE))
        self.assertEqual(d.decision, Decision.FAIL_SAFE)
        self.assertIn(ReasonCode.STALE_DATA, d.reason_codes)
        self.assertTrue(any("funding_info" in v for v in d.violated_limits))

    def test_stale_correlation_still_fail_safes_with_a_position_open(self):
        rm = RiskManager(_limits(max_stale_data_seconds=60))
        d = rm.evaluate(**_full_eval_kwargs(
            open_positions=(_aged_position(symbol="ETH"),),
            correlation_info=_correlation(
                (CorrelationEntry(Symbol("ETH"), Decimal("0.3")),), as_of_utc=STALE),
        ))
        self.assertEqual(d.decision, Decision.FAIL_SAFE)
        self.assertIn(ReasonCode.STALE_DATA, d.reason_codes)
        self.assertTrue(any("correlation_info" in v for v in d.violated_limits))

    def test_future_portfolio_observation_still_rejected(self):
        d = self._decide(portfolio_snapshot=_portfolio(updated_at_utc=FUTURE))
        self.assertEqual(d.decision, Decision.FAIL_SAFE)
        self.assertIn(ReasonCode.STALE_DATA, d.reason_codes)
        self.assertTrue(any("future" in v for v in d.violated_limits))

    def test_fresh_observations_with_an_aged_position_are_approved(self):
        """The whole point: the close path is open again, and only the
        position stamp changed category."""
        d = self._decide()
        self.assertEqual(d.decision, Decision.APPROVED, d.violated_limits)


if __name__ == "__main__":
    unittest.main()
