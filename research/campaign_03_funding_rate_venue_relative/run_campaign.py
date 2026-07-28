"""Executes Research Campaign 03's experiments (contrarian, momentum),
independently for Binance and Hyperliquid, each scored against its OWN
locked, venue-relative threshold -- see
docs/RESEARCH_CAMPAIGN_03_funding_rate_venue_relative.md for the full
pre-registration. Reuses Campaign 02's build_samples (PIT construction)
and the same orchestration pattern as Campaign 02's run_campaign.py,
adapted only where genuinely venue-relative: THRESHOLDS is now a
per-source mapping instead of one shared constant, and N_FOLDS is 3
(not 5), per the pre-registration's feasibility review.

Unlike Campaign 02 (Binance screen -> Hyperliquid Production Venue
Validation, one shared threshold), each venue here is an independent,
self-contained test of the same directional hypotheses under its own
correctly-operationalized threshold -- no screen/replicate dependency.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from exchange_adapter import Symbol

from alpha_engine.candidates import funding_rate_candidate_specification
from alpha_engine.governance import GovernanceDecision, GovernanceDecisionType, record_governance_decision
from alpha_engine.historical import load
from alpha_engine.historical.models import FundingRateObservation, MarkPriceObservation
from alpha_engine.historical.storage import series_filename
from alpha_engine.registry import ExperimentRegistry, FileRegistryStorage, LifecycleState
from alpha_engine.research import run_research_cycle

from research.campaign_02_funding_rate.build_samples import build_samples, make_regime_labeler

# ---- Pre-registered constants (LOCKED — docs/RESEARCH_CAMPAIGN_03_funding_rate_venue_relative.md) ----
THRESHOLDS = {
    "binance": "0.0001000000",         # pooled 75th percentile of |funding|, Binance's own distribution
    "hyperliquid": "0.000038592350",   # pooled 75th percentile of |funding|, Hyperliquid's own distribution
}
HORIZON_HOURS = 24
SAMPLE_SPACING_HOURS = 24
CADENCE_SECONDS = HORIZON_HOURS * 3600
MIN_HIT_RATE = 0.55
MIN_SIGNALED_SAMPLES = 100
N_FOLDS = 3   # reduced from Campaign 02's 5 — locked from the outcome-blind feasibility review
N_RESAMPLES = 1000
SEED = 7
_FIXED_CLOCK_TS = "2026-07-24T00:00:00+00:00"

_KNOWN_LIMITATIONS = (
    "Threshold is a pooled 75th percentile of |funding rate|, derived independently from THIS "
    "venue's own historical distribution (venue-relative methodology, locked before any outcome was "
    "examined) -- not the same absolute value used for the other venue. See "
    "docs/RESEARCH_CAMPAIGN_03_funding_rate_venue_relative.md section 1.",
    "n_folds=3 (not 5, unlike Campaigns 01-02) -- reduced from the mandatory pre-registration "
    "feasibility review, which found n_folds=5 structurally infeasible (average per-fold signaled "
    "count below min_signaled_samples regardless of true edge) on both venues at this percentile.",
    "A 75th-percentile cut is a milder 'extreme funding' operationalization than Campaign 02's 90th "
    "percentile -- this result answers a related but distinct question, not a rerun of Campaign 02.",
    "Funding rate is positive-skewed on both venues (see docs/HISTORICAL_DATA.md, "
    "docs/RESEARCH_CAMPAIGN_02_funding_rate.md section 1); a symmetric threshold therefore produces "
    "an asymmetric split of upper- vs lower-tail signals.",
    "24h forward-return horizon; non-overlapping daily samples; signaled_samples counts regime-days, "
    "not fully independent draws given funding's persistence.",
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
    boot_mean_hit_rate: Optional[str] = None
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
        # Mark price is always Binance's series (Campaign 01) -- outcomes are price
        # returns, unaffected by which venue's funding history is under review.
        mark_by_symbol[symbol] = load(root / series_filename("mark_price", symbol, "binance"), MarkPriceObservation)
    return funding_by_symbol, mark_by_symbol


def _spec(direction_convention: str, source: str, universe):
    return funding_rate_candidate_specification(
        version=f"{direction_convention}-{source}-v1",
        universe=tuple(universe),
        cadence_seconds=CADENCE_SECONDS,
        parameters={"threshold": THRESHOLDS[source], "direction_convention": direction_convention},
        acceptance_criteria={"min_hit_rate": MIN_HIT_RATE, "min_signaled_samples": MIN_SIGNALED_SAMPLES},
    )


def _extract(package_dict: Dict[str, Any], stage: str, key: str):
    vr = package_dict.get("validation_results", {}).get(stage)
    return vr.get(key) if isinstance(vr, dict) else None


def _record_governance(registry, experiment_id, evidence_fingerprint, supported) -> str:
    registry.transition(experiment_id, LifecycleState.IN_REVIEW)
    decision_type = GovernanceDecisionType.APPROVE if supported else GovernanceDecisionType.REJECT
    rationale = (
        "Cleared all pre-registered acceptance criteria and validation stages using this venue's own "
        "venue-relative threshold."
        if supported else
        "Failed pre-registered min_hit_rate and/or min_signaled_samples, or a validation stage, using "
        "this venue's own venue-relative threshold: no reliable directional edge found."
    )
    record = record_governance_decision(registry, GovernanceDecision(
        experiment_id=experiment_id, decision=decision_type,
        evidence_fingerprint=evidence_fingerprint,
        proposed_by="researcher-campaign03", reviewed_by="reviewer-campaign03",
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
            registry, "funding_rate_threshold_rule", experiment_id, spec, samples,
            n_folds=N_FOLDS, n_resamples=N_RESAMPLES, seed=SEED,
            known_limitations=_KNOWN_LIMITATIONS, clock=_fixed_clock,
        )
    except Exception as exc:  # noqa: BLE001 -- report, never crash the whole campaign
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


def run(
    *,
    symbols: Tuple[Symbol, ...] = _DEFAULT_SYMBOLS,
    source: str = "binance",
    storage_root: str = "data/alpha_engine_historical",
    registry_path: str = "data/alpha_engine_research/campaign_03.jsonl",
    label: str = "combined",
    record_governance: bool = False,
) -> CampaignReport:
    """Runs both pre-registered experiments (contrarian, momentum) over the
    given symbol set and funding source (each source uses its OWN locked
    threshold from THRESHOLDS), returns a structured report."""
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
        _run_experiment(registry, f"camp03-{source}-{label}-contrarian", "contrarian", source,
                        built.samples, symbols, record_governance=record_governance),
        _run_experiment(registry, f"camp03-{source}-{label}-momentum", "momentum", source,
                        built.samples, symbols, record_governance=record_governance),
    ]

    return CampaignReport(
        sample_count=len(built.samples),
        sample_diagnostics=built.diagnostics,
        experiments=experiments,
    )


def run_all(source: str = "binance", storage_root: str = "data/alpha_engine_historical"):
    """Runs each symbol individually AND the pooled (combined) universe.
    Governance decisions are recorded only for the combined dataset (the
    pre-registered, statistically-powered analysis)."""
    datasets = {
        "BTC": (Symbol("BTC"),), "ETH": (Symbol("ETH"),), "SOL": (Symbol("SOL"),),
        "combined": _DEFAULT_SYMBOLS,
    }
    reports = {}
    for label, syms in datasets.items():
        reports[label] = run(
            symbols=syms, source=source, storage_root=storage_root, label=label,
            record_governance=(label == "combined"),
        )
    return reports


def format_report(label: str, report: CampaignReport) -> str:
    lines = [f"=== Campaign 03 — Funding Rate (venue-relative) [{label}] ===",
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
