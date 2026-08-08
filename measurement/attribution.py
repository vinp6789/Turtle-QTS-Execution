"""Why a cycle decided what it decided -- persisted, once per cycle.

NOT A SECOND JOURNAL. This writes into the SAME append-only EventStore
every other lifecycle event goes to, through the ordinary public append().
There is one immutable record of truth and this adds to it.

NOTHING HERE IS COMPUTED. Every value already exists on the CycleResult
that run_cycle returns and then discards. This module only serialises it.
No sizing, no risk evaluation, no execution logic is duplicated or
re-derived -- doing so would be exactly the drift this project keeps
finding.

WHAT IT CAPTURES THAT THE EXISTING EVENTS CANNOT. Order and position
events only exist for intents that BECAME orders. A rejected or skipped
intent produces no event at all, so any future analysis reading only the
event stream would see the trades risk permitted and never those it
blocked -- survivorship bias by construction. Rejections are also the
cheapest data in the system: already computed, previously thrown away.

LINKAGE, and why it is unambiguous.
  intent   -> strategy   by object identity (see attributed_strategy)
  intent   -> order      by SYMBOL. portfolio_construction groups intents
                         by_symbol and keeps exactly ONE survivor per
                         symbol (constructor.py:99-105), so within a cycle
                         a symbol identifies at most one approved
                         TradeRequest and therefore at most one order.
  order    -> fill/position  already carried by ORDER_FILLED /
                         POSITION_OPENED via client_order_id / position_id.
                         Attribution stops at the decision boundary and
                         never restates what the lifecycle events own.

IMMUTABILITY. The store is append-only, so an entry record cannot be
rewritten. Post-trade assessment and human notes are LATER, SEPARATE
appends -- never a mutation of this one.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional

from event_store import MAX_PAYLOAD_BYTES, EventType

from alpha_engine.platform.attributed_strategy import forget_all, resolve

# A feature snapshot records what the strategy ACTUALLY CONSUMED at the
# decision instant -- never a market dataset. Point-in-time values cannot
# be recomputed later without look-ahead risk, which is the entire reason
# they are persisted now rather than derived on demand.
MAX_FEATURES_PER_INTENT = 64

# Leaves generous headroom under the store's own limit; a cycle that would
# exceed it is truncated and flagged rather than rejected, because a
# partial record honestly labelled beats a lost one.
PAYLOAD_BUDGET_BYTES = MAX_PAYLOAD_BYTES // 2


def _s(value: Any) -> Any:
    """Decimal -> str, deterministically. Never through a float."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def _features(raw: Any) -> Dict[str, Any]:
    """Scalars only, capped, deterministically ordered.

    A strategy that offers a dict of point-in-time scalars gets it
    recorded; anything else (a list of candles, a book) is dropped rather
    than serialised, because storing a market dataset here is explicitly
    out of scope.
    """
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Any] = {}
    for key in sorted(raw)[:MAX_FEATURES_PER_INTENT]:
        v = raw[key]
        if isinstance(v, (Decimal, str, int, bool)) or v is None:
            out[str(key)] = _s(v)
    return out


def _intent_record(intent, identity, disposition: str, *, reason: str = "",
                   trade_request=None, decision=None) -> Dict[str, Any]:
    rec: Dict[str, Any] = {
        "strategy_id": identity.strategy_id,
        "strategy_version": identity.strategy_version,
        "strategy_kind": identity.strategy_kind,
        "disposition": disposition,
        "symbol": intent.symbol.value,
        "side": intent.side.value,
        "order_type": intent.order_type.value,
        "time_in_force": intent.time_in_force.value,
        "reduce_only": intent.reduce_only,
        "stop_price": _s(intent.stop_price),
        "limit_price": _s(intent.limit_price),
        "t1_price": _s(intent.t1_price),
        "t2_price": _s(intent.t2_price),
        "conviction": _s(intent.conviction),
    }
    thesis = getattr(intent, "thesis", None)
    if thesis is None:
        thesis = getattr(identity, "thesis", None)
    if reason:
        rec["reason"] = reason
    if trade_request is not None:
        rec["sizing"] = {
            "quantity": _s(trade_request.quantity),
            "entry_price": _s(trade_request.entry_price),
            "stop_price": _s(trade_request.stop_price),
            "risk_amount": _s(trade_request.proposed_risk_amount),
            "notional": _s(trade_request.proposed_notional),
            "margin_required": _s(trade_request.proposed_margin_required),
            "leverage": _s(trade_request.leverage),
            "estimated_liquidation_price": _s(trade_request.estimated_liquidation_price),
        }
    if decision is not None:
        rec["risk_decision"] = {
            "decision": getattr(decision.decision, "value", str(decision.decision)),
            "reason_codes": [getattr(c, "value", str(c))
                             for c in getattr(decision, "reason_codes", ()) or ()],
            "violated_limits": [str(v) for v in getattr(decision, "violated_limits", ()) or ()],
        }
    return rec


def build(cycle_result, strategies, *, thesis_by_strategy=None,
          features_by_intent=None) -> Dict[str, Any]:
    """The attribution payload for one cycle. Pure -- no I/O, no mutation."""
    thesis_by_strategy = thesis_by_strategy or {}
    features_by_intent = features_by_intent or {}

    records: List[Dict[str, Any]] = []

    def add(intent, disposition, **kw):
        identity = resolve(strategies, intent)
        rec = _intent_record(intent, identity, disposition, **kw)
        t = thesis_by_strategy.get(identity.strategy_id)
        if t:
            rec["thesis"] = str(t)
        feats = _features(features_by_intent.get(id(intent)))
        if feats:
            rec["features"] = feats
            raw = features_by_intent.get(id(intent))
            if isinstance(raw, dict) and len(raw) > MAX_FEATURES_PER_INTENT:
                rec["features_truncated"] = True
        records.append(rec)

    construction = cycle_result.construction
    rejected_ids = {id(r.intent) for r in construction.rejected}
    skipped_ids = {id(s.intent) for s in construction.skipped}
    suppressed_ids = {id(i) for i in getattr(cycle_result, "suppressed_by_open_orders", ())}

    for r in construction.rejected:
        add(r.intent, "REJECTED", trade_request=r.trade_request, decision=r.decision)
    for s in construction.skipped:
        add(s.intent, "SKIPPED", reason=s.reason)
    for i in getattr(cycle_result, "suppressed_by_open_orders", ()):
        add(i, "SUPPRESSED", reason="a live engine-owned order already rests for this symbol")

    # Whatever remains was approved. Its TradeRequest is matched by SYMBOL,
    # which portfolio construction guarantees is unique among survivors.
    approved_by_symbol = {tr.symbol.value: tr for tr in construction.approved}
    for intent in cycle_result.intents:
        if id(intent) in rejected_ids or id(intent) in skipped_ids or id(intent) in suppressed_ids:
            continue
        add(intent, "APPROVED", trade_request=approved_by_symbol.get(intent.symbol.value))

    # Orders actually submitted this cycle, keyed by the same symbol.
    orders = []
    for ex in getattr(cycle_result, "executions", ()) or ():
        snap = getattr(ex, "order_snapshot", None)
        if snap is None:
            continue
        orders.append({
            "client_order_id": getattr(snap, "client_order_id", None),
            "symbol": getattr(getattr(snap, "symbol", None), "value", None),
            "operation": getattr(ex.operation, "value", str(ex.operation)),
        })

    return {
        "schema": 1,
        "evaluated_at_utc": cycle_result.evaluated_at_utc,
        "intents": records,
        "orders": orders,
    }


def record(store, cycle_result, strategies, **kw) -> Optional[str]:
    """Append one TRADE_ATTRIBUTION event. Returns None on success, or a
    short reason string on failure -- it NEVER raises, because execution
    must not depend on attribution persistence.

    The caller is responsible for surfacing a non-None return as a
    degraded condition; silently dropping it would let a cycle be
    presented as fully auditable when it is not.
    """
    try:
        payload = build(cycle_result, strategies, **kw)
        import json
        size = len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        if size > PAYLOAD_BUDGET_BYTES:
            for rec in payload["intents"]:
                rec.pop("features", None)
                rec["features_truncated"] = True
            payload["payload_truncated"] = True
        store.append(EventType.TRADE_ATTRIBUTION, payload,
                     idempotency_key=f"attribution:{cycle_result.evaluated_at_utc}")
        return None
    except Exception as exc:                       # noqa: BLE001
        return f"{type(exc).__name__}: {exc}"
    finally:
        forget_all(strategies)
