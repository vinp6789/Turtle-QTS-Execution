# PROJECT_DASHBOARD.md

**Read this first.** Single-page executive summary. Every number here is
sourced from a specific document — this page aggregates, it does not
duplicate; follow a link for the underlying detail and reasoning.

---

## Headline

| | |
|---|---|
| **Overall completion toward long-term vision** | ~50–55% (`docs/STRATEGIC_GAP_ANALYSIS.md`) |
| **Current phase** | Alpha Engine: research phase, between campaigns · Execution Engine: dormant, stable |
| **Current campaign** | None active — Campaign 05 closed (both experiments REJECTED) |
| **Approved alpha models** | **0** |
| **Rejected hypotheses** | **18** (4 each: Campaigns 01–04; 2: Campaign 05) · 1 deferred (Funding Persistence, non-viable N_eff) |
| **Retired models** | 0 (nothing has ever gone live) |
| **Watchlist size** | 3 symbols (BTC, ETH, SOL) — `docs/WATCHLIST.md` |
| **Historical datasets available** | OI + funding rate + mark price, BTC/ETH/SOL, 18 months, both Binance and Hyperliquid for funding — `docs/HISTORICAL_DATA.md` |
| **Full regression suite** | 1,602 passing (820 Execution Engine + 782 Alpha Engine), 0 failing |
| **Next milestone** | Decision required: accept a credentialed, requester-pays AWS dependency to acquire official Hyperliquid S3 liquidation-bearing fill archives (**RD-10**) |

## Engineering status

| Subsystem | Status | Detail |
|---|---|---|
| Execution Engine (Modules 1–10 + app layer) | Frozen, complete, independently audited — GO on engineering/capital safety, CONDITIONAL on secrets hygiene, testnet-ready pending 2 operator actions | `docs/PROJECT_STATUS.md`, `FINAL_PRODUCTION_AUDIT.md` |
| Alpha Engine platform (registry → validation → evidence → governance → lifecycle → bridge) | Complete and proven end-to-end on real data across three independent campaigns (CAMP-01, CAMP-02, CAMP-03) with zero new platform code required for the 2nd or 3rd | `docs/ALPHA_ENGINE.md`, `docs/PROJECT_STATUS.md` |
| Historical data pipeline | Complete, tested, incrementally rerunnable | `docs/HISTORICAL_DATA.md` |

## Research status

| | |
|---|---|
| Campaigns run | 5 closed (CAMP-01 OI level, CAMP-02 Funding absolute, CAMP-03 Funding venue-relative, CAMP-04 Funding delta, CAMP-05 OI velocity) |
| Campaigns closed | 5 — all 18 experiments REJECTED; CAMP-05 (OI velocity) was the cleanest, best-powered rejection (every walk-forward fold cleared the sample floor; regime-balanced failure); Funding Persistence deferred as statistically non-viable (N_eff too low) |
| Alpha Library | Empty of approved models — `docs/ALPHA_LIBRARY.md` |
| Family state (RD-07 two-state model) | Funding **NEAR-EXHAUSTED**/READY · Open Interest **ACTIVE**/READY (Binance only, capped; only Divergence untested) · Liquidations **LOCKED**/**NONE** (official S3 history exists but unacquired — credential + requester-pays gated, RD-10) · all others LOCKED or PAUSED/NONE |
| Current campaign | None active |

## Operations status

| | |
|---|---|
| Paper trading | Never run |
| Live trading | Never run |
| Alpha Engine wired into any deployment | No (verified: zero references to `alpha_engine` in `app/` or `composition_root/`) |
| Execution Engine mainnet | NO-GO — testnet checklist + soak incomplete (`docs/PRODUCTION_CHECKLIST.md`, `FINAL_PRODUCTION_AUDIT.md`) |

## Major risks (see `docs/PROJECT_STATUS.md` "Known risks" for full detail)

1. Binance-vs-Hyperliquid venue mismatch was **confirmed** by Campaign 02
   and is now **permanently mitigated** by the venue-relative methodology
   rule Campaign 03 applied — every future exchange-native threshold is
   derived independently per venue.
2. Per-symbol research slices are underpowered and were directionally
   inconsistent in Campaign 01, and Campaigns 02–03's aggregate "passes"
   were 75–94% concentrated in one market regime — a caution against
   trusting pooled or per-symbol headline numbers without inspecting the
   breakdown.
3. Walk-forward's `min_signaled_samples` floor can still fail per-fold
   even after reducing `n_folds`, if signals cluster unevenly across
   chronological folds (Campaign 03 finding) — the feasibility review
   should check the real chronological split, not just the average.
4. A plaintext secrets file was found and partially remediated
   (`FINAL_PRODUCTION_AUDIT.md` SEC-1) — key rotation still recommended
   before mainnet.

## Where to go next

- **New to the project?** Read `PROJECT_CONSTITUTION.md`, then this page,
  then `docs/PROJECT_STATUS.md`.
- **Picking up research work?** `ROADMAP.md` §1, then
  `docs/RESEARCH_PLAYBOOK.md`, then `docs/RESEARCH_LEDGER.md`.
- **Reviewing a change?** `docs/REVIEW_PROTOCOL.md`.
- **Looking for a specific document?** `docs/MASTER_INDEX.md`.
