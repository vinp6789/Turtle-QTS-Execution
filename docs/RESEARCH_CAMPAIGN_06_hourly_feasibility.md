# Campaign 06 — Hourly Feasibility Screen (Backlog 3.5, RD-16 §E)

**Verdict: APPROVE FOR PRE-REGISTRATION**, scoped to `p75` at
`n_folds` 3 or 5, on a Hyperliquid-native window — with one
**time-sensitive collection prerequisite** (§5).

- **Date:** 2026-08-05 · **Author:** researcher · **Reviewer:** pending
- **Runtime:** 21.1s. Outcome-blind: reads only the liquidation event
  series; no price series opened, no return computed.

## 0. What this review was for

RD-16 deferred Campaign 06 at daily resolution and named exactly one
live alternative, with a stated expectation:

> *"a finer-grained (e.g. hourly) specification could multiply raw counts
> ~24× — but hourly data carries **materially higher serial
> autocorrelation** and possibly different cross-symbol dependence, both
> of which attack N_eff directly. It would need its own feasibility
> review first."*

**That expectation is refuted by measurement.**

## 1. Pre-flight — 8/8 PASS

8,784 hourly slots (366 days × 24), contiguous, 2025-07-27 excluded per
RD-15. RD-14 extended from days to hours — licensed by the whole-window
coverage audit, which confirmed 24/24 hourly objects on every remaining
day, so an absent `(symbol, hour)` is a verified zero:

| Symbol | Zero-event hours materialized | Total events |
|---|---|---|
| BTC | 4,531 (51.6%) | 1,246,230 |
| ETH | 5,212 (59.3%) | 512,194 |
| SOL | 5,313 (60.5%) | 379,408 |

## 2. The decisive measurement — serial dependence

| Symbol | hourly lag-1 ρ | N_eff (serial) |
|---|---|---|
| BTC | **+0.2230** | 5,580 of 8,784 |
| ETH | **+0.2056** | 5,788 of 8,784 |
| SOL | **+0.1845** | 6,048 of 8,784 |

**Hourly serial autocorrelation is LOW — ~65% of samples survive as
effective.** RD-16 §E expected the opposite.

The reason is structural and worth recording: liquidations are **bursty
events**, not a slowly-varying state. Contrast RD-04's Funding
Persistence (ρ ≈ 0.98), which was a *state* variable — elapsed time since
a sign flip — where consecutive observations are near-duplicates. Event
counts in adjacent hours are largely independent. **The 24× raw gain
therefore survives, discounted only ×0.65.**

## 3. Cross-symbol dependence (RD-13 §C)

| Window | BTC–ETH | BTC–SOL | ETH–SOL | ρ̄ | N_eff |
|---|---|---|---|---|---|
| Full 366d, hourly | +0.795 | +0.783 | +0.871 | **+0.817** | **1.14** of 3 |
| *RD-16, daily* | *+0.758* | *+0.799* | *+0.898* | *+0.818* | *1.14* |

**Essentially scale-invariant** — sampling finer does not decorrelate the
symbols. Pooling still buys ~1.14 symbols' worth of information, not 3.

## 4. Per-fold signalled samples vs the floor of 100

Effective counts apply **both** haircuts: cross-symbol (×0.380) and
serial (×0.65).

**Full 366-day window** (requires a cross-venue outcome — see §5):

| Threshold | folds | worst fold | eff (cross) | eff (both) | |
|---|---|---|---|---|---|
| p75 | 3 | 1,802 | 684 | **452** | **CLEARS 4.5×** |
| p75 | 5 | 1,051 | 399 | **264** | **CLEARS** |
| p90 | 3 | 654 | 248 | **164** | **CLEARS** |
| p90 | 5 | 361 | 137 | 91 | fails |
| p99 | 3/5 | 51/12 | 19/5 | 13/3 | fails |

Bootstrap (moving-block b=24h, n=1000, seed=7): P(raw ≥ 100) = **1.00**
for p75 and p90 at both fold counts.

## 5. The binding constraint — and it is time-sensitive

**No Hyperliquid-native hourly outcome series exists.** Measured:

- `mark_price__*__hyperliquid.csv` is **1 row/day** (daily candles).
- `mark_price__*__binance.csv` is 288 rows/day (5-min) — but Binance,
  which under Constitution §6 makes any finding a research hypothesis
  only, never promotion-eligible.

Probing the venue directly for `candleSnapshot interval="1h"`:

| Start | Candles returned |
|---|---|
| −2d, −30d, −90d, −180d | present |
| **−213d, −225d, −240d, −300d, −374d** | **0** |

**Hyperliquid retains 1h candles for only ~210 days** (binary-searched
boundary: 2026-01-07). Daily candles reach back to 2025-07-27; hourly do
not.

**Feasibility restricted to the DEX-native-viable window** (2026-01-07 →
2026-07-28, 4,872 hours, 203 days):

| Threshold | folds | worst fold | eff (both) | |
|---|---|---|---|---|
| **p75** | **3** | 977 | **260** | **CLEARS 2.6×** |
| **p75** | **5** | 567 | **151** | **CLEARS** |
| p90 | 3 | 336 | 89 | fails (marginal) |
| p90 | 5 | 199 | 53 | fails |
| p99 | 3/5 | 24/11 | 6/3 | fails |

(ρ̄ = +0.731 → N_eff 1.22; serial retention ×0.655 — both consistent with
the full window.)

**⚠ The 1h candle history is ephemeral. Every day that passes, one more
day ages out of the venue's ~210-day retention.** If the hourly outcome
series is wanted, it must be collected **now**, not when Campaign 08 is
written.

## 6. Verdict

> **APPROVE FOR PRE-REGISTRATION** — scoped to **p75**, `n_folds` 3 or 5,
> BTC/ETH/SOL pooled, on the Hyperliquid-native window.
>
> **Excluded on measurement:** p90 (89 effective on the DEX-native
> window — marginal fail), p99 (6), and any cross-venue-outcome variant
> as a *promotable* result.

This reverses RD-16's daily deferral **for the hourly specification
only**. The daily specification remains deferred exactly as RD-16 states;
nothing here revives it.

**Prerequisite before pre-registration (time-sensitive):** collect
Hyperliquid 1h candles for BTC/ETH/SOL over 2026-01-07 → present, using
the existing `fetch_daily_candles` pattern with `interval="1h"`.

**Standing mitigation already in place:** the Live Recorder deployed in
Backlog 3.4 (RD-18) captures Hyperliquid mark price hourly from
2026-08-05 forward. From today the DEX-native window **grows on its own**
and the 210-day retention limit stops applying to new data. The
recorder's deployment and this finding are directly connected — the
recorder is what prevents this constraint recurring.

## 7. Limitations

- `N_eff = N(1−ρ₁)/(1+ρ₁)` is a first-order AR(1) approximation, used
  because it is the exact form RD-04 and RD-16 used — the comparison is
  like-for-like, not exact.
- Applying the cross-symbol and serial haircuts multiplicatively is an
  approximation. It is **conservative**: the verdict rests on the
  double-discounted figure, and p75 clears even so.
- The 210-day boundary was binary-searched on BTC only; ETH/SOL retention
  is assumed identical and should be confirmed at collection time.
- Hourly liquidation counts are heavily zero-inflated (52–61% zero
  hours). A count-based threshold on such a distribution is legitimate
  but should be declared as a `known_limitation` under RD-11 A.

---

**Artifacts:** `research/campaign_06_liquidations/hourly_feasibility.py` ·
`data/alpha_engine_research/campaign_06_feasibility/hourly_feasibility_statistics.json`
