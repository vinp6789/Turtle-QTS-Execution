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
| **Current objective** | **Backlog 3.5 APPROVED an hourly Campaign 06 specification** — the first APPROVE any feasibility gate has ever returned. Next: collect the Hyperliquid 1h outcome series (3.6, **time-sensitive — ~210-day venue retention**), then pre-register Campaign 08. The Live Recorder (3.4) runs continuously and makes this constraint non-recurring. |
| **Current blocker** | No blocker on either running job. **Open technical debt (does not affect either running job):** the job-launcher's duplicate-start guard has a real, reproduced concurrency race (see Current Blockers → Operational) — deferred by explicit decision, to be closed before the *next* long-running collection campaign is *started* (not before these two, which are already past the vulnerable window). |
| **Immediate next task** | Let the recorder accumulate. Check with `python scripts/recorder_health.py` (read-only, exit 0 = healthy). Then the hourly-liquidation screen (RD-16 §E). |
| **Full regression** | **1,831 passed, 102 subtests, 0 failed** (20 launcher-concurrency, 25 recorder, 13 recorder-health tests added; **all job-tooling QA findings now closed, including L1/H1**) |
| **Approved alpha models** | **0** |
| **Rejected hypotheses** | **24 registered** (Campaigns 01–05: 18; **Campaign 07: 6**) — but only ~**12 independent measurements** (contrarian/momentum pairs are algebraically complementary, RD-17 §D) · **2 deferred pre-registrations** (RD-04, RD-16) |

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

All Priority 0/1.x and 2.1 items are closed. The 12-month liquidation
backfill (1.5) completed and passed independent audit; the feasibility
gate (1.6) then **DEFERRED Campaign 06** (RD-16) — measured cross-symbol
correlation ρ̄ = +0.818 gives **N_eff = 1.14** effective independent
series from 3 symbols, and no threshold/fold configuration reaches the
locked `min_signaled_samples = 100` per fold on an effective-sample
basis. The mechanism is **untested, not rejected**; revisit trigger is
≈18 further months of archive accumulation.

**Campaign 06 was a leaf in the dependency graph, not a prerequisite —
its deferral frees capacity rather than unblocking work.** What actually
opened the next research step was **Backlog 2.1's completion**
(2026-07-30), which deepened Binance funding/OI/mark-price history to
2020–2021.

The **DEX-first venue ceiling has been narrowed but not removed**
(Backlog 3.1, 2026-08-05): Hyperliquid funding now spans **~37 months**
(2023-07-01 → present) against Binance's 77 — from 22% to ~48% of
Binance's span. Under Constitution §6 a finding that exists only on CEX
data is never promotion-eligible, so any funding campaign remains
replication-limited by the shorter Hyperliquid history. Next is **3.2**,
the outcome-blind N_eff screen. See **Immediate Backlog** for the exact
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

**Backlog 1.5 IN PROGRESS + long-running-job hardening (2026-07-29/30):**
- **First attempt died with its parent chat session** after 49 of 367 days. The output file was **empty** — no `BACKFILL_COMPLETE`, no `BACKFILL_FAILED`, no traceback — the signature of external teardown, not a crash. **The defect was operational, never in the pipeline:** a job's lifetime was coupled to a chat session's lifetime.
- **Zero committed work was lost.** The Backlog 1.3 H1 durability invariant did exactly its job: checkpoint at `20250913/23.lz4`, collected days **2025-07-27 → 2025-09-13 contiguous (49 days)**, identical across all three symbols, `rows/event` exactly 2.00 everywhere, pilot month (2026-06) untouched. 974,096 rows survived. At most one *partial* day was discarded — by design, since the checkpoint only advances after a day's flush succeeds. **No `--force`, no manual data edits, no restart from scratch.**
- **Operational hardening (no pipeline/storage/checkpoint/research changes):**
  - `scripts/run_detached_job.py` — starts a job detached from the calling shell (POSIX `start_new_session`; Windows `DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP`). Records pid/cmd/started/log under `data/runtime/jobs/<name>/`. **Refuses a second concurrent copy of the same job** — the one genuinely dangerous mistake here is two backfills writing the same CSVs at once.
  - `scripts/job_status.py` — the reattach path. You never reattach to the *process* (a detached job has no terminal by design); you reattach to its observable state. **Strictly read-only.**
  - `scripts/liquidation_backfill_progress.py` — % complete, contiguous-run map, and data-sanity checks (`rows/event`, side balance) from durable on-disk state alone. **Strictly read-only**, safe mid-flight and from parallel sessions.
  - `docs/LONG_RUNNING_JOBS.md` — the runbook: start, check, recover, reboot, and the explicit "never do this to recover" list.
- **A real defect was found and fixed by these tests, in the new tooling itself:** `run_detached_job.start()` leaked the parent's log file handle, which on Windows locked the log against readers and cleanup. Fixed by closing the parent handle once the child has inherited its own.
- Backfill **relaunched detached** and verified resuming from day 49 (not restarting). 16 new tests. Full regression: **1,703 passed, 92 subtests, 0 failed.**

**Independent QA audit of the job tooling, then fixes (2026-07-30) — the running backfill was never interrupted:**
- **M1 (Medium, closed) — the duplicate-job guard failed OPEN.** `is_running()` returned `False` on *any* probe error (tasklist timeout, `OSError`), so a failing probe let `start()` spawn a second copy of a genuinely-live job. Reproduced end-to-end. This mattered because `storage.merge_and_write` is read-modify-write with **no inter-process lock** (verified) — two collectors on the same CSVs silently lose one writer's rows. **Fix:** split the two uses. `is_running()` stays fail-open but is now display-only; a new tri-state `liveness()` drives the guard and **refuses to start when liveness cannot be determined**, naming the pid it could not verify.
- **M2 (Medium, closed) — liveness was pid-only, with no identity check.** An OS-recycled pid belonging to an unrelated process read as "the job is still running" forever: `job_status.py` showed `RUNNING` (even displaying the backfill's `cmd`), and `start()` refused to resume. Reproduced by writing an unrelated live pid into a job's `pid` file. **Fix:** `liveness()` compares the live process's command line against the recorded `cmd`, distinguishing `ALIVE_AND_MATCHES` / `RECYCLED` / `GONE` / `UNKNOWN`. Verified the check still correctly identifies the **currently running** backfill as `alive_and_matches`, so protection was strengthened, never weakened.
- **L1 (Low) — check-then-start race. Claimed closed here; a follow-up independent audit found the fix incomplete — see the dated entry below, corrected the moment it was found, not silently carried forward.** The guard read the pid file before spawning and wrote the new pid after, so two near-simultaneous starts could both pass. **Attempted fix:** an `O_CREAT|O_EXCL` `lock` file was meant to make claiming a job atomic. It does not: the lock is created *empty* and only stamped with the real pid after `Popen` succeeds, leaving an empty-lock window a second concurrent caller can still steal (see Current Blockers → Operational).
- **L3 / I1 (Low, closed) —** the side-balance check compared only the counts *present*, so a wholly one-sided series (every `A` row lost) passed both sanity checks with a clean `rows/event=2.00`; and a checkpoint outside the expected window printed a negative day count beside a correctly-clamped percentage. Both fixed.
- **Windows liveness hardening:** the pid match was a bare substring test against `tasklist` output; now matches the pid as its own column, and `PermissionError` on POSIX is correctly read as "alive" rather than "gone".
- **Nothing in the pipeline, storage, checkpoint semantics, or research logic was touched** — verified: the commit contains no `alpha_engine/` or `research/` file.
- **The running backfill was never interrupted.** Same pid throughout; its checkpoint advanced from day 52 to day 54 *during* this work, proving it kept collecting. A live duplicate-launch attempt was correctly refused. 14 new tests, each confirmed to fail against the pre-fix code. Full regression: **1,717 passed, 92 subtests, 0 failed.**

**Final independent QA audit of the job tooling (2026-07-30) — found the L1 fix above incomplete, running backfill never interrupted:**
- **H1 (renamed from L1; not closed) — the `lock` file is created empty and only stamped with the real pid after `Popen` succeeds.** An empty lock is indistinguishable from "no holder" to the steal-path logic, so two concurrent `_acquire_lock()` calls can both succeed. Reproduced end-to-end: two concurrent `start()` calls both actually spawned live child processes. Measured window ~0.25s (tasklist+wmic latency) up to ~35s under load (internal timeouts: 15s tasklist, 20s wmic). **Only bites on a fresh START/RESUME race** — while a job is genuinely alive, any racing caller correctly resolves it as `ALIVE_AND_MATCHES` and refuses, so a job already running (like both `liq_backfill` and, from today, `deep_history_backfill`) is not exposed.
- **H2 (not closed) — both `docs/LONG_RUNNING_JOBS.md` and this document (in the L1 bullet above, now corrected in place) asserted an atomicity guarantee that does not hold.** Left as-is in `LONG_RUNNING_JOBS.md` itself per the decision below (not touching operational-tooling docs/code today); flagged here so the claim is not trusted.
- Also found: no test exercises the actual empty-lock state (L1/new), no test uses concurrency/threading (L2/new), and an informational note that Windows liveness checks depend on the deprecated `wmic` (I1/new).
- **Decision (2026-07-30): stop spending further time on operational-framework QA today.** Do not fix H1/H2 now, do not interrupt `liq_backfill`, do not touch `run_detached_job.py` / `job_status.py` / `liquidation_backfill_progress.py` / `LONG_RUNNING_JOBS.md`. Recorded as open technical debt (Current Blockers → Operational), to be closed **before the next long-running collection campaign is *started*** — not before Backlog 2.1, which was already past the vulnerable fresh-start window by the time it was launched (verified: no concurrent start was attempted against either job name). Project execution resumed instead — see Backlog 2.1 below.

**Backlog 2.1 started (2026-07-30) — deep-history backfill, orthogonal to Campaign 06:**
- Identified as the highest-priority backlog item with no dependency on 1.5/1.6 and no need to touch the running liquidation backfill or the operational tooling (Backlog 2.2, the Railway-volume config item, was the only other candidate with no open dependency; 2.1 ranks first in the Immediate Backlog and gates the next funding/OI campaign — a concrete future deliverable — vs. 2.2's config-only, no-current-urgency scope).
- Spot-verified via a scratch-root probe (not the production data root) before committing to the full multi-year job: Binance's public archive does have data at every one of the ROADMAP-declared boundary months (BTC/ETH funding 2020-01, SOL funding 2020-09 — and confirmed SOL funding 2020-08 correctly reports `unavailable` pre-listing; BTC metrics 2021-01, ETH/SOL metrics 2022-01). Confirms the ROADMAP's "verified free and available" claim rather than trusting it from memory.
- **New driver, zero changes to any tested collection code:** `research/deep_history_backfill/collect_backfill.py` — calls only the existing, already-tested `collect_funding_rate`/`collect_metrics`, one month at a time per symbol (mirrors `research/campaign_01_open_interest/collect_backfill.py` and `campaign_02_funding_rate/collect_backfill.py`'s established resumable-chunking pattern exactly). Per-symbol start months are asymmetric by design (SOL's Binance futures listing postdates BTC/ETH) and are read from module-level constants sourced directly from `docs/ROADMAP.md` §1.2, not re-derived. Re-running over already-covered months (2023-07 onward) is intentional and cheap — both underlying collectors skip anything already on disk.
- 12 new tests (`tests/test_research_deep_history_backfill.py`) covering month-range dispatch (each symbol starts from its own declared month), retry/backoff on transient `HistoricalDataError`, retry-exhaustion recorded as failed without aborting the run, and `BACKFILL_COMPLETE`/`BACKFILL_INCOMPLETE` reporting — each confirmed to fail against a deliberately-broken copy of the dispatch logic and pass against the real code. Full regression: **1,729 passed, 92 subtests, 0 failed.**
- **Launched detached** as job `deep_history_backfill` (distinct pid, distinct job name from `liq_backfill` — no shared lock, no shared output files) via the existing `scripts/run_detached_job.py`; this is *using* the operational tooling as designed, not modifying it. Verified starting: first 9 months (BTC funding 2020-01→2020-09) fetched successfully within the first 15 seconds; `liq_backfill` re-checked immediately after and confirmed still running, same pid, unaffected.

**Both jobs found stopped after an unattended interval (2026-07-30); neither was killed or restarted by any action taken — both exited through their own existing failure/completion paths:**
- **`liq_backfill`:** `BACKFILL_FAILED after 6 attempts` — genuine transient Hyperliquid S3 connectivity failures (`Read timeout`, `Could not connect to the endpoint URL`), the CLI's own already-tested exponential-backoff retry exhausted. Checkpoint at the time: day 60/367 (16.3%), all three symbols' CSVs contiguous and clean (`rows/event` exactly 2.00), no partial day. **Resumed** via the identical documented command; new pid, checkpoint untouched at day 60 (proving no restart-from-scratch), progressed cleanly through day 63/367 (17.2%) with no further errors.
- **`deep_history_backfill`:** actually completed its full scheduled month range (ended `BACKFILL_INCOMPLETE`, not a crash — its log runs ~100 minutes past `liq_backfill`'s failure). 5 months flagged: `ETH 2022-06`/`2022-07` (transient DNS failure, `getaddrinfo failed`) and **`BTC/ETH/SOL 2023-04`** (deterministic `MarkPriceObservation.value must be strictly positive, got 0` — see below). Verified on disk: all 5 months cleanly absent (zero rows), immediate neighboring months fully intact — the atomic-merge-per-month design held exactly as intended, no partial/corrupt data anywhere.
- **Investigation (no code changed during this phase):** independently re-fetched the real Binance archive for April 2023 (checksum-verified, outside the production data root). Confirmed genuine, live, reproducible archive data: `sum_open_interest > 0` with `sum_open_interest_value` literally `"0E-8"` in the raw file, clustered within the same few minutes across BTC/ETH/SOL on **2023-04-10** — a transient valuation-service hiccup on Binance's own side (open-interest counts continue moving normally through the same window), not a market event, not a parsing defect, not a checksum/corruption issue.
- **Fix (`alpha_engine/historical/sources/binance.py`):** `fetch_mark_price_day` and `fetch_metrics_day` both extended from skipping only `oi <= 0` to skipping `oi <= 0 or oi_value <= 0` before constructing a `MarkPriceObservation` — mirroring the function's own pre-existing "skip rather than fabricate a mark it cannot yield" principle exactly, no new semantics. `MarkPriceObservation`'s strict-positivity validation is untouched. In `fetch_metrics_day`, the open-interest observation for the same timestamp is kept unconditionally — only the derived price is skipped. 3 new regression tests (one reproducing the exact 2023-04-10 row shape), each confirmed to fail against the pre-fix code with the exact production error, and to pass against the fix. Full regression: **1,734 passed, 92 subtests, 0 failed.** Independently re-verified against the live archive for all three symbols post-fix (BTC/ETH/SOL 2023-04-10, read-only, no storage writes): 0 exceptions, 12/10/10 rows correctly skipped respectively.
- **Both fixes committed separately:** `75f9353` (raw `TimeoutError` → `HistoricalDataError` translation, closing the earlier `deep_history_backfill` crash) and `8667cb2` (the `oi_value` skip fix above).
- **`deep_history_backfill` resumed** via the identical documented command (new pid). Verified: the entire funding-rate phase re-walked with `skipped=1, rows_added=0` for every month (funding CSVs' row counts unchanged: BTC/ETH 7120, SOL 6425 lines, before and after), then the metrics phase resumed and correctly skipped every already-collected month (`fetched=0, skipped=N`) without re-fetching any of them.

**Backlog 1.5 COMPLETE (2026-08-05) — full 12-month liquidation backfill, independently audited:**
- Terminal status `BACKFILL_COMPLETE symbols=['BTC','ETH','SOL'] range=2025-07-27..2026-07-28`; final checkpoint `node_fills_by_block/hourly/20260728/23.lz4` — the last hour of the requested end date.
- **Final dataset:** 367/367 days · **4,277,522 rows** / **2,138,761 unique events** · 0.92 GB on disk (BTC 2,493,516 rows / 1,246,758 events · ETH 1,025,120 / 512,560 · SOL 758,886 / 379,443).
- **Integrity, measured not assumed:** `rows/event` **exactly 2.0000** on all three symbols · **0** unpaired `tid`s across 2,138,761 events (the strongest available evidence against partially-written days — a truncated day would split fill pairs) · **0** exact duplicate dedup keys · **0** rows outside the requested window · no orphaned `.tmp` files · checkpoint end hour consistent with the data's own end date.
- **Coverage:** BTC **367/367 complete**. ETH 364/367, SOL 362/367 — all **6** missing `(symbol, day)` pairs verified as **RD-14 zero-event days** (on each, at least one other symbol has rows, proving the archive hours were fetched and decoded): 2025-12-20 (SOL), 2026-01-17 (ETH+SOL), 2026-01-24 (ETH), 2026-04-25 (SOL), 2026-05-03 (SOL), 2026-07-25 (ETH+SOL).
- **The RD-14 §D whole-window coverage audit is now COMPLETE** (it was recorded as an outstanding prerequisite): every hourly object across all 367 days listed from the live archive — **8,800 objects**, and **exactly one** day deviates from 24/24.
- **That one deviation is the new finding, now governed by RD-15:** **2025-07-27 carries only 16/24 hours** (archive's first object is `20250727/8.lz4`; hours 00–07 absent; 2025-07-26 has zero objects, so this is a true start boundary, not a gap). The 8-object shortfall across the whole year is accounted for exactly and entirely by those eight hours. **This day must never be treated as statistically equivalent to a complete day** — exclude it, or normalize by 1.5× with the method documented; and **RD-14 must not be applied to it**. RD-15 also corrects RD-12's "from hour 10" to hour 08.
- **Pilot re-collection verified benign.** The requested range includes the 2026-06 pilot month, so the production checkpoint marched through it and re-fetched those 30 days, producing 90 conflict warnings (30 days × 3 symbols), confined to exactly `20260601`–`20260630`. A conflicting hour was re-decoded from source and compared field by field: **every market-data field is identical** (price, size, side, direction, method, liquidated_user, mark_price, source, source_detail); **only `ingested_at_utc` differs** (pilot `2026-07-28` vs re-fetch). First-seen values were correctly kept. **No duplicate rows were written and no data changed** — but note the precise wording: recollection *did* occur and changed nothing; "no recollection occurred" would be false.
- Collection required **five** resumes from checkpoint across transient S3 outages (18 logged connectivity failures, zero deterministic). **No data was lost on any of them** — the Backlog 1.3 H1 durability invariant held throughout.

**Backlog 3.3 + 3.4 (2026-08-05) — launcher race closed, Live Recorder DEPLOYED:**
- **3.3 — H1/H2 closed (`4325782`).** Root cause proven deterministically *before* any change: the lock was created with `O_CREAT|O_EXCL` but written **empty**, and stamped with the child's pid only after the liveness probe and `Popen`. A second caller in that window read `''`, computed `holder_pid = -1`, and **skipped the liveness guard entirely**. Fix is 35 insertions: stamp the claiming process's own pid at creation, and refuse (never steal) an unstamped lock. 20 concurrency tests with real threads/processes; the prior suite had **zero** concurrency coverage, which is why an audit once declared this fixed when it was not.
- **3.4 — Live Recorder deployed.** Scope strictly as approved: **Hyperliquid OI + funding + mark price, BTC/ETH/SOL, hourly**. One `metaAndAssetCtxs` call per cycle returns all three metrics for all symbols (live-verified; symbols located **by name** — SOL is at index 5, not 2). Written under its own `hyperliquid_live` source tag so these series never collide with the API-backfilled ones.
- **Order-flow capture deliberately NOT built.** The frozen Module 10 adapter declares `websocket_connected=False, # no websocket in this (REST-only) build`, and `get_fills` reads `userFills` (the account's own fills, not market flow). RD-07's "verify HL historical order-flow" precondition remains unverified, so building capture for it would be the speculative engineering §5 forbids.
- **Additive only:** two new modules and one new script; **no frozen module, no storage, no provider, no research or campaign code touched.**
- **Monitoring: `scripts/recorder_health.py`** — read-only, no daemon, no framework; exit 0 healthy / 1 degraded. Detects all nine required failure modes: running-but-writing-nothing, stale timestamps, repeated unavailable readings, malformed responses, disk-write failure (surfaces as unexpected exit), storage corruption, duplicate timestamps, excessive gaps, unexpected process exit.
- **Idempotency by design:** `observed_at_utc` is the **top of the hour**; the precise fetch instant is preserved in `ingested_at_utc`. A restart within the same hour re-writes the same dedup keys and adds **0 rows** (verified live).
- Full regression: **1,831 passed, 102 subtests, 0 failed.**

**Campaign 07 EXECUTED AND CLOSED (2026-08-05) — all six experiments REJECTED on merit:**
- **What it tested:** the forward-return **horizon** — the one dimension all 18 prior registered models held fixed at 24h. Pre-registered at 72h and 120h with strictly non-overlapping outcome windows; `docs/RESEARCH_CAMPAIGN_07_oi_long_horizon.md`.
- **Design resolved from existing governance, no new methodology:** both tails come free from the platform's `percentile_rank_centered` feature (CAMP-01 precedent); `horizon_hours` and the non-overlap assertion already existed in CAMP-01's `build_samples`, which was **reused unchanged**. Only a new runner was written.
- **Results:** hit rates **0.4775–0.5225** — the same coin-flip cluster as every prior campaign. Causality/leakage audit PASSED on all six; single-pass, walk-forward and regime FAILED on all six. Governance recorded through the frozen module (reviewer ≠ researcher, fingerprint verified).
- **Well-powered, not a power failure.** Cross-symbol ρ̄ = +0.296 → **N_eff = 1.88 of 3** (RD-13 §C); effective signalled samples ≈359 / ≈650 / ≈209 against a floor of 100 — 2–6× clearance. Contrast Campaign 06 (RD-16), deferred at N_eff 1.14 with ~40 effective per fold. **Campaign 07 had the power to find an edge and found none.**
- **RD-17 created**, and it creates a rule: **horizon is closed as a *rescue* for an already-rejected mechanism.** A strategic review had identified horizon as the cheapest untested axis in the program; it is now spent. Also records that contrarian/momentum are algebraically complementary (every pair sums to exactly 1.0000), so campaign reporting must state independent measurements, not registered experiments — this campaign reports **three**, not six.
- **Open Interest family: ACTIVE → NEAR-EXHAUSTED.** Level (CAMP-01), velocity (CAMP-05) and longer-horizon extremeness (CAMP-07) all rejected on merit; **Divergence** is the sole untested mechanism, still under the DEFER-ceiling.
- **Honest limitation:** the 120h robustness arm was power-marginal — one walk-forward fold returned 93 signalled samples against the 100 floor (feasibility projected 107; the live run applies the regime labeler). It failed on hit rate regardless.
- 20 new tests including literal pre-registration-immutability guards (RD-11 B). Full regression: **1,773 passed, 101 subtests, 0 failed.**

**Backlog 3.1 COMPLETE (2026-08-05) — Hyperliquid funding extended to present:**
- **Planning pass first, measured not estimated.** A read-only probe (`fetch_funding_rate_range`, writes nothing) measured ~1.23s/page against the live API and predicted ~103s for ~84 paginated requests. **Actual: 101.7s** — 1.3% error. Predicted +13,956 rows/symbol; actual +13,956/symbol exactly.
- **A latent defect was found by that planning pass and fixed first (`23d08bb`):** `sources/hyperliquid.py` carried the *identical* raw-`TimeoutError` gap that commit `75f9353` fixed in `sources/binance.py` — both call sites translated only `HTTPError`/`URLError`, so a stalled read on an already-open connection escaped as a non-`HistoricalDataError`. That exact defect had already escaped a retry loop and killed a running collection job once. Fixed with the identical pattern (no new retry framework, no unrelated refactoring); 3 regression tests (first page, later page mid-pagination, and the candles call site), each verified red against the pre-fix source.
- **Execution: foreground, existing collector only** — three `collect_funding_rate(source="hyperliquid")` calls. No detached launcher, no checkpoint framework, no new infrastructure. `fetch_funding_rate_range` paginates internally past the 500-record cap, so one call per symbol covered the whole 581-day gap.
- **Integrity audit (measured):** 27,153 rows/symbol (13,197 + 13,956) · **0 duplicates** · coverage `2023-07-01 → 2026-08-05T11:00`, lag 0.7h · sorted on disk · symbol/source fields consistent · **0 newly-introduced gaps** (the 3 gaps >1.5h are all pre-existing, in 2023–24; the collected range is dense — 13,956 rows over 13,955 hours) · size 6.22 → **12.79 MB**, matching the ~12.8 MB forecast.
- **Resumability re-verified on production, idempotent:** re-running the identical full-range call added **0 rows** in 1.7s. Verified beforehand on a scratch root: high-water resume suppresses already-collected data, extension fetches only the tail, dedup key `(symbol, observed_at_utc)`, 0 duplicates.
- **Effect on the research program:** the DEX-first ceiling is **narrowed, not removed** — Hyperliquid now covers ~37 months against Binance's 77 (22% → ~48%). Any funding campaign remains replication-limited by the shorter native history. **No governance decision changed**, so no RD entry was created.
- Full regression: **1,753 passed, 97 subtests, 0 failed.**

**Backlog 2.1 CLOSED (2026-07-30) — `BACKFILL_COMPLETE target=all`, zero failed months:**
- All 5 previously-failed months collected on the resumed run: `ETH 2022-06`/`2022-07` (the transient DNS failures — 8640/8928 rows, no skips) and **`BTC/ETH/SOL 2023-04`** (8640 OI rows each; mark-price rows 8628/8630/8630 — i.e. exactly **12/10/10** rows skipped per symbol).
- **Those skip counts independently corroborate the investigation:** they match, exactly, the anomalous-row counts measured by a separate live-archive probe run *before* the fix was written (BTC 12, ETH 10, SOL 10 rows with `sum_open_interest_value == "0E-8"` on 2023-04-10). The fix skipped precisely the anomalous rows and nothing else.
- **Data integrity verified by arithmetic, not assertion:** `open_interest__ETH__binance.csv` grew by exactly 26,208 rows = 8,640 (Apr-23) + 8,640 (Jun-22) + 8,928 (Jul-22); BTC and SOL each grew by exactly 8,640 (Apr-23 only). Funding-rate row counts unchanged (7120/7120/6425) — nothing recollected. Every previously-empty month is now fully populated with its expected 288 rows/day.
- Deep-history coverage is now continuous: **funding 2020-01→2026-07** (BTC/ETH; SOL from 2020-09) and **metrics 2021-01→2026-07** (BTC; ETH/SOL from 2022-01). This unblocks the next funding/OI campaign (it never gated Campaign 06).
- **Reminder for whoever uses this window:** RD-11 A requires declaring survivorship bias, non-stationarity, and the asymmetric per-symbol start dates as `known_limitations` in any campaign built on it. To that list add a fourth, now-measured item: **~0.1% of 5-minute mark-price observations in this window are absent by design** (the archive anomaly above) — the OI series is complete, the derived mark-price series is very slightly sparser, and sample construction must not assume the two are row-for-row aligned.

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
| ~~1.5~~ | ~~Full 12-month liquidation backfill, single pass, all symbols retained~~ | — | — | — | **Done 2026-08-05 — independently audited.** 367/367 days, 4,277,522 rows / 2,138,761 events, rows/event exactly 2.0000, 0 duplicates, 0 unpaired fills. Five checkpoint resumes across transient S3 outages, no data lost. Surfaced **RD-15** (2025-07-27 is a 16/24-hour partial day) |
| ~~1.6~~ | ~~Campaign 06 outcome-blind feasibility review (N_eff + cross-symbol correlation)~~ | 1.5 (done) | — | — | **Done 2026-08-05 — verdict DEFER (RD-16).** ρ̄ = +0.818 → N_eff = 1.14 of 3 symbols; no threshold/fold config reaches `min_signaled_samples = 100` per fold effectively (best 40.2; P(eff≥100) = 0.00). Bar not weakened. Runtime 13.83s |
| ~~2.1~~ | ~~Deep-history backfill: funding→2020-01 (BTC/ETH), 2020-09 (SOL); metrics→2021-01 (BTC), ~2022-01 (ETH/SOL)~~ | — | — | — | **Done 2026-07-30 — `BACKFILL_COMPLETE target=all`, 0 failed months.** Two real defects found and fixed en route (raw `TimeoutError` escaping the retry path; a genuine Binance archive `oi_value==0` anomaly on 2023-04-10) — see Active Work |
| **2.2** | Route `data/alpha_engine_historical` through `config/loader.py` with an env override; declare a persistent Railway volume (`railway.json` currently declares none — `data/` is ephemeral there) | None | No | ~3 hrs | Not started |
| ~~3.1~~ | ~~Extend Hyperliquid-native funding coverage from 2024-12-31 to present~~ | — | — | — | **Done 2026-08-05.** +41,868 rows (13,956/symbol), 101.7s foreground, 0 duplicates, 0 new gaps. Coverage now **2023-07-01 → 2026-08-05 (~37 months)**, lag 0.7h. Zero new infrastructure |
| ~~3.2~~ | ~~Outcome-blind N_eff screen for the next funding/OI campaign~~ | — | — | — | **Done 2026-08-05 — DEFER.** Funding Persistence N_eff 14–18 (unchanged by 3.9× data); BTC-only momentum Binance-powered but Hyperliquid-unpowered |
| ~~3.4~~ | ~~**Campaign 07** — longer-horizon OI (72h/120h)~~ | 3.2 (done) | — | — | **Done 2026-08-05 — all six REJECTED on merit (RD-17).** Horizon dimension falsified; OI family → NEAR-EXHAUSTED |
| ~~3.3~~ | ~~Close the launcher concurrency race (H1/H2)~~ | — | — | — | **Done 2026-08-05 (`4325782`).** Root cause proven first: lock created empty, second caller skipped the liveness guard. 35-line fix + 20 concurrency tests (prior suite had none) |
| ~~3.4~~ | ~~Deploy the Live Recorder~~ | 3.3 (done) | — | — | **Done 2026-08-05 (RD-18).** Running as `live_recorder`: HL OI/funding/mark, BTC/ETH/SOL, hourly data / 15-min poll. Monitoring: `scripts/recorder_health.py`. **Order-flow capture NOT built — remains NOT YET** |
| ~~3.5~~ | ~~Hourly-liquidation feasibility screen (RD-16 §E)~~ | — | — | — | **Done 2026-08-05 — APPROVE** (p75, folds 3/5). RD-16 §E's fear is **refuted**: hourly serial autocorrelation is LOW (+0.18–0.22), so the 24× raw gain survives (×0.65). Cross-symbol dependence is scale-invariant (ρ̄ +0.817 hourly vs +0.818 daily) |
| **3.6** | **Collect Hyperliquid 1h candles** (BTC/ETH/SOL, 2026-01-07 → present) — the hourly outcome series Campaign 08 needs. **TIME-SENSITIVE: the venue retains 1h candles only ~210 days**, so one more day ages out daily | 3.5 (done) | **Yes — gates Campaign 08 pre-registration** | ~minutes | **NEXT** |

---

## Deferred Work

| Item | Why deferred | Where it will land |
|---|---|---|
| **Campaign 06 (Liquidations)** | **Deferred at the feasibility gate 2026-08-05 (RD-16)** — N_eff = 1.14 of 3 symbols; effective per-fold samples 40.2 vs a floor of 100. Mechanism **untested, not rejected**. Trigger: ≈264 worst-fold raw signalled samples (~18 further months of archive). Do **not** revisit by lowering the floor, loosening the threshold, or dropping the N_eff requirement. | `RESEARCH_DECISIONS.md` RD-16 |
| **Open Interest Divergence / longer-horizon OI** | DEFER-ceiling **unchanged** by Backlog 2.1 — verified: no Hyperliquid `open_interest` series exists at all (2.1 was Binance-only). Knowledge-only until a live OI recorder exists. | `ROADMAP.md` §1.3 |
| **Historical Validation Layer (HVL)** | Trigger: the first campaign producing a SUPPORTED hypothesis (RD-11). Nothing has ever passed governance. | `ROADMAP.md` §2 |
| **"Robustness Validation" as a separate layer** | Rejected on Constitution §5 — its contents (Monte Carlo, parameter sensitivity → Research; stress/spread/fills → HVL; latency/delay → Paper Trading) dissolve into three existing homes with nothing left over. Zero concrete instances exist to justify a fourth layer. | Not scheduled — absorbed into HVL/Research/Paper Trading design notes |
| ~~**Live Sample Recorder**~~ | **PROMOTED AND DEPLOYED 2026-08-05 (Backlog 3.4).** The §5 threshold was crossed by measurement, not opinion: RD-17 closed three OI mechanisms on merit leaving only Divergence (whose named unlock is this recorder), and Backlog 3.2 measured that Hyperliquid history **cannot be extended backwards**. Scoped strictly to HL-native OI/funding/mark snapshots — **order-flow capture remains NOT YET**, since the frozen adapter is REST-only by its own declaration and RD-07's "verify HL historical order-flow" precondition is still unverified. | Running as job `live_recorder` |
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
- ~~OPEN — launcher concurrency race (`scripts/run_detached_job.py::_acquire_lock`)~~ — **CLOSED 2026-08-05 (`4325782`, Backlog 3.3).** Root cause proven deterministically before any change: the lock was created with `O_CREAT|O_EXCL` but **written empty**, and only stamped with the child's pid after the liveness probe and `Popen`. A second caller in that window read `''`, computed `holder_pid = -1` from `"".isdigit() == False`, and therefore **skipped the liveness guard entirely**, falling through to the steal path. Fix (35 insertions): a `_claim()` helper stamps the **claiming process's own pid** into the lock as part of creating it, before any slow work; and an unstamped/unparseable lock is now **refused rather than stolen**, closing the residual one-syscall window. 20 concurrency tests using real threads and real processes — the prior suite had zero concurrency coverage, which is why the defect survived an audit that claimed it fixed. **H2 resolved without a documentation edit:** `LONG_RUNNING_JOBS.md`'s atomicity claim was false when written and is now true.

**Documentation**
- ~~RD-12's stale "no backfill has been executed" claim~~ — **corrected 2026-07-29** via RD-13, with an inline pointer left at RD-12 itself.
- ~~`RESEARCH_PLAYBOOK.md` missing the governance-inspection clause~~ — **closed 2026-07-29**, restored in §5.

---

## Known Risks

**Scientific risks**
- Liquidation cascades across BTC/ETH/SOL may be one correlated market-wide process rather than three independent signals — the defining open question Backlog 1.6 exists to answer.
- Deep-history backfill (2.1) introduces **survivorship bias** (a 2026-chosen watchlist tested against 2020–21 conditions where SOL fell ~96% and was widely considered terminal) and **non-stationarity** (a 2020–2026 full-sample threshold spans two halvings, LUNA, FTX, and the ETF era) — both must become permanent `known_limitations` entries whenever the deep window is used, via the existing RD-11 A mechanism. Per-symbol archive start dates are also asymmetric (BTC ~2021-01, ETH/SOL ~2022-01 for `metrics`), a compositional break that sample construction must not silently pool across. **Fourth item, measured during the 2.1 collection (2026-07-30):** a small fraction of 5-minute mark-price observations are legitimately absent — Binance's archive reports `sum_open_interest_value == 0` alongside a normal `sum_open_interest` for a handful of snapshots (32 rows across BTC/ETH/SOL on 2023-04-10 alone), which yields no derivable mark and is skipped rather than fabricated. **The open-interest series is complete; the derived mark-price series is very slightly sparser.** Sample construction must join the two on timestamp rather than assuming row-for-row alignment.
- **RD-15 (2026-08-05): 2025-07-27 is a structurally partial day — 16 of 24 archive hours.** The archive's first object is `20250727/8.lz4`; hours 00–07 do not exist upstream. Counts that day are mechanically understated ~33% for **every** symbol simultaneously, so including it raw shifts every percentile and corrupts threshold derivation, distributional statistics, and N_eff. Backlog 1.6 must exclude it (recommended) or normalize by 1.5× with the method documented. **RD-14 must not be applied to this day.** The whole-window audit confirmed it is the *only* such day in 367.
- **RD-14 (2026-08-02): a liquidation day with no rows is a VERIFIED ZERO-EVENT day, not a missing observation.** Verified three ways (cross-symbol coincidence; 24/24 archive objects present on all nine days checked; live re-decode of 2026-01-17 returning zero rows for every symbol while 2026-01-18 returned rows). Campaign 06 sample construction **must materialize these as `count = 0`** — dropping them conditions the sample on activity and inflates every percentile threshold, breaking the venue-relative-threshold rule. **That prerequisite is now CLOSED:** the whole-window coverage audit ran 2026-08-05 across all 367 days (8,800 objects) and found exactly one deviation — the 2025-07-27 partial day, now governed by RD-15. Applied in the 1.6 review (RD-16): 8 zero-event cells materialized.
- `min_hit_rate = 0.55` has been copied unexamined into all five pre-registrations; re-deriving it for a structurally different feature (liquidation-event density vs. a continuous rate/level) rather than reusing the constant is a live methodology risk for Campaign 06.

**Engineering risks**
- The two-resume-mechanism divergence (day-granularity for OI/funding/mark-price vs. hour-granularity checkpoint for liquidations) is deliberate and justified but undocumented as such — a future contributor could "simplify" it away and reintroduce a large re-download cost per interrupted day.
- CSV + `Decimal` storage will not scale to tick-level data (e.g. a future order-flow family); not an issue today, worth flagging before it's discovered under deadline.

**Operational risks**
- This machine's connectivity to the Hyperliquid S3 endpoint drops for multi-minute stretches (18 logged transient failures on 2026-07-30/31, zero deterministic). The retry budget now absorbs ~12 minutes of outage (commit `e63cbab`), but an outage longer than that will still stop the job -- it resumes cleanly from the checkpoint with no data loss, and `--retry-max-total-seconds` raises the tolerance further if needed.
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
8. ~~Execute the full 12-month liquidation backfill, single pass, all symbols retained.~~ — **done 2026-08-05**, audited: 367/367 days, 2,138,761 events, rows/event exactly 2.0000. Surfaced RD-15.
8a. ~~Deep-history backfill (Backlog 2.1), orthogonal to Campaign 06.~~ — **done 2026-07-30**, `BACKFILL_COMPLETE target=all`, 0 failed months.
9. ~~Run the outcome-blind feasibility review; render the APPROVE/DEFER/REJECT call on Campaign 06.~~ — **done 2026-08-05: DEFER (RD-16)**, N_eff = 1.14, bar not weakened.
10. **Extend Hyperliquid funding coverage to present (3.1)** — the DEX-first ceiling is now the binding constraint.
10a. ~~Outcome-blind N_eff screen (3.2)~~ — **done 2026-08-05: DEFER.**
10b. ~~Campaign 07, longer-horizon OI~~ — **done 2026-08-05: all six REJECTED on merit (RD-17).** Horizon closed as a rescue path.
11. **Hourly-liquidation feasibility screen (RD-16 §E)** — the last near-free experiment in the queue.
11. Before starting any *future* long-running collection job beyond the two currently in flight: close the launcher concurrency race (`scripts/run_detached_job.py::_acquire_lock`) — see Current Blockers → Operational.

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
- **RD-18 (2026-08-05)** — **Live Recorder promoted and deployed**,
  reversing a standing §5 deferral on measured evidence: RD-17 left OI
  Divergence as the sole untested mechanism (whose named unlock is this
  recorder), Backlog 3.2 measured the venue ceiling biting, and Backlog
  3.1 established that Hyperliquid history cannot be extended backwards
  — so uncaptured data is unrecoverable. **Scoped to venue-native
  snapshots only** (OI/funding/mark). **Order-flow capture is explicitly
  NOT YET**: the frozen adapter is REST-only by its own declaration,
  `get_fills` reads the account's own fills rather than market flow, and
  RD-07's "verify HL historical order-flow" precondition is unverified.
  Also records a correction — two earlier strategic reviews priced the
  recorder as one monolithic item; architecture inspection showed it is
  two propositions with entirely different readiness, and only the ready
  half was built.
- **RD-17 (2026-08-05)** — **Campaign 07 closure: the horizon dimension
  is falsified for OI extremeness.** Six experiments at 72h/120h, all
  REJECTED on merit (hit rates 0.4775–0.5225), and **well-powered** —
  N_eff 1.88 of 3 symbols, effective signalled samples 2–6× the floor.
  Creates a rule: **horizon is closed as a *rescue* for an
  already-rejected mechanism** (it remains open for families never tested
  at 24h). Records that contrarian/momentum are algebraically
  complementary — every pair sums to exactly 1.0000 — so reporting must
  state independent measurements, not registered experiments; Campaign 07
  reports three, not six. Open Interest family ACTIVE → NEAR-EXHAUSTED.
- **RD-16 (2026-08-05)** — **Campaign 06 DEFERRED at the feasibility
  gate.** Measured on the full audited window (366 days × 3 symbols):
  cross-symbol correlation ρ̄ = +0.818 → **N_eff = 1.14** effective
  independent series from 3 symbols. No threshold/fold configuration
  reaches `min_signaled_samples = 100` per fold on an effective-sample
  basis (best case p60/n_folds=3 = 40.2; moving-block bootstrap
  P(effective ≥ 100) = 0.00 across all six configurations). Regime
  coverage adequate — sample size alone binds. **The bar was not
  weakened:** counted raw, p60/n_folds=3 would pass (106, P = 0.99); it
  fails only once RD-13 §C's mandatory N_eff requirement is applied,
  which is precisely the case that requirement was created for — its
  first applied instance, and it changed the outcome. **DEFER, not
  REJECT**, per RD-04's precedent: only testability failed, so recording
  it as rejected would enter a false negative into the ledger. Supersedes
  RD-13's one-month correlation estimate (+0.85–0.90) with the
  full-window measurement. Revisit at ≈264 worst-fold raw (~18 further
  months).
- **RD-15 (2026-08-05)** — data-interpretation rule, distinct from
  RD-14: the liquidation archive **begins mid-day on 2025-07-27**, whose
  first object is hour 08, so that day carries **16/24 hours** and is
  structurally partial. Established by the whole-window coverage audit
  (367 days, 8,800 objects listed; exactly one day deviates from 24/24,
  and its 8-object shortfall accounts for the year's entire shortfall)
  plus a direct listing showing 2025-07-26 has zero objects — a true
  start boundary, not a gap, and upstream of this project rather than a
  collection fault. **The day must never be treated as statistically
  equivalent to a complete day**: it mechanically understates counts for
  every symbol at once, contaminating percentile/threshold derivation
  (Constitution §6), distributional statistics, and N_eff. A future
  analysis must either exclude it (recommended — assumption-free, costs
  0.27% of the window) or normalize by 1.5× with the method documented,
  and must state which. **Bounds RD-14:** RD-14's zero-event rule does
  not apply to this day, since its precondition (archive hours complete)
  fails. Also corrects RD-12's "from hour 10" to hour 08.
- **RD-14 (2026-08-02)** — data-interpretation rule: within the
  checkpoint-covered window, an absent `(symbol, day)` row in the
  liquidation series means that symbol recorded **zero events** that
  day; it is an observation of value zero, not a missing one. Arose
  from ETH/SOL showing interior day-gaps that BTC did not; established
  by cross-symbol coincidence (BTC itself collapsing to 2–22 rows vs a
  4,960 median on those days), archive completeness (24/24 hourly
  objects on all nine days listed), and a decisive live re-decode of
  2026-01-17 returning zero rows for every symbol while the adjacent
  day returned rows. Consistent with RD-13's measured concentration
  (top-10 days = 65.2% of events) — the same heavy-tailed process seen
  at its lower tail. Scope-limited: does not apply beyond the
  checkpoint or to any under-covered day, and a whole-window coverage
  audit remains a prerequisite before final analysis.
- **[Session finding] Final independent QA audit of the job tooling, and
  the diminishing-returns decision (2026-07-30)** — a second independent
  audit re-verified the M1/M2/L1/L3/I1 fixes above rather than trusting
  the claim, and found the L1 fix incomplete: the `lock` file is created
  empty and only stamped with the real pid after `Popen` succeeds, so an
  empty lock remains stealable for a measured ~0.25s–35s window; two
  concurrent `start()` calls were reproduced both spawning live
  collectors end-to-end. Also found: both `docs/LONG_RUNNING_JOBS.md`
  and this document asserted an atomicity guarantee that does not hold;
  no test covered the empty-lock state or concurrent starts. Given this
  only bites a fresh start/resume race on a *dead* job (a live job is
  unambiguously refused regardless), and the running `liq_backfill` was
  never at risk, the decision was made to **defer the fix rather than
  spend further time on operational QA today**: recorded as open
  technical debt (Current Blockers → Operational), not fixed, not
  documented as closed, to be resolved before the next long-running
  campaign is *started*. Project execution then resumed with Backlog
  2.1 (deep-history backfill), launched detached under a distinct job
  name with no exposure to this race (verified: no concurrent start was
  attempted against either job name).

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
2026-07-29   Commit `9334d4f` — Backlog 1.3 committed (see above); commit
             `508d4b4` — Backlog 1.3 QA fixes committed (see above);
             commit `6bf8452` — Backlog 1.4 committed (see above).
2026-07-30   Backlog 1.5 relaunched detached after the parent-session-
             death incident; first independent QA audit of the job
             tooling (M1/M2/L1/L3/I1) found and fixed (commit `e01dcae`).
             1,717 tests passing.
2026-07-30   Final independent QA audit of the job tooling: the L1 fix
             found incomplete (empty-lock stealable window, reproduced
             end-to-end), plus a false atomicity claim in two documents
             and untested concurrency paths. Decision: defer the fix
             (diminishing returns on operational QA today), record as
             open technical debt, resume project execution. `liq_backfill`
             re-confirmed running throughout, never interrupted, day
             55→56.
2026-07-30   Backlog 2.1 started: deep-history backfill driver
             (`research/deep_history_backfill/collect_backfill.py`, zero
             changes to any tested collection code) built, 12 new tests
             red→green, launched detached as `deep_history_backfill`
             (distinct pid/job name from `liq_backfill`, no shared lock
             or output files). 1,729 tests passing.
2026-07-30   Commit `33e7dff` — Backlog 2.1 driver + tests +
             PROJECT_STATE.md update committed. 4 files changed
             (+423/-18). Working tree clean.
2026-07-30   Commit `3894421` — documentation-only follow-up recording
             `33e7dff`'s own hash in the timeline (had not been
             committed before an API disconnect).
2026-07-30   Both `liq_backfill` and `deep_history_backfill` found
             stopped after an unattended interval -- neither killed nor
             restarted by any action taken. `liq_backfill`:
             BACKFILL_FAILED after 6 attempts, transient S3
             connectivity, checkpoint clean at day 60/367. Resumed.
             `deep_history_backfill`: completed its full scheduled
             range (not a crash), flagged 5 months -- 2 transient DNS
             failures, 3 (BTC/ETH/SOL 2023-04) a deterministic
             MarkPriceObservation zero-value rejection.
2026-07-30   Commit `75f9353` — translate raw TimeoutError to
             HistoricalDataError in binance.py (root cause of the
             earlier deep_history_backfill crash at the metrics-phase
             boundary). 2 new tests, red→green verified. 1,731 tests
             passing.
2026-07-30   Investigation (no code changed): independently re-fetched
             the live Binance archive for April 2023 -- confirmed a
             genuine, checksum-verified, reproducible archive anomaly
             (sum_open_interest_value == "0E-8" alongside sum_open_
             interest > 0), clustered across BTC/ETH/SOL within the
             same few minutes on 2023-04-10. Not a parsing defect, not
             corruption, not a market event.
2026-07-30   Commit `8667cb2` — fetch_mark_price_day/fetch_metrics_day
             extended to skip (not fabricate) a mark price when
             oi_value <= 0, mirroring the existing oi <= 0 skip exactly.
             3 new tests including the exact 2023-04-10 shape, each
             confirmed to fail against the pre-fix code with the exact
             production error. Full regression: 1,734 tests passing.
             `deep_history_backfill` resumed; funding phase re-verified
             all-skip (no recollection), metrics phase resumed skipping
             already-covered months correctly.
2026-07-30   Both jobs again found stopped. `liq_backfill`:
             BACKFILL_FAILED after 6 attempts -- total loss of network
             connectivity to the Hyperliquid S3 endpoint ("Could not
             connect to the endpoint URL"), purely transient, checkpoint
             clean at day 67/367 (18.3%). Connectivity re-verified
             recovered, then resumed via the documented path.
             `deep_history_backfill`: exited BACKFILL_COMPLETE
             target=all -- it FINISHED, 0 failed months. All 5
             previously-failed months collected; the 2023-04 mark-price
             skip counts (BTC 12 / ETH 10 / SOL 10) exactly match the
             pre-fix live-archive probe. BACKLOG 2.1 CLOSED.
2026-07-31   Commit `e63cbab` -- liquidation-backfill retry policy made
             configurable (RetryPolicy + --retry-* flags). The
             hard-coded 6-attempt/~62s budget was shorter than the real
             outages and had forced FOUR manual resumes; defaults now
             ride out ~12 minutes. Backoff is capped (the original was
             not); bounded on both attempts and wall clock so a
             deterministic failure cannot loop forever; KeyboardInterrupt
             and non-HistoricalDataError still propagate immediately.
             First five backoffs unchanged (2/4/8/16/32s), so this
             strictly extends the prior behaviour. 11 new tests, verified
             red against the pre-change source. 1,745 tests passing.
             Resumed from day 72/367; data verified byte-identical
             (md5) and checkpoint unchanged -- nothing recollected.
2026-08-05   Backlog 1.5 COMPLETE. BACKFILL_COMPLETE, checkpoint at
             20260728/23 (the requested end date). Final dataset:
             367/367 days, 4,277,522 rows / 2,138,761 events, 0.92 GB;
             rows/event exactly 2.0000, 0 unpaired fills, 0 duplicate
             keys, 0 rows outside the window, no orphaned .tmp files.
             Five checkpoint resumes across transient S3 outages, no
             data lost on any.
2026-08-05   Final collection audit (independent). Completed the
             whole-window coverage audit RD-14 Section D had recorded as
             an outstanding prerequisite: 8,800 hourly objects across
             367 days, exactly ONE day deviating from 24/24. All six
             missing (symbol, day) pairs confirmed as RD-14 zero-event
             days. Pilot-month recollection (30 days, 90 conflict
             warnings) verified benign by field-by-field re-decode from
             source: every market-data field identical, only
             ingested_at_utc differing.
2026-08-05   Commit `RD15` — RD-15 recorded: the archive begins
             2025-07-27 at hour 08, so that day is 16/24 hours and is
             never statistically equivalent to a complete day. Corrects
             RD-12's "from hour 10". Bounds RD-14's applicability.
             Liquidations Data Status COLLECTING -> READY.
2026-08-05   Backlog 1.6 executed (commit `4a24c0a`) -- outcome-blind
             feasibility review, 13.83s foreground, 11/11 pre-flight
             assertions passed. Measured rho_bar = +0.818 -> N_eff = 1.14
             of 3 symbols; P(effective >= 100) = 0.00 in all six
             threshold/fold configurations. VERDICT: DEFER Campaign 06.
2026-08-05   RD-16 recorded -- formal DEFER of Campaign 06's
             pre-registration (deferred, NOT rejected; mechanism
             untested). Second deferred pre-registration after RD-04.
             Roadmap re-prioritized: the DEX-first venue ceiling
             (Hyperliquid funding stale at 2024-12-31 vs Binance at
             77 months) is now the binding constraint, so 3.1 precedes
             3.2. MCP data-provider evaluation recorded as a future
             gate, not an active item.
2026-08-05   Commit `23d08bb` -- TimeoutError translation added to
             sources/hyperliquid.py, mirroring 75f9353 in binance.py.
             Found by the Backlog 3.1 planning pass. 3 tests, red->green.
             1,753 passing.
2026-08-05   Backlog 3.1 COMPLETE -- Hyperliquid funding extended
             2024-12-31 -> 2026-08-05. Foreground, 101.7s (predicted
             103s), +41,868 rows across 3 symbols, 0 duplicates, 0 new
             gaps, 6.22 -> 12.79 MB. Idempotent re-run added 0 rows.
             DEX-first ceiling narrowed 22% -> ~48% of Binance's span.
2026-08-05   Backlog 3.2 complete -- funding deep-window feasibility
             review, verdict DEFER (commit aad1884).
2026-08-05   CAMPAIGN 07 EXECUTED AND CLOSED. Longer-horizon OI (72h,
             120h), six pre-registered experiments, all REJECTED on
             merit. Hit rates 0.4775-0.5225; causality PASSED, all other
             stages FAILED. Well-powered: N_eff 1.88 of 3 symbols,
             effective signalled 359/650/209 vs a floor of 100. RD-17
             created -- horizon closed as a rescue path for an
             already-rejected mechanism; OI family ACTIVE ->
             NEAR-EXHAUSTED. 20 new tests, 1,773 passing.
2026-08-05   Backlog 3.3 -- launcher concurrency race (H1/H2) CLOSED
             (commit `4325782`). Root cause proven deterministically
             first: the lock was created empty, so a second caller read
             '' and skipped the liveness guard entirely. 35-line fix;
             20 concurrency tests with real threads/processes.
2026-08-05   Backlog 3.4 -- LIVE RECORDER DEPLOYED as job
             `live_recorder` (RD-18). Hyperliquid OI/funding/mark,
             BTC/ETH/SOL, hourly data cadence / 15-min poll. First cycle
             wrote 9 rows; health check HEALTHY. Order-flow capture
             deliberately NOT built (adapter is REST-only; RD-07
             precondition unverified). Monitoring added:
             scripts/recorder_health.py (read-only, exit 0/1).
             1,831 tests passing.
   ...        [next: verify the recorder over multiple cycles, then the
              hourly-liquidation feasibility screen (RD-16 Section E) --
              the last near-free experiment in the queue. The Live
              Recorder decision is CLOSED (RD-18, deployed); the launcher
              concurrency race is CLOSED (3.3). Start no new campaign
              until recorder deployment is verified.]
```
