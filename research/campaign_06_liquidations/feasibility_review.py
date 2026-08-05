"""Backlog 1.6 — outcome-blind FEASIBILITY REVIEW for Campaign 06.

STRICTLY OUTCOME-BLIND. This script reads ONLY the liquidation event
series. It never opens the mark-price / outcome series, never computes a
return, never evaluates profitability, and never tunes a threshold
against a result. It answers one question, mandated by
PROJECT_CONSTITUTION.md Section 6 and RESEARCH_DECISIONS.md RD-13:

    Is a 12-month liquidation campaign STATISTICALLY TESTABLE at all,
    given this window, this validation methodology, and the measured
    cross-symbol dependence?

Governing rules applied (not re-derived here):
  - RD-14: within the collected window, an absent (symbol, day) row is a
    VERIFIED ZERO-EVENT day -> materialized as count = 0, never dropped.
  - RD-15: 2025-07-27 carries only 16/24 archive hours -> EXCLUDED
    (RD-15 Section D option 1, the recommended assumption-free default).
    RD-14 is deliberately NOT applied to that day.
  - Constitution Section 6: thresholds are venue-relative, derived from
    the venue's own distribution. Only Hyperliquid data is used.
  - RD-13 Section C: the review MUST report effective sample size
    (N_eff) and cross-symbol correlation, not raw pooled counts alone.

Acceptance bar being tested against (NOT weakened here):
  - min_signaled_samples = 100, applied PER FOLD (Campaigns 01/02/03).
  - n_folds = 5 standard; n_folds = 3 is a precedented outcome-blind
    fallback (Campaign 03 checked and documented exactly this).

Run: python -m research.campaign_06_liquidations.feasibility_review
"""

import csv
import json
import math
import random
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

_STORAGE_ROOT = Path("data/alpha_engine_historical")
_OUT_DIR = Path("data/alpha_engine_research/campaign_06_feasibility")
_SYMBOLS = ("BTC", "ETH", "SOL")

# Collected window (Backlog 1.5, audited complete).
_COLLECTED_START = date(2025, 7, 27)
_COLLECTED_END = date(2026, 7, 28)
# RD-15: the archive's first day is structurally partial (16/24 hours).
_RD15_EXCLUDED_DAY = date(2025, 7, 27)
_ANALYSIS_START = date(2025, 7, 28)
_ANALYSIS_END = _COLLECTED_END

_MIN_SIGNALED_SAMPLES = 100          # locked bar, Campaigns 01/02/03
_CANDIDATE_PERCENTILES = (60, 75, 90)
_CANDIDATE_N_FOLDS = (3, 5)
_BOOTSTRAP_RESAMPLES = 1000
_BOOTSTRAP_SEED = 7                  # same seed convention as Campaign 01


# --------------------------------------------------------------------------
# Stage 1 — audited daily panel
# --------------------------------------------------------------------------

def _daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def build_panel():
    """Daily UNIQUE-EVENT counts per symbol, RD-14/RD-15 applied.

    Counts distinct `tid` (one liquidation = two paired fills sharing a
    tid), not rows, so the panel is in events regardless of fill pairing.
    """
    raw = {}
    for sym in _SYMBOLS:
        per_day = defaultdict(set)
        path = _STORAGE_ROOT / f"liquidation__{sym}__hyperliquid_s3.csv"
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                per_day[row["observed_at_utc"][:10]].add(row["tid"])
        raw[sym] = {d: len(t) for d, t in per_day.items()}

    panel = {}
    for sym in _SYMBOLS:
        series = {}
        for d in _daterange(_ANALYSIS_START, _ANALYSIS_END):
            # RD-14: absence inside the covered window is a measured zero.
            series[d] = raw[sym].get(d.isoformat(), 0)
        panel[sym] = series
    return panel, raw


def preflight(panel, raw):
    """Fail LOUDLY on any violated expectation. No silent degradation."""
    results, failures = [], []

    def check(name, ok, detail):
        results.append({"assertion": name, "passed": bool(ok), "detail": detail})
        if not ok:
            failures.append(f"{name}: {detail}")

    expected_days = (_ANALYSIS_END - _ANALYSIS_START).days + 1
    check("symbol_count", len(panel) == 3, f"{len(panel)} symbols (expected 3)")
    for sym in _SYMBOLS:
        check(f"date_coverage[{sym}]", len(panel[sym]) == expected_days,
              f"{len(panel[sym])} days (expected {expected_days})")
    total_rows = sum(len(v) for v in panel.values())
    check("panel_row_count", total_rows == expected_days * 3,
          f"{total_rows} rows (expected {expected_days * 3})")

    # Contiguity: no gaps, no duplicates.
    for sym in _SYMBOLS:
        days = sorted(panel[sym])
        contiguous = all((b - a).days == 1 for a, b in zip(days, days[1:]))
        check(f"contiguous[{sym}]", contiguous and days[0] == _ANALYSIS_START
              and days[-1] == _ANALYSIS_END,
              f"{days[0]}..{days[-1]}")

    # RD-14: zero-event days must be PRESENT as zeros, not missing.
    zero_days = {sym: sorted(d.isoformat() for d, c in panel[sym].items() if c == 0)
                 for sym in _SYMBOLS}
    n_zero = sum(len(v) for v in zero_days.values())
    check("rd14_zero_materialization", n_zero >= 1,
          f"{n_zero} zero-event (symbol,day) cells materialized: "
          + "; ".join(f"{s}={zero_days[s]}" for s in _SYMBOLS if zero_days[s]))

    # RD-15: the partial day must be absent from the analysis panel,
    # while being present in the raw collected data (proving exclusion
    # was deliberate, not a collection gap).
    excluded_iso = _RD15_EXCLUDED_DAY.isoformat()
    in_panel = any(_RD15_EXCLUDED_DAY in panel[s] for s in _SYMBOLS)
    in_raw = any(excluded_iso in raw[s] for s in _SYMBOLS)
    check("rd15_partial_day_excluded", (not in_panel) and in_raw,
          f"{excluded_iso} in_panel={in_panel} (expected False), "
          f"in_raw_collected={in_raw} (expected True)")

    check("no_negative_counts",
          all(c >= 0 for s in _SYMBOLS for c in panel[s].values()), "all counts >= 0")
    return results, failures


# --------------------------------------------------------------------------
# statistics helpers (pure stdlib, deterministic)
# --------------------------------------------------------------------------

def percentile(sorted_vals, p):
    """Linear-interpolation percentile on an ascending list."""
    if not sorted_vals:
        raise ValueError("empty")
    k = (len(sorted_vals) - 1) * (p / 100.0)
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return float(sorted_vals[int(k)])
    return sorted_vals[lo] * (hi - k) + sorted_vals[hi] * (k - lo)


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return num / (dx * dy) if dx and dy else float("nan")


def lag1_autocorr(vals):
    return pearson(vals[:-1], vals[1:])


def fold_boundaries(n_samples, n_folds):
    """Identical convention to alpha_engine/validation/walk_forward.py:
    first (n % k) folds take one extra sample."""
    base, rem = divmod(n_samples, n_folds)
    out, start = [], 0
    for i in range(n_folds):
        size = base + (1 if i < rem else 0)
        out.append((start, start + size))
        start += size
    return out


def n_eff_symbols(n, rho_bar):
    """Effective independent series among n equicorrelated series.
    N_eff = n / (1 + (n-1) * rho). Same form RD-13 used to obtain ~1.1."""
    return n / (1.0 + (n - 1) * rho_bar)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    timings = {}
    t0 = time.perf_counter()

    # ---- Stage 1
    t = time.perf_counter()
    panel, raw = build_panel()
    timings["stage1_build_panel_s"] = time.perf_counter() - t

    assertions, failures = preflight(panel, raw)
    print("=" * 74)
    print("STAGE 1 — audited daily panel + pre-flight assertions")
    print("=" * 74)
    for a in assertions:
        print(f"  [{'PASS' if a['passed'] else 'FAIL'}] {a['assertion']}: {a['detail']}")
    if failures:
        print("\nPRE-FLIGHT FAILED — refusing to continue:")
        for f in failures:
            print(f"  - {f}")
        return 1

    days = sorted(panel[_SYMBOLS[0]])
    n_days = len(days)
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    panel_path = _OUT_DIR / "daily_event_counts.csv"
    with open(panel_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["day"] + list(_SYMBOLS))
        for d in days:
            w.writerow([d.isoformat()] + [panel[s][d] for s in _SYMBOLS])
    print(f"\n  panel artifact -> {panel_path}  ({n_days} days x 3 symbols)")

    print("\n  descriptive (event counts/day, outcome-blind):")
    for s in _SYMBOLS:
        v = sorted(panel[s][d] for d in days)
        print(f"    {s}: min={v[0]:>6}  p25={percentile(v,25):>9.1f}  "
              f"median={percentile(v,50):>9.1f}  p75={percentile(v,75):>9.1f}  "
              f"max={v[-1]:>7}  zero_days={sum(1 for x in v if x==0)}")

    # ---- Stage 2: venue-relative thresholds (Hyperliquid only)
    t = time.perf_counter()
    thresholds = {}
    for s in _SYMBOLS:
        v = sorted(panel[s][d] for d in days)
        thresholds[s] = {p: percentile(v, p) for p in _CANDIDATE_PERCENTILES}
    timings["stage2_thresholds_s"] = time.perf_counter() - t

    print("\n" + "=" * 74)
    print("STAGE 2 — venue-relative thresholds (Hyperliquid distribution only)")
    print("=" * 74)
    print("  Per-symbol percentiles of that symbol's OWN daily-count distribution")
    print("  (Constitution Section 6: never one absolute magnitude across venues;")
    print("   applied per-instrument here because BTC/ETH/SOL counts differ ~3x).")
    for s in _SYMBOLS:
        row = "  ".join(f"p{p}={thresholds[s][p]:,.0f}" for p in _CANDIDATE_PERCENTILES)
        print(f"    {s}: {row}")

    # ---- Stage 3: feasibility statistics
    t = time.perf_counter()
    series = {s: [panel[s][d] for d in days] for s in _SYMBOLS}

    pairs = [("BTC", "ETH"), ("BTC", "SOL"), ("ETH", "SOL")]
    cross = {f"{a}-{b}": pearson(series[a], series[b]) for a, b in pairs}
    rho_bar = sum(cross.values()) / len(cross)
    neff = n_eff_symbols(3, rho_bar)
    haircut = neff / 3.0
    autocorr = {s: lag1_autocorr(series[s]) for s in _SYMBOLS}

    grid = []
    for p in _CANDIDATE_PERCENTILES:
        sig = {s: [1 if panel[s][d] >= thresholds[s][p] else 0 for d in days]
               for s in _SYMBOLS}
        pooled_total = sum(sum(sig[s]) for s in _SYMBOLS)
        for k in _CANDIDATE_N_FOLDS:
            per_fold = []
            for (a, b) in fold_boundaries(n_days, k):
                per_fold.append(sum(sum(sig[s][a:b]) for s in _SYMBOLS))
            worst = min(per_fold)
            mean_fold = sum(per_fold) / k
            eff_worst = worst * haircut
            eff_mean = mean_fold * haircut
            grid.append({
                "percentile": p, "n_folds": k,
                "pooled_signalled_total": pooled_total,
                "per_fold_raw": per_fold,
                "worst_fold_raw": worst, "mean_fold_raw": mean_fold,
                "worst_fold_effective": eff_worst, "mean_fold_effective": eff_mean,
                "raw_clears_floor": worst >= _MIN_SIGNALED_SAMPLES,
                "effective_clears_floor": eff_worst >= _MIN_SIGNALED_SAMPLES,
            })

    # bootstrap stability of the worst-fold signalled count (moving-block,
    # block=7d, to respect the measured serial dependence; an iid day
    # bootstrap would understate variance).
    rng = random.Random(_BOOTSTRAP_SEED)
    block = 7
    boot = {}
    for p in _CANDIDATE_PERCENTILES:
        sig_sum = [sum(1 for s in _SYMBOLS if panel[s][d] >= thresholds[s][p])
                   for d in days]
        for k in _CANDIDATE_N_FOLDS:
            fold_len = n_days // k
            samples = []
            for _ in range(_BOOTSTRAP_RESAMPLES):
                seq = []
                while len(seq) < fold_len:
                    st = rng.randrange(0, n_days - block)
                    seq.extend(sig_sum[st:st + block])
                samples.append(sum(seq[:fold_len]))
            samples.sort()
            boot[f"p{p}_folds{k}"] = {
                "mean": sum(samples) / len(samples),
                "p05": samples[int(0.05 * len(samples))],
                "p95": samples[int(0.95 * len(samples))],
                "frac_ge_floor": sum(1 for x in samples if x >= _MIN_SIGNALED_SAMPLES) / len(samples),
                "frac_eff_ge_floor": sum(1 for x in samples if x * haircut >= _MIN_SIGNALED_SAMPLES) / len(samples),
            }

    # temporal dispersion (outcome-blind proxy for regime coverage):
    # formal BTC-trend-regime labelling belongs to the validation stage,
    # post-pre-registration, because it requires the price series.
    disp = {}
    for p in _CANDIDATE_PERCENTILES:
        per_q = defaultdict(int)
        for d in days:
            q = f"{d.year}Q{(d.month - 1) // 3 + 1}"
            per_q[q] += sum(1 for s in _SYMBOLS if panel[s][d] >= thresholds[s][p])
        disp[p] = dict(sorted(per_q.items()))
    timings["stage3_statistics_s"] = time.perf_counter() - t
    timings["total_s"] = time.perf_counter() - t0

    print("\n" + "=" * 74)
    print("STAGE 3 — feasibility statistics (NO returns, NO profitability)")
    print("=" * 74)
    print("\n  cross-symbol correlation of daily event counts:")
    for k_, v in cross.items():
        print(f"    {k_}: {v:+.3f}")
    print(f"    mean pairwise rho = {rho_bar:+.3f}")
    print(f"    N_eff (3 symbols) = {neff:.2f} effective independent series"
          f"  -> haircut x{haircut:.3f}")
    print("\n  within-symbol lag-1 autocorrelation (serial dependence):")
    for s in _SYMBOLS:
        print(f"    {s}: {autocorr[s]:+.3f}")

    print(f"\n  per-fold signalled samples vs floor "
          f"(min_signaled_samples = {_MIN_SIGNALED_SAMPLES}, applied per fold):")
    print(f"    {'thresh':>7} {'folds':>6} {'worst_raw':>10} {'mean_raw':>9} "
          f"{'worst_eff':>10} {'mean_eff':>9} {'raw?':>5} {'eff?':>5}")
    for g in grid:
        print(f"    {'p'+str(g['percentile']):>7} {g['n_folds']:>6} "
              f"{g['worst_fold_raw']:>10} {g['mean_fold_raw']:>9.1f} "
              f"{g['worst_fold_effective']:>10.1f} {g['mean_fold_effective']:>9.1f} "
              f"{'YES' if g['raw_clears_floor'] else 'no':>5} "
              f"{'YES' if g['effective_clears_floor'] else 'no':>5}")

    print("\n  bootstrap stability of a fold's signalled count "
          f"(moving-block b=7d, n={_BOOTSTRAP_RESAMPLES}, seed={_BOOTSTRAP_SEED}):")
    for key, b in boot.items():
        print(f"    {key:>12}: mean={b['mean']:7.1f}  90% CI=[{b['p05']},{b['p95']}]  "
              f"P(raw>=100)={b['frac_ge_floor']:.2f}  P(eff>=100)={b['frac_eff_ge_floor']:.2f}")

    print("\n  temporal dispersion of signalled samples by quarter (regime-coverage proxy):")
    for p in _CANDIDATE_PERCENTILES:
        print(f"    p{p}: {disp[p]}")

    report = {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "window": {"start": _ANALYSIS_START.isoformat(), "end": _ANALYSIS_END.isoformat(),
                   "n_days": n_days, "rd15_excluded_day": _RD15_EXCLUDED_DAY.isoformat()},
        "preflight": assertions,
        "thresholds": {s: {f"p{p}": thresholds[s][p] for p in _CANDIDATE_PERCENTILES}
                       for s in _SYMBOLS},
        "cross_symbol_correlation": cross,
        "mean_pairwise_rho": rho_bar,
        "n_eff_symbols": neff,
        "n_eff_haircut": haircut,
        "lag1_autocorrelation": autocorr,
        "min_signaled_samples_floor": _MIN_SIGNALED_SAMPLES,
        "grid": grid,
        "bootstrap": boot,
        "temporal_dispersion_by_quarter": {f"p{p}": disp[p] for p in _CANDIDATE_PERCENTILES},
        "timings_seconds": timings,
    }
    rp = _OUT_DIR / "feasibility_statistics.json"
    rp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n  statistics artifact -> {rp}")
    print("\n  timings: " + "  ".join(f"{k}={v:.2f}s" for k, v in timings.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
