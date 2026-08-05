"""Backlog 3.2 — outcome-blind FEASIBILITY REVIEW for the next funding campaign.

STRICTLY OUTCOME-BLIND. Reads ONLY funding-rate series. Never opens the
mark-price / outcome series, never computes a return, never evaluates
profitability, never tunes a threshold against a result.

Two questions, both mandated by the governing documents:

  Q1 (RD-04 revisit). RD-04 deferred **Funding Persistence** as
      "statistically non-viable" at daily-grid lag-1 autocorrelation
      ~0.94-0.99 -> N_eff ~4-18 on the then-18-month window, with an
      explicit revisit trigger: "a materially longer data window".
      Backlog 2.1 took Binance to 77 months. Re-measure, do not assume.

  Q2 (ROADMAP 1.2). **BTC-only funding momentum, properly powered** is
      the strongest funding candidate not yet retried (CAMP-02 Binance
      n=35; CAMP-03 Hyperliquid n=138 -- both underpowered in isolation).
      Does the extended window now clear `min_signaled_samples = 100`
      per fold for a BTC-only design?

Governing rules applied, not re-derived:
  - Constitution Section 6 (venue-relative thresholds): every threshold
    is a percentile of THAT VENUE's own distribution. Never one absolute
    magnitude across venues.
  - Constitution Section 6 (venue-transfer / DEX-first): Binance may be
    used to reach power, but a finding is a research hypothesis only
    until replicated on Hyperliquid's own history. BOTH venues are
    therefore screened, and the Hyperliquid result is the binding one for
    promotability.
  - RD-13 Section C: report N_eff and cross-symbol dependence, not raw
    pooled signalled counts alone.

Acceptance bar, NOT weakened here:
  - min_signaled_samples = 100, applied PER FOLD (Campaigns 01/02/03).
  - n_folds = 5 standard; n_folds = 3 the precedented fallback (CAMP-03).

Run: python -m research.funding_deep_window_feasibility.feasibility_review
"""

import csv
import json
import math
import random
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

_ROOT = Path("data/alpha_engine_historical")
_OUT = Path("data/alpha_engine_research/funding_deep_window_feasibility")
_SYMBOLS = ("BTC", "ETH", "SOL")
_VENUES = ("binance", "hyperliquid")

_MIN_SIGNALED_SAMPLES = 100
_CANDIDATE_PERCENTILES = (75, 90)      # CAMP-02 chose p90; CAMP-03 chose p75
_CANDIDATE_N_FOLDS = (3, 5)
_BOOTSTRAP_RESAMPLES = 1000
_BOOTSTRAP_SEED = 7


# ---------------------------------------------------------------- helpers
def percentile(sorted_vals, p):
    if not sorted_vals:
        raise ValueError("empty")
    k = (len(sorted_vals) - 1) * (p / 100.0)
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return float(sorted_vals[int(k)])
    return sorted_vals[lo] * (hi - k) + sorted_vals[hi] * (k - lo)


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return num / (dx * dy) if dx and dy else float("nan")


def lag1(vals):
    return pearson(vals[:-1], vals[1:])


def n_eff_serial(n, rho1):
    """Effective sample size of an AR(1)-like series: N*(1-r)/(1+r).
    This is the exact form RD-04 used to obtain N_eff ~4-18."""
    if rho1 >= 1.0:
        return 0.0
    return n * (1.0 - rho1) / (1.0 + rho1)


def n_eff_cross(n, rho_bar):
    """Effective independent series among n equicorrelated series."""
    return n / (1.0 + (n - 1) * rho_bar)


def fold_boundaries(n, k):
    base, rem = divmod(n, k)
    out, start = [], 0
    for i in range(k):
        size = base + (1 if i < rem else 0)
        out.append((start, start + size))
        start += size
    return out


# ---------------------------------------------------- Stage 1: load + panel
def load_series():
    """Raw (timestamp, value) per (venue, symbol), ascending."""
    raw = {}
    for venue in _VENUES:
        for sym in _SYMBOLS:
            p = _ROOT / f"funding_rate__{sym}__{venue}.csv"
            rows = []
            with open(p, newline="", encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    rows.append((datetime.fromisoformat(r["observed_at_utc"]), float(r["value"])))
            rows.sort(key=lambda x: x[0])
            raw[(venue, sym)] = rows
    return raw


def daily_grid(rows):
    """Last settlement of each UTC day -> (day, value). Deterministic."""
    per_day = {}
    for ts, v in rows:
        per_day[ts.date()] = v          # ascending input => last wins
    return per_day


def persistence_daily(rows):
    """RD-04's feature: elapsed HOURS since the funding rate last changed
    sign, sampled at the last settlement of each UTC day. Also returns
    the observed run durations by sign."""
    per_day = {}
    runs = {"pos": [], "neg": []}
    last_flip = rows[0][0]
    cur_sign = 1 if rows[0][1] >= 0 else -1
    for ts, v in rows:
        sign = 1 if v >= 0 else -1
        if sign != cur_sign:
            dur_h = (ts - last_flip).total_seconds() / 3600.0
            runs["pos" if cur_sign > 0 else "neg"].append(dur_h)
            last_flip = ts
            cur_sign = sign
        per_day[ts.date()] = (ts - last_flip).total_seconds() / 3600.0
    return per_day, runs


def preflight(raw, common):
    results, failures = [], []

    def check(name, ok, detail):
        results.append({"assertion": name, "passed": bool(ok), "detail": detail})
        if not ok:
            failures.append(f"{name}: {detail}")

    for venue in _VENUES:
        for sym in _SYMBOLS:
            rows = raw[(venue, sym)]
            check(f"nonempty[{venue}/{sym}]", len(rows) > 0, f"{len(rows):,} rows")
            ts = [t for t, _ in rows]
            check(f"ascending[{venue}/{sym}]", ts == sorted(ts), "timestamps ascending")
            check(f"unique[{venue}/{sym}]", len(set(ts)) == len(ts),
                  f"{len(ts)-len(set(ts))} duplicate timestamps (expected 0)")

    # cadence: modal inter-arrival, per venue
    for venue in _VENUES:
        rows = raw[(venue, "BTC")]
        gaps = [round((b[0] - a[0]).total_seconds() / 3600.0) for a, b in zip(rows, rows[1:])]
        modal = max(set(gaps), key=gaps.count)
        expect = 8 if venue == "binance" else 1
        check(f"cadence[{venue}]", modal == expect,
              f"modal inter-arrival {modal}h (expected {expect}h)")

    # venue overlap must be non-trivial for any replication claim
    ov_start, ov_end, ov_days = common["overlap"]
    check("venue_overlap_nonempty", ov_days > 365,
          f"{ov_start}..{ov_end} = {ov_days} days of Binance/Hyperliquid overlap")

    # Hyperliquid must actually be current after Backlog 3.1
    hl_last = max(raw[("hyperliquid", s)][-1][0] for s in _SYMBOLS)
    lag_days = (datetime.now(hl_last.tzinfo) - hl_last).total_seconds() / 86400
    check("hyperliquid_current", lag_days < 7,
          f"last Hyperliquid settlement {hl_last.isoformat()} ({lag_days:.2f} days ago)")

    for venue in _VENUES:
        n = common[venue]["n_days"]
        check(f"window_len[{venue}]", n > 300, f"{n} common days across all 3 symbols")
    return results, failures


# ------------------------------------------------------------------- main
def main():
    t_all = time.perf_counter()
    timings = {}

    t = time.perf_counter()
    raw = load_series()
    timings["stage1_load_s"] = time.perf_counter() - t

    # common per-venue window across all three symbols
    common = {}
    for venue in _VENUES:
        starts = [raw[(venue, s)][0][0].date() for s in _SYMBOLS]
        ends = [raw[(venue, s)][-1][0].date() for s in _SYMBOLS]
        st, en = max(starts), min(ends)
        common[venue] = {"start": st, "end": en, "n_days": (en - st).days + 1}
    ov_s = max(common["binance"]["start"], common["hyperliquid"]["start"])
    ov_e = min(common["binance"]["end"], common["hyperliquid"]["end"])
    common["overlap"] = (ov_s, ov_e, (ov_e - ov_s).days + 1)

    assertions, failures = preflight(raw, common)
    print("=" * 78)
    print("STAGE 1 — audited funding panel + pre-flight assertions")
    print("=" * 78)
    for a in assertions:
        print(f"  [{'PASS' if a['passed'] else 'FAIL'}] {a['assertion']}: {a['detail']}")
    if failures:
        print("\nPRE-FLIGHT FAILED — refusing to continue:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("\n  coverage:")
    for venue in _VENUES:
        for sym in _SYMBOLS:
            r = raw[(venue, sym)]
            print(f"    {venue:12s} {sym}: {r[0][0].date()} .. {r[-1][0].date()}  {len(r):>7,} rows")
    for venue in _VENUES:
        c = common[venue]
        print(f"    common window [{venue}]: {c['start']} .. {c['end']}  ({c['n_days']} days, "
              f"{c['n_days']/30.44:.1f} months)")
    print(f"    venue OVERLAP: {ov_s} .. {ov_e}  ({common['overlap'][2]} days) "
          f"-- the window any DEX-first replication is limited to")

    # build daily panels restricted to each venue's common window
    daily, persist, runs = {}, {}, {}
    for venue in _VENUES:
        c = common[venue]
        days = [c["start"] + timedelta(days=i) for i in range(c["n_days"])]
        for sym in _SYMBOLS:
            g = daily_grid(raw[(venue, sym)])
            pg, rr = persistence_daily(raw[(venue, sym)])
            daily[(venue, sym)] = [g.get(d) for d in days]
            persist[(venue, sym)] = [pg.get(d) for d in days]
            runs[(venue, sym)] = rr
        common[venue]["days"] = days

    # ---------------------------------------------- Stage 2/3: statistics
    t = time.perf_counter()
    print("\n" + "=" * 78)
    print("STAGE 2/3 — outcome-blind feasibility statistics (NO returns)")
    print("=" * 78)

    # ---- Q1: RD-04 Funding Persistence revisit
    print("\n--- Q1. RD-04 FUNDING PERSISTENCE REVISIT (elapsed hours since sign flip) ---")
    print("    RD-04 baseline (18-month window): daily-grid lag-1 rho ~0.94-0.99 -> N_eff ~4-18")
    persistence = {}
    for venue in _VENUES:
        for sym in _SYMBOLS:
            v = [x for x in persist[(venue, sym)] if x is not None]
            r1 = lag1(v)
            ne = n_eff_serial(len(v), r1)
            neg = runs[(venue, sym)]["neg"]
            pos = runs[(venue, sym)]["pos"]
            neg_med = sorted(neg)[len(neg)//2] if neg else 0.0
            persistence[f"{venue}/{sym}"] = {
                "n_days": len(v), "lag1": r1, "n_eff": ne,
                "n_neg_runs": len(neg), "median_neg_run_h": neg_med,
                "n_pos_runs": len(pos),
            }
            print(f"    {venue:12s} {sym}: n={len(v):>5}  lag1={r1:+.4f}  "
                  f"N_eff={ne:>7.1f}  neg_runs={len(neg):>4} (median {neg_med:.1f}h)  "
                  f"{'CLEARS' if ne >= _MIN_SIGNALED_SAMPLES else 'below'} floor {_MIN_SIGNALED_SAMPLES}")

    # ---- cross-symbol dependence (RD-13 Section C) on |funding| daily
    print("\n--- Cross-symbol dependence of daily |funding| (RD-13 Section C) ---")
    cross = {}
    for venue in _VENUES:
        vals = {s: [abs(x) for x in daily[(venue, s)] if x is not None] for s in _SYMBOLS}
        m = min(len(v) for v in vals.values())
        pairs = [("BTC", "ETH"), ("BTC", "SOL"), ("ETH", "SOL")]
        cc = {f"{a}-{b}": pearson(vals[a][:m], vals[b][:m]) for a, b in pairs}
        rb = sum(cc.values()) / len(cc)
        ne = n_eff_cross(3, rb)
        cross[venue] = {"pairs": cc, "rho_bar": rb, "n_eff_symbols": ne, "haircut": ne / 3.0}
        print(f"    {venue}: " + "  ".join(f"{k}={v:+.3f}" for k, v in cc.items()))
        print(f"    {'':12s} mean rho={rb:+.3f}  N_eff={ne:.2f} of 3 symbols  haircut x{ne/3.0:.3f}")

    # ---- Q2: BTC-only signalled counts at venue-relative thresholds
    print("\n--- Q2. BTC-ONLY funding-level signalled samples vs the floor ---")
    print("    Thresholds are percentiles of THAT VENUE's own |funding| distribution")
    print("    (Constitution Section 6). BTC-only: no pooling, so no cross-symbol haircut.")
    grid = []
    for venue in _VENUES:
        series = [abs(x) for x in daily[(venue, "BTC")] if x is not None]
        n = len(series)
        srt = sorted(series)
        for p in _CANDIDATE_PERCENTILES:
            thr = percentile(srt, p)
            sig = [1 if x >= thr else 0 for x in series]
            for k in _CANDIDATE_N_FOLDS:
                pf = [sum(sig[a:b]) for a, b in fold_boundaries(n, k)]
                worst, mean = min(pf), sum(pf) / k
                grid.append({"venue": venue, "percentile": p, "n_folds": k,
                             "threshold": thr, "n_days": n, "total_signalled": sum(sig),
                             "per_fold": pf, "worst_fold": worst, "mean_fold": mean,
                             "clears_floor": worst >= _MIN_SIGNALED_SAMPLES})
                print(f"    {venue:12s} p{p} folds={k}: thr={thr:.8f}  total={sum(sig):>5}  "
                      f"worst_fold={worst:>5}  mean={mean:>7.1f}  "
                      f"{'CLEARS' if worst >= _MIN_SIGNALED_SAMPLES else 'FAILS':>6}")

    # ---- bootstrap stability of the worst fold (moving block, b=7d)
    print(f"\n--- Bootstrap stability (moving-block b=7d, n={_BOOTSTRAP_RESAMPLES}, "
          f"seed={_BOOTSTRAP_SEED}) ---")
    rng = random.Random(_BOOTSTRAP_SEED)
    boot = {}
    for venue in _VENUES:
        series = [abs(x) for x in daily[(venue, "BTC")] if x is not None]
        n = len(series)
        srt = sorted(series)
        for p in _CANDIDATE_PERCENTILES:
            thr = percentile(srt, p)
            sig = [1 if x >= thr else 0 for x in series]
            for k in _CANDIDATE_N_FOLDS:
                fl = n // k
                samples = []
                for _ in range(_BOOTSTRAP_RESAMPLES):
                    seq = []
                    while len(seq) < fl:
                        st = rng.randrange(0, max(1, n - 7))
                        seq.extend(sig[st:st + 7])
                    samples.append(sum(seq[:fl]))
                samples.sort()
                key = f"{venue}_p{p}_folds{k}"
                boot[key] = {"mean": sum(samples)/len(samples),
                             "p05": samples[int(0.05*len(samples))],
                             "p95": samples[int(0.95*len(samples))],
                             "frac_ge_floor": sum(1 for x in samples if x >= _MIN_SIGNALED_SAMPLES)/len(samples)}
                b = boot[key]
                print(f"    {key:28s} mean={b['mean']:7.1f}  90% CI=[{b['p05']},{b['p95']}]  "
                      f"P(>=100)={b['frac_ge_floor']:.2f}")
    timings["stage23_stats_s"] = time.perf_counter() - t
    timings["total_s"] = time.perf_counter() - t_all

    _OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "windows": {v: {"start": str(common[v]["start"]), "end": str(common[v]["end"]),
                        "n_days": common[v]["n_days"]} for v in _VENUES},
        "venue_overlap": {"start": str(ov_s), "end": str(ov_e), "n_days": common["overlap"][2]},
        "preflight": assertions,
        "q1_persistence": persistence,
        "cross_symbol": cross,
        "q2_btc_only_grid": grid,
        "bootstrap": boot,
        "min_signaled_samples_floor": _MIN_SIGNALED_SAMPLES,
        "timings_seconds": timings,
    }
    (_OUT / "feasibility_statistics.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n  artifact -> {_OUT/'feasibility_statistics.json'}")
    print("  timings: " + "  ".join(f"{k}={v:.2f}s" for k, v in timings.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
