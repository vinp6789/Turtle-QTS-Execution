"""Research Campaign 08 — Hourly Liquidation Density. Orchestration only.

Every decision is PRE-REGISTERED in
docs/RESEARCH_CAMPAIGN_08_liquidation_hourly.md and frozen in the
constants below. Fixed clock, fixed seed: deterministic and reproducible.

Uses the `liquidation_density_rule` family (Backlog 3.7b) so every
evidence package identifies the feature as liquidation density -- never
funding_rate, which is what reusing the funding family would have
recorded.

Run: python -m research.campaign_08_liquidation_hourly.run_campaign
"""

import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from exchange_adapter import Symbol

from alpha_engine.candidates import liquidation_density_candidate_specification
from alpha_engine.governance import (
    GovernanceDecision,
    GovernanceDecisionType,
    record_governance_decision,
)
from alpha_engine.registry import ExperimentRegistry, FileRegistryStorage, LifecycleState
from alpha_engine.research import run_research_cycle
from alpha_engine.watchlist import Watchlist

from .build_samples import build_samples, load_hourly_prices, make_regime_labeler

# ---- Pre-registered constants (LOCKED -- see the campaign doc) ----
PERCENTILE = 75                 # per-symbol threshold; p90/p99 excluded on measurement
THRESHOLD = "1.0"               # value is count/p75(symbol), so 1.0 == "count >= p75"
HORIZON_HOURS = 1
MIN_HIT_RATE = 0.55
MIN_SIGNALED_SAMPLES = 100
N_FOLDS = (3, 5)                # 3 = PRIMARY, 5 = robustness
N_RESAMPLES = 1000
SEED = 7
DIRECTIONS = ("contrarian", "momentum")

_FIXED_CLOCK_TS = "2026-08-05T00:00:00+00:00"
_SYMBOLS = (Symbol("BTC"), Symbol("ETH"), Symbol("SOL"))
_KNOWN_LIMITATIONS = (
    "Zero-inflation: 51-65% of hours have zero liquidation events. CAMP-05's "
    "'continuous threshold, zero ties' criterion is NOT met; the threshold is well defined "
    "only because p75 sits above the zero mass.",
    "Window bounded by VENUE RETENTION, not by data: Hyperliquid retains 1h candles ~210 days, "
    "so 200 usable days of a 366-day liquidation archive. The Live Recorder (RD-18) removes this "
    "constraint for future data only.",
    "High cross-symbol dependence: rho_bar +0.731, N_eff 1.22 of 3 symbols -- pooling three "
    "symbols buys ~1.2 symbols' worth of independent information.",
    "Short window: ~6.5 months, versus the 18-month windows Campaigns 01-05 used. Regime "
    "coverage is correspondingly narrow.",
    "Liquidation counts do not reveal which side was liquidated -- the density->direction "
    "mapping is a tested structural assumption, not a known fact.",
    "Derivation scope (RD-11 A): feature is a raw hourly count; the per-symbol p75 threshold is "
    "FULL-SAMPLE, a recorded methodological impurity (RD-11 E), the same scope CAMP-02/03 carried.",
    "Backtests flatter. Single-pass results are the most optimistic number here and should carry "
    "the least weight. The walk-forward stage checks whether one fixed, pre-registered rule holds "
    "across chronological periods -- it is NOT an out-of-sample generalization test: no parameter "
    "is refit per fold. Treat every number as an upper bound on what live trading would deliver, "
    "before fees, slippage, and execution costs -- none of which are modelled.",
)


def _fixed_clock() -> str:
    return _FIXED_CLOCK_TS


@dataclass
class ExperimentReport:
    experiment_id: str
    n_folds: int
    direction_convention: str
    role: str
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
    feature_name_recorded: Optional[str] = None
    overall_verdict: str = "INSUFFICIENT DATA"
    governance_outcome: Optional[str] = None
    error: Optional[str] = None


@dataclass
class CampaignReport:
    sample_count: int
    diagnostics: Dict[str, Any]
    scale: Dict[str, Decimal]
    experiments: List[ExperimentReport]


def _spec(n_folds: int, direction: str, universe):
    return liquidation_density_candidate_specification(
        version=f"p{PERCENTILE}-f{n_folds}-{direction}-v1",
        universe=tuple(universe),
        cadence_seconds=HORIZON_HOURS * 3600,
        parameters={"threshold": THRESHOLD, "direction_convention": direction,
                    "percentile": PERCENTILE, "horizon_hours": HORIZON_HOURS},
        acceptance_criteria={"min_hit_rate": MIN_HIT_RATE,
                             "min_signaled_samples": MIN_SIGNALED_SAMPLES},
    )


def _extract(pkg: Dict[str, Any], stage: str, key: str):
    vr = pkg.get("validation_results", {}).get(stage)
    return vr.get(key) if isinstance(vr, dict) else None


def _record_governance(registry, experiment_id, fingerprint, supported) -> str:
    registry.transition(experiment_id, LifecycleState.IN_REVIEW)
    decision = GovernanceDecisionType.APPROVE if supported else GovernanceDecisionType.REJECT
    rationale = (
        "Cleared all pre-registered acceptance criteria and validation stages."
        if supported else
        "Failed pre-registered min_hit_rate (or signalled-sample floor): no reliable "
        "directional edge from hourly liquidation density."
    )
    record = record_governance_decision(registry, GovernanceDecision(
        experiment_id=experiment_id, decision=decision, evidence_fingerprint=fingerprint,
        proposed_by="researcher-campaign08", reviewed_by="reviewer-campaign08",
        rationale=rationale, decided_at_utc=_FIXED_CLOCK_TS,
    ))
    return f"{record.lifecycle_state.value.upper()} (reviewer!=researcher, fingerprint verified)"


def _run_experiment(registry, eid, n_folds, direction, role, samples, universe) -> ExperimentReport:
    base = ExperimentReport(experiment_id=eid, n_folds=n_folds, direction_convention=direction,
                            role=role, total_samples=len(samples))
    spec = _spec(n_folds, direction, universe)
    base.feature_name_recorded = spec.feature_name
    try:
        result = run_research_cycle(
            registry, "liquidation_density_rule", eid, spec, samples,
            n_folds=n_folds, n_resamples=N_RESAMPLES, seed=SEED,
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
    passed = bool(base.single_pass_passed and base.causality_passed
                  and base.walk_forward_passed and base.regime_passed)
    base.overall_verdict = "SUPPORTED (advance to review)" if passed else "REJECTED"
    base.governance_outcome = _record_governance(
        registry, eid, result.record.evidence_fingerprint, passed)
    return base


def run(symbols=_SYMBOLS,
        registry_path: str = "data/alpha_engine_research/campaign_08.jsonl") -> CampaignReport:
    _ = Watchlist(name="campaign-08", symbols=tuple(symbols))  # universe discipline

    prices = load_hourly_prices(symbols)
    labeler = make_regime_labeler(prices["BTC"])
    built = build_samples(symbols, horizon_hours=HORIZON_HOURS,
                          percentile_threshold=PERCENTILE, regime_labeler=labeler)

    reg_path = Path(registry_path)
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    if reg_path.exists():
        reg_path.unlink()  # fresh registry per run so re-execution is reproducible
    registry = ExperimentRegistry(FileRegistryStorage(str(reg_path)))

    experiments = []
    for n_folds in N_FOLDS:
        role = "PRIMARY" if n_folds == 3 else "robustness-folds"
        for direction in DIRECTIONS:
            eid = f"camp08-p{PERCENTILE}-f{n_folds}-{direction}"
            experiments.append(_run_experiment(
                registry, eid, n_folds, direction, role, built.samples, symbols))

    return CampaignReport(sample_count=len(built.samples), diagnostics=built.diagnostics,
                          scale=built.scale, experiments=experiments)


def format_report(report: CampaignReport) -> str:
    lines = ["=== Research Campaign 08 — Hourly Liquidation Density ==="]
    lines.append(f"samples: {report.sample_count:,}   diagnostics: {report.diagnostics}")
    lines.append(f"per-symbol p{PERCENTILE} thresholds (counts/hour): "
                 + "  ".join(f"{k}={v}" for k, v in sorted(report.scale.items())))
    lines.append("")
    for e in report.experiments:
        lines.append(f"[{e.experiment_id}]  (folds={e.n_folds} / {e.direction_convention} / {e.role})")
        lines.append(f"    feature recorded in evidence: {e.feature_name_recorded}")
        lines.append(f"    total={e.total_samples:,} signaled={e.signaled_samples} "
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
    print(format_report(run()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
