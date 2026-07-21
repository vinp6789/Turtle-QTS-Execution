# AD-25: Accepted Accounting Crash Windows (Venue-ACK ↔ EventStore)

**Status:** Accepted. Documentation of a deliberately retained residual, not
a defect awaiting a fix.
**Scope:** the app-layer accounting synchronization
(`app/runtime/accounting.py`, `app/runtime/state.py`,
`trading_system/scheduling/cycle.py` `on_execution` hook).
**Verified by:** adversarial crash-injection probes (13/13) and the
permanent regression suite (`tests/test_app_accounting.py`,
`TestLevelsCrashWindow`, `TestF1CrashWindowHealing`).

---

## 1. Context

The accounting layer wires venue fills into PositionManager and
PortfolioManager. Two of its writes correlate state across **independent
durability domains**:

1. **Levels recording** — after an order is accepted by the venue, the
   order's stop/entry metadata is appended to the local EventStore so any
   later fill can be booked into a position.
2. **Order→position mapping** — after `create_position` (which mints its
   own id, fsync'd by frozen Module 7), the correlation
   `client_order_id → position_id` is appended by the accounting layer.

Every other accounting write is single-domain and fully healed by the
fill-id-keyed durable idempotency ledger (see the F1 fix): a crash at any
point among `record_entry_fill` / `reserve_margin` / `allocate_margin` /
`apply_fee` / `record_exit` / `apply_realized_pnl` / `release_margin`
re-applies exactly once on the next sync. Crash-injection at **every** one
of those points reconverges to a byte-identical baseline.

What remains are exactly **two** windows, each one local fsync wide:

| Window | Between | And |
|---|---|---|
| **W1 (ACK↔levels)** | venue matching engine accepts the order (durable *at the venue*) | the levels event's local fsync |
| **W2 (create↔mapping)** | Module 7's CREATE event fsync (durable *locally, in another module's scope*) | the mapping event's local fsync |

## 2. Crash timeline

```
      LOCAL ENGINE (our EventStore)                VENUE (Hyperliquid's own durability)
  ────────────────────────────────────────         ─────────────────────────────────────
  t0  OrderManager.place_order
      └─ SUBMIT event fsync'd  (durable)
  t1  adapter signs + transmits  ────────────────► t1' matching engine ACCEPTS the order
                                                        ORDER IS NOW DURABLE AT THE VENUE
  t2  execute_place() returns ◄──────────────────  (ack)
  ╔═══════════════════════════════════════════════════════════════════════════════════╗
  ║ W1: THE RESIDUAL WINDOW — exactly one append wide                                 ║
  ╚═══════════════════════════════════════════════════════════════════════════════════╝
  t3  on_execution hook fires
      └─ order_levels_recorded event fsync'd (durable)          ← window closed
  t4  (next order's t1, or post-cycle sync)

  Crash inside [t1', t3):
      venue state : live order (may fill at any time)
      local state : SUBMIT event only — no stop/entry metadata
  ─────────────────────────────────────────────────────────────────────────────────────
  RECOVERY (restart):
  r0  EventStore replay        → every fsync'd fact reconstructed exactly (no half-writes:
                                 each accounting fact is ONE append)
  r1  orchestration.synchronize → OrderManager resyncs the order itself (find_order by
                                 deterministic cloid — the ORDER is never lost)
  r2  fill arrives             → dispatch → OrderManager records it durably (fill-id dedup)
  r3  accounting sync          → levels missing → CONSERVATIVE SKIP + loud note
                                 (never fabricates a stop; no position, no margin invented)
  r4  orchestration.reconcile  → local-vs-venue position mismatch reported EVERY cycle
  r5  operator resolves        → close at venue, or backfill levels; books converge
```

Before the `on_execution` hook existed, W1 spanned the **remainder of the
entire execution loop plus the post-cycle batch append** — on a live venue,
multi-second network round-trips covering *all* of a cycle's orders. The
hook collapsed it to the single append at t3, and a mid-loop failure of
order N+1 can no longer lose orders 1..N's metadata (regression-tested).

## 3. Why W1 cannot be eliminated without distributed transactions

The order becomes durable in the **venue's** failure domain at t1' (their
matching engine, their disks); the metadata becomes durable in **ours** at
t3. Making those a single atomic step requires an atomic commit across two
systems that share no transaction coordinator — the classic distributed
atomic commit / Two Generals impossibility. Concretely, every reordering
fails:

- **Record levels before transmitting?** The key to record under —
  `client_order_id` — is generated *inside* frozen
  `OrderManager.place_order` at transmission time (Module 6). It does not
  exist at "before". Recording under a provisional key would still require
  a post-ACK append to bind provisional→actual — an identical window, plus
  a new orphan class for orders that fail to transmit.
- **Two-phase commit?** Requires the venue to act as a prepared resource
  manager (prepare/ack/commit). No exchange exposes XA semantics over
  REST; Hyperliquid's `/exchange` accept is its commit, unilaterally.
- **Compensate by cancelling on recovery?** The order may have **filled**
  before restart — fills are not compensable; capital moved.

Every protocol reachable from this architecture has some instant at which
one domain has committed and the other has not. The only engineering
choices are *where* that instant sits, *how wide* it is, and *what the
failure mode is*. This architecture chooses: after venue-ACK, one append
wide, conservative-and-loud.

## 4. Why W1 is equivalent to the already-accepted W2 (create↔mapping)

| Property | W1 (ACK↔levels) | W2 (create↔mapping) |
|---|---|---|
| Width | one local fsync | one local fsync |
| Frequency | once per order | once per position |
| Trigger | hard crash in a microsecond-class window | hard crash in a microsecond-class window |
| Result | order with unbookable fills | inert orphan position in NEW |
| Fabricates data? | never | never |
| Enters a risk decision? | no (position never created) | no (never margined, never in `open_position_ids`) |
| Detection | loud note every sync **and** reconciliation mismatch every cycle | none needed (provably inert) |
| Prior durable anchor | venue's own order record + local SUBMIT event | Module 7's CREATE event |

Both are "one correlation append behind an already-durable fact in a scope
this layer does not control" (the venue's matching engine; frozen Module
7's self-minted id). Accepting one and not the other would be
inconsistent.

## 5. Why the failure mode is conservative

"Conservative" here means **bookkeeping-conservative**: the system never
invents a number it does not know.

- No position is created without a real stop price — a fabricated stop
  would silently corrupt stop-distance, heat, R-multiples, and every
  downstream risk figure. Corrupted-but-plausible books are strictly worse
  than visibly incomplete books.
- No margin is reserved, no fee applied, no PnL booked — the portfolio
  ledger's `Assets == Equity` invariant is never touched by guessed data.
- The gap is **impossible to miss**: the skip note surfaces in every
  sync's notes (→ `AppState.last_error` → `/status`, `/reports`, the
  dashboard, Telegram), and `reconcile()` reports the local-vs-venue
  position mismatch **every cycle** until resolved.

The honest cost: until the operator acts, risk evaluation under-counts the
venue position (it is absent from `open_position_ids`). That direction is
mitigated by loudness — the condition cannot silently persist or compound,
unlike fabricated books, which would compound invisibly.

## 6. Why replay and reconciliation recover safely

- **Replay:** every accounting fact is exactly one append; there are no
  multi-record partial writes to tear. Replay after any crash
  reconstructs precisely the fsync'd prefix (torn tails truncated by
  Module 3's recovery), and re-syncing the venue's full fill history
  against that prefix is a proven no-op for everything already booked
  (fill-id-keyed ledger; zero-append verified under triple replay and
  double-crash sequences).
- **The order and its fills are never lost** — only this layer's
  *metadata about* them. OrderManager's SUBMIT precedes transmission
  (persist-before-transmit), its resync re-derives the venue order from
  the deterministic cloid, and fills are durably recorded with per-fill-id
  dedup. Recovery therefore has the complete factual record; it lacks only
  the strategy's stop level, which existed nowhere durable at crash time.
- **Reconciliation** is the independent safety net: it compares venue
  positions against local books from primary sources each cycle, so the
  divergence is re-detected forever until resolved — it does not depend
  on any state that the crash could have lost.

## 7. Why "fixing" it in the current architecture is not available

| Approach | Verdict |
|---|---|
| Carry `stop_price` in Module 6's SUBMIT event / `OrderSnapshot` | Requires modifying frozen Module 6 (its event schema and public snapshot). The correct long-term home for the fix, but a freeze-breaking change needing explicit authorization — not an app-layer patch. |
| Enlist the venue in a transaction with the EventStore | Impossible: cross-system atomicity without a coordinator (§3). |
| Pre-record under a provisional key | Reintroduces an equivalent post-ACK bind window + a new orphan class (§3). |
| Derive a stop at fill time (from fill price, config default, etc.) | Fabrication. Violates the layer's founding rule — corrupts capital bookkeeping silently. Rejected. |
| Cancel-on-recovery for unrecorded orders | Unsound: the order may have filled; fills cannot be compensated. |

**Decision:** W1 and W2 are accepted residuals — bounded to one append,
once per order/position, conservative, loud, and operator-recoverable.
Should Module 6 ever be reopened under the additive-evolution discipline
(AD-18), carrying the stop level in the SUBMIT event would eliminate W1 at
the source; until then, no change is warranted.
