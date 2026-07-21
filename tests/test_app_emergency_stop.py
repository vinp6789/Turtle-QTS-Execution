"""Verification tests for M1: emergency-stop propagation into the
Execution State Machine and RiskManager.

THE PREVIOUS FAILURE: emergency_stop() revoked signing but never drove
the ESM, so RiskManager (which receives esm.current_state every cycle)
kept APPROVING trades; OrderManager then durably persisted a SUBMIT
before the adapter's signing gate raised SecretRevokedError -- which
escapes OrderManager's `except ExchangeAdapterError` -- leaving a durable
orphan order in NEW (invisible to in-doubt resync) EVERY cycle, while
monitoring reported the kill switch inactive and a restart silently
resumed trading with fresh signing.
"""

import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path

from execution_state_machine import State
from exchange_adapter import FundingRate, MarkPrice, OrderSide, OrderType, Symbol, TimeInForce
from risk_manager import Decision, ReasonCode

from app.runtime import AppSettings, AppState, EmergencyStopActive
from trading_system.strategy import Strategy, TradeIntent

_SIGNING_ENV = {"TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1": "signing-secret-material"}


class _FixedIntentStrategy(Strategy):
    """Always-signalling stub: the exact scenario that produced orphan
    SUBMITs post-stop before the fix. Not a trading strategy."""

    @property
    def name(self):
        return "m1-repro"

    def generate_intents(self, context):
        return (TradeIntent(
            symbol=Symbol("BTC"), side=OrderSide.BUY, order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.GTC, reduce_only=False,
            stop_price=Decimal("90"), limit_price=Decimal("100"),
        ),)


class _EmergencyStopCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.env = {
            **_SIGNING_ENV,
            "ENGINE_CONFIG_PATH": "deploy/engine.paper.toml",
            "ENGINE_STORE_PATH": str(Path(self._tmp.name) / "events.log"),
            "PORTFOLIO_INITIAL_DEPOSIT": "100000",
            "RISK_MAX_STALE_DATA_SECONDS": "3600",
        }
        self.settings = AppSettings.from_env(self.env)
        self.state = AppState.create(self.settings, env=self.env,
                                     strategies=(_FixedIntentStrategy(),))
        self.addCleanup(self.state.shutdown)
        adapter = self.state.engine.adapter
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        adapter.set_mark_price(MarkPrice(symbol=Symbol("BTC"), price=Decimal("100"), timestamp_utc=now))
        adapter.set_funding_rate(FundingRate(symbol=Symbol("BTC"), rate=Decimal("0.0001"),
                                              next_funding_time_utc=now, timestamp_utc=now))

    def _esm_state(self):
        return self.state.engine.execution_state_machine.current_state

    def _kill_events(self):
        return [e for e in self.state.engine.event_store.replay()
                if e.payload.get("source") == "execution_state_machine"
                and e.payload.get("to_state") == "EMERGENCY_KILL"]

    def _submit_events(self):
        return [e for e in self.state.engine.event_store.replay()
                if e.payload.get("source") == "order_manager"
                and e.payload.get("action") == "SUBMIT"]


class TestStopPropagation(_EmergencyStopCase):
    def test_idle_stop_drives_esm_durably_and_monitoring_sees_it(self):
        self.assertEqual(self._esm_state(), State.INITIALIZING)
        self.state.emergency_stop()
        self.assertEqual(self._esm_state(), State.EMERGENCY_KILL)
        self.assertEqual(len(self._kill_events()), 1)          # durable, exactly once
        snapshot = self.state.capture()
        self.assertTrue(snapshot.is_kill_switch_active)        # monitoring truthful (was False pre-fix)
        self.assertEqual(snapshot.current_state, State.EMERGENCY_KILL)

    def test_repeated_stop_is_idempotent(self):
        self.state.emergency_stop()
        self.state.emergency_stop()
        self.state.emergency_stop()
        self.assertEqual(len(self._kill_events()), 1)          # no duplicate events
        self.assertIsNone(self.state.last_error)               # no illegal-transition noise

    def test_concurrent_stops_produce_exactly_one_kill_event(self):
        errors = []

        def stop():
            try:
                self.state.emergency_stop()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=stop) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(self._kill_events()), 1)
        self.assertEqual(self._esm_state(), State.EMERGENCY_KILL)


class TestNoOrphanSubmits(_EmergencyStopCase):
    def test_stop_before_place_creates_no_orphan_and_no_venue_io(self):
        """THE M1 HEADLINE. Pre-fix: this exact sequence appended a durable
        orphan SUBMIT (state NEW, invisible to resync) every cycle and let
        SecretRevokedError escape. Post-fix: the cycle refuses up front --
        zero SUBMIT events, zero orders, a clear typed error."""
        self.state.emergency_stop()
        events_before = len(tuple(self.state.engine.event_store.replay()))
        with self.assertRaises(EmergencyStopActive):
            self.state.run_one_cycle()
        self.assertEqual(self._submit_events(), [])                        # no orphan, ever
        self.assertEqual(len(tuple(self.state.engine.event_store.replay())), events_before)
        self.assertEqual(self.state.cycles_run, 0)

    def test_stop_after_approval_path_risk_now_blocks(self):
        """'After approval' cannot exist post-fix: with the ESM in
        EMERGENCY_KILL, RiskManager's precedence-1 check returns BLOCKED
        (KILL_SWITCH_EMERGENCY) before any approval -- verified by driving
        run_cycle directly, BYPASSING the app-layer gate."""
        from risk_manager import CorrelationInfo
        from trading_system.scheduling import run_cycle

        self.state.run_one_cycle()   # engine started, working normally
        self.state.emergency_stop()
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        result = run_cycle(
            self.state.engine, self.state.strategies,
            universe=self.state.universe, risk_profile=self.state.risk_profile,
            correlation_info=CorrelationInfo(entries=(), as_of_utc=now),
            maintenance_margin_rate=Decimal("0.005"),
        )
        self.assertEqual(result.construction.approved, ())
        self.assertEqual(result.executions, ())
        self.assertEqual(len(result.construction.rejected), 1)
        decision = result.construction.rejected[0].decision
        self.assertEqual(decision.decision, Decision.BLOCKED)
        self.assertIn(ReasonCode.KILL_SWITCH_EMERGENCY, decision.reason_codes)
        self.assertEqual(self._submit_events()[1:], [])  # only the pre-stop cycle's SUBMIT exists

    def test_stop_during_transmission_is_serialized_by_the_engine_lock(self):
        """emergency_stop and run_one_cycle share engine_lock: a stop
        requested mid-cycle takes effect at the cycle boundary -- the
        running cycle completes atomically, the NEXT one is refused."""
        results = {}

        def cycle():
            try:
                results["cycle"] = self.state.run_one_cycle()
            except Exception as exc:  # noqa: BLE001
                results["cycle_error"] = exc

        t = threading.Thread(target=cycle)
        t.start()
        self.state.emergency_stop()    # may run before or after the cycle wins the lock
        t.join()
        # Whichever won the race, the invariant holds: either the cycle
        # completed cleanly THEN the stop landed, or the stop landed first
        # and the cycle was refused. Never a half-cycle, never an orphan.
        if "cycle" in results:
            self.assertLessEqual(len(self._submit_events()), 1)
        else:
            self.assertIsInstance(results["cycle_error"], EmergencyStopActive)
            self.assertEqual(self._submit_events(), [])
        self.assertEqual(self._esm_state(), State.EMERGENCY_KILL)


class TestRestartAndReplay(_EmergencyStopCase):
    def test_restart_replays_the_stop_and_stays_stopped(self):
        """Pre-fix a restart silently RESUMED trading (fresh signing from
        env, no durable stop record). Post-fix the ESM replays into
        EMERGENCY_KILL: flag restored, cycles refused, no orphans."""
        self.state.run_one_cycle()
        self.state.emergency_stop()
        self.state.shutdown()

        restarted = AppState.create(self.settings, env=self.env,
                                    strategies=(_FixedIntentStrategy(),))
        self.addCleanup(restarted.shutdown)
        self.assertEqual(restarted.engine.execution_state_machine.current_state,
                         State.EMERGENCY_KILL)                  # replayed, not re-derived
        self.assertTrue(restarted.emergency_stopped)            # flag restored at create
        with self.assertRaises(EmergencyStopActive):
            restarted.run_one_cycle()

    def test_replay_integrity_and_ordering(self):
        """The kill event is a single, ESM-validated append: replay
        reconstructs it (ReplayIntegrityError would fire on any ordering
        corruption), and it appears AFTER every event of the completed
        pre-stop cycle."""
        self.state.run_one_cycle()
        self.state.emergency_stop()
        events = tuple(self.state.engine.event_store.replay())
        kill_ids = [e.event_id for e in events
                    if e.payload.get("source") == "execution_state_machine"
                    and e.payload.get("to_state") == "EMERGENCY_KILL"]
        self.assertEqual(len(kill_ids), 1)
        self.assertEqual(kill_ids[0], events[-1].event_id)      # last event: strictly after the cycle
        # Replay integrity: rebuilding the ESM from the store must succeed
        # (frozen replay validates every edge) and land in EMERGENCY_KILL.
        from execution_state_machine import ExecutionStateMachine
        rebuilt = ExecutionStateMachine(self.state.engine.event_store)
        self.assertEqual(rebuilt.current_state, State.EMERGENCY_KILL)


class TestH2CancelBeforeRevoke(_EmergencyStopCase):
    """H2 regression: emergency stop previously revoked signing WITHOUT
    cancelling resting venue orders -- and revocation is one-way, so those
    orders stayed live at the venue, fillable at any later time, with the
    engine permanently unable to cancel them."""

    def _place_resting_order(self):
        self.state.run_one_cycle()   # strategy places one resting order
        orders = self.state.engine.adapter.get_orders()
        self.assertEqual(len(orders), 1)
        return orders[0]

    def test_defect_mechanism_post_revoke_cancel_is_impossible(self):
        """Empirical proof of the H2 claim from source: once signing is
        revoked, the frozen cancel path's authorization gate raises before
        anything is transmitted -- the resting order is stranded. This is
        why cancel-first ordering is load-bearing."""
        from secrets_boundary import SecretRevokedError

        order = self._place_resting_order()
        self.state.engine.signing_boundary.revoke_all()   # revoke WITHOUT cancelling (old behavior)
        with self.assertRaises(SecretRevokedError):
            self.state.engine.order_manager.cancel_order(order.client_order_id)
        # The order is still LIVE at the venue (not cancelled) -- and this
        # engine can never cancel it again: stranded forever.
        venue_order = self.state.engine.adapter.get_orders()[0]
        self.assertNotEqual(venue_order.status.value, "CANCELLED")

    def test_emergency_stop_cancels_resting_orders_before_revoking(self):
        order = self._place_resting_order()
        cancelled = self.state.emergency_stop()
        # Venue-confirmed cancellation happened BEFORE revocation:
        self.assertEqual(len(cancelled), 1)
        self.assertEqual(cancelled[0].client_order_id, order.client_order_id)
        self.assertEqual(cancelled[0].lifecycle_state.value, "CANCELLED")
        # Nothing is left RESTING at the venue: the mock retains the order
        # record but marks it CANCELLED (venue-affirmed).
        venue_order = self.state.engine.adapter.get_orders()[0]
        self.assertEqual(venue_order.status.value, "CANCELLED")
        # And the stop itself is complete: signing revoked + ESM killed.
        self.assertTrue(self.state.emergency_stopped)
        self.assertEqual(self._esm_state(), State.EMERGENCY_KILL)
        self.assertTrue(self.state.engine.signing_boundary.is_revoked(
            "hyperliquid_signing_key_v1"))

    def test_cancel_failure_never_delays_revocation(self):
        """Fail-safe: if the cancel attempt itself fails (venue down,
        adapter fault), revocation and ESM propagation must proceed
        unconditionally, with the stranding surfaced loudly."""
        self._place_resting_order()
        om = self.state.engine.order_manager

        def broken_cancel_all(*args, **kwargs):
            raise RuntimeError("venue unreachable")

        om.cancel_all = broken_cancel_all      # instance shadow
        cancelled = self.state.emergency_stop()
        del om.cancel_all
        self.assertEqual(cancelled, ())
        self.assertTrue(self.state.emergency_stopped)
        self.assertEqual(self._esm_state(), State.EMERGENCY_KILL)
        self.assertIn("cancel_all before revocation failed", self.state.last_error)
        self.assertIn("unmanageable", self.state.last_error)

    def test_repeat_stop_does_not_reattempt_cancel(self):
        """Post-revocation a cancel could only fail noisily -- the cancel
        is attempted exactly once, on the first stop."""
        self._place_resting_order()
        first = self.state.emergency_stop()
        second = self.state.emergency_stop()
        self.assertEqual(len(first), 1)
        self.assertEqual(second, ())
        self.assertIsNone(self.state.last_error)   # no SecretRevokedError noise

    def test_event_ordering_cancels_precede_the_kill_event(self):
        """Durable narrative must read 'cancelled, then killed': every
        cancel event of the stop appears BEFORE the EMERGENCY_KILL event."""
        self._place_resting_order()
        self.state.emergency_stop()
        events = tuple(self.state.engine.event_store.replay())
        kill_index = next(i for i, e in enumerate(events)
                          if e.payload.get("source") == "execution_state_machine"
                          and e.payload.get("to_state") == "EMERGENCY_KILL")
        cancel_indexes = [i for i, e in enumerate(events)
                          if e.payload.get("source") == "order_manager"
                          and "CANCEL" in str(e.payload.get("action", "")) +
                                          str(e.payload.get("details", {}))]
        self.assertTrue(cancel_indexes, "expected durable cancel events")
        self.assertTrue(all(i < kill_index for i in cancel_indexes),
                        f"cancels {cancel_indexes} must precede kill {kill_index}")

    def test_unstarted_engine_stop_skips_cancel_silently(self):
        # Never-connected engine: nothing transmitted, venue unreachable --
        # no cancel attempt, no error noise, stop still completes.
        cancelled = self.state.emergency_stop()
        self.assertEqual(cancelled, ())
        self.assertIsNone(self.state.last_error)
        self.assertEqual(self._esm_state(), State.EMERGENCY_KILL)


class TestAccountingInteraction(_EmergencyStopCase):
    def test_observation_and_accounting_reads_still_work_after_stop(self):
        """A stop must not blind the operator: capture (monitoring) and the
        accounting layer's read/heal sync remain functional -- only new
        CYCLES are refused."""
        self.state.run_one_cycle()
        order = self.state.engine.adapter.get_orders()[-1] if self.state.engine.adapter.get_orders() else None
        self.state.emergency_stop()
        snapshot = self.state.capture()                      # no raise
        self.assertTrue(snapshot.is_kill_switch_active)
        notes = self.state.accounting.sync()                 # read-only heal path still available
        self.assertIsInstance(notes, list)
        if order is not None:
            # Fills that occur post-stop are still BOOKED (they are venue
            # facts; refusing them would corrupt the books, not protect them).
            self.state.engine.adapter.simulate_fill(order.exchange_order_id, order.quantity, order.limit_price)
            self.state.accounting.sync()
            booked = self.state.engine.portfolio_manager.get_snapshot()
            self.assertEqual(len(booked.open_position_ids), 1)


if __name__ == "__main__":
    unittest.main()
