# ALPHA_LIBRARY.md

**The catalog of alpha models — approved, rejected, retired, experimental,
and future-candidate.** This is the intended long-term "what do we
currently trust, and why" reference (`PROJECT_CONSTITUTION.md` §1 item 5).

**Implementation note (honest, as of this writing):** there is no
dedicated "Alpha Library" software abstraction in the codebase — verified,
zero hits for any such class or module. What exists instead is the
durable Experiment Registry (`alpha_engine.registry`), queryable via
`list_experiments(state=...)` and `alpha_engine.governance.
approved_experiments()`, plus the candidate mechanism catalog
(`alpha_engine.candidates.CANDIDATE_CATALOG` — the available *rule
mechanisms*, not validated *models*). This document is, for now, the
curated human-readable view over that registry data; formalizing it into
a queryable library abstraction is `ROADMAP.md` §2 item 2 — deliberately
deferred until there are enough approved models to justify it.

---

## Approved

**None.** Zero models have cleared governance to date.

## Rejected

| Model | Family | Version | Evidence | Venue-validated | Ledger entry |
|---|---|---|---|---|---|
| Open Interest percentile-rank, contrarian | `open_interest_extremeness_rule` | pctrank-contrarian-v1 | fp `33569639aa91185f…` | Not applicable — no Hyperliquid historical OI source exists | CAMP-01 |
| Open Interest percentile-rank, momentum | `open_interest_extremeness_rule` | pctrank-momentum-v1 | fp `1b3d713954af4feb…` | Not applicable | CAMP-01 |
| Open Interest z-score, contrarian | `open_interest_extremeness_rule` | zscore-contrarian-v1 | fp `9489c0e973da9ae2…` | Not applicable | CAMP-01 |
| Open Interest z-score, momentum | `open_interest_extremeness_rule` | zscore-momentum-v1 | fp `fca4ffff3521967b…` | Not applicable | CAMP-01 |
| Funding Rate threshold, contrarian (Binance screen) | `funding_rate_threshold_rule` | contrarian-v1 | fp `02d0e0db30439934…` | No — rejected on Binance screen itself, replication moot | CAMP-02 |
| Funding Rate threshold, momentum (Binance screen) | `funding_rate_threshold_rule` | momentum-v1 | fp `1fd5d92a2fb9da51…` | No — cleared single-pass but rejected on walk-forward/regime; replication moot | CAMP-02 |
| Funding Rate threshold, contrarian (Hyperliquid PVV) | `funding_rate_threshold_rule` | contrarian-v1 | fp `051df9d90ed8e0d0…` | No — see note below | CAMP-02 |
| Funding Rate threshold, momentum (Hyperliquid PVV) | `funding_rate_threshold_rule` | momentum-v1 | fp `f99575814fb8e18a…` | No — see note below | CAMP-02 |
| Funding Rate threshold, contrarian (Binance, venue-relative) | `funding_rate_threshold_rule` | contrarian-binance-v1 | fp `c745f1d63a08cf46…` | Yes — tested independently on both venues, own threshold each | CAMP-03 |
| Funding Rate threshold, momentum (Binance, venue-relative) | `funding_rate_threshold_rule` | momentum-binance-v1 | fp `6b14ecab8f6d29f3…` | Yes | CAMP-03 |
| Funding Rate threshold, contrarian (Hyperliquid, venue-relative) | `funding_rate_threshold_rule` | contrarian-hyperliquid-v1 | fp `88cfa48376514920…` | Yes | CAMP-03 |
| Funding Rate threshold, momentum (Hyperliquid, venue-relative) | `funding_rate_threshold_rule` | momentum-hyperliquid-v1 | fp `40209b99fe7fc8ed…` | Yes | CAMP-03 |
| Funding Delta, contrarian (Binance) | `funding_rate_threshold_rule` (feature `funding_delta`) | contrarian-binance-v1 | fp `14ab0f05b1da9760…` | Yes | CAMP-04 |
| Funding Delta, momentum (Binance) | `funding_rate_threshold_rule` (feature `funding_delta`) | momentum-binance-v1 | fp `25bc38e0cbe7e86f…` | Yes | CAMP-04 |
| Funding Delta, contrarian (Hyperliquid) | `funding_rate_threshold_rule` (feature `funding_delta`) | contrarian-hyperliquid-v1 | fp `4182edebb7888432…` | Yes | CAMP-04 |
| Funding Delta, momentum (Hyperliquid) | `funding_rate_threshold_rule` (feature `funding_delta`) | momentum-hyperliquid-v1 | fp `c237e53ff9972534…` | Yes | CAMP-04 |
| OI Velocity, contrarian (Binance) | `funding_rate_threshold_rule` (feature `oi_velocity`) | contrarian-binance-v1 | fp `ccc56cd026521f56…` | Not applicable — no Hyperliquid historical OI source exists (DEFER-ceiling) | CAMP-05 |
| OI Velocity, momentum (Binance) | `funding_rate_threshold_rule` (feature `oi_velocity`) | momentum-binance-v1 | fp `6fbce5305a663a32…` | Not applicable — same structural blocker | CAMP-05 |
| OI extremeness 72h horizon, contrarian | `open_interest_extremeness_rule` | h72-t040-contrarian-v1 | see `data/alpha_engine_research/campaign_07.jsonl` | Not applicable — no Hyperliquid historical OI source exists (DEFER-ceiling) | CAMP-07 |
| OI extremeness 72h horizon, momentum | `open_interest_extremeness_rule` | h72-t040-momentum-v1 | see `data/alpha_engine_research/campaign_07.jsonl` | Not applicable — no Hyperliquid historical OI source exists (DEFER-ceiling) | CAMP-07 |
| OI extremeness 72h horizon, contrarian | `open_interest_extremeness_rule` | h72-t025-contrarian-v1 | see `data/alpha_engine_research/campaign_07.jsonl` | Not applicable — no Hyperliquid historical OI source exists (DEFER-ceiling) | CAMP-07 |
| OI extremeness 72h horizon, momentum | `open_interest_extremeness_rule` | h72-t025-momentum-v1 | see `data/alpha_engine_research/campaign_07.jsonl` | Not applicable — no Hyperliquid historical OI source exists (DEFER-ceiling) | CAMP-07 |
| OI extremeness 120h horizon, contrarian | `open_interest_extremeness_rule` | h120-t040-contrarian-v1 | see `data/alpha_engine_research/campaign_07.jsonl` | Not applicable — no Hyperliquid historical OI source exists (DEFER-ceiling) | CAMP-07 |
| OI extremeness 120h horizon, momentum | `open_interest_extremeness_rule` | h120-t040-momentum-v1 | see `data/alpha_engine_research/campaign_07.jsonl` | Not applicable — no Hyperliquid historical OI source exists (DEFER-ceiling) | CAMP-07 |

CAMP-01 (all four): hit rate 0.49–0.51 (indistinguishable from chance),
causality audit passed (not a leakage artifact), sample floor cleared
(not a data-shortfall artifact).

CAMP-02: Binance-screen contrarian showed no edge; Binance-screen
momentum cleared single-pass (hit rate 0.560, 141 signalled) but failed
walk-forward and regime stratification (93.6% of signal concentrated in
one market regime) — REJECTED overall. The Hyperliquid Production Venue
Validation rows are **not a "venue-validated: yes"** despite being
executed on Hyperliquid data — the identical locked threshold produced
only 9 pooled signalled samples there (vs. 141 on Binance), because
Hyperliquid's funding rate runs ~3–8× smaller in typical magnitude than
Binance's for the same assets/period. This is a confirmed operationalization
failure (the threshold, not necessarily the hypothesis), and is
insufficient to validate *or* refute transferability — recorded as such,
not glossed over.

CAMP-03: same hypothesis family as CAMP-02, re-operationalized with an
independent, per-venue threshold (75th percentile of |funding|, derived
from each venue's own distribution) — removing the absolute-threshold
confound CAMP-02 found. Both directions, both venues, REJECTED: neither
venue's momentum hit rate reached 0.55 (Binance 0.525, Hyperliquid
0.531). Hyperliquid's rejection is clean and well-powered (every
walk-forward fold cleared the sample floor, failed purely on hit rate);
Binance's walk-forward failure is partly a residual, smaller-scale
recurrence of CAMP-02's structural fold-floor issue (signals cluster
unevenly across folds). This is the first funding-rate finding marked
**venue-validated: yes** — not because either result was promising, but
because each venue was independently and correctly tested under its own
threshold, resolving the specific transferability question CAMP-02 left
open.

CAMP-05 (OI Velocity): both directions REJECTED on the Binance screen
(contrarian 0.5154, momentum 0.4846 — neither reached the 0.55 bar).
Notable as the **best-powered rejection to date**: every walk-forward
fold cleared the sample floor ([169, 113, 108]), so the failure is on
hit-rate merit rather than sample starvation, and regime stratification
failed by even spread across bull/chop/bear rather than by concentration.
Venue-validated is **"not applicable"**, not "no": Open Interest has no
Hyperliquid historical source, so the DEX-first replication check can
never be satisfied — the campaign carried a structural **DEFER-ceiling**
(REJECT or DEFER only, APPROVE unreachable by construction).

Full detail: `docs/RESEARCH_LEDGER.md` (CAMP-01 … CAMP-05),
`docs/RESEARCH_CAMPAIGN_01_open_interest.md`,
`docs/RESEARCH_CAMPAIGN_02_funding_rate.md`,
`docs/RESEARCH_CAMPAIGN_03_funding_rate_venue_relative.md`,
`docs/RESEARCH_CAMPAIGN_04_funding_delta.md`,
`docs/RESEARCH_CAMPAIGN_05_oi_velocity.md`.

## Retired

**None.** No model has ever reached live trading, so none has ever been
retired.

## Experimental / awaiting research

**None currently in flight.** No campaign is registered as of this
writing (see `PROJECT_STATUS.md` "Current campaign").

## Future candidates (queued, per `ROADMAP.md` §1 and CAMP-02's own recommendation)

| Candidate family | Mechanism exists today? | Priority |
|---|---|---|
| BTC-only Funding momentum, properly powered (Binance deep history, 2020+) | Same candidate/feature; needs a longer BTC-only backfill | Next — strongest single-symbol signal across CAMP-02/03 (0.686/n=35 Binance, 0.580/n=138 Hyperliquid), both underpowered or sub-bar in isolation |
| Open Interest velocity/change | No — needs a new rolling-delta feature | After the above |
| Longer-horizon OI (3–7 day) | Partially — reuses the existing extremeness feature, needs a new horizon parameter and fresh pre-registration | After the above |
| Combined OI + Funding | No — needs a multi-feature candidate type | After both components have independent evidence |
| Stablecoin flows / on-chain / macro / cross-asset | No — zero provider/feature/candidate code for any of these | Lower priority, per `docs/RESEARCH_PLAN.md` §3 |

## Candidate mechanism families available (not the same as "approved
models" — see note above)

From `alpha_engine.candidates.CANDIDATE_CATALOG` (verified against source):

- `funding_rate_threshold_rule` — signed threshold rule over raw funding
  rate (naturally stationary; no *rolling* normalization needed). **CAMP-02
  finding: an absolute threshold value IS venue-specific** — Hyperliquid's
  funding runs ~3–8× smaller in magnitude than Binance's for the same
  assets/period, so a threshold calibrated on one venue does not transfer
  to the other. A venue-relative (per-venue percentile) threshold is
  recommended for any future use of this family across venues.
- `open_interest_threshold_rule` — fixed absolute threshold over raw Open
  Interest. **Known-invalid for "extreme" claims** — Campaign 01 proved
  raw OI is too non-stationary for a fixed threshold to mean anything;
  retained only because it was the first (proof-of-pattern) OI candidate,
  superseded by `open_interest_extremeness_rule` for any real OI
  research.
- `open_interest_extremeness_rule` — the two-sided, rolling-normalized
  (percentile-rank or z-score) rule Campaign 01 actually used. The four
  rejected entries above are instances of this family.

## Fields tracked per entry (for future additions)

Version · Evidence (fingerprint + link to ledger entry) · Current health
(for anything ever approved: does it still clear its own pre-registered
bar against recent samples — see `alpha_engine.lifecycle.
assess_degradation`) · Dependencies (which data source(s)/feature(s) it
requires) · Family (which `CANDIDATE_CATALOG` mechanism it uses) ·
**Venue-validated** (DEX-first gate, `docs/PROJECT_CONSTITUTION.md` §6 /
`docs/HISTORICAL_DATA.md` §0: has this finding been replicated on
Hyperliquid's own historical data with the identical locked
specification? "Yes" / "No — CEX-only, not promotion-eligible" / "Not
applicable — no Hyperliquid historical source exists for this metric").

---

*Update this document every time a governance decision is recorded
(APPROVE, REJECT, or a later DEFER/RETIRE). Never delete a rejected or
retired entry — move it between sections if its state changes (e.g.
approved → retired), but the historical fact that it was once approved
must remain visible.*
