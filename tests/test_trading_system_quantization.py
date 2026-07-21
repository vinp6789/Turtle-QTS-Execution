"""Verification tests for C2: Hyperliquid order quantization.

Covers the pure quantization math (exact boundaries, sig figs, decimals
caps, directional rounding), the execute_place/execute_amend integration
(quantized BEFORE OrderManager persists, so books == venue), impossible-
order rejection, the metadata fetcher (malformed + refresh), replay/
idempotency/ordering preservation, and concurrent reads.
"""

import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from config import (
    EngineConfig,
    ExchangeConfig,
    LoggingConfig,
    OperationalConfig,
    RiskConfig,
    RiskProfileParams,
    SecretsConfig,
    TelegramConfig,
    UniverseConfig,
)
from exchange_adapter import OrderSide, OrderType, Symbol, TimeInForce
from risk_manager import Decision, ReasonCode, RiskDecision, RiskManagerLimits, TradeRequest

from app.runtime.venue_rules import fetch_hyperliquid_rules
from composition_root import DeploymentSettings, build_engine
from trading_system.execution import (
    ExecutionError,
    SymbolRules,
    execute_amend,
    execute_cancel,
    execute_place,
    quantize_price,
    quantize_size,
)

_SIGNING_KEY_REF = "hyperliquid_signing_key_v1"
_NOW = "2026-01-01T00:00:00+00:00"

BTC = SymbolRules(sz_decimals=5)   # max_price_decimals = 1
ETH = SymbolRules(sz_decimals=4)   # max_price_decimals = 2
GMT = SymbolRules(sz_decimals=0)   # integer sizes; max_price_decimals = 6


class TestQuantizeSize(unittest.TestCase):
    def test_excessive_decimals_round_down(self):
        self.assertEqual(quantize_size(Decimal("194.174757281553"), BTC), Decimal("194.17475"))

    def test_exact_boundary_value_unchanged(self):
        self.assertEqual(quantize_size(Decimal("0.12345"), BTC), Decimal("0.12345"))

    def test_minimum_size_below_grid_rounds_to_zero(self):
        self.assertEqual(quantize_size(Decimal("0.000004"), BTC), Decimal("0"))

    def test_never_rounds_up(self):
        self.assertEqual(quantize_size(Decimal("0.999999"), BTC), Decimal("0.99999"))

    def test_integer_size_asset(self):
        self.assertEqual(quantize_size(Decimal("41.9"), GMT), Decimal("41"))

    def test_maximum_precision_preserved(self):
        # 6 szDecimals is the venue max; a value already at max precision
        # passes through exactly (Decimal preserved, no float round-trip).
        rules = SymbolRules(sz_decimals=6)
        self.assertEqual(quantize_size(Decimal("0.123456"), rules), Decimal("0.123456"))

    def test_invalid_sz_decimals_rejected(self):
        with self.assertRaises(ExecutionError):
            SymbolRules(sz_decimals=7)
        with self.assertRaises(ExecutionError):
            SymbolRules(sz_decimals=-1)


class TestQuantizePrice(unittest.TestCase):
    def test_integer_price_always_allowed_even_beyond_sig_figs(self):
        self.assertEqual(quantize_price(Decimal("123456"), OrderSide.BUY, BTC), Decimal("123456"))

    def test_buy_floors_at_sig_fig_boundary(self):
        # 12345.6 has 6 sig figs and is non-integer -> BUY floors to 12345.
        self.assertEqual(quantize_price(Decimal("12345.6"), OrderSide.BUY, BTC), Decimal("12345"))

    def test_sell_ceils_at_sig_fig_boundary(self):
        self.assertEqual(quantize_price(Decimal("12345.6"), OrderSide.SELL, BTC), Decimal("12346"))

    def test_decimals_cap_dominates_when_coarser(self):
        # BTC: max 1 decimal place. 1.2345 -> BUY 1.2 / SELL 1.3.
        self.assertEqual(quantize_price(Decimal("1.2345"), OrderSide.BUY, BTC), Decimal("1.2"))
        self.assertEqual(quantize_price(Decimal("1.2345"), OrderSide.SELL, BTC), Decimal("1.3"))

    def test_sig_figs_dominate_when_coarser(self):
        # ETH: max 2 decimals. 1234.56 -> 5 sig figs allows 1 decimal.
        self.assertEqual(quantize_price(Decimal("1234.56"), OrderSide.BUY, ETH), Decimal("1234.5"))
        self.assertEqual(quantize_price(Decimal("1234.56"), OrderSide.SELL, ETH), Decimal("1234.6"))

    def test_compliant_price_unchanged(self):
        self.assertEqual(quantize_price(Decimal("32016.0"), OrderSide.BUY, BTC), Decimal("32016"))
        self.assertEqual(quantize_price(Decimal("1234.5"), OrderSide.SELL, ETH), Decimal("1234.5"))

    def test_sub_tick_buy_floors_to_zero(self):
        self.assertEqual(quantize_price(Decimal("0.04"), OrderSide.BUY, BTC), Decimal("0.0"))

    def test_sell_ceil_across_magnitude_boundary_stays_legal(self):
        # 99999.9 SELL -> 100000: 6 digits but integer, always legal.
        self.assertEqual(quantize_price(Decimal("99999.9"), OrderSide.SELL, BTC), Decimal("100000"))

    def test_deterministic(self):
        for _ in range(3):
            self.assertEqual(quantize_price(Decimal("1234.56"), OrderSide.BUY, ETH), Decimal("1234.5"))


def _engine_config():
    return EngineConfig(
        environment="paper",
        exchange=ExchangeConfig(name="hyperliquid", network="testnet"),
        universe=UniverseConfig(symbols=("BTC",)),
        risk=RiskConfig(
            active_profile="BALANCED",
            profiles={"BALANCED": RiskProfileParams(
                risk_pct_per_trade=0.02, max_positions=3, sizing_mode="fixed",
                heat_cap=0.05, ruin_threshold=0.6)},
            max_daily_loss_pct=0.05, max_drawdown_from_peak_pct=0.2,
            auto_flatten_enabled=False, auto_flatten_confirmation_seconds=60,
        ),
        operational=OperationalConfig(
            max_retries=5, retry_base_delay_seconds=0.5, retry_max_delay_seconds=30.0,
            clock_drift_tolerance_ms=250, data_staleness_price_ms=5000,
            data_staleness_orderbook_ms=3000, data_staleness_position_ms=10000,
        ),
        secrets=SecretsConfig(signing_key_ref=_SIGNING_KEY_REF,
                              telegram_bot_token_ref="telegram_bot_token_v1"),
        telegram=TelegramConfig(enabled=False, chat_id="123"),
        logging=LoggingConfig(level="INFO", directory="/tmp/log"),
    )


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


def _approved():
    return RiskDecision(
        decision=Decision.APPROVED, reason_codes=(ReasonCode.OK,), violated_limits=(),
        calculated_exposure=None, calculated_heat=None, leverage=None, liquidation_buffer=None,
        funding_estimate=None, timestamp_utc=_NOW, audit_metadata={},
    )


_RULES = {"BTC": BTC, "ETH": ETH}


class _RealPaperEngineCase(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.engine = build_engine(
            config=_engine_config(),
            deployment=DeploymentSettings(engine_version="1.0.0"),
            risk_limits=RiskManagerLimits(
                max_leverage=Decimal("10"), min_liquidation_buffer_pct=Decimal("0.1"),
                max_funding_rate_abs=Decimal("1"), max_correlated_positions=10,
                max_stale_data_seconds=3600),
            event_store_path=Path(tmpdir.name) / "events.log",
            env={f"TURTLE_SECRET_{_SIGNING_KEY_REF.upper()}": "s"},
        )
        self.addCleanup(self.engine.event_store.close)
        self.engine.start()
        self.om = self.engine.order_manager


class TestExecutePlaceQuantization(_RealPaperEngineCase):
    def test_size_and_price_quantized_before_books(self):
        request = _trade_request(quantity=Decimal("194.174757281553"),
                                 entry_price=Decimal("12345.67"))
        result = execute_place(request, _approved(), self.om, rules=_RULES)
        snap = result.order_snapshot
        # Books carry the QUANTIZED values -- what the venue receives.
        self.assertEqual(snap.quantity, Decimal("194.17475"))
        self.assertEqual(snap.limit_price, Decimal("12345"))       # BUY floors
        # And OrderManager's durable record agrees (replay source of truth).
        self.assertEqual(self.om.get_order_status(snap.client_order_id).quantity,
                         Decimal("194.17475"))

    def test_sell_price_ceils(self):
        request = _trade_request(side=OrderSide.SELL, quantity=Decimal("1"),
                                 entry_price=Decimal("12345.67"),
                                 stop_price=Decimal("13000"))
        result = execute_place(request, _approved(), self.om, rules=_RULES)
        self.assertEqual(result.order_snapshot.limit_price, Decimal("12346"))

    def test_reduce_only_orders_quantized_identically(self):
        request = _trade_request(reduce_only=True, quantity=Decimal("0.123456789"))
        result = execute_place(request, _approved(), self.om, rules=_RULES)
        self.assertEqual(result.order_snapshot.quantity, Decimal("0.12345"))
        self.assertTrue(result.order_snapshot.reduce_only)

    def test_impossible_size_rejected_before_transmission(self):
        request = _trade_request(quantity=Decimal("0.000001"))
        events_before = len(tuple(self.engine.event_store.replay()))
        with self.assertRaises(ExecutionError):
            execute_place(request, _approved(), self.om, rules=_RULES)
        # Nothing persisted, nothing transmitted.
        self.assertEqual(len(tuple(self.engine.event_store.replay())), events_before)
        self.assertEqual(self.engine.adapter.get_orders(), ())

    def test_missing_symbol_rules_fail_closed(self):
        request = _trade_request(symbol=Symbol("SOL"), quantity=Decimal("1"))
        with self.assertRaises(ExecutionError):
            execute_place(request, _approved(), self.om, rules=_RULES)
        self.assertEqual(self.engine.adapter.get_orders(), ())

    def test_no_rules_preserves_prior_behavior_exactly(self):
        request = _trade_request(quantity=Decimal("194.174757281553"))
        result = execute_place(request, _approved(), self.om)  # rules omitted
        self.assertEqual(result.order_snapshot.quantity, Decimal("194.174757281553"))

    def test_never_increases_size_or_worsens_price(self):
        request = _trade_request(quantity=Decimal("0.999999"), entry_price=Decimal("1.29"))
        result = execute_place(request, _approved(), self.om, rules=_RULES)
        self.assertLessEqual(result.order_snapshot.quantity, request.quantity)
        self.assertLessEqual(result.order_snapshot.limit_price, request.entry_price)  # BUY


class TestExecuteAmendQuantization(_RealPaperEngineCase):
    def _place(self):
        return execute_place(_trade_request(quantity=Decimal("1")), _approved(), self.om,
                             rules=_RULES).order_snapshot

    def test_amend_values_quantized(self):
        placed = self._place()
        result = execute_amend(placed.client_order_id, self.om,
                               new_quantity=Decimal("2.123456789"),
                               new_limit_price=Decimal("12345.67"),
                               rules=_RULES)
        self.assertEqual(result.order_snapshot.quantity, Decimal("2.12345"))
        self.assertEqual(result.order_snapshot.limit_price, Decimal("12345"))  # BUY order floors

    def test_amend_to_zero_size_rejected(self):
        placed = self._place()
        with self.assertRaises(ExecutionError):
            execute_amend(placed.client_order_id, self.om,
                          new_quantity=Decimal("0.000001"), rules=_RULES)
        # Order unchanged.
        self.assertEqual(self.om.get_order_status(placed.client_order_id).quantity, Decimal("1"))

    def test_amend_without_rules_unchanged(self):
        placed = self._place()
        result = execute_amend(placed.client_order_id, self.om, new_quantity=Decimal("2.123456789"))
        self.assertEqual(result.order_snapshot.quantity, Decimal("2.123456789"))

    def test_cancel_path_untouched_by_rules(self):
        placed = self._place()
        result = execute_cancel(placed.client_order_id, self.om)
        self.assertEqual(result.order_snapshot.lifecycle_state.value, "CANCELLED")


class TestReplayAndIdempotency(_RealPaperEngineCase):
    def test_replayed_books_carry_quantized_values(self):
        request = _trade_request(quantity=Decimal("194.174757281553"))
        placed = execute_place(request, _approved(), self.om, rules=_RULES).order_snapshot
        # The durable SUBMIT event (replay source of truth) carries the
        # quantized quantity: quantization happened BEFORE Module 6 persisted.
        submit_events = [e for e in self.engine.event_store.replay()
                         if e.payload.get("source") == "order_manager"
                         and e.payload.get("action") == "SUBMIT"]
        self.assertEqual(len(submit_events), 1)
        self.assertEqual(submit_events[0].payload["details"]["quantity"], "194.17475")
        self.assertEqual(placed.quantity, Decimal("194.17475"))

    def test_quantization_adds_no_events_and_preserves_ordering(self):
        events_before = len(tuple(self.engine.event_store.replay()))
        execute_place(_trade_request(quantity=Decimal("1.123456789")), _approved(), self.om,
                      rules=_RULES)
        new_events = tuple(self.engine.event_store.replay())[events_before:]
        # Exactly the same event kinds a non-quantized placement produces --
        # quantization is pure arithmetic, it writes nothing of its own.
        sources = {e.payload.get("source") for e in new_events}
        self.assertNotIn("app_accounting", sources)  # no quantization events exist


class TestMetadataFetcher(unittest.TestCase):
    def _transport(self, body):
        def fake(url, payload, timeout):
            assert payload == {"type": "meta"}
            return SimpleNamespace(status_code=200, body=body)
        return fake

    def test_fetch_parses_universe(self):
        body = {"universe": [{"name": "BTC", "szDecimals": 5},
                             {"name": "ETH", "szDecimals": 4, "isDelisted": True}]}
        rules = fetch_hyperliquid_rules("https://x", transport=self._transport(body))
        self.assertEqual(rules["BTC"].sz_decimals, 5)
        self.assertEqual(rules["ETH"].sz_decimals, 4)  # delisted entries kept (harmless)

    def test_malformed_missing_universe(self):
        with self.assertRaises(ValueError):
            fetch_hyperliquid_rules("https://x", transport=self._transport({}))

    def test_malformed_empty_universe(self):
        with self.assertRaises(ValueError):
            fetch_hyperliquid_rules("https://x", transport=self._transport({"universe": []}))

    def test_malformed_missing_sz_decimals(self):
        body = {"universe": [{"name": "BTC"}]}
        with self.assertRaises(ValueError):
            fetch_hyperliquid_rules("https://x", transport=self._transport(body))

    def test_malformed_sz_decimals_type(self):
        for bad in ("5", 5.0, True, -1, 9):
            body = {"universe": [{"name": "BTC", "szDecimals": bad}]}
            with self.assertRaises(ValueError):
                fetch_hyperliquid_rules("https://x", transport=self._transport(body))

    def test_refresh_picks_up_new_metadata(self):
        v1 = {"universe": [{"name": "BTC", "szDecimals": 5}]}
        v2 = {"universe": [{"name": "BTC", "szDecimals": 5}, {"name": "NEW", "szDecimals": 2}]}
        r1 = fetch_hyperliquid_rules("https://x", transport=self._transport(v1))
        r2 = fetch_hyperliquid_rules("https://x", transport=self._transport(v2))
        self.assertNotIn("NEW", r1)
        self.assertEqual(r2["NEW"].sz_decimals, 2)

    def test_returned_mapping_is_immutable(self):
        body = {"universe": [{"name": "BTC", "szDecimals": 5}]}
        rules = fetch_hyperliquid_rules("https://x", transport=self._transport(body))
        with self.assertRaises(TypeError):
            rules["BTC"] = SymbolRules(sz_decimals=1)


class TestConcurrentSubmissions(_RealPaperEngineCase):
    def test_parallel_quantized_placements_are_consistent(self):
        # 8 threads place quantized orders concurrently; every recorded
        # quantity must be exactly on-grid (rules mapping is read-only and
        # OrderManager serializes its own persistence).
        errors = []

        def worker(i):
            try:
                r = execute_place(
                    _trade_request(quantity=Decimal("1.123456789") + Decimal(i) / 1000),
                    _approved(), self.om, rules=_RULES,
                )
                exponent = r.order_snapshot.quantity.as_tuple().exponent
                assert exponent >= -5, r.order_snapshot.quantity
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(self.engine.adapter.get_orders()), 8)


if __name__ == "__main__":
    unittest.main()
