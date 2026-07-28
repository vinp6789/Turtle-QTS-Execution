"""Executes Campaign 04's experiments (contrarian, momentum), independently
for Binance and Hyperliquid, each scored against its OWN locked
venue-relative delta threshold. Full pre-registration:
docs/RESEARCH_CAMPAIGN_04_funding_delta.md.

Reuses the `funding_rate_threshold_rule` candidate MECHANISM via a
CandidateSpecification whose feature identity is `funding_delta` (the
mechanism is feature-agnostic: it compares the feature value against
+/- threshold under a direction convention). Every locked parameter is a
module constant; NONE may change after results are observed.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from exchange_adapter import Symbol

from alpha_engine.candidates import CandidateSpecification
from alpha_engine.governance import GovernanceDecision, GovernanceDecisionType, record_governance_decision
from alpha_engine.historical import load
from alpha_engine.historical.models import FundingRateObservation, MarkPriceObservation
from alpha_engine.historical.storage import series_filename
from alpha_engine.registry import ExperimentRegistry, FileRegistryStorage, LifecycleState
from alpha_engine.research import run_research_cycle

from .build_samples import build_samples, make_regime_labeler, FEATURE_NAME, FEATURE_VERSION

# ---- Pre-registered constants (LOCKED — docs/RESEARCH_CAMPAIGN_04_funding_delta.md) ----
THRESHOLDS = {
    "binance": "0.00005239",       # per-venue 75th percentile of |funding_delta|, Binance own distribution
    "hyperliquid": "0.00001205",   # per-venue 75th percentile of |funding_delta|, Hyperliquid own distribution
}
CANDIDATE_NAME = "funding_rate_threshold_rule"
CANDIDATE_TYPE = "rule_based"
HORIZON_HOURS = 24
SAMPLE_SPACING_HOURS = 24
CADENCE_SECONDS = HORIZON_HOURS * 3600
MIN_HIT_RATE = 0.55
MIN_SIGNALED_SAMPLES = 100
N_FOLDS = 3   # locked from feasibility: max fold count clearing >=100 signalled/fold at p75, both venues
N_RESAMPLES = 1000
SEED = 7
_FIXED_CLOCK_TS = "2026-07-24T00:00:00+00:00"

_KNOWN_LIMITATIONS = (
    "Feature is funding_delta (first difference of consecutive funding settlements), threshold is the "
    "per-venue 75th percentile of |funding_delta| from THIS venue's own distribution (venue-relative, "
    "locked before any outcome examined). See docs/RESEARCH_CAMPAIGN_04_funding_delta.md.",
    "n_folds=3 (not 5): the max fold count clearing the 100-signalled/fold walk-forward floor at the "
    "p75 threshold on both venues; n_folds=5 was infeasible on Binance.",
    "Moderate non-stationarity: |delta| magnitude rose ~40-70% across the window; under a fixed "
    "full-sample threshold, later folds signal somewhat more than earlier ones.",
    "High-|delta| observations are ~70% bull-regime concentrated (Binance 71%, Hyperliquid 69%) -- a "
    "regime confound the stratification stage scrutinizes.",
    "delta is rank-orthogonal to funding level on Binance (Spearman ~0) but moderately correlated on "
    "Hyperliquid (Spearman ~0.5); a Hyperliquid positive carries a mild level-confound.",
    "High zero-delta mass (~30% Binance, ~40% Hyperliquid) from clamped/repeated funding values; zeros "
    "are non-signals by construction.",
    "24h forward-return horizon; non-overlapping daily samples; residual daily |delta| autocorrelation "
    "0.02-0.38 (N_eff ~247-526) -- signalled samples retain mild dependence.",
)

_DEFAULT_SYMBOLS = (Symbol("BTC"), Symbol("ETH"), Symbol("SOL"))


def _fixed_clock() -> str:
    return _FIXED_CLOCK_TS


@dataclass
class ExperimentReport:
    experiment_id: str
    direction_convention: str
    source: str
    total_samples: int
    signaled_samples: Optional[int] = None
    hit_rate: Optional[str] = None
    mean_directional_return: Optional[str] = None
    boot_min_hit_rate: Optional[str] = None
    boot_max_hit_rate: Optional[str] = None
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
    sample_count: int
    sample_diagnostics: Dict[str, int]
    experiments: List[ExperimentReport]


def _load_series(symbols, source: str, storage_root: str):
    funding_by_symbol = {}
    mark_by_symbol = {}
    root = Path(storage_root)
    for symbol in symbols:
        funding_by_symbol[symbol] = load(root / series_filename("funding_rate", symbol, source), FundingRateObservation)
        mark_by_symbol[symbol] = load(root / series_filename("mark_price", symbol, "binance"), MarkPriceObservation)
    return funding_by_symbol, mark_by_symbol


def _spec(direction_convention: str, source: str, universe) -> CandidateSpecification:
    """Directly-constructed spec: candidate MECHANISM is
    funding_rate_threshold_rule, feature identity is funding_delta."""
    return CandidateSpecification(
        name=CANDIDATE_NAME,
        version=f"{direction_convention}-{source}-v1",
        candidate_type=CANDIDATE_TYPE,
        universe=tuple(universe),
        feature_name=FEATURE_NAME,
        feature_version=FEATURE_VERSION,
        cadence_seconds=CADENCE_SECONDS,
        acceptance_criteria={"min_hit_rate": MIN_HIT_RATE, "min_signaled_samples": MIN_SIGNALED_SAMPLES},
        parameters={"threshold": THRESHOLDS[source], "direction_convention": direction_convention},
    )


def _extract(pkg: Dict[str, Any], stage: str, key: str):
    vr = pkg.get("validation_results", {}).get(stage)
    return vr.get(key) if isinstance(vr, dict) else None


def _record_governance(registry, experiment_id, fingerprint, supported) -> str:
    registry.transition(experiment_id, LifecycleState.IN_REVIEW)
    decision = GovernanceDecisionType.APPROVE if supported else GovernanceDecisionType.REJECT
    rationale = (
        "Cleared all pre-registered acceptance criteria and validation stages using this venue's own "
        "venue-relative funding_delta threshold."
        if supported else
        "Failed pre-registered min_hit_rate and/or min_signaled_samples, or a validation stage, using "
        "this venue's own venue-relative funding_delta threshold: no reliable directional edge found."
    )
    record = record_governance_decision(registry, GovernanceDecision(
        experiment_id=experiment_id, decision=decision, evidence_fingerprint=fingerprint,
        proposed_by="researcher-campaign04", reviewed_by="reviewer-campaign04",
        rationale=rationale, decided_at_utc=_FIXED_CLOCK_TS,
    ))
    return f"{record.lifecycle_state.value.upper()} (reviewer!=researcher, fingerprint verified)"


def _run_experiment(registry, experiment_id, direction_convention, source, samples, universe,
                    record_governance=False) -> ExperimentReport:
    spec = _spec(direction_convention, source, universe)
    base = ExperimentReport(
        experiment_id=experiment_id, direction_convention=direction_convention,
        source=source, total_samples=len(samples),
    )
    if len(samples) < N_FOLDS:
        base.error = f"only {len(samples)} samples (< n_folds={N_FOLDS})"
        return base
    try:
        result = run_research_cycle(
            registry, CANDIDATE_NAME, experiment_id, spec, samples,
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
    base.boot_min_hit_rate = boot.get("min_hit_rate_observed")
    base.boot_max_hit_rate = boot.get("max_hit_rate_observed")
    base.boot_fraction_meeting_bar = boot.get("fraction_meeting_min_hit_rate")
    base.single_pass_passed = _extract(pkg, "single_pass", "overall_passed")
    base.causality_passed = _extract(pkg, "leakage_causality_audit", "passed")
    base.walk_forward_passed = _extract(pkg, "walk_forward", "overall_passed")
    base.regime_passed = _extract(pkg, "regime_stratification", "overall_passed")
    base.evidence_fingerprint = result.record.evidence_fingerprint

    passed_all = bool(base.single_pass_passed and base.causality_passed
                      and base.walk_forward_passed and base.regime_passed)
    base.overall_verdict = "SUPPORTED" if passed_all else "REJECTED"
    if record_governance:
        base.governance_outcome = _record_governance(
            registry, experiment_id, result.record.evidence_fingerprint, passed_all)
    return base


def run(*, symbols=_DEFAULT_SYMBOLS, source="binance",
        storage_root="data/alpha_engine_historical",
        registry_path="data/alpha_engine_research/campaign_04.jsonl",
        label="combined", record_governance=False) -> CampaignReport:
    funding_by_symbol, mark_by_symbol = _load_series(symbols, source, storage_root)
    btc_mark = mark_by_symbol.get(Symbol("BTC"), ())
    labeler = make_regime_labeler(btc_mark) if btc_mark else None

    built = build_samples(
        funding_by_symbol, mark_by_symbol,
        horizon_hours=HORIZON_HOURS, sample_spacing_hours=SAMPLE_SPACING_HOURS,
        regime_labeler=labeler,
    )

    reg_path = registry_path.replace(".jsonl", f"_{source}_{label}.jsonl")
    Path(reg_path).parent.mkdir(parents=True, exist_ok=True)
    if Path(reg_path).exists():
        Path(reg_path).unlink()
    registry = ExperimentRegistry(FileRegistryStorage(reg_path))

    experiments = [
        _run_experiment(registry, f"camp04-{source}-{label}-contrarian", "contrarian", source,
                        built.samples, symbols, record_governance=record_governance),
        _run_experiment(registry, f"camp04-{source}-{label}-momentum", "momentum", source,
                        built.samples, symbols, record_governance=record_governance),
    ]
    return CampaignReport(sample_count=len(built.samples),
                          sample_diagnostics=built.diagnostics, experiments=experiments)


def run_all(source="binance", storage_root="data/alpha_engine_historical"):
    datasets = {"BTC": (Symbol("BTC"),), "ETH": (Symbol("ETH"),), "SOL": (Symbol("SOL"),),
                "combined": _DEFAULT_SYMBOLS}
    return {label: run(symbols=syms, source=source, storage_root=storage_root, label=label,
                       record_governance=(label == "combined"))
            for label, syms in datasets.items()}


def format_report(label: str, report: CampaignReport) -> str:
    lines = [f"=== Campaign 04 — Funding Delta [{label}] ===",
             f"samples: {report.sample_count}   diagnostics: {report.sample_diagnostics}", ""]
    for e in report.experiments:
        lines.append(f"[{e.experiment_id}]  ({e.direction_convention}, source={e.source})")
        lines.append(f"    total={e.total_samples} signaled={e.signaled_samples} "
                     f"hit_rate={e.hit_rate} mean_ret={e.mean_directional_return}")
        lines.append(f"    boot[{e.boot_min_hit_rate}..{e.boot_max_hit_rate}] "
                     f"frac_meet_bar={e.boot_fraction_meeting_bar}")
        lines.append(f"    single_pass={e.single_pass_passed} causality={e.causality_passed} "
                     f"walk_forward={e.walk_forward_passed} regime={e.regime_passed}")
        lines.append(f"    VERDICT: {e.overall_verdict}" + (f"  ({e.error})" if e.error else ""))
        if e.governance_outcome:
            lines.append(f"    GOVERNANCE: {e.governance_outcome}")
        lines.append("")
    return "\n".join(lines)
