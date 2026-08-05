"""Research Campaign 07 — Longer-Horizon Open Interest. Orchestration only.

Every decision (horizons, thresholds, criteria) is PRE-REGISTERED in
docs/RESEARCH_CAMPAIGN_07_oi_long_horizon.md and frozen in the constants
below. Runs against a fixed clock and fixed seed so the run is
deterministic and reproducible.

Reuses research.campaign_01_open_interest.build_samples UNCHANGED: the
feature construction, point-in-time discipline and non-overlap assertion
are identical to CAMP-01 and already unit-tested. This campaign varies
ONLY the forward-return horizon and the extremeness threshold.

Run: python -m research.campaign_07_oi_long_horizon.run_campaign
"""

import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from exchange_adapter import Symbol

from alpha_engine.candidates import open_interest_extremeness_candidate_specification
from alpha_engine.features import PCTRANK_NAME, PCTRANK_VERSION
from alpha_engine.governance import (
    GovernanceDecision,
    GovernanceDecisionType,
    record_governance_decision,
)
from alpha_engine.historical import load
from alpha_engine.historical.models import MarkPriceObservation, OpenInterestObservation
from alpha_engine.historical.storage import series_filename
from alpha_engine.registry import ExperimentRegistry, FileRegistryStorage, LifecycleState
from alpha_engine.research import run_research_cycle
from alpha_engine.watchlist import Watchlist

from research.campaign_01_open_interest.build_samples import build_samples, make_regime_labeler

# ---- Pre-registered constants (LOCKED -- see the campaign doc) ----
WINDOW_DAYS = 30
MIN_HIT_RATE = 0.55
MIN_SIGNALED_SAMPLES = 100
N_FOLDS = 3
N_RESAMPLES = 1000
SEED = 7

# (horizon_hours, threshold, role). Sample spacing ALWAYS equals the
# horizon, so outcome windows are strictly non-overlapping.
CONFIGURATIONS: Tuple[Tuple[int, str, str], ...] = (
    (72, "0.40", "PRIMARY"),
    (72, "0.25", "robustness-threshold"),
    (120, "0.40", "robustness-horizon"),
)
DIRECTIONS = ("contrarian", "momentum")

_FIXED_CLOCK_TS = "2026-08-05T00:00:00+00:00"
_KNOWN_LIMITATIONS = (
    "Binance USDT-perp data used as a cross-venue proxy for the live Hyperliquid venue "
    "(different mark formula, funding cadence, trader population) -- not venue-exact.",
    "DEFER-CEILING, knowledge-only: no Hyperliquid historical open-interest source exists, "
    "so a positive result is NOT promotion-eligible under Constitution Section 6.",
    "Outcome derived as sum_open_interest_value / sum_open_interest, sharing the "
    "sum_open_interest field with the feature. Cancellation verified against an independent "
    "price source (Hyperliquid daily candles, 367d): agreement within +/-0.03 in every symbol "
    "and volatility stratum, r=+0.89-0.92 between sources, coupling POSITIVE where an artifact "
    "would be negative. Independent validation covers 18% of the campaign window.",
    "Survivorship bias: BTC/ETH/SOL selected in 2026, tested from 2021/2022.",
    "Non-stationarity: window spans two halvings and the ETF era.",
    "Asymmetric per-symbol starts: BTC 2021-01, ETH/SOL 2022-01.",
    "Non-overlapping forward-return windows at 72h/120h; OI extremeness measured as a "
    "30-day trailing rolling normalization (point-in-time).",
    "OI magnitude does not reveal positioning side -- the tail->direction mapping is a tested "
    "structural assumption, not a known fact.",
)

_DEFAULT_SYMBOLS = (Symbol("BTC"), Symbol("ETH"), Symbol("SOL"))


def _fixed_clock() -> str:
    return _FIXED_CLOCK_TS


@dataclass
class ExperimentReport:
    experiment_id: str
    horizon_hours: int
    threshold: str
    role: str
    direction_convention: str
    total_samples: int
    signaled_samples: Optional[int] = None
    hit_rate: Optional[str] = None
    mean_directional_return: Optional[str] = None
    boot_mean_hit_rate: Optional[str] = None
    boot_fraction_meeting_bar: Optional[str] = None
    single_pass_passed: Optional[bool] = None
    causality_passed: Optional[bool] = None
    walk_forward_passed: Optional[bool] = None
    regime_passed: Optional[bool] = None
    evidence_fingerprint: Optional[str] = None
    overall_verdict: str = "INSUFFICIENT DATA"
    governance_outcome: Optional[str] = None
    error: Optional[str] = None


@dataclass
class CampaignReport:
    sample_counts: Dict[int, int]
    sample_diagnostics: Dict[int, Dict[str, int]]
    experiments: List[ExperimentReport]


def _load_series(symbols, storage_root: str):
    root = Path(storage_root)
    oi, mark = {}, {}
    for symbol in symbols:
        oi[symbol] = load(root / series_filename("open_interest", symbol, "binance"), OpenInterestObservation)
        mark[symbol] = load(root / series_filename("mark_price", symbol, "binance"), MarkPriceObservation)
    return oi, mark


def _spec(horizon_hours: int, threshold: str, direction_convention: str, universe):
    return open_interest_extremeness_candidate_specification(
        version=f"h{horizon_hours}-t{threshold.replace('.', '')}-{direction_convention}-v1",
        universe=tuple(universe),
        feature_name=PCTRANK_NAME, feature_version=PCTRANK_VERSION,
        cadence_seconds=horizon_hours * 3600,
        parameters={"threshold": threshold, "direction_convention": direction_convention},
        acceptance_criteria={"min_hit_rate": MIN_HIT_RATE, "min_signaled_samples": MIN_SIGNALED_SAMPLES},
    )


def _extract(pkg: Dict[str, Any], stage: str, key: str):
    vr = pkg.get("validation_results", {}).get(stage)
    return vr.get(key) if isinstance(vr, dict) else None


def _record_governance(registry, experiment_id, evidence_fingerprint, supported) -> str:
    registry.transition(experiment_id, LifecycleState.IN_REVIEW)
    decision_type = GovernanceDecisionType.APPROVE if supported else GovernanceDecisionType.REJECT
    rationale = (
        "Cleared all pre-registered acceptance criteria and validation stages."
        if supported else
        "Failed pre-registered min_hit_rate (or signalled-sample floor): no reliable "
        "directional edge at this horizon; hit rate indistinguishable from chance."
    )
    record = record_governance_decision(registry, GovernanceDecision(
        experiment_id=experiment_id, decision=decision_type,
        evidence_fingerprint=evidence_fingerprint,
        proposed_by="researcher-campaign07", reviewed_by="reviewer-campaign07",
        rationale=rationale, decided_at_utc=_FIXED_CLOCK_TS,
    ))
    return f"{record.lifecycle_state.value.upper()} (reviewer!=researcher, fingerprint verified)"


def _run_experiment(registry, experiment_id, horizon_hours, threshold, role,
                    direction_convention, samples, universe,
                    record_governance=True) -> ExperimentReport:
    base = ExperimentReport(
        experiment_id=experiment_id, horizon_hours=horizon_hours, threshold=threshold,
        role=role, direction_convention=direction_convention, total_samples=len(samples),
    )
    if len(samples) < N_FOLDS:
        base.error = f"only {len(samples)} samples (< n_folds={N_FOLDS})"
        return base
    spec = _spec(horizon_hours, threshold, direction_convention, universe)
    try:
        result = run_research_cycle(
            registry, "open_interest_extremeness_rule", experiment_id, spec, samples,
            n_folds=N_FOLDS, n_resamples=N_RESAMPLES, seed=SEED,
            known_limitations=_KNOWN_LIMITATIONS, clock=_fixed_clock,
        )
    except Exception as exc:  # noqa: BLE001 -- report, never crash the campaign
        base.overall_verdict = "ERROR"
        base.error = f"{type(exc).__name__}: {exc}"
        return base

    pkg = result.package.to_dict()
    single = pkg.get("validation_results", {}).get("single_pass", {})
    boot = pkg.get("validation_results", {}).get("bootstrap_resampling", {})
    base.signaled_samples = single.get("signaled_samples")
    base.hit_rate = single.get("hit_rate")
    base.mean_directional_return = single.get("mean_directional_return")
    base.boot_mean_hit_rate = boot.get("mean_hit_rate")
    base.boot_fraction_meeting_bar = boot.get("fraction_meeting_min_hit_rate")
    base.single_pass_passed = _extract(pkg, "single_pass", "overall_passed")
    base.causality_passed = _extract(pkg, "leakage_causality_audit", "passed")
    base.walk_forward_passed = _extract(pkg, "walk_forward", "overall_passed")
    base.regime_passed = _extract(pkg, "regime_stratification", "overall_passed")
    base.evidence_fingerprint = result.record.evidence_fingerprint

    passed_all = bool(base.single_pass_passed and base.causality_passed
                      and base.walk_forward_passed and base.regime_passed)
    base.overall_verdict = "SUPPORTED (advance to review)" if passed_all else "REJECTED"
    if record_governance:
        base.governance_outcome = _record_governance(
            registry, experiment_id, result.record.evidence_fingerprint, passed_all)
    return base


def run(
    *,
    symbols: Tuple[Symbol, ...] = _DEFAULT_SYMBOLS,
    storage_root: str = "data/alpha_engine_historical",
    registry_path: str = "data/alpha_engine_research/campaign_07.jsonl",
    record_governance: bool = True,
) -> CampaignReport:
    """Runs the six pre-registered experiments. No collection: Campaign 07
    uses data already on disk (Backlog 2.1)."""
    _ = Watchlist(name="campaign-07", symbols=tuple(symbols))  # universe discipline

    oi_by_symbol, mark_by_symbol = _load_series(symbols, storage_root)
    btc_mark = load(
        Path(storage_root) / series_filename("mark_price", Symbol("BTC"), "binance"),
        MarkPriceObservation,
    )
    labeler = make_regime_labeler(btc_mark) if btc_mark else None

    reg_path = Path(registry_path)
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    if reg_path.exists():
        reg_path.unlink()  # fresh registry per run so re-execution is reproducible
    registry = ExperimentRegistry(FileRegistryStorage(str(reg_path)))

    # Build once per distinct horizon; thresholds reuse the same samples.
    horizons = sorted({h for h, _, _ in CONFIGURATIONS})
    built = {}
    for h in horizons:
        built[h] = build_samples(
            oi_by_symbol, mark_by_symbol,
            window_days=WINDOW_DAYS, horizon_hours=h,
            sample_spacing_hours=h, regime_labeler=labeler,
        )

    experiments: List[ExperimentReport] = []
    for horizon, threshold, role in CONFIGURATIONS:
        samples = built[horizon].pctrank_samples
        for direction in DIRECTIONS:
            eid = f"camp07-h{horizon}-t{threshold.replace('.', '')}-{direction}"
            experiments.append(_run_experiment(
                registry, eid, horizon, threshold, role, direction, samples, symbols,
                record_governance=record_governance,
            ))

    return CampaignReport(
        sample_counts={h: len(built[h].pctrank_samples) for h in horizons},
        sample_diagnostics={h: built[h].diagnostics for h in horizons},
        experiments=experiments,
    )


def signalled_census(built_samples, threshold: str, n_folds: int = N_FOLDS):
    """Per-fold signalled counts for a sample set at a threshold.
    Outcome-blind: inspects only the feature value."""
    thr = Decimal(threshold)
    ordered = sorted(built_samples, key=lambda s: s.feature_value.computed_at_utc)
    sig = [1 if abs(s.feature_value.value) >= thr else 0 for s in ordered]
    n = len(sig)
    base, rem = divmod(n, n_folds)
    out, start = [], 0
    for i in range(n_folds):
        size = base + (1 if i < rem else 0)
        out.append(sum(sig[start:start + size]))
        start += size
    return out


def format_report(report: CampaignReport) -> str:
    lines = ["=== Research Campaign 07 — Longer-Horizon Open Interest ==="]
    for h, n in sorted(report.sample_counts.items()):
        lines.append(f"horizon {h}h: {n:,} pooled non-overlapping samples   "
                     f"diagnostics={report.sample_diagnostics[h]}")
    lines.append("")
    for e in report.experiments:
        lines.append(f"[{e.experiment_id}]  ({e.horizon_hours}h / thr {e.threshold} / "
                     f"{e.direction_convention} / {e.role})")
        lines.append(f"    total={e.total_samples} signaled={e.signaled_samples} "
                     f"hit_rate={e.hit_rate} mean_ret={e.mean_directional_return}")
        lines.append(f"    boot_mean_hit={e.boot_mean_hit_rate} "
                     f"boot_frac_meeting_bar={e.boot_fraction_meeting_bar}")
        lines.append(f"    single_pass={e.single_pass_passed} causality={e.causality_passed} "
                     f"walk_forward={e.walk_forward_passed} regime={e.regime_passed}")
        lines.append(f"    VERDICT: {e.overall_verdict}" + (f"  ({e.error})" if e.error else ""))
        if e.governance_outcome:
            lines.append(f"    GOVERNANCE: {e.governance_outcome}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    report = run()
    print(format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
