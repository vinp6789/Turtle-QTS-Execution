# Historical Data Pipeline — Open Interest & Funding Rate (BTC/ETH/SOL)

**Status:** implemented (2026-07-22), additive to the Alpha Engine
(`alpha_engine/historical/`), zero frozen Execution Engine modules
touched. This is backfill/research infrastructure only — nothing here is
wired into the execution bridge, and no hypothesis research has begun
(per instruction, this document stops at "the data pipeline exists and
is tested").

All source claims below (endpoint shapes, retention windows, earliest
coverage dates, pagination caps) were **live-verified against the real
public endpoints** during implementation, not assumed — matching this
project's own established discipline (`data_sources/open_interest.py`'s
own live-verification precedent).

## 0. Production-venue alignment (DEX-first — read before using this data for promotion)

**The production target is decentralized perpetual exchanges exclusively
— Hyperliquid primary, Lighter future (`PROJECT_CONSTITUTION.md` §4).
Binance is a research data source only and is never a production
target.** Its use here is justified purely by depth (§1) — it is the only
free source with enough history to reach a statistically meaningful
sample size for most exchange-native metrics. This does **not** make a
Binance-screened finding promotion-ready:

- **Binance data screens a hypothesis.** Use it to determine, with real
  statistical power, whether a candidate mechanism shows any edge at all.
- **Hyperliquid data validates venue-transfer.** Before any finding is
  promotion-eligible, it must be re-checked — same locked specification,
  no re-tuning — against Hyperliquid's own historical data (where one
  exists; see §1's per-metric coverage). A result that only exists on
  Binance is a research hypothesis, not a candidate for
  `docs/ALPHA_LIBRARY.md`.
- **Open Interest cannot clear this gate at all today** — Hyperliquid has
  no historical OI endpoint (§1, §3). Any OI-based hypothesis (level,
  velocity, or otherwise) is structurally blocked from promotion until
  either a live OI recorder accumulates Hyperliquid-native history going
  forward, or a paid multi-exchange aggregator is adopted (§1's Coinalyze
  row). This is a standing limitation, not specific to Campaign 01.
- **Funding Rate can clear this gate** — Hyperliquid's own `fundingHistory`
  (§1) is a real, if shallower, native source, making Funding Rate the
  only currently-collected metric where the full Binance-screen →
  Hyperliquid-replicate → (later) Hyperliquid-paper-trade sequence is
  actually executable today.
- **Venue-relative thresholds are now a required methodology, not a
  documented risk (permanent rule, confirmed by Campaign 02).** Absolute
  thresholds are not considered transferable across exchanges. Campaign
  02's Production Venue Validation showed Hyperliquid funding runs
  ~3–8× smaller in typical magnitude than Binance's, for the same
  assets/period, over the same window — a threshold locked from
  Binance's own distribution produced a near-empty signal set on
  Hyperliquid (9 vs. 141 pooled signalled samples), independent of
  whether the underlying hypothesis has any edge. **Every future
  exchange-native threshold (funding, open interest, order flow,
  liquidations, or any future metric measured natively by an exchange)
  must be derived independently per venue, from that venue's own
  historical distribution.** See `docs/RESEARCH_LEDGER.md` CAMP-02,
  `docs/PROJECT_CONSTITUTION.md` §6, and `docs/RESEARCH_PLAYBOOK.md` §2.

## 1. Source comparison and recommendation

Two candidate metrics (Open Interest, Funding Rate) × three symbols
(BTC, ETH, SOL) × two realistic free sources (Hyperliquid's own public
API, Binance's public bulk archive):

| Metric | Source | Free? | Depth (BTC/ETH/SOL) | Resolution | Notes |
|---|---|---|---|---|---|
| Funding Rate | **Hyperliquid** `/info` `fundingHistory` | Yes, no key | from ~2023-06 (venue launch) | Hourly | Venue-consistent — exactly what the live bridge pays/receives. Capped at 500 records/call (paginated). |
| Funding Rate | **Binance** bulk archive (`fundingRate`) | Yes, no key | BTC/ETH from 2020-01; SOL from 2020-09 | 8-hourly (native; recorded per-row) | Deepest free option by 3+ years. Cross-venue proxy, not Hyperliquid's own history. |
| Open Interest | Hyperliquid `/info` | — | **None** | — | **No historical OI endpoint exists.** `metaAndAssetCtxs` is current-snapshot only; an `openInterestHistory`-shaped request is rejected. Confirmed live, not assumed. |
| Open Interest | **Binance** bulk archive (`metrics`) | Yes, no key | BTC from ~2020-09; ETH/SOL from ~late 2021/early 2022 | 5-minute | The only free historical OI source found for these three symbols. |
| Open Interest | Binance live REST (`openInterestHist`) | Yes, no key | **~29 days only** (retention window measured live) | 5-minute | Explicitly rejected as a backfill source — see §3. Not used by this pipeline. |
| Both | Coinalyze (third-party aggregator) | Requires free API key (registration) | Multi-exchange, likely deep | — | Not used: introduces a credential/registration dependency this pipeline avoids; noted as a future option if Binance/Hyperliquid prove insufficient. |
| **Liquidations** | **Hyperliquid** official S3 `node_fills_by_block` | **No — authenticated AWS, Requester Pays** | **2025-07-27 → present (~12 months)** | Hourly objects (per-fill events) | Added RD-12. **Liquidations are not a stream** — they are an optional `liquidation` field ON FILLS (`{liquidatedUser, markPx, method}`), measured present on 0.31% of fills and 100% non-null when present. `hourly/YYYYMMDD/H.lz4`, LZ4 ~4.8×, 24 objects/day, ~240 GB total, backfill ~$27 (~$0 same-region). **One liquidation = two paired fills sharing one `tid`.** Source: `historical/sources/hyperliquid_s3.py`. |
| Liquidations | Hyperliquid WebSocket / REST `/info` | Yes | **None (market-wide)** | — | **No market-wide liquidation channel or request type exists** — live-verified (RD-06): 10 candidate WS subscriptions enum-rejected identically to a fake channel; REST returns HTTP 422. Per-user only (`userEvents`/`userFills`), so unusable for market-wide research. |

**Recommendation: Binance's public bulk archive
(`data.binance.vision/data/futures/um/{daily,monthly}/...`) is the
PRIMARY source for both metrics, for all three symbols.** It is free, key-less, has no rate limit (static
CloudFront-backed file downloads), ships a SHA-256 checksum per file, and
has by far the deepest history of any free option tested.

**Hyperliquid's own `fundingHistory` is used as a SECONDARY,
venue-consistent source for funding rate only** — shallower (≈3 years
less), but the one series whose values are literally what the live
execution bridge pays/receives, with no cross-venue basis to reason
about. Both are collected into separate, clearly-labeled series
(`source="binance"` / `source="hyperliquid"`) — never merged into one
undifferentiated file.

### If a dataset cannot be obtained historically for free

**Open Interest has no free historical source directly from Hyperliquid.**
This is a genuine, confirmed gap, not an oversight: the venue's public
API exposes only a current snapshot. **Recommended practical
alternative: Binance's daily `metrics` archive**, used explicitly as a
cross-venue proxy (see known biases, §4) rather than pretending it is
Hyperliquid's own history. If a research conclusion built on this proxy
data later needs venue-exact confirmation, the two realistic upgrade
paths are (a) begin accumulating Hyperliquid's own OI going forward via
a live recorder (not yet built — see `docs/RESEARCH_PLAN.md`'s
"historical sample store" item) so at least *future* history is
venue-exact, or (b) register for a free Coinalyze API key for
deeper, multi-exchange (including Hyperliquid) aggregated OI history —
not implemented here because it introduces a credential dependency this
pipeline currently has none of.

## 2. Update frequency

- **Binance daily `metrics` (Open Interest):** one new file published
  per calendar day, per symbol, at 5-minute resolution within the file
  (288 rows/day). Re-run the pipeline daily-or-slower; it only fetches
  days not already on disk (incremental by design — see §6 of
  `alpha_engine/historical/pipeline.py`'s own docstring).
- **Binance monthly `fundingRate`:** one new file per calendar month, per
  symbol, containing every settlement in that month (Binance's native
  cadence is 8-hourly for these three symbols, but this is recorded
  per-row via `funding_interval_hours`, never assumed). Re-run
  monthly-or-slower.
- **Hyperliquid `fundingHistory`:** a live, continuously-appending
  series (hourly settlements). Re-run at any cadence; the pipeline
  resumes from the latest timestamp already collected (a high-water
  mark), never re-fetching the full range.
- None of this is currently scheduled — per `docs/ALPHA_ENGINE.md`'s
  already-documented "no scheduler" limitation, the pipeline is invoked,
  not self-running.

## 3. Limitations

- **Binance's live `openInterestHist` REST endpoint was tested and
  rejected as a backfill source.** Live probing found its historical
  query window is restricted to roughly the trailing 29 days
  (`startTime` outside that window is rejected with error code -1130) —
  confirmed by testing 27/28/29/30/31 days back. It is useful only for
  a live/near-real-time OI recorder, never for backfilling real history;
  the bulk daily `metrics` archive is the only free path to deep OI
  history.
- **Binance's `metrics` (OI) archive does not go back as far as each
  symbol's exchange listing.** Binance began publishing this specific
  data type well after BTC/ETH/SOL were already listed — confirmed live:
  BTCUSDT metrics start ~2020-09 (BTC itself listed on Binance futures
  in 2019), ETHUSDT/SOLUSDT metrics start only in ~late 2021/early 2022.
  There is no way to get OI further back than this for free.
- **No monthly `metrics` (OI) archive exists** — only daily files
  (confirmed live: the monthly path 404s). The pipeline therefore issues
  one request per DAY for OI, versus one request per MONTH for funding
  rate — a real asymmetry in request volume for a wide backfill.
- **Symbol mapping is fixed and narrow**: `Symbol("BTC")` →
  `"BTCUSDT"`, and only that USDT-margined pairing, for exactly these
  three symbols. A different quote asset or a symbol outside this
  project's watchlist is out of scope for this pipeline as written.
- **The pipeline does not currently discover a symbol's true earliest
  coverage automatically** — a caller supplies `start_date`/`end_date`
  explicitly (informed by the depths documented above). Requesting a
  date before real coverage begins is handled gracefully (logged,
  skipped, reported in `CollectionResult.periods_unavailable`), never a
  crash or a fabricated row — but the pipeline will not tell you the
  *exact* first available day/month beyond "before this date, expect
  every period to come back unavailable."
- **Rerun safety, not rerun completeness monitoring**: incremental reruns
  are safe (idempotent) and cheap (skip what's already collected), but
  nothing currently alerts an operator if a scheduled rerun silently
  stopped happening — there is no scheduler or monitoring layer (see
  `docs/ALPHA_ENGINE.md`).

## 4. Point-in-time considerations

- **Binance funding rate**: PIT-safe by nature — a settled rate at time
  T was fixed and published at T, and Binance's bulk archive does not
  appear to retroactively republish historical months (each month's file
  content matched its own checksum consistently across repeated
  fetches during verification). Treat as immutable once collected.
- **Binance open interest**: PIT-safe in the sense that each 5-minute
  snapshot in the archive is a genuine historical record, not a
  reconstruction — but OI (unlike funding) has no independent
  "settlement" concept; it is a continuously-changing state variable
  sampled at 5-minute intervals, so a strategy operating at a
  DIFFERENT cadence than 5 minutes must explicitly decide how to
  resample/aggregate rather than assume the raw 5-minute series is
  already at the "right" frequency for its hypothesis.
- **Hyperliquid funding rate**: identical PIT-safety reasoning to
  Binance's — a settled rate is fixed at settlement — with the
  additional property that this IS the exact series the live bridge
  already consumes going forward (no cross-venue reconciliation risk to
  reason about at all when using this source specifically).
- **`ingested_at_utc` vs. `observed_at_utc`**: every stored row carries
  both — `observed_at_utc` is the historically correct timestamp the
  value pertains to; `ingested_at_utc` is when THIS pipeline run fetched
  it. A validation/feature pipeline must always key off
  `observed_at_utc`, never `ingested_at_utc` — using the latter would
  reintroduce exactly the look-ahead risk this project's existing
  causality-audit stage (`alpha_engine.validation.causality_audit`)
  already exists to catch downstream.
- **No revision-tracking is needed for either metric** (unlike the
  stablecoin-flow/on-chain/macro sources flagged as higher PIT-risk in
  `docs/RESEARCH_PLAN.md` §2) — funding settlements and OI snapshots are
  not analytics-provider-derived aggregates subject to silent
  methodology revision; they are the exchange's own primary records.

## 5. Known biases

- **Binance data is not Hyperliquid data — and Binance is not a
  production target at all (see §0).** This is the single most important
  bias to carry into any research conclusion: funding rate and open
  interest are strictly venue-specific (different mark-price formulas,
  different funding cadence — Binance's historical cadence for these
  symbols was 8-hourly vs. Hyperliquid's 1-hourly — different trader
  populations, different liquidity depth; Binance is also a centralized
  exchange, a structurally different market design from the decentralized
  perpetual venues — Hyperliquid, and Lighter in future — this project
  actually trades on). A pattern found in Binance's multi-year history is
  a hypothesis about derivatives-market behavior *in general*, not a
  proven fact about what would happen on the production venue
  specifically, and **must not be promoted to `docs/ALPHA_LIBRARY.md`
  without the Hyperliquid-replication check in §0**. Any experiment built
  primarily on Binance-sourced history should say so explicitly in its
  `known_limitations` (the existing `EvidencePackage` field this project
  already reserves for exactly this kind of caveat).
- **Survivorship / listing bias in "earliest available" dates.** BTC and
  ETH have deep coverage; SOL's coverage starts later for BOTH the OI
  archive and funding archive (its Binance futures listing itself is
  later). Any cross-symbol comparison (e.g. "does this rule work
  equally on BTC/ETH/SOL?") implicitly compares different amounts of
  history and different market regimes for SOL versus BTC/ETH unless
  explicitly windowed to a common overlapping period.
  `alpha_engine.validation.run_regime_stratified_validation` already
  exists to help surface exactly this kind of regime-concentration risk
  once real samples are validated.
- **5-minute OI sampling is Binance's publishing choice, not a
  neutral default.** Any feature built on "OI at time T" is implicitly
  built on Binance's own snapshot cadence; a genuinely different
  cadence would require either resampling this series or a different
  source entirely.
- **Single-source risk for OI.** Only one provider (Binance) was found
  for free historical OI on these symbols — there is no independent
  second source to cross-check a suspicious value against (a limitation
  already flagged generically for OI in `docs/RESEARCH_PLAN.md` §2, now
  concretely confirmed to apply to whichever source this pipeline
  actually uses).

## 6. Pipeline design (implementation summary)

`alpha_engine/historical/` — additive, zero coupling to any frozen
Execution Engine package (test-enforced by
`test_alpha_engine_scaffold.py`'s `TestNoFrozenModuleCoupling`, which
scans this package too):

- `models.py` — `FundingRateObservation`, `OpenInterestObservation`:
  typed, canonical-UTC-validated (reusing `alpha_engine._time`'s B5
  timestamp discipline), immutable.
- `validation.py` — `assess_quality()`: duplicate detection, chronological
  ordering, and gap detection (given an expected sampling interval) over
  a collected series — never raises for a data condition, only counts
  and reports (mirrors `alpha_engine.validation.causality_audit`'s own
  discipline). `verify_checksum()`: SHA-256 integrity check against each
  source file's published `.CHECKSUM`.
- `storage.py` — one plain CSV file per (metric, symbol, source); loads,
  merges, deduplicates, and atomically rewrites (temp file + rename) on
  every collection run — safe to interrupt, safe to rerun.
- `sources/binance.py`, `sources/hyperliquid.py` — stdlib-only
  (`urllib`, `zipfile`, `csv`, `json`) clients, each with an injectable
  transport function for offline testing (mirroring
  `alpha_engine.data_sources.open_interest`'s own `TransportFn` pattern).
  A 404 (file/date genuinely not published) is handled gracefully; any
  other transport failure or a checksum mismatch raises.
- `pipeline.py` — `collect_open_interest()` / `collect_funding_rate()`:
  the incremental orchestrators. Before fetching a period, each checks
  whether it is already present on disk and skips the network call if
  so (`force=True` overrides this). Returns a `CollectionResult`
  carrying a full-series `DataQualityReport`.

Storage location (not committed to source control — `data/` is already
git-ignored repository-wide): `data/alpha_engine_historical/`, e.g.
`data/alpha_engine_historical/open_interest__BTC__binance.csv`.

### Example usage

```python
from datetime import date
from exchange_adapter import Symbol
from alpha_engine.historical import collect_open_interest, collect_funding_rate

result = collect_open_interest(
    Symbol("BTC"), date(2024, 1, 1), date(2024, 12, 31),
    storage_root="data/alpha_engine_historical",
)
print(result.rows_added, result.periods_unavailable, result.quality_report.clean)

# Re-running the same call later only fetches new/missing days.
collect_funding_rate(
    Symbol("ETH"), date(2020, 1, 1), date(2024, 12, 31),
    storage_root="data/alpha_engine_historical", source="binance",
)
collect_funding_rate(
    Symbol("BTC"), date(2023, 6, 1), date(2024, 12, 31),
    storage_root="data/alpha_engine_historical", source="hyperliquid",
)
```

## 7. Tests

`tests/test_alpha_engine_historical_models.py`,
`test_alpha_engine_historical_validation.py`,
`test_alpha_engine_historical_storage.py`,
`test_alpha_engine_historical_sources_binance.py`,
`test_alpha_engine_historical_sources_hyperliquid.py`,
`test_alpha_engine_historical_pipeline.py` — 72 tests, all offline (every
network-facing function takes an injectable transport; no test makes a
real HTTP call). Covers: value-type validation, duplicate/gap/ordering
detection, checksum verification, atomic incremental merge (including
the conflicting-vs.-identical-duplicate distinction), both sources'
happy/unavailable/malformed/transport-error paths, Hyperliquid
pagination past its 500-record cap, and end-to-end incremental
collection (including `force=True` and the high-water-mark resume
behavior) for both metrics and both funding-rate sources.

Full repository regression: 1,520 passed (72 new), zero failures, zero
frozen Execution Engine files touched.

## What this document does NOT do

Per instruction, this is infrastructure documentation only. No hypothesis
has been tested, no candidate has been evaluated against this data, and
no `ValidationSample` has been constructed from it. That work begins only
after this pipeline has been reviewed and real historical data has
actually been collected — see `docs/RESEARCH_PLAN.md` for what comes
next.
