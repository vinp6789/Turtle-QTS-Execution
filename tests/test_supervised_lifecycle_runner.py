"""Safety properties of the supervised ENGINE_TEST lifecycle runner.

These tests exist because of a specific incident: lifecycle #1 submitted a
real order, filled it, then died on a print referencing
OrderSnapshot.status -- an attribute that does not exist -- leaving a real
position open at the venue with nothing supervising it.

A subsequent adversarial review found six further blockers (B-1..B-6): no
venue-flat precheck, fill detection that checked only "non-zero", arbitrary
ids[0] position selection, an ignored position_id in the close, unguarded
venue reads on the critical path, and a freshness "check" that only logged.
Everything below asserts that none of those can recur.

No test touches the network: venue reads are an injected callable, sleeping
is injected, and the engine is a fake exposing only the verified interface.
"""

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from order_manager import OrderLifecycleState
from risk_manager import Decision, ReasonCode
from trading_system.execution.models import ExecutionOperation

from scripts.supervised_lifecycle_testnet import (
    CONFIRM_ENV, CONFIRM_VALUE, LifecycleAbort, SupervisedLifecycle,
    UnknownVenueState, _FORBIDDEN, _report, preflight,
)

QTY = Decimal("0.00025")


# ------------------------------------------------------------------ fakes
class _Snap:
    def __init__(self, reduce_only=False, reject_reason=None, quantity=QTY):
        self.client_order_id = "cloid-1"
        self.lifecycle_state = OrderLifecycleState.FILLED
        self.exchange_order_id = "999"
        self.quantity = quantity
        self.filled_quantity = quantity
        self.limit_price = Decimal("65000")
        self.reduce_only = reduce_only
        self.reject_reason = reject_reason
        self.symbol = "BTC"
        self.side = "BUY"


class _Exec:
    def __init__(self, snap, operation=ExecutionOperation.PLACE):
        self.operation = operation
        self.order_snapshot = snap
        self.trade_request = None
        self.decision = None


class _Decision:
    def __init__(self):
        self.decision = Decision.FAIL_SAFE
        self.reason_codes = (ReasonCode.STALE_DATA,)
        self.violated_limits = ("position:p1:stale(age=344s)",)


class _Rejected:
    def __init__(self):
        self.intent = None
        self.trade_request = None
        self.decision = _Decision()


class _Construction:
    def __init__(self, approved=(), rejected=(), skipped=()):
        self.approved, self.rejected, self.skipped = approved, rejected, skipped


class _Sym:
    def __init__(self, v):
        self.value = v


class _Intent:
    def __init__(self, reduce_only, symbol="BTC", side="BUY"):
        self.reduce_only = reduce_only
        self.symbol = _Sym(symbol)
        self.side = _Sym(side)


class _VPos:
    """Venue position: symbol + SIGNED quantity, exactly as
    exchange_adapter.Position provides (codec.py:146 sets quantity=szi)."""

    def __init__(self, quantity, symbol="BTC"):
        self.symbol = _Sym(symbol)
        self.quantity = quantity


class _Cycle:
    def __init__(self, intents=(), executions=(), construction=None):
        self.intents = intents
        self.executions = executions
        self.construction = construction or _Construction()
        self.reconciliation = None
        self.evaluated_at_utc = "2026-08-09T00:00:00+00:00"
        self.suppressed_by_open_orders = ()


class _Position:
    def __init__(self, pid="p1", qty=QTY, symbol="BTC", side="BUY"):
        self.position_id = pid
        self.remaining_quantity = qty
        self.avg_entry_price = Decimal("64956")
        self.symbol = _Sym(symbol)
        self.side = _Sym(side)
        self.lifecycle_state = "OPEN"
        self.realized_pnl = Decimal("0")
        self.fees_paid = Decimal("0")
        self.updated_at_utc = "2026-08-09T00:00:00+00:00"


class _PortfolioSnap:
    def __init__(self, ids, updated_at_utc):
        self.open_position_ids = tuple(ids)
        self.equity = Decimal("999")
        self.updated_at_utc = updated_at_utc


class _Recon:
    def __init__(self, matches=True):
        self.matches = matches
        self.discrepancies = () if matches else ("BTC: local=1 exchange=0",)
        self.local_positions = ()
        self.exchange_positions = ()


class _State:
    """Fake AppState exposing only the verified interface.

    open_ids_after: the engine's open_position_ids AFTER each cycle, so the
    set-difference identification can be exercised realistically.
    """

    def __init__(self, cycles, open_ids=(), open_ids_after=None,
                 recon_matches=True, shutdown_raises=False,
                 position=None, portfolio_age_seconds=1):
        self._cycles = list(cycles)
        self._after = list(open_ids_after or [])
        self.open_ids = list(open_ids)
        self.recon_matches = recon_matches
        self.shutdown_called = False
        self.cycles_run = 0
        self._shutdown_raises = shutdown_raises
        self._position = position or _Position()
        self._age = portfolio_age_seconds
        self.strategies = ()
        self.quantization_rules = {}
        self.settings = type("S", (), {"risk_max_stale_data_seconds": 150})()

        outer = self

        class _PM:
            @staticmethod
            def get_position(pid):
                return outer._position

        class _PF:
            @staticmethod
            def get_snapshot():
                ts = (datetime.now(timezone.utc)
                      - timedelta(seconds=outer._age)).isoformat()
                return _PortfolioSnap(outer.open_ids, ts)

        class _AD:
            @staticmethod
            def reconcile(local):
                return _Recon(outer.recon_matches)

        self.engine = type("E", (), {
            "position_manager": _PM(), "portfolio_manager": _PF(),
            "adapter": _AD(), "event_store": object()})()

    def run_one_cycle(self):
        if not self._cycles:
            raise AssertionError("more cycles requested than the test provided")
        nxt = self._cycles.pop(0)
        self.cycles_run += 1
        if self._after:
            self.open_ids = list(self._after.pop(0))
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    def shutdown(self):
        self.shutdown_called = True
        if self._shutdown_raises:
            raise RuntimeError("shutdown blew up")


def _runner(state, venue_seq, **kw):
    """venue_seq: a list of venue-position LISTS, or Exceptions to raise."""
    seq = list(venue_seq)

    def venue():
        item = seq.pop(0) if seq else []
        if isinstance(item, Exception):
            raise item
        return item

    kw.setdefault("sleep_fn", lambda s: None)
    kw.setdefault("age_seconds", 1)
    ticks = iter(range(0, 100_000, 5))
    kw.setdefault("now_fn", lambda: next(ticks))
    return SupervisedLifecycle(state, (), venue_positions_fn=venue, **kw)


def _entry_cycle():
    return _Cycle(intents=(_Intent(False),), executions=(_Exec(_Snap()),))


def _close_cycle():
    return _Cycle(intents=(_Intent(True),),
                  executions=(_Exec(_Snap(reduce_only=True)),))


def _happy_state(**kw):
    return _State([_entry_cycle(), _close_cycle()],
                  open_ids=(), open_ids_after=[("p1",), ()], **kw)


FLAT, HELD = [], [_VPos(QTY)]


# ------------------------------------------------------------- preflight
class TestPreflight(unittest.TestCase):
    def test_preflight_passes_against_the_real_interfaces(self):
        self.assertEqual(preflight(), [], "preflight must pass on the real codebase")

    def test_forbidden_attributes_are_still_absent(self):
        import importlib
        for module_name, cls_name, attr in _FORBIDDEN:
            cls = getattr(importlib.import_module(module_name), cls_name)
            self.assertFalse(hasattr(cls, attr),
                             f"{cls_name}.{attr} now exists -- review the runner")

    def test_preflight_catches_a_missing_interface(self):
        import scripts.supervised_lifecycle_testnet as mod
        original = dict(mod._REQUIRED)
        try:
            mod._REQUIRED["Bogus"] = ("order_manager", "OrderSnapshot", ["nope_missing"])
            self.assertTrue(any("nope_missing" in f for f in preflight()))
        finally:
            mod._REQUIRED.clear()
            mod._REQUIRED.update(original)

    # AST-based, so the runner's own prose -- which must NAME the forbidden
    # attributes to explain them -- cannot cause a false positive, and a real
    # access cannot hide inside a string.

    @staticmethod
    def _runner_ast():
        import ast
        from pathlib import Path
        return ast.parse(
            Path("scripts/supervised_lifecycle_testnet.py").read_text(encoding="utf-8"))

    def test_runner_never_accesses_a_forbidden_attribute(self):
        import ast
        forbidden = {"status", "total_equity", "list_open_positions", "connect"}
        offenders = [f"line {n.lineno}: .{n.attr}"
                     for n in ast.walk(self._runner_ast())
                     if isinstance(n, ast.Attribute) and n.attr in forbidden]
        self.assertEqual(offenders, [], f"forbidden attribute access: {offenders}")

    def test_runner_makes_no_direct_adapter_submission(self):
        import ast
        offenders = [f"line {n.lineno}" for n in ast.walk(self._runner_ast())
                     if isinstance(n, ast.Attribute) and n.attr == "place_order"]
        self.assertEqual(offenders, [], "runner must never submit directly to the adapter")

    def test_hasattr_appears_only_inside_preflight(self):
        import ast
        tree = self._runner_ast()
        pf = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "preflight")
        # preflight is the ONLY place hasattr is acceptable, because absence
        # there is a loud failure rather than a silent skip. The B-6
        # correction removed the last hasattr outside it.
        allowed = set(range(pf.lineno, (pf.end_lineno or 0) + 1))
        offenders = [f"line {n.lineno}" for n in ast.walk(tree)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                     and n.func.id == "hasattr" and n.lineno not in allowed]
        self.assertEqual(offenders, [], f"hasattr outside preflight: {offenders}")


# ------------------------------------------------ B-1 flat precheck
class TestFlatPrecheck(unittest.TestCase):
    def test_pre_existing_position_blocks_entry(self):
        """B-1. A pre-existing position must prevent ANY submission."""
        state = _happy_state()
        out = _runner(state, [HELD]).run()
        self.assertIn("NOT flat", out.aborted_reason)
        self.assertFalse(out.entry_submitted, "no order may be submitted")
        self.assertEqual(state.cycles_run, 0, "no cycle may run")
        self.assertTrue(state.shutdown_called)

    def test_engine_positions_without_venue_positions_blocks_entry(self):
        state = _State([_entry_cycle()], open_ids=("stale-1",))
        out = _runner(state, [FLAT]).run()
        self.assertIn("local/venue divergence", out.aborted_reason)
        self.assertEqual(state.cycles_run, 0)

    def test_precheck_read_failure_aborts_before_submission(self):
        state = _happy_state()
        out = _runner(state, [ConnectionError("down")] * 5).run()
        self.assertIsInstance(out.aborted_reason, str)
        self.assertIn("STATE UNKNOWN", out.aborted_reason)
        self.assertEqual(state.cycles_run, 0, "unknown venue must not submit")
        self.assertFalse(out.entry_submitted)


# ------------------------------------------- B-2 entry fill verification
class TestEntryFillVerification(unittest.TestCase):
    def test_submission_is_not_treated_as_a_fill(self):
        state = _happy_state()
        out = _runner(state, [FLAT] + [FLAT] * 20).run()
        self.assertIn("not filled", out.aborted_reason)
        self.assertIsNone(out.aged_seconds, "must not age an unfilled entry")

    def test_wrong_symbol_does_not_count_as_entry_fill(self):
        """B-2. An ETH position is not evidence our BTC entry filled."""
        state = _happy_state()
        out = _runner(state, [FLAT, [_VPos(QTY, symbol="ETH")]]).run()
        self.assertIn("another symbol", out.aborted_reason)
        self.assertIsNone(out.aged_seconds)

    def test_wrong_side_does_not_count_as_entry_fill(self):
        """B-2. A SHORT position cannot satisfy a BUY entry."""
        state = _happy_state()
        out = _runner(state, [FLAT, [_VPos(-QTY)]]).run()
        self.assertIn("side does not match", out.aborted_reason)
        self.assertIsNone(out.aged_seconds)

    def test_wrong_quantity_does_not_count_as_entry_fill(self):
        state = _happy_state()
        out = _runner(state, [FLAT, [_VPos(Decimal("0.005"))]]).run()
        self.assertIn("!=", out.aborted_reason)
        self.assertIsNone(out.aged_seconds)

    def test_partial_entry_does_not_pass(self):
        state = _happy_state()
        out = _runner(state, [FLAT, [_VPos(Decimal("0.0001"))]]).run()
        self.assertIn("partial or unexpected fill", out.aborted_reason)
        self.assertIsNone(out.aged_seconds)

    def test_multiple_same_symbol_positions_abort(self):
        state = _happy_state()
        out = _runner(state, [FLAT, [_VPos(QTY), _VPos(QTY)]]).run()
        self.assertIn("ambiguous", out.aborted_reason)

    def test_correct_fill_is_accepted(self):
        state = _happy_state()
        out = _runner(state, [FLAT, HELD, HELD, FLAT]).run()
        self.assertEqual(out.venue_entry_quantity, QTY)
        self.assertIsNone(out.aborted_reason)


# --------------------------------------------- B-3 position identification
class TestPositionIdentification(unittest.TestCase):
    def test_ambiguous_position_selection_aborts(self):
        """B-3. Two new ids -> refuse to guess. Never ids[0]."""
        state = _State([_entry_cycle(), _close_cycle()],
                       open_ids=(), open_ids_after=[("p1", "p2"), ()])
        out = _runner(state, [FLAT, HELD, HELD, FLAT]).run()
        self.assertIn("ambiguous position identity", out.aborted_reason)

    def test_no_new_position_is_reported_as_divergence(self):
        state = _State([_entry_cycle()], open_ids=(), open_ids_after=[()])
        out = _runner(state, [FLAT, HELD]).run()
        self.assertIn("no NEW open position", out.aborted_reason)

    def test_identified_position_must_match_symbol_and_side(self):
        state = _State([_entry_cycle(), _close_cycle()], open_ids=(),
                       open_ids_after=[("p1",), ()],
                       position=_Position(side="SELL"))
        out = _runner(state, [FLAT, HELD, HELD, FLAT]).run()
        self.assertIn("side", out.aborted_reason)

    def test_identity_is_the_new_id_not_index_zero(self):
        state = _happy_state()
        out = _runner(state, [FLAT, HELD, HELD, FLAT]).run()
        self.assertEqual(out.position_id, "p1")


# ---------------------------------------------------- B-4 close targeting
class TestCloseTargeting(unittest.TestCase):
    def test_close_uses_identified_position(self):
        """B-4. If the open set is not exactly our pid, refuse to close."""
        state = _State([_entry_cycle(), _close_cycle()], open_ids=(),
                       open_ids_after=[("p1",), ("p1", "intruder")])
        runner = _runner(state, [FLAT, HELD, HELD, FLAT])
        # Make an unrelated position appear before the close cycle.
        original = runner._age

        def age_then_intrude():
            original()
            state.open_ids = ["p1", "intruder"]

        runner._age = age_then_intrude
        out = runner.run()
        self.assertIn("cannot target the close", out.aborted_reason)

    def test_close_intent_symbol_must_match_the_position(self):
        state = _State([_entry_cycle(),
                        _Cycle(intents=(_Intent(True, symbol="ETH"),),
                               executions=(_Exec(_Snap(reduce_only=True)),))],
                       open_ids=(), open_ids_after=[("p1",), ()])
        out = _runner(state, [FLAT, HELD, HELD, FLAT]).run()
        self.assertIn("reduce_only intent targets ETH", out.aborted_reason)

    def test_close_must_be_reduce_only(self):
        state = _State([_entry_cycle(), _Cycle(intents=(_Intent(False),))],
                       open_ids=(), open_ids_after=[("p1",), ("p1",)])
        out = _runner(state, [FLAT, HELD, HELD, FLAT]).run()
        self.assertIn("no reduce_only intent", out.aborted_reason)

    def test_submitted_close_order_must_carry_reduce_only(self):
        state = _State([_entry_cycle(),
                        _Cycle(intents=(_Intent(True),),
                               executions=(_Exec(_Snap(reduce_only=False)),))],
                       open_ids=(), open_ids_after=[("p1",), ("p1",)])
        out = _runner(state, [FLAT, HELD, HELD, FLAT]).run()
        self.assertIn("NOT reduce_only", out.aborted_reason)

    def test_risk_rejection_of_the_close_stops_without_retry(self):
        state = _State([_entry_cycle(),
                        _Cycle(intents=(_Intent(True),),
                               construction=_Construction(rejected=(_Rejected(),)))],
                       open_ids=(), open_ids_after=[("p1",), ("p1",)])
        out = _runner(state, [FLAT, HELD, HELD, FLAT]).run()
        self.assertIn("CLOSE REJECTED BY RISK", out.aborted_reason)
        self.assertIn("no automatic retry", out.aborted_reason)
        self.assertEqual(state._cycles, [], "no further cycle after rejection")

    def test_partial_close_does_not_pass(self):
        state = _happy_state()
        residual = [_VPos(Decimal("0.0001"))]
        out = _runner(state, [FLAT, HELD, HELD] + [residual] * 20).run()
        self.assertIn("MANUAL UI CLOSE REQUIRED", out.aborted_reason)
        self.assertFalse(out.succeeded)


# ------------------------------------------------- B-5 network retries
class TestNetworkReadRetries(unittest.TestCase):
    def test_entry_poll_network_error_is_bounded(self):
        state = _happy_state()
        out = _runner(state, [FLAT] + [ConnectionError("blip")] * 10).run()
        self.assertIn("STATE UNKNOWN", out.aborted_reason)
        self.assertTrue(state.shutdown_called)

    def test_close_poll_network_error_is_bounded(self):
        state = _happy_state()
        out = _runner(state, [FLAT, HELD] + [TimeoutError("t")] * 10).run()
        self.assertIn("STATE UNKNOWN", out.aborted_reason)
        self.assertTrue(state.shutdown_called)

    def test_network_failure_never_means_flat(self):
        """An exception must not be read as 'no position'."""
        state = _happy_state()
        out = _runner(state, [FLAT, HELD] + [ConnectionError("x")] * 10).run()
        self.assertFalse(out.position_closed_locally)
        self.assertFalse(out.succeeded)
        self.assertNotIn("closed", (out.aborted_reason or "").lower())

    def test_network_failure_never_means_filled(self):
        state = _happy_state()
        out = _runner(state, [FLAT] + [ConnectionError("x")] * 10).run()
        self.assertIsNone(out.venue_entry_quantity)
        self.assertIsNone(out.aged_seconds)

    def test_transient_read_error_recovers_within_the_bound(self):
        state = _happy_state()
        out = _runner(state, [FLAT, ConnectionError("blip"), HELD, HELD, FLAT]).run()
        self.assertIsNone(out.aborted_reason)
        self.assertTrue(out.succeeded)

    def test_unknown_venue_state_is_its_own_type(self):
        self.assertTrue(issubclass(UnknownVenueState, LifecycleAbort))


# ------------------------------------------------------- B-6 freshness
class TestPreCloseObservations(unittest.TestCase):
    """B-6 CORRECTED. The pre-close observation is a LOG plus a reachability
    check -- never a gate. An earlier version aborted when the portfolio
    observation was older than risk_max_stale_data_seconds, which made the
    lifecycle impossible: the observation is refreshed only by a cycle, no
    cycle runs while the position ages, and the lifecycle deliberately ages
    ~195s past the 150s limit. The gate fired every time."""

    def test_old_pre_close_observation_does_not_abort_the_close(self):
        """THE REAL TIMELINE. Portfolio last refreshed by the entry cycle,
        then AGE_SECONDS pass. The close must still proceed to RiskManager."""
        from scripts.supervised_lifecycle_testnet import AGE_SECONDS
        state = _happy_state(portfolio_age_seconds=AGE_SECONDS)
        out = _runner(state, [FLAT, HELD, HELD, FLAT]).run()
        self.assertIsNone(out.aborted_reason,
                          "an aged pre-close observation must NOT abort -- the close "
                          "cycle refreshes it and RiskManager decides")
        self.assertTrue(out.close_submitted, "the close cycle must run")
        self.assertTrue(out.succeeded)

    def test_even_a_grossly_old_observation_does_not_abort(self):
        state = _happy_state(portfolio_age_seconds=3600)
        out = _runner(state, [FLAT, HELD, HELD, FLAT]).run()
        self.assertIsNone(out.aborted_reason)
        self.assertTrue(out.close_submitted)

    def test_observation_age_is_recorded_for_evidence(self):
        from scripts.supervised_lifecycle_testnet import AGE_SECONDS
        state = _happy_state(portfolio_age_seconds=AGE_SECONDS)
        out = _runner(state, [FLAT, HELD, HELD, FLAT]).run()
        self.assertIsNotNone(out.freshness_age_seconds)
        self.assertGreater(out.freshness_age_seconds, 150,
                           "the age is recorded, not enforced")

    def test_risk_manager_remains_the_authority_on_staleness(self):
        """If risk rejects the aged close, THAT is the definitive answer."""
        state = _State([_entry_cycle(),
                        _Cycle(intents=(_Intent(True),),
                               construction=_Construction(rejected=(_Rejected(),)))],
                       open_ids=(), open_ids_after=[("p1",), ("p1",)],
                       portfolio_age_seconds=195)
        out = _runner(state, [FLAT, HELD, HELD, FLAT]).run()
        self.assertIn("CLOSE REJECTED BY RISK", out.aborted_reason)
        self.assertIn("STALE_DATA", out.risk_rejection)

    def test_unreachable_venue_before_close_stops_the_lifecycle(self):
        """Reachability IS checked -- an unreadable venue is never assumed OK."""
        state = _happy_state()
        out = _runner(state, [FLAT, HELD] + [ConnectionError("down")] * 10).run()
        self.assertIn("STATE UNKNOWN", out.aborted_reason)
        self.assertFalse(out.close_submitted)

    def test_no_timestamp_is_fabricated(self):
        import ast
        from pathlib import Path
        tree = ast.parse(Path("scripts/supervised_lifecycle_testnet.py").read_text(encoding="utf-8"))
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                  and n.name == "_log_pre_close_observations")
        writes = [t.attr for n in ast.walk(fn) if isinstance(n, ast.Assign)
                  for t in n.targets if isinstance(t, ast.Attribute)]
        self.assertNotIn("updated_at_utc", writes)
        self.assertNotIn("evaluated_at_utc", writes)


# -------------------------------------------------- reporting / cleanup
class TestReportingCannotKillTheLifecycle(unittest.TestCase):
    def test_report_swallows_any_exception(self):
        self.assertIsNone(_report("x", lambda: (_ for _ in ()).throw(RuntimeError("boom"))))

    def test_report_returns_value_on_success(self):
        self.assertEqual(_report("x", lambda: 42), 42)

    def test_attribute_error_in_reporting_does_not_abort(self):
        """The literal lifecycle #1 failure."""
        missing = object()
        self.assertIsNone(_report("status-like", lambda: missing.status))


class TestGuaranteedCleanup(unittest.TestCase):
    def test_shutdown_runs_when_entry_is_rejected_by_risk(self):
        state = _State([_Cycle(construction=_Construction(rejected=(_Rejected(),)))])
        out = _runner(state, [FLAT]).run()
        self.assertTrue(state.shutdown_called)
        self.assertIn("rejected by risk", out.aborted_reason)

    def test_shutdown_runs_on_unexpected_exception(self):
        state = _State([ValueError("kaboom")])
        out = _runner(state, [FLAT]).run()
        self.assertTrue(state.shutdown_called)
        self.assertIn("ValueError", out.aborted_reason)

    def test_shutdown_failure_does_not_mask_the_original_error(self):
        state = _State([ValueError("original")], shutdown_raises=True)
        out = _runner(state, [FLAT]).run()
        self.assertIn("original", out.aborted_reason)
        self.assertFalse(out.shutdown_clean)

    def test_shutdown_runs_after_a_successful_lifecycle(self):
        state = _happy_state()
        out = _runner(state, [FLAT, HELD, HELD, FLAT]).run()
        self.assertTrue(state.shutdown_called)
        self.assertTrue(out.shutdown_clean)


# --------------------------------------------------------- duplication
class TestNoDuplication(unittest.TestCase):
    def test_no_duplicate_entry(self):
        state = _happy_state()
        _runner(state, [FLAT, HELD, HELD, FLAT]).run()
        self.assertEqual(state.cycles_run, 2, "exactly one entry and one close cycle")

    def test_no_duplicate_close(self):
        state = _happy_state()
        runner = _runner(state, [FLAT, HELD, HELD, FLAT])
        runner.run()
        self.assertEqual(state._cycles, [], "no extra cycle was requested")

    def test_abort_after_entry_does_not_resubmit(self):
        state = _State([_entry_cycle()], open_ids=(), open_ids_after=[()])
        out = _runner(state, [FLAT, HELD]).run()
        self.assertEqual(state.cycles_run, 1, "must not run a second cycle after abort")
        self.assertIsNotNone(out.aborted_reason)


# ------------------------------------------------- ageing & reconcile
class TestAgeingAndReconciliation(unittest.TestCase):
    def test_ageing_uses_elapsed_time_not_timestamp_manipulation(self):
        from pathlib import Path
        src = Path("scripts/supervised_lifecycle_testnet.py").read_text(encoding="utf-8")
        body = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        for forbidden in ("updated_at_utc =", "clock=", "evaluated_at_utc ="):
            self.assertNotIn(forbidden, body,
                             "runner must never fabricate or inject a timestamp")

    def test_ageing_waits_for_the_configured_elapsed_time(self):
        state = _happy_state()
        out = _runner(state, [FLAT, HELD, HELD, FLAT], age_seconds=60).run()
        self.assertGreaterEqual(out.aged_seconds, 60)

    def test_reconciliation_mismatch_is_reported_not_fatal(self):
        state = _happy_state(recon_matches=False)
        out = _runner(state, [FLAT, HELD, HELD, FLAT]).run()
        self.assertFalse(out.reconciliation_matches)
        self.assertIsNone(out.aborted_reason)
        self.assertTrue(state.shutdown_called)

    def test_successful_lifecycle_sets_succeeded(self):
        state = _happy_state()
        out = _runner(state, [FLAT, HELD, HELD, FLAT]).run()
        self.assertTrue(out.entry_submitted)
        self.assertTrue(out.close_submitted)
        self.assertTrue(out.position_closed_locally)
        self.assertTrue(out.succeeded)


class TestMainGuard(unittest.TestCase):
    def test_main_refuses_without_explicit_confirmation(self):
        import os
        from scripts.supervised_lifecycle_testnet import main
        saved = os.environ.pop(CONFIRM_ENV, None)
        try:
            self.assertEqual(main(), 2)
        finally:
            if saved is not None:
                os.environ[CONFIRM_ENV] = saved

    def test_confirmation_value_is_not_trivially_guessable(self):
        self.assertIn("AUTHORIZE", CONFIRM_VALUE)
        self.assertGreater(len(CONFIRM_VALUE), 20)


if __name__ == "__main__":
    unittest.main()
