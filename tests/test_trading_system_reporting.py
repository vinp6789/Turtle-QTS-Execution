"""Verification tests for trading_system.reporting (Milestone 9).

EngineSnapshot instances are constructed directly (not via
capture_snapshot) so reporting's formatting logic can be exercised
against edge cases (rejections, mismatches, no-cycle-yet) without needing
a full running Engine for every case.
"""

import unittest
from decimal import Decimal

from exchange_adapter import (
    ConnectionState,
    HealthStatus,
    OrderSide,
    OrderType,
    ReconciliationReport,
    Symbol,
    TimeInForce,
)
from execution_state_machine import State
from order_manager import OrderLifecycleState, OrderSnapshot
from portfolio_manager import PortfolioSnapshot
from risk_manager import Decision, ReasonCode, RiskDecision, TradeRequest

from trading_system.execution import ExecutionOperation, ExecutionResult
from trading_system.monitoring import EngineSnapshot
from trading_system.portfolio_construction import ConstructionResult, RejectedTrade
from trading_system.reporting import (
    ReportingError,
    cycle_summary,
    execution_summary,
    portfolio_summary,
    reconciliation_summary,
    risk_summary,
)
from trading_system.strategy import TradeIntent

_NOW = "2026-01-01T00:00:00+00:00"


def _health(**overrides):
    fields = dict(
        connection_state=ConnectionState.CONNECTED, websocket_connected=False, rest_reachable=True,
        last_message_age_ms=0.0, sequence_gap_detected=False, checked_at_utc=_NOW,
    )
    fields.update(overrides)
    return HealthStatus(**fields)


def _portfolio_snapshot(**overrides):
    fields = dict(
        available_cash=Decimal("50000"), reserved_margin=Decimal("0"), used_margin=Decimal("10000"),
        unrealized_pnl=Decimal("500"), realized_pnl_cumulative=Decimal("1000"), funding_cumulative=Decimal("0"),
        fees_cumulative=Decimal("10"), deposits_cumulative=Decimal("60000"), withdrawals_cumulative=Decimal("0"),
        exposure=Decimal("10000"), heat=Decimal("0.02"), open_position_ids=("pos-1",), updated_at_utc=_NOW,
    )
    fields.update(overrides)
    return PortfolioSnapshot(**fields)


def _snapshot(**overrides):
    fields = dict(
        captured_at_utc=_NOW, health=_health(), current_state=State.READY, is_kill_switch_active=False,
        is_started=True, open_order_count=0, position_count=1, portfolio_snapshot=_portfolio_snapshot(),
        reconciliation=ReconciliationReport(matches=True, local_positions=(), exchange_positions=(), discrepancies=(), checked_at_utc=_NOW),
    )
    fields.update(overrides)
    return EngineSnapshot(**fields)


def _order_snapshot(**overrides):
    fields = dict(
        client_order_id="co-1", lifecycle_state=OrderLifecycleState.ACKNOWLEDGED, exchange_order_id="ex-1",
        symbol=Symbol("BTC"), side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=Decimal("1"),
        filled_quantity=Decimal("0"), limit_price=Decimal("100"), time_in_force=TimeInForce.GTC,
        reduce_only=False, created_at_utc=_NOW, updated_at_utc=_NOW,
    )
    fields.update(overrides)
    return OrderSnapshot(**fields)


def _trade_intent(**overrides):
    fields = dict(
        symbol=Symbol("BTC"), side=OrderSide.BUY, order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.GTC, reduce_only=False, stop_price=Decimal("90"),
    )
    fields.update(overrides)
    return TradeIntent(**fields)


def _trade_request(**overrides):
    fields = dict(
        symbol=Symbol("BTC"), side=OrderSide.BUY, order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.GTC, reduce_only=False, quantity=Decimal("1"),
        entry_price=Decimal("100"), stop_price=Decimal("90"), proposed_risk_amount=Decimal("100"),
        proposed_notional=Decimal("100"), proposed_margin_required=Decimal("100"),
        leverage=Decimal("1"), estimated_liquidation_price=Decimal("50"),
    )
    fields.update(overrides)
    return TradeRequest(**fields)


def _rejected_decision(*reason_codes):
    return RiskDecision(
        decision=Decision.REJECTED, reason_codes=reason_codes, violated_limits=(), calculated_exposure=None,
        calculated_heat=None, leverage=None, liquidation_buffer=None, funding_estimate=None,
        timestamp_utc=_NOW, audit_metadata={},
    )


class TestPortfolioSummary(unittest.TestCase):
    def test_includes_key_figures(self):
        text = portfolio_summary(_snapshot())
        self.assertIn("Equity:", text)
        self.assertIn("Available cash: 50000", text)
        self.assertIn("Open positions: 1", text)

    def test_rejects_wrong_type(self):
        with self.assertRaises(ReportingError):
            portfolio_summary("not a snapshot")


class TestExecutionSummary(unittest.TestCase):
    def test_no_executions_message(self):
        self.assertEqual(execution_summary(_snapshot()), "No executions in the last completed cycle.")

    def test_lists_each_execution(self):
        execution = ExecutionResult(operation=ExecutionOperation.PLACE, order_snapshot=_order_snapshot())
        text = execution_summary(_snapshot(last_cycle_executions=(execution,)))
        self.assertIn("1 execution(s)", text)
        self.assertIn("PLACE", text)
        self.assertIn("BTC", text)
        self.assertIn("co-1", text)


class TestCycleSummary(unittest.TestCase):
    def test_no_cycle_message(self):
        self.assertEqual(cycle_summary(_snapshot()), "No cycle has completed yet.")

    def test_summarizes_a_completed_cycle(self):
        construction = ConstructionResult(
            approved=(_trade_request(),),
            rejected=(RejectedTrade(intent=_trade_intent(), trade_request=_trade_request(), decision=_rejected_decision(ReasonCode.INSUFFICIENT_MARGIN)),),
            skipped=(),
        )
        text = cycle_summary(_snapshot(
            last_cycle_completed_at_utc=_NOW, last_cycle_construction=construction,
            last_cycle_executions=(ExecutionResult(operation=ExecutionOperation.PLACE, order_snapshot=_order_snapshot()),),
            last_cycle_resynced_order_count=2,
        ))
        self.assertIn("Resynced orders: 2", text)
        self.assertIn("Approved: 1, Rejected: 1, Skipped: 0", text)
        self.assertIn("Executions: 1", text)


class TestRiskSummary(unittest.TestCase):
    def test_no_rejections_message(self):
        text = risk_summary(_snapshot())
        self.assertIn("No rejected trades in the last cycle.", text)
        self.assertIn("Kill switch active: False", text)

    def test_lists_rejection_reasons(self):
        construction = ConstructionResult(
            approved=(),
            rejected=(RejectedTrade(intent=_trade_intent(), trade_request=_trade_request(), decision=_rejected_decision(ReasonCode.INSUFFICIENT_MARGIN, ReasonCode.LEVERAGE_EXCEEDED)),),
            skipped=(),
        )
        text = risk_summary(_snapshot(last_cycle_construction=construction))
        self.assertIn("1 rejected trade(s)", text)
        self.assertIn("INSUFFICIENT_MARGIN", text)
        self.assertIn("LEVERAGE_EXCEEDED", text)

    def test_reflects_kill_switch_active(self):
        text = risk_summary(_snapshot(current_state=State.HARD_KILL, is_kill_switch_active=True))
        self.assertIn("Kill switch active: True", text)
        self.assertIn("HARD_KILL", text)


class TestReconciliationSummary(unittest.TestCase):
    def test_unavailable_when_none(self):
        text = reconciliation_summary(_snapshot(reconciliation=None))
        self.assertIn("unavailable", text)

    def test_ok_when_matching(self):
        text = reconciliation_summary(_snapshot())
        self.assertIn("Reconciliation OK", text)

    def test_lists_discrepancies_when_mismatched(self):
        report = ReconciliationReport(
            matches=False, local_positions=(), exchange_positions=(), discrepancies=("BTC: local=0 exchange=1",),
            checked_at_utc=_NOW,
        )
        text = reconciliation_summary(_snapshot(reconciliation=report))
        self.assertIn("MISMATCH", text)
        self.assertIn("BTC: local=0 exchange=1", text)


if __name__ == "__main__":
    unittest.main()
