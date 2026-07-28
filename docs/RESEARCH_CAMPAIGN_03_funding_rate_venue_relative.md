# Research Campaign 03 — Funding Rate, Venue-Relative Threshold

**Status: CLOSED — all four experiments REJECTED on merit (clean
hit-rate failure, not a sample-floor artifact, on the venue where the
floor was fully cleared).**

Follows Campaign 02 (`docs/RESEARCH_CAMPAIGN_02_funding_rate.md`, permanently
closed, REJECTED — not revisited). Genuinely different operationalization
of the same hypothesis family: Campaign 02 derived one absolute threshold
from Binance's own distribution and applied it unchanged to Hyperliquid;
its own Production Venue Validation showed this does not transfer
(Hyperliquid funding ~3–8× smaller in typical magnitude). Campaign 03
tests the same directional hypotheses (contrarian, momentum) with an
**independent threshold per venue**, derived from that venue's own
historical distribution — the permanent methodology rule adopted after
Campaign 02's review (`PROJECT_CONSTITUTION.md` §6, `RESEARCH_PLAYBOOK.md`
§2).

## 0. Existing infrastructure reused (unchanged)

`alpha_engine.validation` (all five stages), `alpha_engine.governance`,
`alpha_engine.registry`, `alpha_engine.research.run_research_cycle`,
`alpha_engine.candidates.funding_rate_threshold_rule`,
`alpha_engine.historical` (both venues' funding + Binance mark price,
already collected in Campaign 02 — no re-collection needed),
`research.campaign_02_funding_rate.build_samples` (PIT construction,
imported unchanged), `research.campaign_02_funding_rate.
explore_distribution` (imported unchanged). Genuinely new: threshold
derivation per venue and a run_campaign module parameterized by
per-source threshold (`research/campaign_03_funding_rate_venue_relative/`).

## 1. Mandatory pre-registration feasibility review (outcome-blind)

Performed via `research/campaign_03_funding_rate_venue_relative/
feasibility_review.py` — counts signaled samples per candidate threshold
and fold count; never touches hit rate or realized return.

| Percentile | Binance threshold | Binance signaled (n=1458) | Hyperliquid threshold | Hyperliquid signaled (n=1647) |
|---|---|---|---|---|
| p90 (Campaign 02's choice) | 0.000236550 | 141 (9.7%) | 0.00007547910 | 216 (13.1%) |
| **p75 (this campaign's choice)** | **0.0001000000** | **861 (59.1%)** | **0.000038592350** | **461 (28.0%)** |

**Finding: p90 is structurally infeasible for `n_folds=5` (or even 3) on
either venue** — average per-fold signaled count (28.2 Binance, 43.2
Hyperliquid at n_folds=5) falls below `min_signaled_samples=100`
regardless of any true edge, replicating exactly the mechanism Campaign
02 flagged.

**p75 at `n_folds=3` clears the floor on both venues** (287.0/fold
Binance, 153.7/fold Hyperliquid) — the configuration locked below.
`n_folds=5` was checked and rejected for `p75` on Hyperliquid specifically
(92.2/fold, just below the floor); `n_folds=3` is used for both venues for
comparability, not tuned per-venue.

**Regime coverage (signaled samples, informational):** bull-concentrated
on both venues (Binance 583/861 = 67.7%; Hyperliquid 349/461 = 75.7%) —
less extreme than Campaign 02's 93.6%, but the same known, expected
concentration risk, declared here in advance.

**Bootstrap stability:** signaled counts (861, 461) are 3–6× larger than
Campaign 02's Binance screen (141) — ample for a 1,000-resample bootstrap
to be informative.

**This adjustment (percentile 90th→75th, `n_folds` 5→3) was made entirely
from the feasibility review above — zero outcome data (price, return, hit
rate) was examined before this decision.** Per `RESEARCH_PLAYBOOK.md` §2,
this is a legitimate pre-registration-stage reconsideration of validation
configuration, not a post-hoc tuning of a locked parameter.

## 2. Pre-registration (LOCKED)

| Field | Value |
|---|---|
| Experiment IDs | `camp03-{binance,hyperliquid}-{BTC,ETH,SOL,combined}-{contrarian,momentum}` |
| Candidate family | `funding_rate_threshold_rule` (existing, unchanged) |
| Threshold methodology | Pooled 75th percentile of \|funding rate\|, derived **independently per venue** from that venue's own full-window historical distribution — outcome-blind |
| Threshold value — Binance | **0.0001000000** |
| Threshold value — Hyperliquid | **0.000038592350** |
| Universe | BTC, ETH, SOL |
| Holding horizon | 24 hours (same as Campaigns 01–02 — comparability) |
| Sample spacing | 24 hours, non-overlapping |
| Cadence | 86,400 seconds |
| `min_hit_rate` | 0.55 (same standard as Campaigns 01–02) |
| `min_signaled_samples` | 100 (same standard; now verified achievable per-fold, see §1) |
| Walk-forward | **`n_folds=3`** (reduced from 5 — locked from the feasibility review, §1, before any outcome was seen) |
| Bootstrap | `n_resamples=1000`, `seed=7` (same as Campaigns 01–02) |
| Regime stratification | BTC bull/bear/chop, price-derived (same labeler, reused unchanged) |

**Rejection criteria** (any one rejects, checked independently per venue):
single-pass hit rate < 0.55 or signaled samples < 100; causality audit
reports any duplicate, ordering violation, or non-verifiable sample;
walk-forward clears in aggregate but fails in the majority of the 3
folds; bootstrap hit-rate distribution straddles 0.50 inconsistent with
the pre-registered bar; the edge is concentrated in a single regime only;
mean directional return ≤ 0 despite a nominally-passing hit rate.

**No parameter above may be adjusted after any result is observed —
Binance and Hyperliquid are each scored against their own locked
threshold and are independent tests of the same directional hypotheses,
not a screen-then-replicate pair with one shared number** (that
dependency was Campaign 02's design; venue-relative thresholds make each
venue's result self-contained). A venue's result is not retried or
retuned if it disappoints.

## 3. Expected failure modes (stated in advance)

- **Most likely outcome: no edge**, consistent with Campaigns 01–02's
  precedent.
- **Regime concentration** (§1) — expected, declared, not a discovered
  flaw if it recurs.
- **A lower percentile (75th vs. 90th) is a less extreme cut** — a
  genuinely different (milder) operationalization of "extreme funding"
  than Campaign 02 tested, not a weaker test of the same one. Any result
  here answers a related but distinct question from Campaign 02's.
- **Sign-asymmetry** (funding is positive-skewed on both venues, per the
  distribution study) — same structural caveat as Campaign 02.
- **Cross-venue comparability**: because each venue now uses its own
  threshold value, a "Binance passes, Hyperliquid fails" (or vice versa)
  outcome is informative about the *hypothesis's* venue-transferability
  under correct operationalization — not conflatable with Campaign 02's
  threshold-transfer failure, which is now controlled for.

---

## 4. Machinery validation (2-month in-memory slice, 2023-07..2023-09)

Verified before full-depth execution: PIT sample construction correct for
both venues (162 Binance / 180 Hyperliquid samples, correct skip
diagnostics), causality audit passed for both, evidence sealing worked
(fingerprints generated), and the small-slice results were correctly
insufficient (8–31 signaled) — the same pattern Campaigns 01–02 showed at
their own 2-month checks. Machinery confirmed sound; proceeded to full
18-month execution with zero changes to the locked specification.

## 5. Dataset (full execution)

BTC/ETH/SOL, both venues' funding history (2023-07-01 → 2024-12-31,
already collected during Campaign 02 — no re-collection needed) + the
existing Campaign-01 Binance mark-price series (same window) for
outcomes. Pooled non-overlapping daily samples: **1,458 (Binance)**,
**1,647 (Hyperliquid** — no `skip_no_funding`, since Hyperliquid's history
starts at the series' own first day).

**A methodological note discovered during execution, not tunable
retroactively:** the real candidate (`FundingRateThresholdRuleCandidate.
evaluate`) signals on a **strict** `rate > threshold` / `rate < -threshold`
comparison — not `>=`. Because the locked Binance threshold
(0.0001000000) equals a very common capped/default funding value in the
raw series, the actual combined signaled count (280) came in well below
the §1 feasibility review's `>=`-based proxy estimate (861). Hyperliquid's
real count (461) matched its own proxy estimate closely, since its
distribution has no equivalent clamped value at that percentile. This
is recorded as a limitation of the feasibility-review proxy's precision,
not a defect in the locked threshold or the candidate: the threshold
itself was still derived correctly (outcome-blind, from each venue's own
distribution) and the real evaluate function — unchanged since Campaign
02 — was applied exactly as pre-registered.

## 6. Results

### 6.1 Combined universe (pre-registered, powered analysis)

| Venue | Experiment | Signalled | Hit rate | Walk-forward | Regime | Verdict |
|---|---|---|---|---|---|---|
| Binance | contrarian | 280 | 0.475 | FAIL | FAIL | **REJECTED** |
| Binance | momentum | 280 | 0.525 | FAIL | FAIL | **REJECTED** |
| Hyperliquid | contrarian | 461 | 0.469 | FAIL | FAIL | **REJECTED** |
| Hyperliquid | momentum | 461 | 0.531 | FAIL | FAIL | **REJECTED** |

Neither venue's momentum hit rate reaches the pre-registered 0.55 bar
(Binance 0.525, Hyperliquid 0.531) — both fail single-pass outright,
unlike Campaign 02's Binance momentum (which cleared single-pass at
0.560 before failing downstream stages).

### 6.2 Walk-forward — why it failed, traced per fold

**Hyperliquid (combined):** every fold cleared `min_signaled_samples`
(160, 198, 103 — all ≥100). Walk-forward failed on **hit rate alone**, in
every fold, both directions (contrarian 0.460–0.495; momentum
0.505–0.540) — never once reaching 0.55. This is a clean, well-powered
rejection, not a structural artifact.

**Binance (combined):** signals cluster unevenly across the three
chronological folds (64, 171, 45 signalled) — two of three folds fall
below the 100-sample floor despite `n_folds=3` (reduced from Campaign
02's default 5 specifically to fix this). **This is a residual,
smaller-scale recurrence of Campaign 02's structural finding**: reducing
fold count fixes the *average* per-fold count but not *uneven temporal
clustering* of signals across folds. Recorded as a lesson (§9) for a
future campaign's fold-construction design — not patched retroactively
here.

### 6.3 Regime stratification

Signal concentration recurs on both venues, though less extreme than
Campaign 02's 93.6%: Binance 243/280 (86.8%) bull, Hyperliquid 349/461
(75.7%) bull. Critically, **momentum's hit rate does not clear 0.55 even
within the bull regime alone** on either venue (Binance 0.539, Hyperliquid
0.544) — a materially different, broader "no edge" finding than Campaign
02, where the bull-regime hit rate (0.568) *did* clear the bar on its own
and the story was purely regime-concentration. Here there is no regime
in which either direction clears the bar.

### 6.4 Verdict

**Both directions, both venues: REJECTED.** The rejection is honest and
well-evidenced on Hyperliquid (clean hit-rate failure, floor cleared
every fold) and directionally consistent, though partly floor-limited,
on Binance. No result approached promotion-eligibility on either venue.

## 7. Evidence fingerprints

| Experiment | Fingerprint |
|---|---|
| Binance contrarian (combined) | `c745f1d63a08cf46ef476dd260f9cc3bf17af647f596661bfb2c0640a2f0f07a` |
| Binance momentum (combined) | `6b14ecab8f6d29f372245d8c767f936e42de6736a30791c52867063c52169231` |
| Hyperliquid contrarian (combined) | `88cfa48376514920d7a9525bcb82a145bbc55fb5dc0eaa7492aad1648f1b7712` |
| Hyperliquid momentum (combined) | `40209b99fe7fc8ed84f75c622715f56b82b1cef1a02b4a24316e18454ecccd7a` |

Causality audit passed for all four; all four sealed and durably recorded.

## 8. Governance decisions

REJECT recorded for all four (`proposed_by="researcher-campaign03"`,
`reviewed_by="reviewer-campaign03"`, evidence-fingerprint verified) —
durable lifecycle state `REJECTED` for all four experiment records.

## 9. Lessons learned

1. **Venue-relative thresholds do resolve the specific Campaign 02
   finding they were designed to address** — each venue's own threshold
   produced a well-powered sample on that venue (Hyperliquid especially:
   every walk-forward fold cleared the floor cleanly). But the underlying
   hypothesis still shows no edge once correctly operationalized per
   venue — this is a genuine hypothesis rejection, not another
   operationalization failure.
2. **Reducing `n_folds` fixes average per-fold sample count but not
   temporal clustering.** Binance's signals concentrate unevenly across
   chronological thirds of the sample; a future campaign's feasibility
   review should check per-fold counts under the actual chronological
   split, not just the arithmetic average, before locking `n_folds`.
3. **A feasibility-review proxy that doesn't match the real candidate's
   comparison operator (`>` vs. `>=`) can materially misestimate signal
   count**, especially when the chosen percentile coincides with a
   common clamped/capped raw value. Future feasibility reviews should
   use the real candidate's `evaluate()` (with only the direction
   discarded, never the outcome) rather than a hand-written proxy
   comparison.
4. **A 75th-percentile threshold is not "too mild" to be genuinely
   tested** — despite signaling far more often than Campaign 02's 90th
   percentile, neither direction cleared 0.55 on either venue, in
   aggregate or within any single regime. The absence of edge is broader
   and cleaner than Campaign 02's, not merely diluted by a softer cut.
5. **No new platform code was required.** `alpha_engine/` was not
   touched; only campaign-specific harness code
   (`research/campaign_03_funding_rate_venue_relative/`) was added,
   confirming the platform remains sufficient for this class of
   methodology variation.

## 10. Recommendation for Campaign 04

Funding rate (level, either absolute or venue-relative threshold, either
direction) has now been tested twice on both venues with no edge found.
Per `docs/ROADMAP.md` §1, the next candidates are: (1) a dedicated,
properly-powered BTC-only Binance momentum follow-up (the strongest
single-symbol reading across all three funding experiments to date —
Campaign 02's BTC momentum at 0.686/n=35, and this campaign's Hyperliquid
BTC momentum at 0.580/n=138, both underpowered or sub-bar in isolation);
or (2) Open Interest velocity/change, a genuinely new (non-funding)
hypothesis family. A fresh pre-registration, including its own
feasibility review incorporating lesson #2 and #3 above, is required
before either begins.
