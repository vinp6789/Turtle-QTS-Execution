import threading
import unittest
from decimal import Decimal

from config.schema import RiskProfileParams
from exchange_adapter import ExchangeCapabilities, OrderSide, OrderType, Symbol, TimeInForce
from execution_state_machine import State
from position_manager import PositionLifecycleState, PositionSnapshot
from portfolio_manager import PortfolioSnapshot
from risk_manager import (
    CorrelationEntry,
    CorrelationInfo,
    Decision,
    FundingInfo,
    ReasonCode,
    RiskManager,
    RiskManagerConfigurationError,
    RiskManagerLimits,
    TradeRequest,
)

NOW = "2026-07-15T12:00:00+00:00"
FRESH = "2026-07-15T11:59:50+00:00"
STALE = "2026-07-15T10:00:00+00:00"
FUTURE = "2026-07-15T12:05:00+00:00"


def _limits(**overrides) -> RiskManagerLimits:
    base = dict(
        max_leverage=Decimal("10"),
        min_liquidation_buffer_pct=Decimal("0.2"),
        max_funding_rate_abs=Decimal("0.001"),
        max_correlated_positions=1,
        max_stale_data_seconds=60,
    )
    base.update(overrides)
    return RiskManagerLimits(**base)


def _risk_profile(**overrides) -> RiskProfileParams:
    base = dict(
        risk_pct_per_trade=Decimal("0.02"),
        max_positions=3,
        sizing_mode="fixed",
        heat_cap=Decimal("0.06"),
        ruin_threshold=Decimal("0.5"),
    )
    base.update(overrides)
    return RiskProfileParams(**base)


def _trade(**overrides) -> TradeRequest:
    base = dict(
        symbol=Symbol("BTC"),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.GTC,
        reduce_only=False,
        quantity=Decimal("1"),
        entry_price=Decimal("50000"),
        stop_price=Decimal("45000"),
        proposed_risk_amount=Decimal("1000"),
        proposed_notional=Decimal("50000"),
        proposed_margin_required=Decimal("5000"),
        leverage=Decimal("5"),
        estimated_liquidation_price=Decimal("40000"),
    )
    base.update(overrides)
    return TradeRequest(**base)


def _portfolio(**overrides) -> PortfolioSnapshot:
    base = dict(
        available_cash=Decimal("50000"),
        reserved_margin=Decimal("0"),
        used_margin=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        realized_pnl_cumulative=Decimal("0"),
        funding_cumulative=Decimal("0"),
        fees_cumulative=Decimal("0"),
        deposits_cumulative=Decimal("100000"),
        withdrawals_cumulative=Decimal("50000"),
        exposure=Decimal("0"),
        heat=Decimal("0"),
        open_position_ids=(),
        updated_at_utc=FRESH,
    )
    base.update(overrides)
    return PortfolioSnapshot(**base)


def _capabilities(**overrides) -> ExchangeCapabilities:
    base = dict(
        supports_reduce_only=True, supports_post_only=True, supports_ioc=True, supports_fok=True,
        supports_market_orders=True, supports_limit_orders=True, supports_trigger_orders=True,
        supports_partial_fill_notifications=True, supports_funding_rate=True,
        supports_cross_margin=True, supports_isolated_margin=True,
    )
    base.update(overrides)
    return ExchangeCapabilities(**base)


def _funding(**overrides) -> FundingInfo:
    base = dict(symbol=Symbol("BTC"), funding_rate=Decimal("0.0001"), as_of_utc=FRESH)
    base.update(overrides)
    return FundingInfo(**base)


def _correlation(entries=(), **overrides) -> CorrelationInfo:
    base = dict(entries=entries, as_of_utc=FRESH)
    base.update(overrides)
    return CorrelationInfo(**base)


def _full_eval_kwargs(**overrides):
    kwargs = dict(
        trade_request=_trade(),
        risk_profile=_risk_profile(),
        evaluated_at_utc=NOW,
        kill_switch_state=State.READY,
        portfolio_snapshot=_portfolio(),
        open_positions=(),
        capabilities=_capabilities(),
        funding_info=_funding(),
        correlation_info=_correlation(),
    )
    kwargs.update(overrides)
    return kwargs


class ApprovalPaths(unittest.TestCase):
    def test_clean_trade_approved(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs())
        self.assertEqual(decision.decision, Decision.APPROVED)
        self.assertEqual(decision.reason_codes, (ReasonCode.OK,))
        self.assertEqual(decision.violated_limits, ())
        self.assertIsNotNone(decision.calculated_exposure)
        self.assertIsNotNone(decision.calculated_heat)

    def test_approved_with_existing_positions_under_cap(self):
        rm = RiskManager(_limits(max_correlated_positions=5))
        pos = PositionSnapshot(
            position_id="p1", lifecycle_state=PositionLifecycleState.FULLY_FILLED, symbol=Symbol("ETH"),
            side=OrderSide.BUY, intended_quantity=Decimal("1"), filled_quantity=Decimal("1"),
            remaining_quantity=Decimal("1"), avg_entry_price=Decimal("2000"), stop_price=Decimal("1800"),
            stop_d=Decimal("0.1"), t1_price=Decimal("2300"), t2_price=Decimal("2600"), conviction=None,
            realized_pnl=Decimal("0"), realized_r=Decimal("0"), fees_paid=Decimal("0"), funding_paid=Decimal("0"),
            created_at_utc=FRESH, updated_at_utc=FRESH,
        )
        decision = rm.evaluate(**_full_eval_kwargs(
            open_positions=(pos,),
            correlation_info=_correlation((CorrelationEntry(Symbol("ETH"), Decimal("0.3")),)),
        ))
        self.assertEqual(decision.decision, Decision.APPROVED)


class RejectionReasons(unittest.TestCase):
    def test_risk_per_trade_exceeded(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(
            trade_request=_trade(proposed_risk_amount=Decimal("5000")),
        ))
        self.assertEqual(decision.decision, Decision.REJECTED)
        self.assertIn(ReasonCode.RISK_PER_TRADE_EXCEEDED, decision.reason_codes)

    def test_portfolio_heat_exceeded(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(
            portfolio_snapshot=_portfolio(heat=Decimal("0.05")),
        ))
        self.assertEqual(decision.decision, Decision.REJECTED)
        self.assertIn(ReasonCode.PORTFOLIO_HEAT_EXCEEDED, decision.reason_codes)

    def test_max_positions_exceeded(self):
        rm = RiskManager(_limits(max_correlated_positions=10))
        positions = tuple(
            PositionSnapshot(
                position_id=f"p{i}", lifecycle_state=PositionLifecycleState.FULLY_FILLED, symbol=Symbol(f"SYM{i}"),
                side=OrderSide.BUY, intended_quantity=Decimal("1"), filled_quantity=Decimal("1"),
                remaining_quantity=Decimal("1"), avg_entry_price=Decimal("100"), stop_price=Decimal("90"),
                stop_d=Decimal("0.1"), t1_price=Decimal("115"), t2_price=Decimal("130"), conviction=None,
                realized_pnl=Decimal("0"), realized_r=Decimal("0"), fees_paid=Decimal("0"), funding_paid=Decimal("0"),
                created_at_utc=FRESH, updated_at_utc=FRESH,
            )
            for i in range(3)
        )
        decision = rm.evaluate(**_full_eval_kwargs(open_positions=positions))
        self.assertEqual(decision.decision, Decision.REJECTED)
        self.assertIn(ReasonCode.MAX_POSITIONS_EXCEEDED, decision.reason_codes)

    def test_insufficient_margin(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(
            portfolio_snapshot=_portfolio(available_cash=Decimal("100")),
        ))
        self.assertEqual(decision.decision, Decision.REJECTED)
        self.assertIn(ReasonCode.INSUFFICIENT_MARGIN, decision.reason_codes)

    def test_leverage_exceeded(self):
        rm = RiskManager(_limits(max_leverage=Decimal("3")))
        decision = rm.evaluate(**_full_eval_kwargs(trade_request=_trade(leverage=Decimal("5"))))
        self.assertEqual(decision.decision, Decision.REJECTED)
        self.assertIn(ReasonCode.LEVERAGE_EXCEEDED, decision.reason_codes)

    def test_liquidation_too_close(self):
        rm = RiskManager(_limits(min_liquidation_buffer_pct=Decimal("0.5")))
        decision = rm.evaluate(**_full_eval_kwargs(
            trade_request=_trade(estimated_liquidation_price=Decimal("44000")),
        ))
        self.assertEqual(decision.decision, Decision.REJECTED)
        self.assertIn(ReasonCode.LIQUIDATION_TOO_CLOSE, decision.reason_codes)

    def test_liquidation_on_wrong_side_of_stop_is_rejected(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(
            trade_request=_trade(estimated_liquidation_price=Decimal("46000")),
        ))
        self.assertEqual(decision.decision, Decision.REJECTED)
        self.assertIn(ReasonCode.LIQUIDATION_TOO_CLOSE, decision.reason_codes)

    def test_funding_rate_too_high(self):
        rm = RiskManager(_limits(max_funding_rate_abs=Decimal("0.0001")))
        decision = rm.evaluate(**_full_eval_kwargs(funding_info=_funding(funding_rate=Decimal("0.001"))))
        self.assertEqual(decision.decision, Decision.REJECTED)
        self.assertIn(ReasonCode.FUNDING_RATE_TOO_HIGH, decision.reason_codes)

    def test_negative_funding_rate_favorable_to_long_is_not_rejected(self):
        # BUY + negative funding_rate = longs RECEIVE funding (income),
        # not an expense -- must NOT be rejected as "too expensive."
        rm = RiskManager(_limits(max_funding_rate_abs=Decimal("0.0001")))
        decision = rm.evaluate(**_full_eval_kwargs(funding_info=_funding(funding_rate=Decimal("-0.001"))))
        self.assertEqual(decision.decision, Decision.APPROVED)
        self.assertNotIn(ReasonCode.FUNDING_RATE_TOO_HIGH, decision.reason_codes)

    def test_positive_funding_rate_costly_to_long_is_rejected(self):
        # BUY + positive funding_rate = longs PAY funding -- a genuine cost.
        rm = RiskManager(_limits(max_funding_rate_abs=Decimal("0.0001")))
        decision = rm.evaluate(**_full_eval_kwargs(funding_info=_funding(funding_rate=Decimal("0.001"))))
        self.assertEqual(decision.decision, Decision.REJECTED)
        self.assertIn(ReasonCode.FUNDING_RATE_TOO_HIGH, decision.reason_codes)

    def test_positive_funding_rate_favorable_to_short_is_not_rejected(self):
        # SELL + positive funding_rate = shorts RECEIVE funding (income).
        rm = RiskManager(_limits(max_funding_rate_abs=Decimal("0.0001")))
        decision = rm.evaluate(**_full_eval_kwargs(
            trade_request=_trade(side=OrderSide.SELL, stop_price=Decimal("55000"),
                                  estimated_liquidation_price=Decimal("60000")),
            funding_info=_funding(funding_rate=Decimal("0.001")),
        ))
        self.assertEqual(decision.decision, Decision.APPROVED)
        self.assertNotIn(ReasonCode.FUNDING_RATE_TOO_HIGH, decision.reason_codes)

    def test_negative_funding_rate_costly_to_short_is_rejected(self):
        # SELL + negative funding_rate = shorts PAY funding -- a genuine cost.
        rm = RiskManager(_limits(max_funding_rate_abs=Decimal("0.0001")))
        decision = rm.evaluate(**_full_eval_kwargs(
            trade_request=_trade(side=OrderSide.SELL, stop_price=Decimal("55000"),
                                  estimated_liquidation_price=Decimal("60000")),
            funding_info=_funding(funding_rate=Decimal("-0.001")),
        ))
        self.assertEqual(decision.decision, Decision.REJECTED)
        self.assertIn(ReasonCode.FUNDING_RATE_TOO_HIGH, decision.reason_codes)

    def test_correlation_limit_exceeded(self):
        rm = RiskManager(_limits(max_correlated_positions=0))
        decision = rm.evaluate(**_full_eval_kwargs(
            correlation_info=_correlation((CorrelationEntry(Symbol("ETH"), Decimal("0.6")),)),
        ))
        self.assertEqual(decision.decision, Decision.REJECTED)
        self.assertIn(ReasonCode.CORRELATION_LIMIT_EXCEEDED, decision.reason_codes)

    def test_correlation_below_threshold_does_not_count(self):
        rm = RiskManager(_limits(max_correlated_positions=0))
        decision = rm.evaluate(**_full_eval_kwargs(
            correlation_info=_correlation((CorrelationEntry(Symbol("ETH"), Decimal("0.49")),)),
        ))
        self.assertEqual(decision.decision, Decision.APPROVED)

    def test_exchange_capability_unsupported_market_order(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(
            trade_request=_trade(order_type=OrderType.MARKET),
            capabilities=_capabilities(supports_market_orders=False),
        ))
        self.assertEqual(decision.decision, Decision.REJECTED)
        self.assertIn(ReasonCode.EXCHANGE_CAPABILITY_UNSUPPORTED, decision.reason_codes)

    def test_exchange_capability_unsupported_reduce_only(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(
            trade_request=_trade(reduce_only=True),
            capabilities=_capabilities(supports_reduce_only=False),
        ))
        self.assertEqual(decision.decision, Decision.REJECTED)
        self.assertIn(ReasonCode.EXCHANGE_CAPABILITY_UNSUPPORTED, decision.reason_codes)

    def test_multiple_violations_all_collected(self):
        rm = RiskManager(_limits(max_leverage=Decimal("3"), max_funding_rate_abs=Decimal("0.0001")))
        decision = rm.evaluate(**_full_eval_kwargs(
            trade_request=_trade(leverage=Decimal("5"), proposed_risk_amount=Decimal("5000")),
            funding_info=_funding(funding_rate=Decimal("0.001")),
        ))
        self.assertEqual(decision.decision, Decision.REJECTED)
        self.assertIn(ReasonCode.LEVERAGE_EXCEEDED, decision.reason_codes)
        self.assertIn(ReasonCode.FUNDING_RATE_TOO_HIGH, decision.reason_codes)
        self.assertIn(ReasonCode.RISK_PER_TRADE_EXCEEDED, decision.reason_codes)
        self.assertGreaterEqual(len(decision.violated_limits), 3)


class KillSwitchBehavior(unittest.TestCase):
    def test_soft_kill_blocks(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(kill_switch_state=State.SOFT_KILL))
        self.assertEqual(decision.decision, Decision.BLOCKED)
        self.assertEqual(decision.reason_codes, (ReasonCode.KILL_SWITCH_SOFT,))

    def test_hard_kill_blocks(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(kill_switch_state=State.HARD_KILL))
        self.assertEqual(decision.decision, Decision.BLOCKED)

    def test_emergency_kill_blocks(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(kill_switch_state=State.EMERGENCY_KILL))
        self.assertEqual(decision.decision, Decision.BLOCKED)
        self.assertEqual(decision.reason_codes, (ReasonCode.KILL_SWITCH_EMERGENCY,))

    def test_stopped_blocks(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(kill_switch_state=State.STOPPED))
        self.assertEqual(decision.decision, Decision.BLOCKED)
        self.assertEqual(decision.reason_codes, (ReasonCode.ENGINE_STOPPED,))

    def test_kill_switch_overrides_an_otherwise_approvable_trade(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(kill_switch_state=State.HARD_KILL))
        self.assertEqual(decision.decision, Decision.BLOCKED)

    def test_ready_state_does_not_block(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(kill_switch_state=State.READY))
        self.assertNotEqual(decision.decision, Decision.BLOCKED)


class MissingAndStaleData(unittest.TestCase):
    def test_missing_kill_switch_state_is_fail_safe(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(kill_switch_state=None))
        self.assertEqual(decision.decision, Decision.FAIL_SAFE)
        self.assertIn(ReasonCode.MISSING_REQUIRED_DATA, decision.reason_codes)

    def test_missing_portfolio_snapshot_is_fail_safe(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(portfolio_snapshot=None))
        self.assertEqual(decision.decision, Decision.FAIL_SAFE)

    def test_missing_funding_info_is_fail_safe(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(funding_info=None))
        self.assertEqual(decision.decision, Decision.FAIL_SAFE)

    def test_missing_correlation_info_is_fail_safe(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(correlation_info=None))
        self.assertEqual(decision.decision, Decision.FAIL_SAFE)

    def test_missing_liquidation_price_is_fail_safe(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(
            trade_request=_trade(estimated_liquidation_price=None),
        ))
        self.assertEqual(decision.decision, Decision.FAIL_SAFE)

    def test_stale_portfolio_snapshot_is_fail_safe(self):
        rm = RiskManager(_limits(max_stale_data_seconds=30))
        decision = rm.evaluate(**_full_eval_kwargs(portfolio_snapshot=_portfolio(updated_at_utc=STALE)))
        self.assertEqual(decision.decision, Decision.FAIL_SAFE)
        self.assertIn(ReasonCode.STALE_DATA, decision.reason_codes)

    def test_future_timestamped_data_is_fail_safe(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(portfolio_snapshot=_portfolio(updated_at_utc=FUTURE)))
        self.assertEqual(decision.decision, Decision.FAIL_SAFE)
        self.assertIn(ReasonCode.STALE_DATA, decision.reason_codes)

    def test_non_positive_equity_is_fail_safe_never_approved(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(
            portfolio_snapshot=_portfolio(deposits_cumulative=Decimal("0"), withdrawals_cumulative=Decimal("0")),
        ))
        self.assertEqual(decision.decision, Decision.FAIL_SAFE)
        self.assertIn(ReasonCode.NON_POSITIVE_EQUITY, decision.reason_codes)

    def test_fail_safe_never_approves_even_with_perfect_trade(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(kill_switch_state=None))
        self.assertNotEqual(decision.decision, Decision.APPROVED)


class InvalidConfiguration(unittest.TestCase):
    def test_negative_max_leverage_rejected_at_construction(self):
        with self.assertRaises(RiskManagerConfigurationError):
            _limits(max_leverage=Decimal("-1"))

    def test_negative_max_funding_rejected(self):
        with self.assertRaises(RiskManagerConfigurationError):
            _limits(max_funding_rate_abs=Decimal("-0.01"))

    def test_non_decimal_leverage_in_trade_rejected(self):
        with self.assertRaises(RiskManagerConfigurationError):
            _trade(leverage=5.0)

    def test_manager_requires_risk_manager_limits_type(self):
        with self.assertRaises(RiskManagerConfigurationError):
            RiskManager("not-a-limits-object")

    def test_immutable_after_construction(self):
        rm = RiskManager(_limits())
        with self.assertRaises(AttributeError):
            rm._limits = _limits()

    def test_correlation_out_of_range_rejected(self):
        with self.assertRaises(RiskManagerConfigurationError):
            CorrelationEntry(Symbol("BTC"), Decimal("1.5"))

    def test_risk_profile_with_negative_heat_cap_rejected(self):
        rm = RiskManager(_limits())
        bad_profile = _risk_profile(heat_cap=Decimal("-0.05"))
        with self.assertRaises(RiskManagerConfigurationError):
            rm.evaluate(**_full_eval_kwargs(risk_profile=bad_profile))

    def test_risk_profile_with_zero_risk_pct_per_trade_rejected(self):
        rm = RiskManager(_limits())
        bad_profile = _risk_profile(risk_pct_per_trade=Decimal("0"))
        with self.assertRaises(RiskManagerConfigurationError):
            rm.evaluate(**_full_eval_kwargs(risk_profile=bad_profile))

    def test_risk_profile_with_zero_max_positions_rejected(self):
        rm = RiskManager(_limits())
        bad_profile = _risk_profile(max_positions=0)
        with self.assertRaises(RiskManagerConfigurationError):
            rm.evaluate(**_full_eval_kwargs(risk_profile=bad_profile))

    def test_valid_risk_profile_still_works_normally(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs())
        self.assertEqual(decision.decision, Decision.APPROVED)


class DecimalContextIsolation(unittest.TestCase):
    def test_result_unaffected_by_ambient_context_precision(self):
        import decimal

        rm = RiskManager(_limits())
        kwargs = _full_eval_kwargs()
        baseline = rm.evaluate(**kwargs)

        original_prec = decimal.getcontext().prec
        original_rounding = decimal.getcontext().rounding
        try:
            decimal.getcontext().prec = 3  # deliberately corrupt the ambient context
            decimal.getcontext().rounding = decimal.ROUND_DOWN
            under_corrupted_context = rm.evaluate(**kwargs)
        finally:
            decimal.getcontext().prec = original_prec
            decimal.getcontext().rounding = original_rounding

        self.assertEqual(baseline.decision, under_corrupted_context.decision)
        self.assertEqual(baseline.calculated_heat, under_corrupted_context.calculated_heat)
        self.assertEqual(baseline.calculated_exposure, under_corrupted_context.calculated_exposure)
        self.assertEqual(baseline.funding_estimate, under_corrupted_context.funding_estimate)

    def test_result_unaffected_by_ambient_context_in_thread(self):
        import decimal
        import threading

        rm = RiskManager(_limits())
        kwargs = _full_eval_kwargs()
        results = {}

        def corrupted_thread():
            decimal.getcontext().prec = 2
            decimal.getcontext().rounding = decimal.ROUND_CEILING
            results["corrupted"] = rm.evaluate(**kwargs)

        t = threading.Thread(target=corrupted_thread)
        t.start()
        t.join()

        normal = rm.evaluate(**kwargs)
        self.assertEqual(normal.decision, results["corrupted"].decision)
        self.assertEqual(normal.calculated_heat, results["corrupted"].calculated_heat)


class BoundaryValues(unittest.TestCase):
    def test_exactly_at_risk_pct_limit_is_approved(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(
            trade_request=_trade(proposed_risk_amount=Decimal("1000")),
            risk_profile=_risk_profile(risk_pct_per_trade=Decimal("0.02")),
        ))
        self.assertEqual(decision.decision, Decision.APPROVED)

    def test_one_cent_over_risk_pct_limit_is_rejected(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(
            trade_request=_trade(proposed_risk_amount=Decimal("1000.01")),
            risk_profile=_risk_profile(risk_pct_per_trade=Decimal("0.02")),
        ))
        self.assertEqual(decision.decision, Decision.REJECTED)

    def test_exactly_at_max_positions_is_rejected(self):
        rm = RiskManager(_limits(max_correlated_positions=10))
        positions = tuple(
            PositionSnapshot(
                position_id=f"p{i}", lifecycle_state=PositionLifecycleState.FULLY_FILLED, symbol=Symbol(f"S{i}"),
                side=OrderSide.BUY, intended_quantity=Decimal("1"), filled_quantity=Decimal("1"),
                remaining_quantity=Decimal("1"), avg_entry_price=Decimal("100"), stop_price=Decimal("90"),
                stop_d=Decimal("0.1"), t1_price=Decimal("115"), t2_price=Decimal("130"), conviction=None,
                realized_pnl=Decimal("0"), realized_r=Decimal("0"), fees_paid=Decimal("0"), funding_paid=Decimal("0"),
                created_at_utc=FRESH, updated_at_utc=FRESH,
            )
            for i in range(3)
        )
        decision = rm.evaluate(**_full_eval_kwargs(open_positions=positions))
        self.assertEqual(decision.decision, Decision.REJECTED)

    def test_correlation_exactly_at_threshold_counts(self):
        rm = RiskManager(_limits(max_correlated_positions=0))
        decision = rm.evaluate(**_full_eval_kwargs(
            correlation_info=_correlation((CorrelationEntry(Symbol("ETH"), Decimal("0.5")),)),
        ))
        self.assertEqual(decision.decision, Decision.REJECTED)

    def test_stale_data_exactly_at_threshold_is_ok(self):
        rm = RiskManager(_limits(max_stale_data_seconds=60))
        exactly_60s_old = "2026-07-15T11:59:00+00:00"
        decision = rm.evaluate(**_full_eval_kwargs(portfolio_snapshot=_portfolio(updated_at_utc=exactly_60s_old)))
        self.assertNotEqual(decision.decision, Decision.FAIL_SAFE)

    def test_one_second_past_stale_threshold_fails_safe(self):
        rm = RiskManager(_limits(max_stale_data_seconds=60))
        just_over = "2026-07-15T11:58:59+00:00"
        decision = rm.evaluate(**_full_eval_kwargs(portfolio_snapshot=_portfolio(updated_at_utc=just_over)))
        self.assertEqual(decision.decision, Decision.FAIL_SAFE)


class DecimalPrecision(unittest.TestCase):
    def test_no_float_anywhere_in_decision(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs())
        for value in (decision.calculated_exposure, decision.calculated_heat, decision.leverage,
                      decision.liquidation_buffer, decision.funding_estimate):
            if value is not None:
                self.assertIsInstance(value, Decimal)
                self.assertNotIsInstance(value, float)

    def test_precise_fraction_boundary_no_rounding_error(self):
        rm = RiskManager(_limits())
        decision = rm.evaluate(**_full_eval_kwargs(
            trade_request=_trade(proposed_risk_amount=Decimal("999.999999999999999999")),
            portfolio_snapshot=_portfolio(available_cash=Decimal("999999999999999999999")),
        ))
        self.assertIsInstance(decision.calculated_heat, Decimal)


class DeterminismAndConcurrency(unittest.TestCase):
    def test_same_inputs_always_produce_same_decision(self):
        rm = RiskManager(_limits())
        kwargs = _full_eval_kwargs()
        results = [rm.evaluate(**kwargs) for _ in range(20)]
        self.assertTrue(all(r.decision == results[0].decision for r in results))
        self.assertTrue(all(r.calculated_heat == results[0].calculated_heat for r in results))
        self.assertTrue(all(r.reason_codes == results[0].reason_codes for r in results))

    def test_concurrent_evaluations_are_independent_and_correct(self):
        rm = RiskManager(_limits())
        results = []
        lock = threading.Lock()

        def worker(risk_amount):
            decision = rm.evaluate(**_full_eval_kwargs(trade_request=_trade(proposed_risk_amount=risk_amount)))
            with lock:
                results.append((risk_amount, decision.decision))

        threads = [threading.Thread(target=worker, args=(Decimal(v),)) for v in ["500", "1000", "1500", "5000"]]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        results_by_amount = dict(results)
        self.assertEqual(results_by_amount[Decimal("500")], Decision.APPROVED)
        self.assertEqual(results_by_amount[Decimal("1000")], Decision.APPROVED)
        self.assertEqual(results_by_amount[Decimal("1500")], Decision.REJECTED)
        self.assertEqual(results_by_amount[Decimal("5000")], Decision.REJECTED)


if __name__ == "__main__":
    unittest.main()
