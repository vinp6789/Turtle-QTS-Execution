# WATCHLIST.md

This document holds **two separate lists that must never be confused**:

1. **The executable trading universe** (below) — the instruments the Alpha
   Engine may research and trade. An enforced guardrail, wired into
   `alpha_engine.watchlist` and refused at construction time if violated.
   Owned by **Track B (Product Development)**.
2. **The Reverse Engineering watchlist** (§ at the end) — *systems* to
   study for mechanism candidates. Enforced by nothing; it is a reading
   list. Owned by **Track C (Reverse Engineering)**.

The first constrains capital. The second constrains attention. Merging
them would make a research target look like a trading permission.

---

# Part 1 — Executable trading universe

The watchlist is the configurable universe the Alpha Engine is allowed to
research and trade — "generate alpha only from a configurable watchlist"
is a system objective stated in `PROJECT_CONSTITUTION.md` §1 item 6.

## Current watchlist

**BTC, ETH, SOL** — the symbols used throughout Campaigns 01–08 and the
only symbols the historical data pipeline has backfilled
(`docs/HISTORICAL_DATA.md`).

**Pending expansion (Track B, `ROADMAP.md` B5).** The cross-sectional
mechanism requires a materially wider universe: `[M]` three symbols carry
an effective sample size of 1.61 directionally, thirty carry 4.54, and
thirty market-neutral carry 21.58 (`docs/MECHANISMS.md`). Any expansion
must be **reconstructed point-in-time** — the 30-symbol panel used in
feasibility work was selected by *today's* volume, which is survivorship
bias and is not admissible in a pre-registration.

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

Per `docs/STRATEGIC_GAP_ANALYSIS.md` (#6, #8, #9) and `ROADMAP.md` Track B (B4):
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
exists; see `ROADMAP.md` Track B (B4) for the explicit sequencing rationale.

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

---

# Part 2 — Reverse Engineering watchlist (Track C)

**Systems to study, not instruments to trade.** Nothing here is a
permission, a hypothesis, or a commitment to build.

**Output contract:** studying a system produces **a row in
`docs/MECHANISMS.md` and nothing else** — no code, no campaign, no report
series. The mechanism column below is a *pointer* to that table, not a
copy of it; mechanism status, evidence and next actions live there and are
deliberately not repeated here.

**Compatibility rule (standing, `PROJECT_CONSTITUTION.md` §5 and
`docs/HISTORICAL_DATA.md`):** no paid datasets, no paid APIs, no paid
software. A system that cannot be studied and reproduced from free,
open-source or public resources is marked **NOT COMPATIBLE** and dropped —
not deferred.

| # | System / body of work | Why it is worth studying | Free-data compatible? |
|---|---|---|---|
| **1** | **HLP (Hyperliquid vault)** | **Study first.** The only target whose mechanism *and* returns are both directly measurable from public endpoints. `[M]` +16.6 %/yr trailing 12 m — the project's own hurdle rate | **Yes** — `vaultDetails`, free, keyless |
| 2 | **CTA / managed-futures programmes** | The largest body of publicly documented systematic trading; published methodology and long track records | **Yes** — academic papers, public factsheets |
| 3 | **Trend following (as a documented industry, not as an indicator)** | Studying *why* it worked and where it decayed, given the family is permanently rejected here (Constitution §4). **Studying is permitted; re-implementing is not** | **Yes** |
| 4 | **Basis / cash-and-carry** | The clearest example of a mechanism with an identifiable counterparty and an economic reason to pay | Partly — `[M]` HL spot volume ≈ 0 for the watchlist, so no deliverable leg exists on the production venue |
| 5 | **Relative value / statistical arbitrage** | Directly informs the highest-ranked untested mechanism | **Yes** — public literature |
| 6 | **Liquidity provision / market making** | HLP's actual business; the structural way to *earn* the maker rebate rather than pay the taker fee | **Yes** to study. `[M]` Live execution is constrained: 0.13 bp spreads, REST-only adapter |
| 7 | **Capacity-constrained strategies** | `[E]` limits-to-arbitrage is the best-documented reason a retail-size edge can persist at all | **Yes** |
| 8 | **Session effects** | Untested here; cheap to test as a by-product of an existing harness | **Yes** — timestamps |
| 9 | **Liquidity sweeps / stop hunts** | Would need market-wide order flow, which the project does not have | **Blocked** — RD-18 §C, adapter is REST-only and reads only the account's own fills |
| 10 | **Calendar effects** | Cheap; `[E]` weak and heavily arbitraged, so low expected value | **Yes** — timestamps |
| 11 | **Perpetual mechanics** (funding settlement, fee tiers, staking discounts, liquidation engine design) | `[M]` The highest-certainty non-predictive lever measured so far: fee tier and staking discounts move the breakeven for **every** future campaign at once | **Yes** — `userFees`, public docs |

**Explicitly excluded as NOT COMPATIBLE:** anything requiring private
order flow, colocation, exchange relationships, prime brokerage, paid
market-data subscriptions, or proprietary datasets. Renaissance/Medallion
is studied only as **published external commentary** — `[E]` its edge is
capacity and turnover, not a secret signal — and never as a reproducible
target.

**How a study closes.** Each target is timeboxed and ends in exactly one
of: a new `MECHANISMS.md` row · an update to an existing row · or a
recorded **NOT COMPATIBLE** verdict with the reason. A study that produces
none of these three was not finished.
