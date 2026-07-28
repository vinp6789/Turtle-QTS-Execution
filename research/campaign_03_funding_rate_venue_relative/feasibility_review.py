"""Mandatory pre-registration feasibility review (Research Campaign 03).

Required by docs/RESEARCH_PLAYBOOK.md SS2, added after Campaign 02's
methodology review: before locking a specification, check that the
expected signal count, expected walk-forward fold size, expected
bootstrap stability, and expected regime coverage are compatible with
the planned validation configuration.

OUTCOME-BLIND: this module counts how many point-in-time samples would
be SIGNALED (|funding| >= a candidate threshold) at each candidate
percentile. It never computes a hit rate, a realized return, or any
other outcome-dependent statistic -- only how many samples a threshold
choice would produce, which is a property of the feature distribution
and the sample-construction grid, not of the hypothesis's correctness.
Regime coverage is checked the same way: the BTC-price-derived regime
label attached to each signaled sample is contemporaneous/trailing
information (already used this way in Campaigns 01-02), not a future
outcome.
"""

from collections import Counter
from decimal import Decimal
from typing import Dict, Sequence, Tuple

from exchange_adapter import Symbol

from alpha_engine.historical import load
from alpha_engine.historical.models import FundingRateObservation, MarkPriceObservation
from alpha_engine.historical.storage import series_filename

from research.campaign_02_funding_rate.build_samples import build_samples, make_regime_labeler
from research.campaign_02_funding_rate.explore_distribution import pooled_abs_percentiles

_STORAGE_ROOT = "data/alpha_engine_historical"
_DEFAULT_SYMBOLS = (Symbol("BTC"), Symbol("ETH"), Symbol("SOL"))
_CANDIDATE_PERCENTILE_KEYS = ("p75", "p90", "p95")


def _load_series(symbols, source: str, storage_root: str = _STORAGE_ROOT):
    funding_by_symbol: Dict[Symbol, Sequence] = {}
    mark_by_symbol: Dict[Symbol, Sequence] = {}
    from pathlib import Path
    root = Path(storage_root)
    for symbol in symbols:
        funding_by_symbol[symbol] = load(root / series_filename("funding_rate", symbol, source), FundingRateObservation)
        # Mark price is always Binance's series -- outcomes (price returns) do not
        # change based on which venue's FUNDING history is under review here.
        mark_by_symbol[symbol] = load(root / series_filename("mark_price", symbol, "binance"), MarkPriceObservation)
    return funding_by_symbol, mark_by_symbol


def review_source(source: str, symbols=_DEFAULT_SYMBOLS, storage_root: str = _STORAGE_ROOT,
                   n_folds_candidates: Tuple[int, ...] = (5, 3), min_signaled_samples: int = 100) -> dict:
    """Returns a feasibility report for one venue: candidate thresholds
    (from that venue's own pooled |funding| percentiles), how many
    pooled samples each would signal, per-fold projections at each
    candidate n_folds, and the signaled-sample regime-label breakdown."""
    funding_by_symbol, mark_by_symbol = _load_series(symbols, source, storage_root)
    btc_mark = mark_by_symbol.get(Symbol("BTC"), ())
    labeler = make_regime_labeler(btc_mark) if btc_mark else None

    built = build_samples(funding_by_symbol, mark_by_symbol, regime_labeler=labeler)
    total = len(built.samples)

    pooled = pooled_abs_percentiles(symbols, source, storage_root)

    percentile_reports = {}
    for key in _CANDIDATE_PERCENTILE_KEYS:
        threshold = pooled[key]
        signaled = [s for s in built.samples if abs(s.feature_value.value) >= threshold]
        n_signaled = len(signaled)
        regime_counts = Counter(s.regime_label for s in signaled)
        fold_projection = {
            n_folds: {
                "per_fold_avg": n_signaled / n_folds,
                "clears_floor_every_fold": (n_signaled / n_folds) >= min_signaled_samples,
            }
            for n_folds in n_folds_candidates
        }
        percentile_reports[key] = {
            "threshold": str(threshold),
            "signaled": n_signaled,
            "signaled_fraction": n_signaled / total if total else None,
            "regime_counts": dict(regime_counts),
            "fold_projection": fold_projection,
        }

    return {
        "source": source,
        "total_samples": total,
        "sample_diagnostics": built.diagnostics,
        "pooled_percentiles": {k: str(v) for k, v in pooled.items() if k != "n_pooled"},
        "n_pooled_raw": pooled["n_pooled"],
        "percentiles": percentile_reports,
    }


def format_report(report: dict) -> str:
    lines = [
        f"=== Feasibility review: source={report['source']} ===",
        f"pooled PIT samples (24h grid, non-overlapping): {report['total_samples']}  "
        f"diagnostics={report['sample_diagnostics']}",
        f"pooled |funding| percentiles (own venue, n_raw={report['n_pooled_raw']}): "
        f"{report['pooled_percentiles']}",
        "",
    ]
    for key, pr in report["percentiles"].items():
        lines.append(f"  [{key}] threshold={pr['threshold']}  signaled={pr['signaled']} "
                     f"({pr['signaled_fraction']:.1%} of {report['total_samples']})")
        lines.append(f"       regime_counts={pr['regime_counts']}")
        for n_folds, fp in pr["fold_projection"].items():
            status = "OK" if fp["clears_floor_every_fold"] else "INFEASIBLE"
            lines.append(f"       n_folds={n_folds}: avg/fold={fp['per_fold_avg']:.1f}  [{status}]")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    for source in ("binance", "hyperliquid"):
        print(format_report(review_source(source)))
