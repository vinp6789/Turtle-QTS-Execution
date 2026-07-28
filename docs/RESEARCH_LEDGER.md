# RESEARCH_LEDGER.md

**Permanent scientific record.** One entry per completed research
campaign, in the order campaigns were run. **Rejected hypotheses are
never deleted** — per `PROJECT_CONSTITUTION.md` §6, a rejected hypothesis,
honestly reached, is a successful research outcome and permanent
knowledge. This ledger is condensed; each entry links to its full
pre-registration/methodology document for complete detail.

For the process this ledger's entries follow, see
`docs/RESEARCH_PLAYBOOK.md`. For the currently-approved (today: empty)
set of models, see `docs/ALPHA_LIBRARY.md`. For what's next, see
`ROADMAP.md` §1.

---

## CAMP-01 — Open Interest (level)

**Status: CLOSED — all four hypotheses REJECTED on merit.**

| Field | Value |
|---|---|
| ID | CAMP-01 |
| Information source | Open Interest (priority #1) |
| Full detail | `docs/RESEARCH_CAMPAIGN_01_open_interest.md` |
| Experiments | 4 (percentile-rank × {contrarian, momentum}; z-score × {contrarian, momentum}) |
| Registry experiment IDs | `camp01-combined-pctrank-contrarian`, `camp01-combined-pctrank-momentum`, `camp01-combined-zscore-contrarian`, `camp01-combined-zscore-momentum` |

**Hypothesis:** Open Interest becoming extreme relative to its own recent
history (30-day trailing percentile rank or z-score) predicts a 24-hour
forward return — tested in both directions, separately: contrarian (mean
reversion: extreme OI → SHORT) and momentum (continuation: extreme OI →
LONG).

**Rationale:** Open Interest measures total open leveraged notional. A
rapid build-up to an extreme is a plausible marker of either (a)
over-crowded positioning vulnerable to a squeeze/reversal (the contrarian
prior) or (b) genuine new-capital conviction confirming the move (the
momentum prior). Both are real, opposing priors in derivatives-market
folklore; the campaign's job was to test both, not assume either.

**Dataset:** BTC/ETH/SOL, Binance USDⓈ-M perpetual Open Interest + derived
mark price (`sum_open_interest_value / sum_open_interest`), 5-minute
resolution, 2023-07-01 → 2024-12-31 (18 months), ~158k rows/series,
integrity-verified (zero duplicates, monotonic, no gap > 1 day). Pooled,
non-overlapping daily point-in-time samples: 1,557.

**Validation:** Full five-stage gate (`alpha_engine.research.
run_research_cycle`) — single-pass, leakage/causality audit, walk-forward
(5 folds), bootstrap resampling (1,000 resamples, seed 7), regime
stratification (BTC bull/bear/chop, price-derived). Pre-registered
acceptance criteria: `min_hit_rate = 0.55`, `min_signaled_samples = 100`.
Locked before any result was seen; never adjusted.

**Evidence package:** Four sealed, content-fingerprinted evidence
packages (SHA-256): `pctrank/contrarian 33569639aa91185f…` ·
`pctrank/momentum 1b3d713954af4feb…` · `zscore/contrarian
9489c0e973da9ae2…` · `zscore/momentum fca4ffff3521967b…`. Causality audit
**passed** for all four (no leakage; every outcome strictly post-dates its
feature).

**Governance decision:** REJECT recorded for all four (reviewer ≠
researcher, evidence-fingerprint verified) — durable lifecycle state
`REJECTED` for all four experiment records.

**Final verdict:** Hit rates 0.49–0.51 (indistinguishable from a coin
flip); the pre-registered 0.55 bar cleared in only 8.5–16.5% of bootstrap
resamples; every bootstrap range straddled 0.5. **Open Interest *level*
extremes — either normalization, either direction — carry no reliable
24-hour directional edge on BTC/ETH/SOL over the 18-month sample.** Not a
leakage artifact (causality passed); not a data-shortfall artifact
(sample floor cleared); the robustness normalization (z-score) agreed
with the primary (percentile rank).

**Lessons learned:**
- Raw Open Interest is strongly non-stationary (a documented 3.4×
  secular swing across the sample) — any future OI-based hypothesis must
  normalize (rank or z-score), never threshold the raw level.
- Per-symbol slices at this depth (35–73 signalled samples) are
  underpowered and **directionally inconsistent** across symbols (BTC
  favoured contrarian, SOL favoured momentum, ETH favoured neither) — the
  signature of noise, not signal. The pooled, powered analysis is the one
  that carries weight; per-symbol breakdowns are diagnostic only until
  each individually clears the sample floor.
- Contrarian and momentum hit rates on the same signalled samples are
  mechanical mirror images (summing to ~1.0) — a favourable-looking hit
  rate in one direction is not, by itself, evidence; both directions must
  be judged against the pre-registered bar independently.
- The historical pipeline and five-stage validation gate handled a real,
  18-month, three-symbol dataset without any change to the platform —
  the research harness built for this campaign is reusable as-is for the
  next one.

**Next suggested direction:** Open Interest *velocity/change* (not level)
as a distinct, new pre-registration; longer horizons (3–7 day); and —
per the original priority order and this campaign's own evidence — the
**Funding Rate campaign** as the highest-value next step (naturally
stationary, no new normalization infrastructure required). See
`ROADMAP.md` §1.

---

## CAMP-02 — Funding Rate

**Status: CLOSED — both hypotheses REJECTED on the Binance screen;
Production Venue Validation inconclusive on the hypothesis but decisive
on a distinct venue-transfer finding.**

| Field | Value |
|---|---|
| ID | CAMP-02 |
| Information source | Funding Rate (priority #2) |
| Full detail | `docs/RESEARCH_CAMPAIGN_02_funding_rate.md` |
| Experiments | 2 (contrarian, momentum) × 2 sources (Binance screen, Hyperliquid Production Venue Validation) |
| Registry files | `data/alpha_engine_research/campaign_02_{binance,hyperliquid}_{BTC,ETH,SOL,combined}.jsonl` |

**Hypothesis:** extreme funding rate (fixed threshold, pooled 90th
percentile of \|funding\| across BTC/ETH/SOL's historical distribution)
predicts a 24-hour forward return — tested contrarian (funding cost
crowding → reversal) and momentum (crowding confirms the trend)
separately.

**Rationale:** funding rate measures the *priced cost* of holding
positioning, a structurally different signal from Campaign 01's Open
Interest (raw positioning *quantity*) — a genuinely different hypothesis
family using an existing, previously-unexercised candidate mechanism
(`funding_rate_threshold_rule`, M3.2).

**Dataset:** BTC/ETH/SOL, 2023-07-01 → 2024-12-31. Binance funding
(1,650 settlements/symbol, 8-hourly, integrity-verified) for statistical
screening; Hyperliquid funding (13,197 settlements/symbol, hourly,
integrity-verified) for Production Venue Validation, per the DEX-first
requirement (`PROJECT_CONSTITUTION.md` §6). Same mark-price series as
Campaign 01 reused for outcomes.

**Validation:** identical five-stage gate and locked criteria as Campaign
01 (`min_hit_rate=0.55`, `min_signaled_samples=100`, `n_folds=5`,
`n_resamples=1000`, `seed=7`) — held constant across campaigns for
comparability, not tuned per-campaign. Threshold (0.00023655) locked from
an outcome-blind exploratory pass over the raw funding distribution
before any sample was built.

**Evidence:** four sealed, fingerprinted evidence packages (two sources ×
two directions, combined universe): Binance contrarian
`02d0e0db30439934…`, Binance momentum `1fd5d92a2fb9da51…`, Hyperliquid
contrarian `051df9d90ed8e0d0…`, Hyperliquid momentum `f99575814fb8e18a…`.
Causality audit passed for every experiment (no leakage).

**Governance decision:** REJECT recorded for all four (reviewer ≠
researcher, evidence-fingerprint verified).

**Final verdict:** **Binance screen — both REJECTED.** Contrarian showed
no edge (hit rate 0.440, well below chance). Momentum cleared single-pass
outright (hit rate 0.560, 141 signalled) — the first Campaign 02 result
to do so — but was correctly rejected once walk-forward and regime
stratification showed 93.6% of its signalled samples concentrated in a
single market regime (bull), with hit rate elsewhere near-random or
sample-starved. **Hyperliquid Production Venue Validation — inconclusive
on the hypothesis, decisive on a distinct finding:** the identical locked
threshold produced only 9 pooled signalled samples (vs. 141 on Binance)
because Hyperliquid's funding rate runs ~3–8× smaller in typical
magnitude than Binance's for the same assets/period (confirmed via the
same outcome-blind distributional method as the original threshold
derivation) — the *threshold's* transferability failed, not (necessarily)
the *hypothesis's*.

**Lessons learned:**
- A raw-magnitude threshold does not transfer across venues with
  structurally different funding scales — future exchange-native
  threshold research should default to a venue-relative (percentile-of-
  that-venue's-own-distribution) methodology from the start.
- The five-stage gate caught a single-pass-clearing result that further
  scrutiny (walk-forward, regime stratification) showed was not
  regime-robust — exactly the scenario the multi-stage design exists to
  catch.
- The per-fold `min_signaled_samples=100` criterion may be miscalibrated
  for walk-forward specifically (no fold could reach 100 with ~141 total
  signalled samples split five ways) — a methodology question flagged
  for review, not changed retroactively.
- Funding's sign-skew and high persistence, both flagged outcome-blind
  before any sample was built, played out exactly as anticipated in the
  results — confirming the value of the outcome-blind exploratory step.
- BTC's individual momentum result (0.686 hit rate, 35 samples,
  underpowered) is the strongest single-symbol result across both
  campaigns to date — a named candidate for a future properly-powered
  follow-up, never acted on directly from this underpowered reading.

**Next suggested direction:** (1) re-attempt funding rate with a
venue-relative threshold methodology (fixes the specific limitation this
campaign surfaced, without violating the no-retuning rule, since the new
methodology would be locked before any new outcome is seen); (2) a
dedicated, properly-powered BTC-only momentum follow-up using Binance's
deeper (2020+) history. Both are new, separately pre-registered
campaigns — CAMP-02 itself is closed and will not be reopened.

---

## CAMP-03 — Funding Rate, Venue-Relative Threshold

**Status: CLOSED — all four experiments REJECTED on merit.**

| Field | Value |
|---|---|
| ID | CAMP-03 |
| Information source | Funding Rate (venue-relative re-attempt, per CAMP-02's own recommendation) |
| Full detail | `docs/RESEARCH_CAMPAIGN_03_funding_rate_venue_relative.md` |
| Experiments | 2 (contrarian, momentum) × 2 venues, each scored against its own locked threshold — no screen/replicate dependency |
| Registry files | `data/alpha_engine_research/campaign_03_{binance,hyperliquid}_{BTC,ETH,SOL,combined}.jsonl` |

**Hypothesis:** identical to CAMP-02 (extreme funding rate predicts a
24h forward return, contrarian and momentum), but operationalized
correctly per the permanent methodology rule adopted after CAMP-02's
review: threshold derived independently per venue from that venue's own
historical distribution, rather than one absolute value carried across
venues.

**Rationale:** CAMP-02's Production Venue Validation showed an
absolute-magnitude threshold does not transfer across venues of
different scale — a threshold-transfer failure, not a settled answer on
the hypothesis itself. CAMP-03 removes that confound by giving each
venue its own correctly-derived threshold, testing whether the
underlying hypothesis (not the number) has any edge.

**Mandatory feasibility review (outcome-blind, before locking):** found
CAMP-02's 90th-percentile choice structurally infeasible for
walk-forward on either venue at any reasonable fold count; locked a 75th
percentile instead, with `n_folds` reduced from 5 to 3 — both decisions
made from signal-count projections alone, zero outcome data examined.
See `docs/RESEARCH_CAMPAIGN_03_funding_rate_venue_relative.md` §1.

**Dataset:** BTC/ETH/SOL, 2023-07-01 → 2024-12-31, both venues' funding
(already collected during CAMP-02) + the existing Binance mark-price
series for outcomes. Binance threshold `0.0001000000` → 280 pooled
signalled samples; Hyperliquid threshold `0.000038592350` → 461 pooled
signalled samples.

**Validation:** identical five-stage gate as CAMP-01/02
(`min_hit_rate=0.55`, `min_signaled_samples=100`, `n_resamples=1000`,
`seed=7`), with `n_folds=3` (not 5) per the feasibility review above.

**Evidence:** four sealed, fingerprinted evidence packages: Binance
contrarian `c745f1d63a08cf46…`, Binance momentum `6b14ecab8f6d29f3…`,
Hyperliquid contrarian `88cfa48376514920…`, Hyperliquid momentum
`40209b99fe7fc8ed…`. Causality audit passed for all four.

**Governance decision:** REJECT recorded for all four (reviewer ≠
researcher, evidence-fingerprint verified).

**Final verdict:** **Both directions, both venues — REJECTED.** Neither
venue's momentum hit rate reaches 0.55 (Binance 0.525, Hyperliquid
0.531) — both fail single-pass outright, unlike CAMP-02's Binance
momentum (which cleared single-pass before failing downstream). On
Hyperliquid, every walk-forward fold cleared `min_signaled_samples`
(160/198/103) and failed on **hit rate alone** in every fold — a clean,
well-powered rejection. On Binance, signals cluster unevenly across
folds (64/171/45 signalled) — a residual, smaller-scale recurrence of
the same structural walk-forward issue CAMP-02 surfaced, only partially
resolved by the fold-count reduction. Regime concentration recurs (86.8%
bull Binance, 75.7% bull Hyperliquid) but, unlike CAMP-02, momentum does
not clear 0.55 even within the bull regime alone on either venue — a
broader, cleaner "no edge" finding than CAMP-02's.

**Lessons learned:**
- Venue-relative thresholds resolve the specific operationalization
  failure CAMP-02 found — the underlying funding-level hypothesis still
  shows no edge once correctly operationalized per venue, a genuine
  hypothesis rejection, not another transfer failure.
- Reducing `n_folds` fixes the *average* per-fold sample count but not
  *temporal clustering* of signals within a chronologically-split fold —
  a future campaign's feasibility review should check per-fold counts
  under the real chronological split, not the average alone.
- A feasibility-review proxy that doesn't match the real candidate's
  comparison operator can materially misestimate signal count,
  especially near a common clamped/capped raw value (discovered here:
  Binance's real signaled count, 280, came in well below the review's
  `>=`-based proxy estimate of 861, because the actual candidate uses
  strict `>`).
- A milder (75th-percentile) threshold is not "too weak to be a real
  test" — the absence of edge here is broader and cleaner than CAMP-02's,
  not merely diluted.
- Zero new `alpha_engine/` platform code was required — only
  campaign-specific harness code, again confirming platform sufficiency.

**Next suggested direction:** funding rate (level) has now been tested
twice, both venues, with no edge found under two different threshold
methodologies. (1) A dedicated, properly-powered BTC-only momentum
follow-up (the strongest single-symbol reading across both funding
campaigns: CAMP-02's Binance BTC 0.686/n=35, this campaign's Hyperliquid
BTC 0.580/n=138, both underpowered or sub-bar in isolation); or (2) Open
Interest velocity/change, a genuinely new hypothesis family. See
`docs/RESEARCH_CAMPAIGN_03_funding_rate_venue_relative.md` §10.

---

## CAMP-04 — Funding Delta (change in funding)

**Status: CLOSED — all four experiments REJECTED on merit; the
best-powered funding rejection to date.**

| Field | Value |
|---|---|
| ID | CAMP-04 |
| Information source | Funding Rate — Delta mechanism (rate-of-change, not level) |
| Full detail | `docs/RESEARCH_CAMPAIGN_04_funding_delta.md` |
| Experiments | 2 (contrarian, momentum) × 2 venues, each scored against its own locked venue-relative delta threshold |
| Registry files | `data/alpha_engine_research/campaign_04_{binance,hyperliquid}_{BTC,ETH,SOL,combined}.jsonl` |

**Hypothesis:** an extreme *change* in funding between consecutive
settlements (`funding_delta`, a shock/rate-of-change feature — distinct
from level and from persistence) predicts a 24h forward return, tested
contrarian and momentum.

**Selection path (outcome-blind):** Funding Persistence was evaluated
first and **deferred** (feasibility: effective sample size N_eff ≈ 4–18
from intrinsic within-run autocorrelation ≈ 0.98; negative-persistence
tail absent). Funding Delta then passed the identical feasibility gate —
differencing removed the ramp autocorrelation (N_eff ≈ 247–526), restored
sign symmetry, and proved rank-orthogonal to level on Binance (Spearman
≈ 0). See `docs/RESEARCH_CAMPAIGN_04_funding_delta.md` §1.

**Mandatory feasibility review:** locked the threshold at the per-venue
**75th percentile of |funding_delta|** and `n_folds = 3` — the
most-extreme percentile / max fold-count clearing the 100-signalled/fold
walk-forward floor on both venues (p80 and n_folds=5 were infeasible).
All decisions made from outcome-blind signal-count projections.

**Dataset:** BTC/ETH/SOL, 2023-07-01 → 2024-12-31, both venues' funding
(already collected) + Binance mark price for outcomes. Binance threshold
`0.00005239` → 354 pooled signalled; Hyperliquid `0.00001205` → 450
pooled signalled.

**Evidence:** four sealed, fingerprinted packages: Binance contrarian
`14ab0f05b1da976027ee42b7…`, Binance momentum `25bc38e0cbe7e86ff2f79b96…`,
Hyperliquid contrarian `4182edebb7888432095a68d1…`, Hyperliquid momentum
`c237e53ff997253484b2f494…`. Causality passed for all four.

**Governance decision:** REJECT recorded for all four (reviewer ≠
researcher, evidence-fingerprint verified).

**Final verdict:** **All four REJECTED.** No venue, no direction reached
the 0.55 single-pass bar (Binance 0.477 / 0.523; Hyperliquid 0.511 /
0.489). **This is the cleanest, best-powered funding rejection to date:**
the locked p75/n_folds=3 configuration gave per-fold signalled counts of
126/130/98 (Binance) and 140/186/124 (Hyperliquid), so walk-forward
failed on **hit-rate merit per fold** (fold hit rates 0.44–0.56) rather
than the CAMP-03 sample-floor artifact — the feasibility fix worked as
designed. Regime coverage was materially more balanced than prior
campaigns (Binance ~58% bull vs. 75–94% before), so regime stratification
failed by even, edgeless spread rather than single-regime concentration.

**Lessons learned:**
- **Differencing converts a low-information feature into a
  high-information one** — funding *persistence* (a within-run ramp)
  carried N_eff ≈ 4–18; its first difference (*delta*) carried
  N_eff ≈ 247–526. Duration/state features are intrinsically
  low-density per sample; change features are high-density. (Durable,
  generalizes beyond funding.)
- **The outcome-blind feasibility gate demonstrably prevented an
  underpowered campaign** (persistence) *and* correctly configured a
  powered one (delta's p75/n_folds=3) — the first time feasibility both
  killed one hypothesis pre-registration and calibrated another's
  validation config.
- **Two distinct viability gates exist:** *intrinsic* (N_eff — unfixable
  if the feature auto-correlates by construction) vs. *configurable*
  (per-fold signalled count — tunable via threshold percentile). Both
  must be checked outcome-blind.
- Funding *level*, *venue-relative*, and *delta* are now all rejected;
  *persistence* is deferred (non-viable on this window). The funding
  family's readily-testable mechanisms are nearly exhausted.

**Next suggested direction:** the funding family is near exhaustion on
this data; per the research operating model, advance to the next family.
Open Interest velocity is testable but production-capped (no Hyperliquid
OI history); the highest-value diverse candidate is a **Liquidations
feasibility spike** (verify whether Hyperliquid exposes historical
liquidation data) before committing any new-family build.

---

## CAMP-05 — Open Interest Velocity

**Status: CLOSED — both hypotheses REJECTED on merit; the cleanest,
best-powered rejection in the program to date.**

| Field | Value |
|---|---|
| ID | CAMP-05 |
| Information source | Open Interest — Velocity mechanism (24h fractional change, not level) |
| Full detail | `docs/RESEARCH_CAMPAIGN_05_oi_velocity.md` |
| Experiments | 2 (contrarian, momentum), Binance only — no Hyperliquid OI history exists |
| Registry files | `data/alpha_engine_research/campaign_05_binance_{BTC,ETH,SOL,combined}.jsonl` |

**Hypothesis:** an extreme 24h *fractional change* in Open Interest
(`oi_velocity` — build-up / unwind velocity, distinct from the rejected
OI *level* of CAMP-01) predicts a 24h forward return, tested contrarian
and momentum.

**Governance ceiling (structural):** Open Interest has no Hyperliquid
historical source, so the DEX-first venue-replication check
(`RESEARCH_PLAYBOOK.md` §5) can never be satisfied — this campaign could
only ever reach **REJECT or DEFER, never APPROVE**. The harness
constructs only those two decisions; APPROVE was unreachable by
construction.

**Mandatory feasibility review:** PASSED on every axis, more cleanly than
any prior feature — near-independence from OI level (Pearson 0.08–0.12,
Spearman 0.05–0.13), daily lag-1 autocorrelation −0.003 to 0.125
(**N_eff ≈ 405–523**), sign-symmetric, stationary (the fractional
transform removed OI's non-stationarity), continuous threshold (zero
ties). Locked **p75 = 0.037901**, **n_folds = 3** (per-fold projection
[169, 113, 108]).

**Locked data-validity rule:** investigation of the \|velocity\| ≈ 1.0
outliers showed every one is a single **OI = 0.0** archive snapshot
surrounded by normal values — an impossible value (missing-data
artifact), not a genuine event, rollover, or methodology change. Rule
(permanent): construct a sample only if **both endpoint OI values are
strictly > 0**, else skip. Fired exactly 5 times in execution.

**Dataset:** BTC/ETH/SOL, Binance OI + mark price, 2023-07-01 →
2024-12-31 (already collected). 1,555 pooled non-overlapping daily
samples from 1,560 grid points; 390 signalled at the locked threshold.

**Evidence:** two sealed, fingerprinted packages — contrarian
`ccc56cd026521f56…`, momentum `6fbce5305a663a32…`. Causality audit passed
for both.

**Governance decision:** REJECT recorded for both (reviewer ≠ researcher,
evidence-fingerprint verified); lifecycle state `REJECTED`.

**Final verdict:** **Both REJECTED.** Neither direction reached the 0.55
bar (contrarian 0.5154, momentum 0.4846). **Walk-forward failed on
hit-rate merit with every fold fully powered** — per-fold signalled
[169, 113, 108] reproduced the feasibility projection exactly, all ≥100,
with no fold reaching 0.55 in either direction. Bootstrap cleared the bar
in only 7.9% (contrarian) / 0.9% (momentum) of resamples. Regime
stratification failed by **even, edgeless spread** across bull (224),
chop (95), and bear (71) — not by single-regime concentration. BTC
contrarian cleared single-pass in isolation (0.5556, n=108) but is an
underpowered per-symbol diagnostic, not the pre-registered analysis, and
was not acted on.

**Lessons learned:**
- **A feature can be statistically excellent and still carry no edge.**
  OI Velocity passed feasibility more cleanly than any prior feature and
  still produced a flat rejection — feasibility quality predicts
  *testability*, never *profitability*.
- **Fractional change is the correct normalization for a non-stationary
  level series** — it removed OI's ~3.4× secular drift (CAMP-01),
  generalizing that campaign's normalization lesson.
- **Filter impossible values on data validity, not on outlier
  magnitude** — the OI>0 rule removed exactly 5 corrupt snapshots while
  retaining every genuine move (max \|velocity\| 0.2405).
- **The feasibility discipline is now fully effective**: the locked
  per-fold projection was reproduced exactly in execution, so
  walk-forward failed on merit rather than the structural sample-floor
  artifact that confounded CAMP-02/03.
- **Regime-balanced failure is a stronger negative result** than
  CAMP-02's concentrated failure — it cannot be attributed to one market
  condition.

**Next suggested direction:** OI *level* and *velocity* are both
rejected; **Divergence** is the sole untested OI mechanism, under the
same standing DEFER-ceiling. The OI family's remaining value is
knowledge-only until a live OI recorder lifts that ceiling.

---

*(Future campaigns are appended below this line, in run order. Do not
edit or remove a prior entry once recorded.)*
