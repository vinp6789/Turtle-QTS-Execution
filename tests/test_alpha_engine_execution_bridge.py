"""Verification tests for the execution bridge (Alpha Engine R6).

Uses the same real paper-mode Engine + MockExchangeAdapter fixture
pattern as tests/test_alpha_engine_funding_rate_provider.py; a real
StrategyContext is constructed exactly the way run_cycle builds one.
Synthetic fixture data throughout.
"""

import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

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
from exchange_adapter import FundingRate, MarkPrice, OrderSide, OrderType, Symbol, TimeInForce
from execution_state_machine import State
from risk_manager import RiskManagerLimits

from composition_root import DeploymentSettings, build_engine
from trading_system.market_data import MarketDataView
from trading_system.strategy import Strategy, StrategyContext

from alpha_engine.candidates import CandidateSpecification, funding_rate_candidate_specification, \
    open_interest_candidate_specification
from alpha_engine.execution_bridge import (
    STRATEGY_NAME,
    ApprovedFundingAlphaStrategy,
    ExecutionBridgeError,
    load_approved_specifications,
)
from alpha_engine.governance import GovernanceDecision, GovernanceDecisionType, record_governance_decision
from alpha_engine.registry import ExperimentRegistry, LifecycleState, RegistryStorage
from alpha_engine.watchlist import Watchlist

_SIGNING_KEY_REF = "hyperliquid_signing_key_v1"
_EVALUATED_AT = "2026-01-01T00:00:00+00:00"


class _InMemoryStorage(RegistryStorage):
    def __init__(self):
        self._entries = []

    def append(self, entry):
        self._entries.append(dict(entry))

    def read_all(self):
        return list(self._entries)


def _engine_config():
    return EngineConfig(
        environment="paper",
        exchange=ExchangeConfig(name="hyperliquid", network="testnet"),
        universe=UniverseConfig(symbols=("BTC",)),
        risk=RiskConfig(
            active_profile="BALANCED",
            profiles={"BALANCED": RiskProfileParams(
                risk_pct_per_trade=0.01, max_positions=3, sizing_mode="fixed",
                heat_cap=0.05, ruin_threshold=0.6,
            )},
            max_daily_loss_pct=0.05, max_drawdown_from_peak_pct=0.2,
            auto_flatten_enabled=False, auto_flatten_confirmation_seconds=60,
        ),
        operational=OperationalConfig(
            max_retries=5, retry_base_delay_seconds=0.5, retry_max_delay_seconds=30.0,
            clock_drift_tolerance_ms=250, data_staleness_price_ms=5000,
            data_staleness_orderbook_ms=3000, data_staleness_position_ms=10000,
        ),
        secrets=SecretsConfig(signing_key_ref=_SIGNING_KEY_REF, telegram_bot_token_ref="telegram_bot_token_v1"),
        telegram=TelegramConfig(enabled=False, chat_id="123"),
        logging=LoggingConfig(level="INFO", directory="/tmp/log"),
    )


def _spec(threshold="0.0005", stop_fraction="0.02", t1_fraction="0.03", t2_fraction="0.06",
          direction_convention=None, symbols=("BTC",), version="v1"):
    parameters = {"threshold": threshold, "stop_fraction": stop_fraction}
    if t1_fraction is not None:
        parameters["t1_fraction"] = t1_fraction
    if t2_fraction is not None:
        parameters["t2_fraction"] = t2_fraction
    if direction_convention is not None:
        parameters["direction_convention"] = direction_convention
    return funding_rate_candidate_specification(
        version=version, universe=tuple(Symbol(s) for s in symbols), cadence_seconds=60,
        parameters=parameters, acceptance_criteria={"min_hit_rate": 0.5},
    )


class _BridgeEngineCase(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.engine = build_engine(
            config=_engine_config(),
            deployment=DeploymentSettings(engine_version="1.0.0"),
            risk_limits=RiskManagerLimits(
                max_leverage=Decimal("5"), min_liquidation_buffer_pct=Decimal("0.1"),
                max_funding_rate_abs=Decimal("0.01"), max_correlated_positions=3,
                max_stale_data_seconds=30,
            ),
            event_store_path=Path(tmpdir.name) / "events.log",
            env={f"TURTLE_SECRET_{_SIGNING_KEY_REF.upper()}": "signing-secret-material"},
        )
        self.addCleanup(self.engine.event_store.close)
        self.engine.start()
        self.adapter = self.engine.adapter

    def _seed(self, symbol="BTC", funding="0.0010", mark="50000"):
        self.adapter.set_funding_rate(FundingRate(
            symbol=Symbol(symbol), rate=Decimal(funding),
            next_funding_time_utc="2026-01-01T01:00:00+00:00", timestamp_utc=_EVALUATED_AT,
        ))
        self.adapter.set_mark_price(MarkPrice(
            symbol=Symbol(symbol), price=Decimal(mark), timestamp_utc=_EVALUATED_AT,
        ))

    def _context(self, universe=("BTC",)):
        return StrategyContext(
            universe=tuple(Symbol(s) for s in universe),
            portfolio_snapshot=self.engine.portfolio_manager.get_snapshot(),
            open_positions=(),
            kill_switch_state=self.engine.execution_state_machine.current_state,
            market_data=MarketDataView(self.engine),
            evaluated_at_utc=_EVALUATED_AT,
        )


class TestConstructionValidation(unittest.TestCase):
    def test_is_a_strategy_with_stable_name(self):
        strategy = ApprovedFundingAlphaStrategy((_spec(),))
        self.assertIsInstance(strategy, Strategy)
        self.assertEqual(strategy.name, STRATEGY_NAME)

    def test_empty_specs_raise(self):
        with self.assertRaises(ExecutionBridgeError):
            ApprovedFundingAlphaStrategy(())

    def test_non_funding_family_refused(self):
        oi = open_interest_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "10000", "stop_fraction": "0.02"},
            acceptance_criteria={"min_hit_rate": 0.5},
        )
        with self.assertRaises(ExecutionBridgeError):
            ApprovedFundingAlphaStrategy((oi,))

    def test_missing_stop_fraction_refused(self):
        spec = funding_rate_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "0.0005"}, acceptance_criteria={"min_hit_rate": 0.5},
        )
        with self.assertRaises(ExecutionBridgeError):
            ApprovedFundingAlphaStrategy((spec,))

    def test_invalid_fractions_refused(self):
        for bad in ({"stop_fraction": "0"}, {"stop_fraction": "1"}, {"stop_fraction": "-0.1"},
                    {"stop_fraction": "0.02", "t1_fraction": "0"},
                    {"stop_fraction": "0.02", "t1_fraction": "abc"}):
            parameters = {"threshold": "0.0005", **bad}
            spec = funding_rate_candidate_specification(
                version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
                parameters=parameters, acceptance_criteria={"min_hit_rate": 0.5},
            )
            with self.subTest(parameters=parameters):
                with self.assertRaises(ExecutionBridgeError):
                    ApprovedFundingAlphaStrategy((spec,))


class TestGenerateIntents(_BridgeEngineCase):
    def test_short_signal_produces_sell_intent_with_declared_levels(self):
        self._seed(funding="0.0010", mark="50000")  # beyond threshold, contrarian -> SHORT
        strategy = ApprovedFundingAlphaStrategy((_spec(),))
        intents = strategy.generate_intents(self._context())

        self.assertEqual(len(intents), 1)
        intent = intents[0]
        self.assertEqual(intent.side, OrderSide.SELL)
        self.assertEqual(intent.order_type, OrderType.LIMIT)
        self.assertEqual(intent.time_in_force, TimeInForce.GTC)
        self.assertFalse(intent.reduce_only)
        self.assertEqual(intent.limit_price, Decimal("50000"))
        self.assertEqual(intent.stop_price, Decimal("50000") * Decimal("1.02"))
        self.assertEqual(intent.t1_price, Decimal("50000") * Decimal("0.97"))
        self.assertEqual(intent.t2_price, Decimal("50000") * Decimal("0.94"))

    def test_long_signal_produces_buy_intent(self):
        self._seed(funding="-0.0010", mark="50000")  # negative beyond threshold, contrarian -> LONG
        strategy = ApprovedFundingAlphaStrategy((_spec(),))
        intents = strategy.generate_intents(self._context())
        self.assertEqual(intents[0].side, OrderSide.BUY)
        self.assertEqual(intents[0].stop_price, Decimal("50000") * Decimal("0.98"))

    def test_flat_signal_emits_nothing(self):
        self._seed(funding="0.0001")  # within threshold band
        strategy = ApprovedFundingAlphaStrategy((_spec(),))
        self.assertEqual(strategy.generate_intents(self._context()), ())

    def test_unavailable_funding_emits_nothing(self):
        self._seed()
        self.adapter.fail_next("get_funding_rate", ConnectionError("simulated outage"))
        strategy = ApprovedFundingAlphaStrategy((_spec(),))
        self.assertEqual(strategy.generate_intents(self._context()), ())

    def test_mark_price_failure_emits_nothing(self):
        self._seed(funding="0.0010")
        self.adapter.fail_next("get_mark_price", ConnectionError("simulated outage"))
        strategy = ApprovedFundingAlphaStrategy((_spec(),))
        self.assertEqual(strategy.generate_intents(self._context()), ())

    def test_symbol_outside_context_universe_skipped(self):
        self._seed(funding="0.0010")
        strategy = ApprovedFundingAlphaStrategy((_spec(symbols=("BTC", "ETH")),))
        intents = strategy.generate_intents(self._context(universe=("BTC",)))
        self.assertEqual([i.symbol.value for i in intents], ["BTC"])  # ETH never fetched/emitted

    def test_conflicting_specs_refuse_the_symbol(self):
        self._seed(funding="0.0010")
        contrarian = _spec(version="v1")                                # -> SHORT
        momentum = _spec(version="v2", direction_convention="momentum")  # -> LONG
        strategy = ApprovedFundingAlphaStrategy((contrarian, momentum))
        self.assertEqual(strategy.generate_intents(self._context()), ())

    def test_deterministic_given_identical_context_inputs(self):
        # A2 added per-instance cadence-tracking state, so replaying the
        # SAME context on the SAME instance a second time is now correctly
        # gated by cadence_seconds (proven separately below) -- genuine
        # determinism means "a fresh instance fed the same context always
        # produces the same result," which is what this checks.
        self._seed(funding="0.0010", mark="50000")
        first = ApprovedFundingAlphaStrategy((_spec(),)).generate_intents(self._context())
        second = ApprovedFundingAlphaStrategy((_spec(),)).generate_intents(self._context())
        self.assertEqual(first, second)

    def test_second_call_within_cadence_window_is_skipped(self):
        # A2: same instance, same cadence_seconds=60 (see _spec()) -- a
        # second call at the identical evaluated_at_utc is not yet due.
        self._seed(funding="0.0010", mark="50000")
        strategy = ApprovedFundingAlphaStrategy((_spec(),))
        first = strategy.generate_intents(self._context())
        second = strategy.generate_intents(self._context())
        self.assertEqual(len(first), 1)
        self.assertEqual(second, ())

    def test_call_after_cadence_elapsed_is_due_again(self):
        # A2: a context evaluated_at_utc far enough past the last
        # evaluation (>= cadence_seconds) is due again.
        self._seed(funding="0.0010", mark="50000")
        strategy = ApprovedFundingAlphaStrategy((_spec(),))
        first = strategy.generate_intents(self._context())
        later_context = StrategyContext(
            universe=(Symbol("BTC"),),
            portfolio_snapshot=self.engine.portfolio_manager.get_snapshot(),
            open_positions=(),
            kill_switch_state=self.engine.execution_state_machine.current_state,
            market_data=MarketDataView(self.engine),
            evaluated_at_utc="2026-01-01T00:01:00+00:00",  # +60s == cadence_seconds
        )
        second = strategy.generate_intents(later_context)
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)

    def test_optional_t_levels_omitted_when_not_declared(self):
        self._seed(funding="0.0010")
        strategy = ApprovedFundingAlphaStrategy((_spec(t1_fraction=None, t2_fraction=None),))
        intent = strategy.generate_intents(self._context())[0]
        self.assertIsNone(intent.t1_price)
        self.assertIsNone(intent.t2_price)


def _approve_in_registry(registry, eid, spec):
    registry.create(eid, spec.to_specification_dict())
    registry.seal(eid)
    registry.attach_evidence(eid, {"stage": {"x": 1}}, f"fp-{eid}")
    registry.transition(eid, LifecycleState.VALIDATING)
    registry.transition(eid, LifecycleState.EVIDENCE_SEALED)
    registry.transition(eid, LifecycleState.IN_REVIEW)
    record_governance_decision(registry, GovernanceDecision(
        experiment_id=eid, decision=GovernanceDecisionType.APPROVE,
        evidence_fingerprint=f"fp-{eid}", proposed_by="researcher", reviewed_by="reviewer",
        rationale="ok", decided_at_utc=_EVALUATED_AT,
    ))


class TestLivenessWithRegistry(_BridgeEngineCase):
    """A1: an optional registry lets generate_intents() re-verify each
    held specification is still live-approved every cycle."""

    def test_no_registry_keeps_trading_forever_the_prior_behavior(self):
        # Backward compatibility: registry=None (the default) never
        # re-checks anything -- exactly the pre-A1 behavior.
        self._seed(funding="0.0010", mark="50000")
        strategy = ApprovedFundingAlphaStrategy((_spec(),))
        self.assertEqual(len(strategy.generate_intents(self._context())), 1)

    def test_frozen_experiment_stops_emitting_intents_next_cycle(self):
        self._seed(funding="0.0010", mark="50000")
        registry = ExperimentRegistry(_InMemoryStorage())
        spec = _spec()
        _approve_in_registry(registry, "exp-funding", spec)
        strategy = ApprovedFundingAlphaStrategy((spec,), registry=registry)

        self.assertEqual(len(strategy.generate_intents(self._context())), 1)

        registry.transition("exp-funding", LifecycleState.SHAKEDOWN)
        registry.transition("exp-funding", LifecycleState.FROZEN)

        later_context = StrategyContext(
            universe=(Symbol("BTC"),),
            portfolio_snapshot=self.engine.portfolio_manager.get_snapshot(),
            open_positions=(),
            kill_switch_state=self.engine.execution_state_machine.current_state,
            market_data=MarketDataView(self.engine),
            evaluated_at_utc="2026-01-01T00:05:00+00:00",
        )
        self.assertEqual(strategy.generate_intents(later_context), ())

    def test_still_approved_experiment_keeps_trading(self):
        self._seed(funding="0.0010", mark="50000")
        registry = ExperimentRegistry(_InMemoryStorage())
        spec = _spec()
        _approve_in_registry(registry, "exp-funding", spec)
        strategy = ApprovedFundingAlphaStrategy((spec,), registry=registry)
        self.assertEqual(len(strategy.generate_intents(self._context())), 1)

        later_context = StrategyContext(
            universe=(Symbol("BTC"),),
            portfolio_snapshot=self.engine.portfolio_manager.get_snapshot(),
            open_positions=(),
            kill_switch_state=self.engine.execution_state_machine.current_state,
            market_data=MarketDataView(self.engine),
            evaluated_at_utc="2026-01-01T00:05:00+00:00",
        )
        self.assertEqual(len(strategy.generate_intents(later_context)), 1)

    def test_invalid_registry_type_refused(self):
        with self.assertRaises(ExecutionBridgeError):
            ApprovedFundingAlphaStrategy((_spec(),), registry="not-a-registry")


class TestWatchlistEnforcement(unittest.TestCase):
    """C4: an optional watchlist gate at bridge construction, independent
    of the one at research-cycle time."""

    def test_no_watchlist_keeps_prior_unconstrained_behavior(self):
        strategy = ApprovedFundingAlphaStrategy((_spec(),))
        self.assertEqual(strategy.name, STRATEGY_NAME)

    def test_specification_outside_watchlist_refused(self):
        watchlist = Watchlist(name="core-perps", symbols=(Symbol("ETH"),))
        with self.assertRaises(ExecutionBridgeError):
            ApprovedFundingAlphaStrategy((_spec(symbols=("BTC",)),), watchlist=watchlist)

    def test_specification_inside_watchlist_proceeds(self):
        watchlist = Watchlist(name="core-perps", symbols=(Symbol("BTC"), Symbol("ETH")))
        strategy = ApprovedFundingAlphaStrategy((_spec(symbols=("BTC",)),), watchlist=watchlist)
        self.assertEqual(strategy.name, STRATEGY_NAME)

    def test_invalid_watchlist_type_refused(self):
        with self.assertRaises(ExecutionBridgeError):
            ApprovedFundingAlphaStrategy((_spec(),), watchlist="not-a-watchlist")


class TestCandidateDispatchViaCatalog(_BridgeEngineCase):
    """C3: evaluate_fn is resolved through the candidate catalog, not a
    hardcoded class reference."""

    def test_generate_intents_resolves_evaluate_fn_via_catalog(self):
        import alpha_engine.execution_bridge.strategy as strategy_module

        calls = []
        real_get_candidate_type = strategy_module.get_candidate_type

        def _spy(name):
            calls.append(name)
            return real_get_candidate_type(name)

        self._seed(funding="0.0010", mark="50000")
        strategy = ApprovedFundingAlphaStrategy((_spec(),))
        original = strategy_module.get_candidate_type
        strategy_module.get_candidate_type = _spy
        try:
            strategy.generate_intents(self._context())
        finally:
            strategy_module.get_candidate_type = original
        self.assertEqual(calls, ["funding_rate_threshold_rule"])


class TestFromSpecificationDict(unittest.TestCase):
    def test_round_trip(self):
        spec = _spec()
        self.assertEqual(CandidateSpecification.from_specification_dict(spec.to_specification_dict()), spec)

    def test_missing_field_raises(self):
        from alpha_engine.candidates import CandidateError
        incomplete = _spec().to_specification_dict()
        del incomplete["universe"]
        with self.assertRaises(CandidateError):
            CandidateSpecification.from_specification_dict(incomplete)

    def test_non_mapping_raises(self):
        from alpha_engine.candidates import CandidateError
        with self.assertRaises(CandidateError):
            CandidateSpecification.from_specification_dict("not-a-mapping")


class TestLoadApprovedSpecifications(unittest.TestCase):
    def _approve(self, registry, eid, spec):
        registry.create(eid, spec.to_specification_dict())
        registry.seal(eid)
        registry.attach_evidence(eid, {"stage": {"x": 1}}, f"fp-{eid}")
        registry.transition(eid, LifecycleState.VALIDATING)
        registry.transition(eid, LifecycleState.EVIDENCE_SEALED)
        registry.transition(eid, LifecycleState.IN_REVIEW)
        record_governance_decision(registry, GovernanceDecision(
            experiment_id=eid, decision=GovernanceDecisionType.APPROVE,
            evidence_fingerprint=f"fp-{eid}", proposed_by="researcher", reviewed_by="reviewer",
            rationale="ok", decided_at_utc=_EVALUATED_AT,
        ))

    def test_returns_only_approved_funding_specs(self):
        registry = ExperimentRegistry(_InMemoryStorage())
        funding = _spec()
        self._approve(registry, "exp-funding", funding)

        oi = open_interest_candidate_specification(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "10000"}, acceptance_criteria={"min_hit_rate": 0.5},
        )
        self._approve(registry, "exp-oi", oi)  # approved, but not bridge-servable

        registry.create("exp-unapproved", _spec(version="v9").to_specification_dict())

        specs = load_approved_specifications(registry)
        self.assertEqual(specs, (funding,))

    def test_loaded_specs_construct_a_working_strategy(self):
        registry = ExperimentRegistry(_InMemoryStorage())
        self._approve(registry, "exp-funding", _spec())
        strategy = ApprovedFundingAlphaStrategy(load_approved_specifications(registry))
        self.assertEqual(strategy.name, STRATEGY_NAME)

    def test_wrong_type_raises(self):
        with self.assertRaises(ExecutionBridgeError):
            load_approved_specifications("not-a-registry")


class TestStrategyContractCompliance(_BridgeEngineCase):
    def test_kill_state_visible_in_context_does_not_break_purity(self):
        # The bridge ignores kill state deliberately: RiskManager blocks
        # downstream (precedence 1), and the strategy contract keeps
        # strategies opinion-only. This test just proves the bridge is a
        # well-behaved Strategy under a non-default context state.
        self._seed(funding="0.0010")
        context = StrategyContext(
            universe=(Symbol("BTC"),),
            portfolio_snapshot=self.engine.portfolio_manager.get_snapshot(),
            open_positions=(),
            kill_switch_state=State.INITIALIZING,
            market_data=MarketDataView(self.engine),
            evaluated_at_utc=_EVALUATED_AT,
        )
        strategy = ApprovedFundingAlphaStrategy((_spec(),))
        intents = strategy.generate_intents(context)
        self.assertEqual(len(intents), 1)


if __name__ == "__main__":
    unittest.main()
