"""Backlog 3.5 — outcome-blind HOURLY feasibility screen (RD-16 Section E).

RD-16 deferred Campaign 06 at daily resolution (N_eff 1.14 of 3 symbols;
best worst-fold 40.2 against a floor of 100) and named exactly one live
alternative:

    "a finer-grained (e.g. hourly) specification could multiply raw
     counts ~24x -- but hourly data carries materially higher serial
     autocorrelation and possibly different cross-symbol dependence,
     both of which attack N_eff directly. It would need its own
     feasibility review first."

This IS that review. The question is NOT whether hourly gives more raw
samples -- arithmetic guarantees it does. The question is whether the
EFFECTIVE sample size rises, once serial dependence at hourly resolution
is measured rather than assumed.

STRICTLY OUTCOME-BLIND: reads only the liquidation event series. Never
opens a price series, never computes a return, never evaluates
profitability, never tunes a threshold against a result.

Governing rules applied as written:
  - RD-15: 2025-07-27 is excluded (16/24 archive hours). Its partial
    hours would otherwise masquerade as quiet hours.
  - RD-14: within the covered window an absent (symbol, hour) is a
    VERIFIED ZERO-EVENT hour, materialized as 0. The whole-window
    coverage audit confirmed 24/24 hourly objects on all 366 remaining
    days, which is what licenses extending RD-14 from days to hours.
  - Constitution Section 6: thresholds are percentiles of that symbol's
    own hourly distribution.
  - RD-13 Section C: N_eff and cross-symbol correlation are mandatory.

Run: python -m research.campaign_06_liquidations.hourly_feasibility
"""

import csv
import json
import math
import random
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path("data/alpha_engine_historical")
_OUT = Path("data/alpha_engine_research/campaign_06_feasibility")
_SYMBOLS = ("BTC", "ETH", "SOL")
_START = date(2025, 7, 28)      # RD-15: 2025-07-27 excluded
_END = date(2026, 7, 28)
_MIN_SIGNALED = 100
_PERCENTILES = (75, 90, 99)
_N_FOLDS = (3, 5)
_RESAMPLES = 1000
_SEED = 7


def percentile(sorted_vals, p):
    k = (len(sorted_vals) - 1) * (p / 100.0)
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return float(sorted_vals[int(k)])
    return sorted_vals[lo] * (hi - k) + sorted_vals[hi] * (k - lo)


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return num / (dx * dy) if dx > 0 and dy > 0 else float("nan")


def n_eff_serial(n, rho1):
    """N*(1-r)/(1+r) -- the exact form RD-04 used, so the comparison
    against every prior N_eff figure in the project is like-for-like."""
    return 0.0 if rho1 >= 1.0 else n * (1.0 - rho1) / (1.0 + rho1)


def n_eff_cross(n, rho_bar):
    return n / (1.0 + (n - 1) * rho_bar)


def folds(n, k):
    base, rem = divmod(n, k)
    out, start = [], 0
    for i in range(k):
        size = base + (1 if i < rem else 0)
        out.append((start, start + size))
        start += size
    return out


def build_hourly_panel():
    """Unique liquidation events per (symbol, hour), zeros materialized."""
    hours = []
    cur = datetime(_START.year, _START.month, _START.day, tzinfo=timezone.utc)
    end = datetime(_END.year, _END.month, _END.day, 23, tzinfo=timezone.utc)
    while cur <= end:
        hours.append(cur)
        cur += timedelta(hours=1)
    index = {h: i for i, h in enumerate(hours)}

    panel = {}
    raw_nonzero = {}
    for sym in _SYMBOLS:
        tids = defaultdict(set)
        with open(_ROOT / f"liquidation__{sym}__hyperliquid_s3.csv",
                  newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                ts = row["observed_at_utc"]
                slot = datetime(int(ts[0:4]), int(ts[5:7]), int(ts[8:10]),
                                int(ts[11:13]), tzinfo=timezone.utc)
                if slot in index:
                    tids[slot].add(row["tid"])
        counts = [0] * len(hours)
        for slot, s in tids.items():
            counts[index[slot]] = len(s)
        panel[sym] = counts
        raw_nonzero[sym] = len(tids)
    return hours, panel, raw_nonzero


def main():
    t0 = time.perf_counter()
    timings = {}

    t = time.perf_counter()
    hours, panel, raw_nonzero = build_hourly_panel()
    timings["build_panel_s"] = time.perf_counter() - t
    n = len(hours)

    print("=" * 78)
    print("STAGE 1 — audited hourly panel + pre-flight assertions")
    print("=" * 78)
    expected = ((_END - _START).days + 1) * 24
    checks = [
        ("hour_count", n == expected, f"{n} hourly slots (expected {expected})"),
        ("symbol_count", len(panel) == 3, f"{len(panel)} symbols"),
        ("rd15_partial_day_excluded", hours[0].date() == _START,
         f"panel starts {hours[0].date()} (2025-07-27 excluded)"),
        ("contiguous", all((b - a).total_seconds() == 3600 for a, b in zip(hours, hours[1:])),
         "no gaps in the hourly grid"),
        ("no_negative", all(c >= 0 for v in panel.values() for c in v), "all counts >= 0"),
    ]
    for sym in _SYMBOLS:
        zeros = sum(1 for c in panel[sym] if c == 0)
        checks.append((f"rd14_zero_materialization[{sym}]", zeros > 0,
                       f"{zeros:,} zero-event hours materialized "
                       f"({zeros / n * 100:.1f}% of {n:,})"))
    failures = []
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        if not ok:
            failures.append(name)
    if failures:
        print(f"\nPRE-FLIGHT FAILED: {failures} -- refusing to continue")
        return 1

    print("\n  descriptive (events/hour, outcome-blind):")
    for sym in _SYMBOLS:
        v = sorted(panel[sym])
        print(f"    {sym}: total={sum(v):,}  nonzero_hours={raw_nonzero[sym]:,}  "
              f"median={percentile(v,50):.0f}  p75={percentile(v,75):.0f}  "
              f"p90={percentile(v,90):.0f}  p99={percentile(v,99):.0f}  max={v[-1]:,}")

    # ---------------- Stage 2/3
    print("\n" + "=" * 78)
    print("STAGE 2/3 — feasibility statistics (NO returns computed)")
    print("=" * 78)

    print("\n--- THE DECISIVE MEASUREMENT: serial dependence at hourly resolution ---")
    print("    (RD-16 Section E's stated risk. Daily-grid comparison from RD-16: N/A --")
    print("     the daily review failed on cross-symbol dependence, not serial.)")
    serial = {}
    for sym in _SYMBOLS:
        r1 = pearson(panel[sym][:-1], panel[sym][1:])
        ne = n_eff_serial(n, r1)
        serial[sym] = {"lag1": r1, "n_eff_serial": ne, "n_hours": n}
        print(f"    {sym}: hourly lag-1 rho={r1:+.4f}   N_eff(serial)={ne:>9,.0f} of {n:,} hours")

    print("\n--- cross-symbol dependence of hourly counts (RD-13 Section C) ---")
    pairs = [("BTC", "ETH"), ("BTC", "SOL"), ("ETH", "SOL")]
    cc = {f"{a}-{b}": pearson(panel[a], panel[b]) for a, b in pairs}
    rho_bar = sum(cc.values()) / 3
    neff_sym = n_eff_cross(3, rho_bar)
    print("    " + "  ".join(f"{k}={v:+.3f}" for k, v in cc.items()))
    print(f"    mean rho={rho_bar:+.3f}   N_eff={neff_sym:.2f} of 3 symbols   "
          f"haircut x{neff_sym/3:.3f}")
    print(f"    (daily equivalent measured in RD-16: rho_bar=+0.818, N_eff=1.14)")

    print(f"\n--- per-fold signalled samples vs floor {_MIN_SIGNALED} ---")
    grid = []
    for p in _PERCENTILES:
        thr = {s: percentile(sorted(panel[s]), p) for s in _SYMBOLS}
        sig = {s: [1 if c >= thr[s] else 0 for c in panel[s]] for s in _SYMBOLS}
        pooled = [sum(sig[s][i] for s in _SYMBOLS) for i in range(n)]
        total = sum(pooled)
        for k in _N_FOLDS:
            pf = [sum(pooled[a:b]) for a, b in folds(n, k)]
            worst, mean = min(pf), sum(pf) / k
            # effective = cross-symbol haircut AND serial haircut
            serial_factor = sum(serial[s]["n_eff_serial"] for s in _SYMBOLS) / (3 * n)
            eff_cross = worst * (neff_sym / 3)
            eff_both = eff_cross * serial_factor
            grid.append({"percentile": p, "n_folds": k, "total": total,
                         "worst_fold": worst, "mean_fold": mean,
                         "worst_effective_cross": eff_cross,
                         "worst_effective_cross_and_serial": eff_both,
                         "clears_raw": worst >= _MIN_SIGNALED,
                         "clears_effective": eff_both >= _MIN_SIGNALED})
            print(f"    p{p:<2} folds={k}: total={total:>7,}  worst_fold={worst:>6,}  "
                  f"eff(cross)={eff_cross:>8,.0f}  eff(cross+serial)={eff_both:>8,.0f}  "
                  f"{'CLEARS' if eff_both >= _MIN_SIGNALED else 'fails'}")

    print(f"\n--- bootstrap stability (moving-block b=24h, n={_RESAMPLES}, seed={_SEED}) ---")
    rng = random.Random(_SEED)
    boot = {}
    for p in _PERCENTILES:
        thr = {s: percentile(sorted(panel[s]), p) for s in _SYMBOLS}
        pooled = [sum(1 for s in _SYMBOLS if panel[s][i] >= thr[s]) for i in range(n)]
        for k in _N_FOLDS:
            flen = n // k
            samples = []
            for _ in range(_RESAMPLES):
                seq = []
                while len(seq) < flen:
                    st = rng.randrange(0, n - 24)
                    seq.extend(pooled[st:st + 24])
                samples.append(sum(seq[:flen]))
            samples.sort()
            boot[f"p{p}_folds{k}"] = {
                "mean": sum(samples) / len(samples),
                "p05": samples[int(0.05 * len(samples))],
                "p95": samples[int(0.95 * len(samples))],
                "frac_ge_floor": sum(1 for x in samples if x >= _MIN_SIGNALED) / len(samples),
            }
            b = boot[f"p{p}_folds{k}"]
            print(f"    p{p:<2} folds={k}: mean={b['mean']:>9,.0f}  "
                  f"90% CI=[{b['p05']:,},{b['p95']:,}]  P(raw>=100)={b['frac_ge_floor']:.2f}")

    timings["total_s"] = time.perf_counter() - t0
    _OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "window": {"start": str(_START), "end": str(_END), "hours": n},
        "serial_dependence": serial,
        "cross_symbol": {"pairs": cc, "rho_bar": rho_bar, "n_eff_symbols": neff_sym},
        "grid": grid, "bootstrap": boot, "timings_seconds": timings,
    }
    (_OUT / "hourly_feasibility_statistics.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n  artifact -> {_OUT/'hourly_feasibility_statistics.json'}")
    print("  timings: " + "  ".join(f"{k}={v:.2f}s" for k, v in timings.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
