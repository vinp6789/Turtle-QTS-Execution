"""Exploratory Funding Rate distribution study for Research Campaign 02.

DESCRIPTIVE STATISTICS ONLY. This script computes properties of the raw
funding-rate SERIES ITSELF -- min, max, median, percentiles, positive/
negative frequency, persistence (run-length of same-sign periods,
lag-1 autocorrelation of sign) -- to ground a defensible, principled
threshold choice.

IT DOES NOT USE ANY OUTCOME DATA (no price, no forward return). Nothing
computed here can leak into or bias the pre-registration -- the threshold
methodology and value chosen from this study are locked in
docs/RESEARCH_CAMPAIGN_02_funding_rate.md BEFORE any sample is built or
any candidate is evaluated. This is the exploratory step the campaign's
own principles require to happen before, and independently of, looking
at a single outcome.
"""

from decimal import Decimal
from pathlib import Path
from typing import Sequence

from exchange_adapter import Symbol

from alpha_engine._time import parse_utc
from alpha_engine.historical import load
from alpha_engine.historical.models import FundingRateObservation
from alpha_engine.historical.storage import series_filename

_STORAGE_ROOT = "data/alpha_engine_historical"


def _percentile(sorted_values: Sequence[Decimal], p: float) -> Decimal:
    """Linear-interpolated percentile, p in [0, 100]."""
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    rank = (Decimal(str(p)) / Decimal(100)) * Decimal(n - 1)
    lo = int(rank)
    frac = rank - lo
    if lo + 1 >= n:
        return sorted_values[-1]
    return sorted_values[lo] + frac * (sorted_values[lo + 1] - sorted_values[lo])


def describe(symbol: Symbol, source: str, storage_root: str = _STORAGE_ROOT) -> dict:
    path = Path(storage_root) / series_filename("funding_rate", symbol, source)
    observations = load(path, FundingRateObservation)
    if not observations:
        return {"symbol": symbol.value, "source": source, "n": 0}

    ordered = sorted(observations, key=lambda o: parse_utc(o.observed_at_utc))
    values = [o.value for o in ordered]
    sorted_values = sorted(values)
    n = len(values)

    positive = sum(1 for v in values if v > 0)
    negative = sum(1 for v in values if v < 0)
    zero = n - positive - negative

    # Persistence: (a) mean run-length of consecutive same-sign settlements,
    # (b) lag-1 sign autocorrelation proxy (fraction of consecutive pairs
    # sharing the same sign) -- both computed on the RAW SIGN SEQUENCE only,
    # no outcome data involved.
    signs = [1 if v > 0 else (-1 if v < 0 else 0) for v in values]
    runs = []
    run_len = 1
    for i in range(1, len(signs)):
        if signs[i] == signs[i - 1] and signs[i] != 0:
            run_len += 1
        else:
            runs.append(run_len)
            run_len = 1
    runs.append(run_len)
    mean_run_length = sum(runs) / len(runs) if runs else 0.0

    same_sign_pairs = sum(
        1 for i in range(1, len(signs)) if signs[i] == signs[i - 1] and signs[i] != 0
    )
    total_pairs = sum(1 for i in range(1, len(signs)) if signs[i] != 0 and signs[i - 1] != 0)
    persistence_ratio = (same_sign_pairs / total_pairs) if total_pairs else None

    return {
        "symbol": symbol.value,
        "source": source,
        "n": n,
        "span": (ordered[0].observed_at_utc, ordered[-1].observed_at_utc),
        "min": sorted_values[0],
        "max": sorted_values[-1],
        "median": _percentile(sorted_values, 50),
        "p01": _percentile(sorted_values, 1),
        "p05": _percentile(sorted_values, 5),
        "p10": _percentile(sorted_values, 10),
        "p90": _percentile(sorted_values, 90),
        "p95": _percentile(sorted_values, 95),
        "p99": _percentile(sorted_values, 99),
        "positive_frequency": positive / n,
        "negative_frequency": negative / n,
        "zero_count": zero,
        "mean_run_length_settlements": mean_run_length,
        "same_sign_persistence_ratio": persistence_ratio,
    }


def format_report(stats: dict) -> str:
    if stats.get("n", 0) == 0:
        return f"{stats['symbol']}/{stats['source']}: NO DATA"
    lines = [
        f"=== {stats['symbol']} ({stats['source']}) — n={stats['n']} span={stats['span'][0][:10]}..{stats['span'][1][:10]} ===",
        f"  min={stats['min']}  max={stats['max']}  median={stats['median']}",
        f"  p01={stats['p01']}  p05={stats['p05']}  p10={stats['p10']}",
        f"  p90={stats['p90']}  p95={stats['p95']}  p99={stats['p99']}",
        f"  positive_freq={stats['positive_frequency']:.4f}  negative_freq={stats['negative_frequency']:.4f}  zero_count={stats['zero_count']}",
        f"  mean_run_length(settlements)={stats['mean_run_length_settlements']:.2f}  "
        f"same_sign_persistence_ratio={stats['same_sign_persistence_ratio']}",
    ]
    return "\n".join(lines)


def pooled_abs_percentiles(symbols, source: str, storage_root: str = _STORAGE_ROOT) -> dict:
    """Percentiles of |funding rate|, POOLED across all given symbols'
    raw historical series. Still purely descriptive of the feature series
    itself -- no outcome data. This is the statistic that actually
    resolves threshold selection under the sign-asymmetry finding: a
    single, symmetric threshold candidate.evaluate() can apply to +value
    or -value alike, chosen from the magnitude distribution rather than
    from one sign's tail alone (which, for a skewed series like this one,
    would barely ever fire on the minority sign for some symbols)."""
    pooled_abs = []
    for symbol in symbols:
        path = Path(storage_root) / series_filename("funding_rate", symbol, source)
        observations = load(path, FundingRateObservation)
        pooled_abs.extend(abs(o.value) for o in observations)
    pooled_abs.sort()
    return {
        "n_pooled": len(pooled_abs),
        "p50": _percentile(pooled_abs, 50),
        "p75": _percentile(pooled_abs, 75),
        "p90": _percentile(pooled_abs, 90),
        "p95": _percentile(pooled_abs, 95),
        "p99": _percentile(pooled_abs, 99),
    }


if __name__ == "__main__":
    for sym in (Symbol("BTC"), Symbol("ETH"), Symbol("SOL")):
        stats = describe(sym, "binance")
        print(format_report(stats))
        print()

    pooled = pooled_abs_percentiles((Symbol("BTC"), Symbol("ETH"), Symbol("SOL")), "binance")
    print(f"=== Pooled |funding rate| percentiles (BTC+ETH+SOL, n={pooled['n_pooled']}) ===")
    print(f"  p50={pooled['p50']}  p75={pooled['p75']}  p90={pooled['p90']}  "
          f"p95={pooled['p95']}  p99={pooled['p99']}")
