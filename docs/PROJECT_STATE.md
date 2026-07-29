# PROJECT_STATE.md

**This is the single authoritative execution-state document for the
entire repository.** It replaces the execution-state role formerly split
across `PROJECT_STATUS.md` and `PROJECT_DASHBOARD.md` — both are now
deprecated pointers to this file (see their banners). For the project's
unchanging vision and principles, see `PROJECT_CONSTITUTION.md`. For
future work only, see `ROADMAP.md`.

All figures below were verified against the repository at the time of
writing (full suite run, `git log`, file listing, live archive probes) —
not carried from memory. Superseded facts are corrected here the moment
they're found, never silently carried forward.

## Read Order

1. **Read this document (`PROJECT_STATE.md`) first — always.**
2. Open only the specific documents referenced below for the task at
   hand (e.g. `RESEARCH_PLAYBOOK.md` before pre-registering a campaign,
   `RESEARCH_DECISIONS.md` before changing methodology).
3. **Never reconstruct project status by cross-referencing multiple
   documents.** If two documents disagree, this one is authoritative —
   the discrepancy is a defect in the other document, report it.
4. `PROJECT_STATE.md` is the **authoritative execution state**. Every
   other document is either unchanging principle (`PROJECT_CONSTITUTION.md`),
   forward-only planning (`ROADMAP.md`), permanent scientific/decision
   record (`RESEARCH_LEDGER.md`, `RESEARCH_DECISIONS.md`, `ALPHA_LIBRARY.md`),
   or point-in-time technical reference (everything else — see
   `MASTER_INDEX.md`'s Core/Reference/Archive tiering).

---

## Executive Summary

| | |
|---|---|
| **Current phase** | Alpha Engine: research phase, between campaigns. Execution Engine: frozen, dormant, stable, no live capital. |
| **Overall completion toward long-term vision** | ~50–55% (`docs/STRATEGIC_GAP_ANALYSIS.md`; platform is no longer the bottleneck — a validated alpha signal is) |
| **Current objective** | Full 12-month liquidation backfill (Backlog 1.5), then Campaign 06's outcome-blind feasibility review (1.6) |
| **Current blocker** | No single blocker — a short, ordered chain of verified prerequisites, none of which is an open research question. **All four P0 items, Backlog 1.3, and Backlog 1.4 (incl. a Medium-severity QA finding) closed.** |
| **Immediate next task** | Full 12-month liquidation backfill, single pass, all symbols retained (Backlog 1.5) |
| **Full regression** | **1,687 passed, 92 subtests, 0 failed** (re-verified this session — independent QA audit of Backlog 1.4 + fixes, 4 new tests) |
| **Approved alpha models** | **0** |
| **Rejected hypotheses** | **18** (4 each: Campaigns 01–04; 2: Campaign 05) · 1 deferred pre-registration (Funding Persistence, non-viable N_eff) |

---

## Current Phase

**Alpha Engine — research phase, five campaigns closed, sixth not yet pre-registered.**
Campaigns 01–05 (Open Interest level, Funding Rate absolute, Funding Rate
venue-relative, Funding Delta, OI Velocity) all ran end-to-end — real
data, real evidence, real governance — and all closed REJECTED. A
one-month outcome-blind liquidation pilot has since completed
successfully (below), and a chain of verified engineering/documentation
prerequisites stands between here and Campaign 06's feasibility review.

**Execution Engine — dormant, stable, unchanged.** No work planned except
an authorized critical-defect correction (`PROJECT_CONSTITUTION.md` §9) or
the outstanding testnet operator actions (`ROADMAP.md` §4), neither gated
by nor gating Alpha Engine research.

---

## Current Objective

All Priority 0/1.1/1.2/1.3 defect-chain items are closed. Remaining:
collect the outcome series (1.4), run the full 12-month liquidation
backfill (1.5), then determine — via an outcome-blind feasibility
review, not intuition — whether a 12-month liquidation campaign is
statistically viable at all (1.6), before spending further engineering
or research effort on it. See **Immediate Backlog** for the exact
ordered chain.

---

## Completed Milestones

### Execution Engine
- **Modules 1–9 frozen** — `f7c5a1e` (2026-07-15). Deterministic,
  event-sourced, crash-safe core. Evidence: `FINAL_PRODUCTION_AUDIT.md`.
- **Module 3.1** — Windows Event Store `O_BINARY` corruption fix, frozen
  alongside (`576e818`, 2026-07-15).
- **Module 10 — HyperliquidAdapter** — WP-1 through WP-5, frozen `cafadba`
  (2026-07-18); production application layer `36c87f4` (2026-07-19);
  production hardening + testnet readiness `0281d69` (2026-07-21).
  Evidence: `MODULE_10_FREEZE.md`.
- **Independent production audit** — passed, conditional GO for testnet
  pending 2 operator actions (`FINAL_PRODUCTION_AUDIT.md`).

### Application Layer
- Accounting, emergency stop, read isolation, Telegram lifecycle
  (monitoring/notification tier only — see Deferred Work), order-manager
  multifill/suppression, quantization, scheduling — all under `0281d69`
  (2026-07-21). Evidence: `tests/test_app_*`, `tests/test_hb_multifill_close.py`,
  `tests/test_open_order_suppression.py`, `tests/test_trading_system_*`.

### Alpha Engine
- Scaffolding → Experiment Registry (write/query) → Funding Rate
  provider/feature/candidate → five-stage validation gate (single-pass,
  causality audit, walk-forward, bootstrap resampling, regime
  stratification) → Evidence Package (sealed, fingerprinted) → lifecycle
  state machine → governance decision recording → candidate catalog +
  Watchlist → research cycle orchestrator → promotion path (portfolio
  selection + execution bridge) → degradation/retirement.
- Full audit remediation (A1–C4, B1–B6) — hardening pass, additive only.
- Evidence: `alpha_engine/DECISIONS.md` D1–D9; `tests/test_alpha_engine_*`.

### Historical Pipeline
- `errors.py` / `models.py` / `storage.py` (CSV, incremental merge) →
  `sources/binance.py` → `sources/hyperliquid.py` → `pipeline.py`
  orchestrator → public API → tests → documentation.
- `MarkPriceObservation` + `collect_mark_price` (derived:
  `price = sum_open_interest_value / sum_open_interest`).
- **RD-10/RD-12:** `LiquidationObservation` + `sources/hyperliquid_s3.py`
  (10 plain functions, 0 classes) — official Hyperliquid S3 fill archive,
  Requester Pays, boto3 default credential chain.
- Evidence: `docs/HISTORICAL_DATA.md`; RD-10/RD-12 in `docs/RESEARCH_DECISIONS.md`.

### Research Campaigns (all closed, immutable — never retried, never edited)

| Campaign | Hypothesis | Result | Detail |
|---|---|---|---|
| **01** | Open Interest (level) | REJECTED — hit rates 0.49–0.51 | `RESEARCH_CAMPAIGN_01_open_interest.md` |
| **02** | Funding Rate (absolute threshold) | REJECTED — venue-transfer confound discovered | `RESEARCH_CAMPAIGN_02_funding_rate.md` |
| **03** | Funding Rate (venue-relative threshold) | REJECTED — confound removed, no edge either venue (Binance 0.525, HL 0.531) | `RESEARCH_CAMPAIGN_03_...md` |
| **04** | Funding Delta | REJECTED — best-powered funding rejection. Funding Persistence deferred pre-registration (N_eff ≈4–18, RD-04) | `RESEARCH_CAMPAIGN_04_funding_delta.md` |
| **05** | OI Velocity | REJECTED, both directions — cleanest, best-powered rejection to date; DEFER-ceiling (no HL OI history) | `RESEARCH_CAMPAIGN_05_oi_velocity.md` |

**18 rejected hypotheses, 1 deferred pre-registration, 0 approved.**
Funding family: **NEAR-EXHAUSTED**. Full detail: `docs/RESEARCH_LEDGER.md`.

### Infrastructure
- Checkpoint durability pattern proven under a real `os._exit(9)` hard-kill
  test: `flush()` → `os.fsync(fd)` → `os.replace` → best-effort
  `_fsync_dir()` (`hyperliquid_s3.py::write_checkpoint`).
- Verified zero platform-specific branches anywhere in `alpha_engine/`
  (repo-wide grep); credentials resolve via boto3's default chain
  identically on Railway/Docker/laptop/VPS.

### Documentation
- Full consolidation: `PROJECT_CONSTITUTION.md`, `RESEARCH_LEDGER.md`,
  `ALPHA_LIBRARY.md`, `WATCHLIST.md`, `RESEARCH_PLAYBOOK.md`,
  `REVIEW_PROTOCOL.md`, `MASTER_INDEX.md` — cross-referenced, indexed.
- `RESEARCH_DECISIONS.md` — RD-01 through RD-13, append-only.
- **This reorganization (2026-07-29):** `PROJECT_STATE.md` created as the
  single execution-state authority; `PROJECT_STATUS.md` and
  `PROJECT_DASHBOARD.md` deprecated in place; `ROADMAP.md` purged of
  completed work and re-synchronized; `MASTER_INDEX.md` given an explicit
  Core/Reference/Archive tiering.

### Operations
- One-month outcome-blind liquidation pilot backfill executed and
  completed (see Decision Register). Current regression figure lives in
  the Executive Summary and Active Work sections above — not duplicated
  here to avoid exactly this kind of drift.

---

## Active Work

**P0 chain closed this session (2026-07-29):**
- `data/alpha_engine_research/` (880 KB, 36 files) now tracked in git —
  `.gitignore` scoped via `data/*` + explicit negation, verified zero
  `data/alpha_engine_historical/` files leak through.
- `storage.py::merge_and_write` durability fixed — identical
  flush+fsync+`os.replace`+dir-fsync pattern as `hyperliquid_s3.py`; 4 new
  tests (fsync-before-replace ordering, hard-kill-after-replace
  simulation, corrupt-directory-fsync-is-best-effort, no-orphaned-tmp).
  Orphaned `open_interest__BTC__binance.csv.tmp` removed after
  re-verifying byte-identical to its live CSV.
- `RESEARCH_PLAYBOOK.md` §5 — expectancy-sign inspection clause restored
  (Constitution §7 / Campaign 01 precedent), citing `mean_directional_return`
  as the quantity a reviewer must inspect at governance, not a new
  `runner.py` acceptance key.
- **RD-13** written — full pilot record (208,486 events, 2.00 rows/event,
  0 duplicates, 0 decode errors), the measured cross-symbol correlation
  finding (+0.85–0.90), a new self-activating feasibility-review
  requirement (N_eff + cross-instrument correlation, not raw pooled
  counts), and the correction to RD-12's now-stale "no backfill executed"
  claim. Liquidations Data Status: `NONE` → `COLLECTING`.
- Full regression: **1,644 passed, 91 subtests, 0 failed.**
- **Committed as `feb84d0`** (2026-07-29) — 50 files, +2591/-577. Working
  tree clean.

**Backlog 1.3 closed (2026-07-29):**
- `collect_liquidations()` added to `pipeline.py` — the 5th `collect_*`
  entry point, deliberately hour-granularity/checkpoint-resumable rather
  than day-covered (see the function's own DURABILITY docstring section)
  and deliberately plural (`symbols: Tuple[Symbol, ...]`, not a single
  `symbol`) since one hourly archive object serves every symbol at once.
- **Durability defect found and PARTIALLY fixed during implementation,
  before commit:** the first draft only called `storage.merge_and_write`
  once at the very end of the whole requested date range, while the
  checkpoint (correctly) advances every hour. Changed to flush to disk
  once per calendar day. **This partial fix was itself defective — see
  the QA review cycle below, which found and closed the remaining gap.**
- `alpha_engine/historical/backfill_liquidations.py` — the CLI entry
  point (Constitution §5), retiring the scratchpad-only pilot driver.
  `python -m alpha_engine.historical.backfill_liquidations --start ... --end ...`.
- `boto3>=1.34.0` / `lz4>=4.3.0` declared in `requirements.txt`, scoped
  to the historical pipeline only (both lazily imported; re-verified the
  deployed `app.main` entrypoint still imports neither).
- 19 new tests (11 `collect_liquidations`, 8 CLI). Full regression at the
  time: 1,661 passed, 92 subtests, 0 failed — **later found incomplete,
  see below.**

**Independent QA audit of Backlog 1.3, then fixes (2026-07-29):** an
independent reviewer audited the committed implementation against
`PROJECT_STATE.md`'s own durability claims and found one High, one
Medium, and three Low findings; all were independently re-verified
before any fix was written (each finding was reproduced from a minimal,
from-scratch probe — not accepted on the audit's word alone — and each
fix was confirmed red→green: the new regression test fails against the
pre-fix code and passes against the fix).

- **H1 (High, closed) — the per-day flush above did not restore the
  actual invariant.** The checkpoint still advanced per HOUR, inside the
  fetch loop, while the flush to disk still only happened once, after
  the loop, per DAY. A crash between the checkpoint write for hour *k*
  and that day's eventual flush left the checkpoint durably ahead of
  hours 0..*k* with **zero** bytes of their data ever written anywhere —
  reproduced directly: crash at hour 3 of a 5-hour day left the
  checkpoint at hour 2 with no CSV file even created. **Root fix:**
  checkpoint write moved to strictly after the day's flush succeeds, and
  reduced to one write per day (to the last hour of that day's batch) —
  not one write per hour. If a fetch fails partway through a day,
  nothing is written and the checkpoint does not move; the **whole day**
  is safely retried from scratch on the next call. Locked in by
  `test_mid_day_interruption_does_not_advance_checkpoint_past_unpersisted_rows`,
  confirmed to fail against the pre-fix code (checkpoint left at hour 2,
  zero rows persisted) and pass against the fix.
- **M1 (Medium, closed) — the CLI's retry only caught `HistoricalDataError`,
  and `hyperliquid_s3.py` never raised it for a real S3 failure.**
  Neither `list_hour_keys` nor `fetch_hour` wrapped their `s3.list_objects_v2`/
  `s3.get_object` calls, so a genuine transient failure surfaced as a raw
  `botocore` exception and escaped the retry loop entirely — reproduced
  directly with a simulated `EndpointConnectionError`. **Fix:** both
  calls now translate `botocore.exceptions.(BotoCoreError, ClientError)`
  into `HistoricalDataError`, mirroring `sources/binance.py`'s own
  `HTTPError`/`URLError` translation exactly — no change needed to the
  CLI's retry loop itself. 3 new tests in `test_historical_hyperliquid_s3.py`.
- **L1 (Low, closed) — `--force`/`--checkpoint-path` were not reachable
  from the CLI**, so the one lever that fully recovers from H1 (before
  it was fixed) required dropping into Python. Both flags added to
  `backfill_liquidations.py`'s argparse and threaded through `run()`.
- **L3 (Low, closed) — a fresh `boto3` client was constructed on every
  `list_hour_keys`/`fetch_hour` call** (measured: 25/day in a synthetic
  test), fragmenting connection reuse against the remote Requester-Pays
  region across a multi-day backfill, both functions already accept
  `client` for exactly this reuse. **Fix:** one client constructed per
  `collect_liquidations()` call, threaded through every call within it.
  Locked in by `test_reuses_one_s3_client_across_the_whole_call`.
- **L2 (Low, deferred, not fixed)** — `CollectionResult.periods_unavailable`
  counts DAYS for liquidations vs. the same-unit-as-`periods_fetched`
  convention every sibling collector uses; already documented in
  `collect_liquidations`'s own docstring, doesn't affect correctness, and
  was explicitly scoped as optional. Left deferred per instruction.
- 8 new tests. Full regression: **1,669 passed, 92 subtests, 0 failed.**

**Backlog 1.4 closed (2026-07-29):** outcome series 2025-07-27 → present.
- `sources/hyperliquid.py::fetch_daily_candles()` — new function, live-verified against the real `candleSnapshot` endpoint (2026-07-29): all price fields string-encoded decimals, no pagination cap up to a 368-day single request (unlike `fundingHistory`'s 500-record cap), a repeated call against an already-closed day returned byte-identical data (point-in-time stable). Decodes into `MarkPriceObservation` using the candle CLOSE — a **daily close, not a point-in-time mark price** (derivation-scope note, RD-11 A), documented in both the function's docstring and `MarkPriceObservation`'s own.
- `pipeline.py::collect_mark_price()` split into a dispatcher + `_collect_mark_price_binance`/`_collect_mark_price_hyperliquid`, mirroring `collect_funding_rate`'s existing two-source pattern exactly (same high-water-mark resume shape for the Hyperliquid side). `_SUPPORTED_MARK_PRICE_SOURCES` extended to `("binance", "hyperliquid")`.
- **Boundary defect found and fixed before committing, via a real end-to-end run against the live API (not caught by unit tests with fakes alone):** `_collect_mark_price_hyperliquid`'s `end_ms` computation copied `collect_funding_rate`'s "+1 day, exclusive" formula verbatim. Live-verified that `candleSnapshot`'s `endTime` is **inclusive** of a candle whose own `t` equals `endTime` exactly — safe for hourly funding settlements (which essentially never land exactly on a day boundary) but not for daily candles (whose `t` always does), so the copied formula silently included one extra day beyond the caller's requested range. First real run for BTC 2025-07-27→2026-07-28 pulled in a 369th, still-forming row for 2026-07-29. Fixed with a `-1ms` adjustment; locked in by `test_end_date_boundary_does_not_leak_the_following_days_candle`, confirmed to fail against the pre-fix formula (leaks a day) and pass against the fix. The erroneous data was deleted and the collection re-run cleanly.
- **Real end-to-end collection executed** (not just tested against fakes): Hyperliquid daily candles for BTC/ETH/SOL, 2025-07-27→2026-07-28 — **367/367/367 rows**, dates and values verified. Binance secondary-source backfill (via `collect_metrics`, chunked weekly with retry, mirroring `research/campaign_01_open_interest/collect_backfill.py`'s established pattern) **completed** — 159 chunks, 0 failures, 275,601 rows/metric — full coverage now Binance `2023-07-01..2026-07-27` (917 days), Hyperliquid `2025-07-27..2026-07-28` (367 days) per symbol; the one-day asymmetry is normal archive-publication lag (`unavailable=1`), not an error. Per the pre-existing, deliberate `data/` gitignore policy, none of this collected data is committed — only the code and tests are.
- **Independent QA audit of Backlog 1.4, then fixes (2026-07-29):** found one Medium and two Low findings; the Medium was independently re-verified with a fresh, self-authored probe (not accepted on the audit's word) before any fix was written, and the fix confirmed red→green.
  - **M1 (Medium, closed) — a still-forming daily candle was silently frozen at its partial value, permanently.** `fetch_daily_candles` returned Hyperliquid's in-progress "today" candle, which mutates as the day continues; `_collect_mark_price_hyperliquid`'s high-water-mark resume then never re-requested that timestamp once stored, and `storage.merge_and_write` keeps the first-seen value on conflict — so a partial close, once collected, could never self-correct. Reproduced directly: collecting mid-day stored close=111; re-collecting after the candle genuinely closed at 222 still returned the stale 111 (`rows_added=0`), no error, no warning. **Root cause:** the funding-settlement pattern (final the instant it's emitted) was reused for candles (not final until the day closes) without accounting for that difference — the same class of "pattern copied where the semantics differ" as the boundary bug already fixed once in this backlog item. **Fix:** `fetch_daily_candles` now compares each row's close time (`T`) against `clock()` and silently excludes any candle that has not yet closed — never an error, since the caller may legitimately be asking for an in-progress day. Verified against the real live API (not just fakes): a request through the end of today correctly returned only fully-closed candles, excluding today's. **Verified NOT present in the already-shipped data** — re-fetched all three symbols from the live API, 0 mismatches, because the manual collection driver used yesterday as `end_date`; the defect was latent, not manifested, and required no data correction.
  - **L1 (Low, closed) — `fetch_daily_candles`'s docstring and log message described the interval as half-open `[start_ms, end_ms)`**, contradicting the live-verified inclusive `endTime` the sibling boundary fix already depends on (copied from `fetch_funding_rate_range`, where it's accurate). Corrected to `[start_ms, end_ms]`, with an explicit note on why this endpoint differs from the funding one.
  - **L2 (informational, closed)** — this document's own "continuing in the background past this session's end" note for the Binance backfill was stale (it has since completed); corrected above.
- 4 new tests (3 source-level in `test_alpha_engine_historical_sources_hyperliquid.py`, 1 integration-level in `test_alpha_engine_historical_pipeline.py`), each confirmed to fail against the pre-fix code and pass against the fix. Full regression: **1,687 passed, 92 subtests, 0 failed.**
- `docs/HISTORICAL_DATA.md` §0/§1 updated: Mark Price added as its own row (both sources) to the source-comparison table; the DEX-first section's "Funding Rate is the only currently-collected metric where Hyperliquid-replicate is executable" claim corrected to scope it to feature metrics (mark price is an outcome series, not a feature, so it was never covered by that claim and didn't need venue-transfer validation — but the zero-overlap gap it closes is recorded).
- 14 new tests (9 `fetch_daily_candles`, 5 `collect_mark_price` Hyperliquid-path incl. the boundary regression). Full regression: **1,683 passed, 92 subtests, 0 failed.**

---

## Immediate Backlog

| Pri | Description | Dependencies | Blocking? | Effort | Status |
|---|---|---|---|---|---|
| ~~0.1~~ | ~~Track `data/alpha_engine_research/` in git~~ | — | — | — | **Done 2026-07-29** |
| ~~0.2~~ | ~~Fix `storage.py::merge_and_write` atomic write~~ | — | — | — | **Done 2026-07-29** |
| ~~0.3~~ | ~~Commit the current staged diff~~ | — | — | — | **Done 2026-07-29 (`feb84d0`)** |
| ~~1.1~~ | ~~Restore the governance-inspection clause in `RESEARCH_PLAYBOOK.md` §5~~ | — | — | — | **Done 2026-07-29** |
| ~~1.2~~ | ~~RD-13: record the pilot; correct RD-12's "no backfill executed"~~ | — | — | — | **Done 2026-07-29** — `ROADMAP.md` §1 also already unstaled in the prior doc-reorg session |
| ~~1.3~~ | ~~`collect_liquidations()` + CLI entry + declare `boto3`/`lz4`~~ | — | — | — | **Done 2026-07-29** — a real durability defect found and fixed during implementation, see Active Work |
| ~~1.4~~ | ~~Outcome series 2025-07-27 → present: Hyperliquid-native daily candles + Binance metrics~~ | — | — | — | **Done 2026-07-29** — a real boundary defect found via live end-to-end run and fixed, see Active Work |
| **1.5** | Full 12-month liquidation backfill, **single pass, all symbols retained** (~2.4 GB retained, ~$27 one-time; staged/partial backfill considered and rejected — walk-forward requires chronological contiguity, and month-selection would be an un-pre-registered researcher choice) | 0.2 (done), 1.3 (done) | Yes, for Campaign 06 only | ~1 day wall-clock | Not started |
| **1.6** | Feasibility review reporting **N_eff and cross-symbol correlation** (measured on pilot: ρ=+0.85–0.90 cross-symbol, ~438 raw signalled/yr at p60 → ~146/fold nominal but ≈53/fold after the correlation haircut) — not raw signalled counts | 1.5 | Yes — gates Campaign 06 pre-registration; **may reject Campaign 06 before it starts, which is the cheapest possible outcome** | ~1 day | Not started |
| **2.1** | Deep-history backfill: funding→2020-01 (BTC/ETH), 2020-09 (SOL); metrics→2021-01 (BTC), ~2022-01 (ETH/SOL); zero new code, verified free via Binance's public archive | None | No — gates the **next funding/OI campaign**, not Campaign 06 (orthogonal; corrected after being mis-sequenced in an earlier pass) | ~1 day | Not started |
| **2.2** | Route `data/alpha_engine_historical` through `config/loader.py` with an env override; declare a persistent Railway volume (`railway.json` currently declares none — `data/` is ephemeral there) | None | No | ~3 hrs | Not started |

---

## Deferred Work

| Item | Why deferred | Where it will land |
|---|---|---|
| **Historical Validation Layer (HVL)** | Trigger: the first campaign producing a SUPPORTED hypothesis (RD-11). Nothing has ever passed governance. | `ROADMAP.md` §2 |
| **"Robustness Validation" as a separate layer** | Rejected on Constitution §5 — its contents (Monte Carlo, parameter sensitivity → Research; stress/spread/fills → HVL; latency/delay → Paper Trading) dissolve into three existing homes with nothing left over. Zero concrete instances exist to justify a fourth layer. | Not scheduled — absorbed into HVL/Research/Paper Trading design notes |
| **Live Sample Recorder** | Correctly demoted after being briefly promoted — ~1.5-year lead time before any family it unlocks becomes testable (12–18mo accumulation, same as every archive-based campaign); addresses none of the failure modes seen to date (5 rejections on evidence, 2 kills on statistical power). Constitution §5: no present concrete need. | `ROADMAP.md` §2, last priority |
| **Telegram Operations Console** | Deferred until paper/live trading is actually imminent — nothing trades today, so a full ops console has nothing to operate (§5 simplicity). **Not dropped** — full four-tier design preserved verbatim: **Monitoring** (read-only) → **Notifications** (event fan-out) → **Operations** (capital-affecting, confirmation-gated) → **Explainability** (deterministic retrieval only, never generative inference). One-path-only constraint (shared Operations Service, no parallel business logic in any client) and the forbidden-actions list (no alpha approval, no threshold changes, no Risk Manager/Governance bypass, no Live Mode switch via any operational channel) both carry forward unchanged. | `ROADMAP.md` §3; also listed in Definition of Done |
| **`min_mean_directional_return` as a runner-recognized key** | Withdrawn after verification — the governance gate is meant to inspect mean directional return / expectancy sign at review time (CAMP-01 precedent, see Backlog 1.1); adding a mechanical runner key would migrate judgment out of the one deliberately human-owned gate. | Superseded by Backlog 1.1 |
| **`docs/RESEARCH_INSIGHTS.md`** (proposed new document) | Rejected — ~80% duplicates `ALPHA_LIBRARY.md` / `RESEARCH_LEDGER.md` / RD-12 with no consistency mechanism between four documents (§5). | Not created; durable findings recorded via RD entries instead |
| **RD-11's full deferred set** | Same HVL trigger. Rolling threshold recalculation, rolling normalization, trade simulation, stop/TP optimization, equity curve, drawdown, profit factor, expectancy, average R, slippage/fee/liquidity models, Constitution no-hindsight amendment. | `ROADMAP.md` §2 |

---

## Current Blockers

**Technical**
- ~~`storage.py::merge_and_write` durability~~ — **closed 2026-07-29.**
- ~~No CLI entry point for the liquidation collector~~ — **closed 2026-07-29**, `alpha_engine/historical/backfill_liquidations.py`.
- ~~`boto3`/`lz4` undeclared~~ — **closed 2026-07-29**, declared in `requirements.txt`, scoped to the historical pipeline only.

**Scientific**
- ~~Zero overlap between mark-price coverage and the liquidation archive~~ — **closed 2026-07-29.** Hyperliquid-native daily-candle mark price now covers 2025-07-27→2026-07-28 (367/367/367 rows, BTC/ETH/SOL) — full overlap with the liquidation archive's own window. Binance secondary-source coverage for the same window still filling in (see Active Work) but is not itself blocking.
- Measured cross-symbol correlation (+0.85–0.90) means the pilot's raw per-fold sample counts overstate true statistical power by roughly 2.5–3×; the feasibility review (Backlog 1.6) may reject Campaign 06 outright.

**Operational**
- ~~Evidence store gitignored~~ — **closed 2026-07-29**, `data/alpha_engine_research/` now tracked. `data/alpha_engine_historical/` (243 MB CSVs) remains deliberately gitignored — reconstructible from public archives, not the provenance-critical asset the evidence store is.
- `railway.json` declares no persistent volume; `data/` is ephemeral on Railway today (affects future live deployment, not current research). (Backlog 2.2)

**Documentation**
- ~~RD-12's stale "no backfill has been executed" claim~~ — **corrected 2026-07-29** via RD-13, with an inline pointer left at RD-12 itself.
- ~~`RESEARCH_PLAYBOOK.md` missing the governance-inspection clause~~ — **closed 2026-07-29**, restored in §5.

---

## Known Risks

**Scientific risks**
- Liquidation cascades across BTC/ETH/SOL may be one correlated market-wide process rather than three independent signals — the defining open question Backlog 1.6 exists to answer.
- Deep-history backfill (2.1) introduces **survivorship bias** (a 2026-chosen watchlist tested against 2020–21 conditions where SOL fell ~96% and was widely considered terminal) and **non-stationarity** (a 2020–2026 full-sample threshold spans two halvings, LUNA, FTX, and the ETF era) — both must become permanent `known_limitations` entries whenever the deep window is used, via the existing RD-11 A mechanism. Per-symbol archive start dates are also asymmetric (BTC ~2021-01, ETH/SOL ~2022-01 for `metrics`), a compositional break that sample construction must not silently pool across.
- `min_hit_rate = 0.55` has been copied unexamined into all five pre-registrations; re-deriving it for a structurally different feature (liquidation-event density vs. a continuous rate/level) rather than reusing the constant is a live methodology risk for Campaign 06.

**Engineering risks**
- The two-resume-mechanism divergence (day-granularity for OI/funding/mark-price vs. hour-granularity checkpoint for liquidations) is deliberate and justified but undocumented as such — a future contributor could "simplify" it away and reintroduce a large re-download cost per interrupted day.
- CSV + `Decimal` storage will not scale to tick-level data (e.g. a future order-flow family); not an issue today, worth flagging before it's discovered under deadline.

**Operational risks**
- Requester-pays S3 archives (Hyperliquid node data) carry no published retention guarantee, unlike Binance's decade-plus public archives — the liquidation dataset is comparatively less permanent than every other historical source in the project.

---

## Next 10 Executable Tasks (strictly ordered)

1. ~~Track `data/alpha_engine_research/` in git~~ — **done 2026-07-29.**
2. ~~Fix `storage.py::merge_and_write` durability~~ — **done 2026-07-29**, 4 new tests, orphaned `.tmp` removed.
3. ~~Commit the staged diff~~ — **done 2026-07-29 (`feb84d0`)**, 50 files, working tree clean.
4. ~~Add the governance-inspection clause to `RESEARCH_PLAYBOOK.md`~~ — **done 2026-07-29**, landed in §5 (governance stage), not §2 (it's a review-time inspection, not a pre-registration criterion).
5. ~~Write RD-13~~ — **done 2026-07-29**: pilot measurements, RD-12 correction, cross-symbol correlation finding, new feasibility-review requirement.
6. ~~Build `collect_liquidations()` + CLI entry; declare `boto3`/`lz4`~~ — **done 2026-07-29**, plus a real durability defect (deferred-write, not per-day flush) found and fixed before commit.
7. ~~Collect Hyperliquid-native daily candles 2025-07-27→present + Binance metrics secondary check~~ — **done 2026-07-29**, plus a real end-date boundary defect found via live run and fixed (see Active Work).
8. Execute the full 12-month liquidation backfill, single pass, all symbols retained. *(Next unstarted task.)*
9. Run the outcome-blind feasibility review reporting N_eff and cross-symbol correlation; render the APPROVE/DEFER/REJECT call on Campaign 06's viability.
10. If feasible: pre-register Campaign 06. If not: record the rejection in RD-14 and move to the deep-history backfill (Backlog 2.1) ahead of the next funding/OI campaign.

---

## Definition of Done

*(for the project's stated long-term end-state — not for any single task)*

- At least one hypothesis has cleared the five-stage research gate **and**
  governance, and become the first **SUPPORTED** entry in the Alpha
  Library.
- The Historical Validation Layer exists and every promoted candidate has
  passed it net of realistic fees, slippage, and liquidity constraints,
  with a frozen stop/TP methodology and a documented before/after
  walk-forward comparison.
- At least one candidate has an established paper-trading track record
  and agreed monitoring cadence before any authorized capital is at risk.
- The Execution Engine has taken at least one live trade sized and vetoed
  entirely by its own frozen risk/portfolio stack, with zero Alpha Engine
  involvement in sizing.
- The **Telegram Operations Console** exists at least through its
  Monitoring + Notifications tiers, giving the human operator observable,
  explainable, safety-bounded visibility into a live system without ever
  becoming a required step in a normal cycle.
- The full loop (`New data → hypothesis → research → evidence →
  governance → library → watchlist re-evaluation`) has executed at least
  once without manual intervention beyond pre-registration authorship.
- All data-integrity defects verified to date are closed (evidence store
  tracked, `storage.py` durability fixed) and remain closed under
  regression.
- Every RD entry accurately reflects repository state — no dangling
  "not yet executed" claims contradicted by committed data.
- The platform runs unchanged, from the same codebase and via the same
  CLI entry points, on Railway and a local laptop, with all research- and
  execution-state persisted outside process memory and outside ephemeral
  container storage.

---

## Decision Register

*(Every entry below is either an existing `RESEARCH_DECISIONS.md` RD, an
existing `PROJECT_CONSTITUTION.md` principle, or a verified finding from
this session's review cycle not yet formally logged as an RD — marked
accordingly.)*

- **OHLCV/technical-indicator family permanently rejected** — Constitution
  §4. Revisit only with a specifically-argued, pre-registered
  justification that context materially differs.
- **DEX-first policy** — Constitution §4/§6: production target is
  decentralized perps (Hyperliquid primary, Lighter future); CEX (Binance)
  data is research-tool-only, never a production outcome reference.
- **Venue-relative threshold methodology (permanent, post-CAMP-02)** —
  every exchange-native metric's threshold derived from that venue's own
  distribution.
- **Pre-registration feasibility review (permanent, post-CAMP-02)** —
  expected signal count, per-fold size, bootstrap stability, regime
  coverage estimated *before* locking any specification.
- **Governance separation** — reviewer ≠ researcher, structurally
  required; the one deliberate human-judgment gate in the pipeline.
- **RD-11 (2026-07-28)** — derivation-scope declaration (A) · immutable
  research-economics assumptions once declared (B) · execution-parameter
  promotion prerequisite (C) · reporting caveat locked (D) · full-sample
  threshold derivation corrected from "active violation" to "outcome-blind
  impurity, not demonstrated bias" (E).
- **RD-12 (2026-07-28)** — Hyperliquid S3 liquidation archive measured and
  source implemented; coverage 2025-07-27→present (~12mo), ~240 GB
  transfer, ~$27/$0 same-region; supersedes RD-06's "no liquidation
  history exists" conclusion only (RD-06's live-verified evidence that no
  WS/REST liquidation stream exists remains valid — liquidations are a
  field on fills, not a separate stream).
- **Historical Validation deferred** — trigger is the first SUPPORTED
  campaign, not a calendar date; nothing built prematurely (§5 verified
  compliant).
- **RD-13 (2026-07-29)** — one-month outcome-blind liquidation pilot
  record: 208,486 unique events, exactly 2.00 rows/event (perfect
  fill-pairing), 0 duplicates, 0 decode errors, 0 missing hours; 0.337%
  density; **measured cross-symbol correlation of daily counts +0.85 to
  +0.90** → effective independent symbols ≈1.1, not 3; top-10-days carry
  65% of all events — on this evidence, **Campaign 06 is more likely to
  be rejected by the feasibility gate than to pass it**, the cheapest
  possible outcome, not a failure. Corrects RD-12's stale "no backfill
  executed" claim; updates Liquidations Data Status `NONE` →
  `COLLECTING`; adds a self-activating N_eff/cross-instrument-correlation
  feasibility-review requirement; and records the restoration of the
  governance-inspection clause in `RESEARCH_PLAYBOOK.md` §5 (CAMP-01
  required the reviewer to inspect mean directional return / expectancy
  sign at governance; CAMP-02–05 dropped the clause — not a compliance
  defect in the architecture, a practice never codified in the Playbook
  that silently lapsed; now restored — **closed**, no longer open work).
- **[Session finding, not yet a formal RD] Campaign 06 sequencing
  changes** (three adversarial passes) — staged 3–4-month backfill
  proposed, then reversed to a single full 12-month pass (walk-forward
  requires chronological contiguity; month-selection would be an
  un-pre-registered researcher choice); mark-price extension reframed
  from "extend Binance" to "collect Hyperliquid-native outcomes, Binance
  secondary" (Constitution §4 — CEX is never the production reference);
  deep-history backfill moved off the Campaign 06 critical path entirely
  (orthogonal — gates the next funding/OI campaign instead); Live Sample
  Recorder promotion made then withdrawn (1.5yr lead time, §5 violation,
  corrected).
- **[Session finding] Documentation reorganization (2026-07-29)** —
  `PROJECT_STATE.md` created as sole execution-state authority;
  `PROJECT_STATUS.md`/`PROJECT_DASHBOARD.md` deprecated in place (content
  retained via git history, not deleted); `ROADMAP.md` purged of all
  completed work; `MASTER_INDEX.md` given explicit Core/Reference/Archive
  tiering.
- **[Session finding] Independent QA audit of Backlog 1.3 (2026-07-29)**
  — a reviewer independent of the implementer audited the committed
  `collect_liquidations()`/CLI work against this document's own
  durability claims, rather than accepting them; found and evidenced 1
  High (checkpoint could still outrun persisted data on a mid-day
  interruption — the earlier per-day-flush fix reduced but did not close
  the exposure), 1 Medium (CLI retry couldn't catch real S3 failures,
  since `hyperliquid_s3.py` never translated them to `HistoricalDataError`),
  and 3 Low findings (recovery flags unreachable from the CLI, a
  reporting-field unit inconsistency, per-call client reconstruction).
  All were independently re-verified (not accepted on the audit's word)
  before any fix was written, and every fix confirmed red→green against
  a dedicated regression test. Established precedent: this project's own
  "independent reviewer, not the implementer" governance principle
  (`RESEARCH_PLAYBOOK.md` §5) applies to engineering review as well as
  research governance, and caught a real defect the implementer's own
  first-pass fix and self-review missed twice.
- **[Session finding] Independent QA audit of Backlog 1.4 (2026-07-29)**
  — found 1 Medium (a still-forming daily candle silently frozen at its
  partial value forever, since the high-water-mark resume never asks
  for that timestamp again once stored) and 2 Low findings (the source
  function's own docstring described the wrong interval semantics; this
  document's Binance-backfill status had gone stale). The Medium was
  independently re-verified with a fresh, self-authored probe before any
  fix was written — not accepted on the audit's word — and confirmed
  not present in the already-shipped data via a live re-fetch. Same
  precedent as the Backlog 1.3 audit: a pattern (funding settlements,
  final the instant they're emitted) was reused a second time
  (candles, not final until the day closes) without accounting for the
  difference — this is now the second confirmed instance of that exact
  failure shape within this one backlog item, worth watching for
  whenever a future collector borrows an existing pattern verbatim.

---

## Project Timeline

```
2026-07-15   Execution Engine v1.0 — Modules 1-9 frozen
2026-07-16   Module 10 WP-1..5 — HyperliquidAdapter (read-only phase A)
2026-07-18   Module 10 Freeze — HyperliquidAdapter v1.0
2026-07-19   Hyperliquid production application layer complete
2026-07-21   Production hardening + Hyperliquid testnet readiness complete
   ...        [Alpha Engine M0.1 → R8, Historical Pipeline, Campaigns 01-05,
              doc consolidation — developed in working tree; git history
              does not carry per-milestone commits for this body of work]
2026-07-28   RD-10 Step 1: authenticated S3 probe (measurement only)
2026-07-28   RD-10 Step 2 committed (5821681) — Hyperliquid S3 liquidation
             source + LiquidationObservation + 144 files, single commit
             bundling Alpha Engine, historical pipeline, Campaigns 01-05,
             and doc consolidation into tracked history
2026-07-28   RD-12 recorded — archive measured (~12mo, ~240GB, ~$27/$0)
2026-07-28   Bounded one-month pilot backfill executed (2026-06-01→06-30,
             BTC/ETH/SOL) — interrupted mid-run, hard-kill exposed a
             checkpoint durability defect
2026-07-28   Durability fix applied to write_checkpoint (flush+fsync+
             dir-fsync); verified via real os._exit(9) hard-kill test
2026-07-29   Pilot resumed from 2026-06-25 hour 0; completed 30/30 days —
             208,486 unique liquidation events, 0 duplicates, 0 decode
             errors, 0 missing hours
2026-07-29   Four full adversarial architectural review passes completed —
             no code modified; verified findings: evidence store
             untracked, storage.py durability gap, governance-inspection
             clause decayed since CAMP-01, deep history available back to
             2020, staged-backfill plan reversed to single-pass, Live
             Sample Recorder promotion withdrawn, Robustness Layer
             rejected, Data Acquisition named as a first-class concern
2026-07-29   Documentation reorganization — PROJECT_STATE.md created,
             ROADMAP.md re-synchronized, PROJECT_STATUS.md/
             PROJECT_DASHBOARD.md deprecated, MASTER_INDEX.md retiered
2026-07-29   Commit `feb84d0` — Backlog 0.1/0.2/1.1/1.2 (evidence store
             tracked, storage.py durability fix, governance-inspection
             clause restored, RD-13 written) + the doc reorg above, all
             in one reviewed commit. 1,644 tests passing.
2026-07-29   Commit `9334d4f` — Backlog 1.3: collect_liquidations() + CLI
             entry point (backfill_liquidations.py) + boto3/lz4 declared.
             A deferred-write durability defect (found during
             implementation, before commit) fixed to flush per calendar
             day instead of once at the end of the whole requested
             range. 1,661 tests passing.
2026-07-29   Commit `26fc8e6` — PROJECT_STATE.md internal-staleness fixes
             ahead of independent QA review (no code changed).
2026-07-29   Independent QA audit of commit 9334d4f: found the per-day
             flush above did not fully close the checkpoint-durability
             defect (High), plus one Medium and three Low findings (see
             Decision Register). Fixed in commit `508d4b4`: checkpoint
             now advances only after a day's flush succeeds, not per
             hour during the fetch loop; S3 exceptions now translate to
             HistoricalDataError so the CLI retry can actually catch
             them; --force/--checkpoint-path exposed on the CLI; one S3
             client reused per call instead of one per request. 8 new
             tests, each confirmed to fail against the pre-fix code and
             pass against the fix. 1,669 tests passing.
2026-07-29   Commit `6bf8452` -- Backlog 1.4: collect_mark_price()
             extended to a Hyperliquid daily-candle source
             (fetch_daily_candles, new), mirroring collect_funding_rate's
             existing two-source pattern. A real end-date boundary
             defect (candleSnapshot's endTime is inclusive, unlike the
             hourly-funding formula it was copied from) found via a live
             end-to-end run against the real API, not by unit tests with
             fakes alone -- fixed with a -1ms adjustment before
             committing. Real collection executed: Hyperliquid daily
             candles for BTC/ETH/SOL, 2025-07-27 to 2026-07-28,
             367/367/367 rows -- full overlap with the liquidation
             archive's window, closing that blocker. 14 new tests. 1,683
             tests passing.
2026-07-29   Binance secondary-source backfill (started during the
             commit above) completed in the background: 159 chunks, 0
             failures, 275,601 rows/metric. Final coverage: Binance
             2023-07-01..2026-07-27 (917 days), Hyperliquid
             2025-07-27..2026-07-28 (367 days), per symbol.
2026-07-29   Independent QA audit of commit 6bf8452: found the
             still-forming-candle interaction with high-water-mark
             resume (Medium -- a partial close, once collected, could
             never self-correct) plus two Low findings. Medium
             independently re-verified with a fresh probe before any fix
             was written, and confirmed absent from the already-shipped
             data via a live re-fetch (0 mismatches). Fixed:
             fetch_daily_candles now excludes any candle whose close
             time has not yet passed "now"; docstring/log wording
             corrected to the verified inclusive interval. 4 new tests,
             each confirmed to fail against the pre-fix code and pass
             against the fix. 1,687 tests passing.
   ...        [next: Immediate Backlog item 1.5, then 1.6, then Campaign
              06 decision point]
```
