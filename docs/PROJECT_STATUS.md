# PROJECT_STATUS.md

**Living document — current state only.** For the project's unchanging
vision and principles, see `PROJECT_CONSTITUTION.md`. For a single-page
executive summary, see `PROJECT_DASHBOARD.md`. For future work, see
`ROADMAP.md`. This document supersedes the root-level
`PROJECT_HANDOVER.md` and `AUDIT_HISTORY.md` snapshots (both retained,
now marked superseded, for history).

All figures below were verified against the repository at the time of
writing (full suite run, registry inspection, file listing) — not carried
from memory.

---

## Overall status

Two subsystems, two different maturity levels:

| Subsystem | Status |
|---|---|
| **Execution Engine** (Modules 1–10 + app layer) | Frozen, engineering-complete, independently audited. Conditional GO for testnet (two operator actions outstanding). No live capital deployed. |
| **Alpha Engine** (`alpha_engine/` + `research/`) | Platform complete and validated end-to-end on real data across three independent research campaigns. **Zero approved alpha models** (three clean, honest rejections). No paper or live trading has ever occurred. |

**Full regression: 1,576+ tests passing** (820 Execution Engine baseline
+ 756+ Alpha Engine / historical-pipeline / research-harness tests,
including Campaigns 02 and 03's own harness code), zero failures, zero
frozen files modified.

## Current phase

**Alpha Engine: research phase, three campaigns complete, fourth not yet
started.** Research Campaign 01 (Open Interest level), Campaign 02
(Funding Rate, absolute threshold), and Campaign 03 (Funding Rate,
venue-relative threshold) all ran end-to-end — real data, real evidence,
real governance — and all closed with every pre-registered hypothesis
rejected. The project remains in "quantitative research engineer" mode:
prioritize research over further infrastructure, per the standing
instruction.

**Execution Engine: dormant, stable, unchanged.** No work is planned here
except an authorized critical-defect correction; see
`PROJECT_CONSTITUTION.md` §9.

## Engineering completion

**Execution Engine: ~100% for its defined scope.** Unchanged since
Campaign 01 — see `FINAL_PRODUCTION_AUDIT.md`.

**Alpha Engine: ~95% for the platform built to date.** Campaigns 02 and
03 both added zero new platform (`alpha_engine/`) code — only
campaign-specific harness code under `research/campaign_0{2,3}_*/`,
exactly as `ROADMAP.md` intends: reuse the existing registry, five-stage
validation, evidence, governance, and historical pipeline unchanged.
Three campaigns, three genuinely different specifications, zero platform
changes — strong evidence the platform is stable and sufficient for this
class of hypothesis. See `docs/STRATEGIC_GAP_ANALYSIS.md` for the
detailed per-capability breakdown (~50–55% against the full long-term
vision).

## Research completion

**Five campaigns complete, zero alpha approved; one mechanism deferred.**

- **Campaign 01 — Open Interest (level).** Four experiments (percentile-
  rank/z-score × contrarian/momentum), all **REJECTED on merit** — hit
  rates 0.49–0.51, indistinguishable from chance.
- **Campaign 02 — Funding Rate (absolute threshold).** Two experiments
  (contrarian, momentum), both **REJECTED**. Momentum cleared
  single-pass (hit rate 0.560, 141 signalled) but failed walk-forward and
  regime stratification — 93.6% of its signal concentrated in one market
  regime (bull). Production Venue Validation on Hyperliquid confirmed the
  identical threshold does not transfer across venues (~3–8× scale
  mismatch) — a venue-transfer failure of the *threshold methodology*.
- **Campaign 03 — Funding Rate (venue-relative threshold).** Same
  hypothesis, re-operationalized with an independent per-venue threshold
  (75th percentile of \|funding\|, derived from each venue's own
  distribution), removing CAMP-02's transfer confound. Both directions,
  both venues, **REJECTED** — neither venue's momentum hit rate reached
  0.55 (Binance 0.525, Hyperliquid 0.531). Hyperliquid's rejection is
  clean and well-powered (every walk-forward fold cleared the sample
  floor, failed purely on hit rate); Binance's walk-forward failure is
  partly a smaller-scale recurrence of CAMP-02's structural fold-floor
  issue. This is the first funding finding marked venue-validated
  ("yes") in `ALPHA_LIBRARY.md` — not because it was promising, but
  because each venue was independently and correctly tested.
- Full detail: `docs/RESEARCH_LEDGER.md` (CAMP-01, CAMP-02, CAMP-03),
  `docs/RESEARCH_CAMPAIGN_01_open_interest.md`,
  `docs/RESEARCH_CAMPAIGN_02_funding_rate.md`,
  `docs/RESEARCH_CAMPAIGN_03_funding_rate_venue_relative.md`.
- **Alpha Library remains empty of approved models** — see
  `docs/ALPHA_LIBRARY.md`.

## Operational readiness

Unchanged since Campaign 01 — see `FINAL_PRODUCTION_AUDIT.md` (Execution
Engine) and below (Alpha Engine: no operational readiness yet, by
design — nothing approved to deploy).

**None active.** Campaign 05 is closed (both experiments in lifecycle
state `REJECTED`, governance decisions durably recorded). No new campaign
has been registered yet.

## Previous campaigns

- **Campaign 01 — Open Interest (level).** `docs/RESEARCH_LEDGER.md`
  CAMP-01. Closed, rejected, not retried.
- **Campaign 02 — Funding Rate (absolute threshold).**
  `docs/RESEARCH_LEDGER.md` CAMP-02. Closed, rejected. Surfaced the
  venue-transfer finding that shaped CAMP-03.
- **Campaign 03 — Funding Rate (venue-relative threshold).**
  `docs/RESEARCH_LEDGER.md` CAMP-03. Closed, rejected. Confirmed no edge
  even once correctly operationalized per venue.
- **Campaign 04 — Funding Delta (change in funding).**
  `docs/RESEARCH_LEDGER.md` CAMP-04. Closed, rejected — the best-powered
  funding rejection (per-fold floors substantially cleared,
  regime-balanced, still edgeless). **Funding Persistence was deferred**
  before it (statistically non-viable, N_eff ≈ 4–18 — `RESEARCH_DECISIONS.md`
  RD-04).
- **Campaign 05 — Open Interest Velocity (24h fractional change).**
  `docs/RESEARCH_LEDGER.md` CAMP-05. Closed, rejected — the cleanest,
  best-powered rejection to date: every walk-forward fold cleared the
  sample floor ([169, 113, 108]), so failure was on hit-rate merit, and
  regime stratification failed by even spread across bull/chop/bear.
  Carried a structural **DEFER-ceiling** (no Hyperliquid OI history →
  APPROVE unreachable). No new methodological rule was created
  (`RESEARCH_DECISIONS.md` RD-09).

## Research family state (two-state model, `RESEARCH_DECISIONS.md` RD-07)

Each family carries an independent **Research Status** and **Data
Status**; the authoritative table is the `RESEARCH_DECISIONS.md`
appendix. Current summary:

- **Funding Rate — NEAR-EXHAUSTED / Data READY.** Level, venue-relative,
  and Delta rejected; Persistence deferred (RD-04); regime-interaction
  untestable on this window. No cheap distinct mechanism remains.
- **Open Interest — ACTIVE / Data READY (Binance only), production-capped.**
  Level (CAMP-01) and Velocity (CAMP-05) both rejected; **Divergence** is
  the sole untested mechanism, under the same DEFER-ceiling.
- **Liquidations — LOCKED / Data NONE.** Historical data exists through
  official Hyperliquid S3 archives but has not been acquired. Access
  requires authenticated AWS Requester Pays credentials. Earliest
  coverage remains unverified. (**RD-10**, which supersedes RD-06's
  conclusion only — RD-06's live-verified evidence that no WS liquidation
  channel and no REST liquidation endpoint exist remains valid.
  Liquidations are a documented `liquidation` field on **fill** records,
  not a standalone event stream.)
- All other families remain LOCKED or PAUSED with Data NONE — see the
  `RESEARCH_DECISIONS.md` appendix for each unlock condition.

## Next campaign (after Campaign 05)

Per `docs/RESEARCH_DECISIONS.md` RD-05:

1. **Open Interest Divergence** — the remaining untested OI mechanism,
   subject to the same production cap (knowledge-only, not
   promotable today).

No campaign should be started without a fresh pre-registration
(`docs/RESEARCH_PLAYBOOK.md`, including its own mandatory feasibility
review); none of the above may reuse or "improve" a prior campaign's
already-closed, rejected specifications.

## Known blockers

Unchanged since Campaign 01 (live sample recorder; Execution Engine
testnet operator actions; zero approved alpha) — see `ROADMAP.md`.

## Known risks

- **Binance-vs-Hyperliquid venue mismatch — CONFIRMED (Campaign 02),
  now permanently mitigated by the venue-relative methodology rule
  (Campaign 03).** Absolute exchange-native thresholds are no longer
  used; every future exchange-native metric derives its threshold
  independently per venue. See `docs/HISTORICAL_DATA.md` §0 and
  `docs/PROJECT_CONSTITUTION.md` §6.
- **Small sample sizes at the per-symbol level**, and **regime
  concentration** — all three campaigns showed pooled/"combined" results
  can be dominated by a single symbol or a single market regime
  (Campaign 01's directionally-inconsistent per-symbol slices; Campaigns
  02 and 03's bull-regime-concentrated signal, 93.6% and 75–87%
  respectively). Per-symbol and per-regime breakdowns must always be
  inspected, never inferred from the pooled headline number alone.
- **The per-fold `min_signaled_samples` criterion can still be
  miscalibrated even after reducing `n_folds`, if signals cluster
  unevenly across chronological folds** (Campaign 03 lesson: Binance's
  folds were 64/171/45 signalled despite a fold-count reduction sized
  from the *average* — two of three folds still missed the floor). The
  mandatory feasibility review (`RESEARCH_PLAYBOOK.md` §2) should check
  per-fold counts under the real chronological split, not the average
  alone — flagged for the next feasibility review to apply, not changed
  retroactively on any closed campaign.
- **Plaintext secrets hygiene (Execution Engine, SEC-1)** — unchanged,
  operator rotation still recommended before mainnet.

## Current priorities

1. Register and execute the next research campaign (BTC-only Funding
   momentum, properly powered, or Open Interest velocity/change).
2. Do not build new Alpha Engine infrastructure unless a specific
   campaign cannot proceed without it — Campaigns 02 and 03 are proof
   this discipline holds (zero new platform code needed for either).
3. Complete the Execution Engine's outstanding testnet operator actions
   whenever live/paper trading readiness becomes relevant (not gated by,
   and not blocking, research work).

## Current completion estimate

**~50–55% toward the full long-term vision** (`PROJECT_CONSTITUTION.md`
§1), unchanged in aggregate since the last full gap analysis
(`docs/STRATEGIC_GAP_ANALYSIS.md`). Campaign 02 further validated the
platform (a second, structurally different candidate family ran
end-to-end with zero new platform code) without changing what's still
architecturally missing (combining models, ranking, continuous
automation). The platform is no longer the bottleneck; a validated alpha
signal is.
