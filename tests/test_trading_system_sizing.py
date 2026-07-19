"""Verification tests for trading_system.sizing (Milestone 6).

Pure unit tests -- size_intent has zero adapter/Engine/RiskManager
dependency, so no composition_root fixture is needed here. Every expected
number below is hand-computed in the test itself.
"""

import unittest
from dataclasses import replace
from decimal import Decimal

from config import RiskProfileParams
from exchange_adapter import OrderSide, OrderType, Symbol, TimeInForce
from risk_manager import TradeRequest

from trading_system.sizing import SizingError, size_intent
from trading_system.strategy import TradeIntent

_FIXED_PROFILE = RiskProfileParams(
    risk_pct_per_trade=0.02, max_positions=3, sizing_mode="fixed", heat_cap=0.05, ruin_threshold=0.6,
)
_CONVICTION_PROFILE = replace(_FIXED_PROFILE, sizing_mode="conviction_weighted")
_VOL_PROFILE = replace(_FIXED_PROFILE, sizing_mode="vol_targeted")


def _intent(**overrides):
    fields = dict(
        symbol=Symbol("BTC"), side=OrderSide.BUY, order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.GTC, reduce_only=False, stop_price=Decimal("90"),
    )
    fields.update(overrides)
    return TradeIntent(**fields)


class TestFixedSizing(unittest.TestCase):
    def test_computes_quantity_notional_margin_and_liquidation(self):
        result = size_intent(
            _intent(), equity=Decimal("100000"), risk_profile=_FIXED_PROFILE,
            current_price=Decimal("100"), maintenance_margin_rate=Decimal("0.005"),
            target_leverage=Decimal("2"),
        )
        self.assertIsInstance(result, TradeRequest)
        self.assertEqual(result.proposed_risk_amount, Decimal("2000"))   # 100000 * 0.02
        self.assertEqual(result.quantity, Decimal("200"))                # 2000 / |100-90|
        self.assertEqual(result.proposed_notional, Decimal("20000"))     # 200 * 100
        self.assertEqual(result.proposed_margin_required, Decimal("10000"))  # 20000 / 2
        self.assertEqual(result.leverage, Decimal("2"))
        self.assertEqual(result.entry_price, Decimal("100"))
        self.assertEqual(result.stop_price, Decimal("90"))
        # long: entry*(1 - 1/leverage + mmr) = 100*(1 - 0.5 + 0.005) = 50.5
        self.assertEqual(result.estimated_liquidation_price, Decimal("50.5"))

    def test_limit_price_overrides_current_price_as_entry(self):
        result = size_intent(
            _intent(limit_price=Decimal("95")), equity=Decimal("100000"), risk_profile=_FIXED_PROFILE,
            current_price=Decimal("100"), maintenance_margin_rate=Decimal("0"), target_leverage=Decimal("1"),
        )
        self.assertEqual(result.entry_price, Decimal("95"))

    def test_sell_side_liquidation_is_above_entry(self):
        result = size_intent(
            _intent(side=OrderSide.SELL, stop_price=Decimal("110")), equity=Decimal("100000"),
            risk_profile=_FIXED_PROFILE, current_price=Decimal("100"),
            maintenance_margin_rate=Decimal("0.005"), target_leverage=Decimal("2"),
        )
        # short: entry*(1 + 1/leverage - mmr) = 100*(1 + 0.5 - 0.005) = 149.5
        self.assertEqual(result.estimated_liquidation_price, Decimal("149.5"))
        self.assertGreater(result.estimated_liquidation_price, result.entry_price)

    def test_buy_side_liquidation_is_below_entry(self):
        result = size_intent(
            _intent(), equity=Decimal("100000"), risk_profile=_FIXED_PROFILE,
            current_price=Decimal("100"), maintenance_margin_rate=Decimal("0.005"), target_leverage=Decimal("2"),
        )
        self.assertLess(result.estimated_liquidation_price, result.entry_price)

    def test_degenerate_zero_distance_raises(self):
        with self.assertRaises(SizingError):
            size_intent(
                _intent(stop_price=Decimal("100")), equity=Decimal("100000"), risk_profile=_FIXED_PROFILE,
                current_price=Decimal("100"), maintenance_margin_rate=Decimal("0"), target_leverage=Decimal("1"),
            )


class TestConvictionWeightedSizing(unittest.TestCase):
    def test_scales_risk_amount_by_abs_conviction(self):
        result = size_intent(
            _intent(conviction=Decimal("0.5")), equity=Decimal("100000"), risk_profile=_CONVICTION_PROFILE,
            current_price=Decimal("100"), maintenance_margin_rate=Decimal("0"), target_leverage=Decimal("1"),
        )
        self.assertEqual(result.proposed_risk_amount, Decimal("1000"))  # 100000*0.02*0.5
        self.assertEqual(result.quantity, Decimal("100"))                # 1000 / 10

    def test_negative_conviction_uses_absolute_value(self):
        result = size_intent(
            _intent(conviction=Decimal("-0.5")), equity=Decimal("100000"), risk_profile=_CONVICTION_PROFILE,
            current_price=Decimal("100"), maintenance_margin_rate=Decimal("0"), target_leverage=Decimal("1"),
        )
        self.assertEqual(result.proposed_risk_amount, Decimal("1000"))

    def test_missing_conviction_raises(self):
        with self.assertRaises(SizingError):
            size_intent(
                _intent(), equity=Decimal("100000"), risk_profile=_CONVICTION_PROFILE,
                current_price=Decimal("100"), maintenance_margin_rate=Decimal("0"), target_leverage=Decimal("1"),
            )


class TestVolTargetedSizing(unittest.TestCase):
    def test_uses_volatility_based_distance(self):
        result = size_intent(
            _intent(), equity=Decimal("100000"), risk_profile=_VOL_PROFILE,
            current_price=Decimal("100"), maintenance_margin_rate=Decimal("0"), target_leverage=Decimal("1"),
            volatility=Decimal("0.05"),
        )
        self.assertEqual(result.proposed_risk_amount, Decimal("2000"))  # 100000*0.02
        self.assertEqual(result.quantity, Decimal("400"))                # 2000 / (100*0.05)

    def test_missing_volatility_raises(self):
        with self.assertRaises(SizingError):
            size_intent(
                _intent(), equity=Decimal("100000"), risk_profile=_VOL_PROFILE,
                current_price=Decimal("100"), maintenance_margin_rate=Decimal("0"), target_leverage=Decimal("1"),
            )

    def test_non_positive_volatility_raises(self):
        with self.assertRaises(SizingError):
            size_intent(
                _intent(), equity=Decimal("100000"), risk_profile=_VOL_PROFILE,
                current_price=Decimal("100"), maintenance_margin_rate=Decimal("0"), target_leverage=Decimal("1"),
                volatility=Decimal("0"),
            )


class TestSizingInputValidation(unittest.TestCase):
    def test_unsupported_sizing_mode_raises(self):
        profile = replace(_FIXED_PROFILE, sizing_mode="unknown_mode")
        with self.assertRaises(SizingError):
            size_intent(
                _intent(), equity=Decimal("100000"), risk_profile=profile, current_price=Decimal("100"),
                maintenance_margin_rate=Decimal("0"), target_leverage=Decimal("1"),
            )

    def test_rejects_non_intent(self):
        with self.assertRaises(SizingError):
            size_intent(
                "not an intent", equity=Decimal("100000"), risk_profile=_FIXED_PROFILE,
                current_price=Decimal("100"), maintenance_margin_rate=Decimal("0"), target_leverage=Decimal("1"),
            )

    def test_rejects_non_positive_equity(self):
        with self.assertRaises(SizingError):
            size_intent(
                _intent(), equity=Decimal("0"), risk_profile=_FIXED_PROFILE, current_price=Decimal("100"),
                maintenance_margin_rate=Decimal("0"), target_leverage=Decimal("1"),
            )

    def test_rejects_wrong_type_risk_profile(self):
        with self.assertRaises(SizingError):
            size_intent(
                _intent(), equity=Decimal("100000"), risk_profile={"sizing_mode": "fixed"},
                current_price=Decimal("100"), maintenance_margin_rate=Decimal("0"), target_leverage=Decimal("1"),
            )

    def test_rejects_non_positive_current_price(self):
        with self.assertRaises(SizingError):
            size_intent(
                _intent(), equity=Decimal("100000"), risk_profile=_FIXED_PROFILE, current_price=Decimal("0"),
                maintenance_margin_rate=Decimal("0"), target_leverage=Decimal("1"),
            )

    def test_rejects_maintenance_margin_rate_out_of_range(self):
        with self.assertRaises(SizingError):
            size_intent(
                _intent(), equity=Decimal("100000"), risk_profile=_FIXED_PROFILE, current_price=Decimal("100"),
                maintenance_margin_rate=Decimal("1"), target_leverage=Decimal("1"),
            )
        with self.assertRaises(SizingError):
            size_intent(
                _intent(), equity=Decimal("100000"), risk_profile=_FIXED_PROFILE, current_price=Decimal("100"),
                maintenance_margin_rate=Decimal("-0.01"), target_leverage=Decimal("1"),
            )

    def test_rejects_non_positive_target_leverage(self):
        with self.assertRaises(SizingError):
            size_intent(
                _intent(), equity=Decimal("100000"), risk_profile=_FIXED_PROFILE, current_price=Decimal("100"),
                maintenance_margin_rate=Decimal("0"), target_leverage=Decimal("0"),
            )


if __name__ == "__main__":
    unittest.main()
