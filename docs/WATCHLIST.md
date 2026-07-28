# WATCHLIST.md

The watchlist is the configurable universe the Alpha Engine is allowed to
research and trade — "generate alpha only from a configurable watchlist"
is a system objective stated in `PROJECT_CONSTITUTION.md` §1 item 6.

## Current watchlist

**BTC, ETH, SOL** — the symbols used throughout Research Campaign 01 and
the only symbols the historical data pipeline has backfilled to date
(`docs/HISTORICAL_DATA.md`).

There is **no persisted watchlist file** in the repository (verified — no
`*.json` watchlist file exists anywhere). The watchlist used by Campaign
01 was constructed in code
(`Watchlist(name="campaign-01", symbols=(Symbol("BTC"), Symbol("ETH"),
Symbol("SOL")))`, `research/campaign_01_open_interest/run_campaign.py`),
not loaded from a checked-in configuration file. Creating a durable,
checked-in watchlist file (via `alpha_engine.watchlist.load_watchlist`,
which already supports this — see Implementation status below) is
low-cost future work once a second campaign needs a possibly-different
universe.

## Purpose

The watchlist is the single, explicit boundary on what the Alpha Engine
may ever touch — no candidate specification, no research cycle, and no
live-trading bridge may reach outside it. It exists so "which assets does
this system evaluate" is always an explicit, reviewable, pre-committed
list, never an emergent side effect of whatever data happened to be
available.

## Selection philosophy

- **Depth and liquidity first.** BTC and ETH are the deepest, most liquid
  perpetual markets with the longest free historical data (Binance
  coverage from 2020-01/2020-09 — see `docs/HISTORICAL_DATA.md`). SOL was
  added as the third symbol specifically to test whether a hypothesis
  generalizes beyond the two largest-cap assets, not because it was
  expected to behave identically.
- **Cross-symbol generalization is a requirement, not a bonus.** Campaign
  01 explicitly pooled all three symbols for its powered analysis and
  additionally inspected per-symbol slices — and found the per-symbol
  results were directionally *inconsistent* (BTC favoured contrarian, SOL
  favoured momentum), which is exactly the kind of finding a
  single-symbol watchlist would have hidden. A watchlist should always
  include enough symbols to catch this.
- **The watchlist is deliberately small today.** Three symbols were
  sufficient depth for Campaign 01's dataset (18 months × 3 symbols ≈ 1M
  rows) to remain tractable to backfill and validate in one session. Size
  grows only when a specific research question needs a broader universe,
  not preemptively.

## Inclusion rules

A symbol may be added to the watchlist when:
1. A free, reliable historical data source exists for it (per
   `docs/HISTORICAL_DATA.md`'s own source-evaluation discipline) for
   every metric a planned campaign needs.
2. The live execution venue (Hyperliquid) actually lists it — a symbol
   the Alpha Engine could research but never trade live provides research
   value only, which is a legitimate but distinct reason to add it (state
   this explicitly if it's the reason).
3. Adding it doesn't silently change the interpretation of an
   already-running or already-completed campaign — a watchlist change
   takes effect for new campaigns, never retroactively for a sealed
   evidence package.

## Removal rules

A symbol is removed from the watchlist when it no longer has a reliable
data source, is delisted from the live venue, or a deliberate research
decision narrows scope for a specific campaign. Removing a symbol never
retroactively invalidates a sealed evidence package or a governance
decision already recorded for it (`docs/RESEARCH_LEDGER.md` entries are
permanent regardless of later watchlist changes).

## Future automation plan

Per `docs/STRATEGIC_GAP_ANALYSIS.md` (#6, #8, #9) and `ROADMAP.md` §2:
today the watchlist is an **enforced guardrail** ("never evaluate outside
this list"), not yet a **driver** ("automatically evaluate every member").
The intended end state (`PROJECT_CONSTITUTION.md` §8):

```
Watchlist → Evaluate every approved alpha → Combine evidence →
Rank assets → Portfolio construction → TradeIntent → Execution Engine
```

This requires, in order: (1) at least one approved alpha model to
evaluate against the watchlist at all, (2) a model-combination policy
(today: conflict-refusal only, no real combination —
`alpha_engine/portfolio/selection.py`), and (3) a per-asset evidence
ranking layer (today: none exists — `compare_experiments()` ranks
experiments, not assets). None of this should be built before item (1)
exists; see `ROADMAP.md` §2 for the explicit sequencing rationale.

## Current implementation status

- **`alpha_engine.watchlist.Watchlist`** — a named, immutable, ordered,
  duplicate-free tuple of `Symbol`s. `load_watchlist(path)` loads and
  validates one from a small JSON file (`{"name": ..., "symbols": [...]}`)
  — implemented, tested, **not yet exercised against a checked-in file**
  (Campaign 01 constructed its watchlist in code).
- **Enforcement (audit finding C4, closed):** both
  `alpha_engine.research.run_research_cycle(..., watchlist=...)` and
  `alpha_engine.execution_bridge.ApprovedFundingAlphaStrategy(...,
  watchlist=...)` accept an optional `watchlist` argument; when supplied,
  a specification whose universe reaches outside it is refused at
  construction/cycle-start. Optional and defaults to `None` (no
  enforcement) for backward compatibility — a caller must consciously
  wire it in.
- **Not yet implemented:** automatic full-watchlist evaluation (a human
  still decides which watchlist symbols go into any given
  `CandidateSpecification.universe`), per-asset ranking, and
  multi-model combination (see Future automation plan above).

See `docs/ALPHA_ENGINE.md` for the full technical architecture and
`alpha_engine/watchlist.py`'s own module docstring for the exact
validation rules.
