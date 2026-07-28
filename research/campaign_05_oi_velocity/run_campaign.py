"""Executes Campaign 05's experiments (contrarian, momentum) on Binance
Open Interest, scored against the locked venue-relative velocity
threshold. Full pre-registration:
docs/RESEARCH_CAMPAIGN_05_oi_velocity.md (accepted as RD-08).

Reuses the `funding_rate_threshold_rule` candidate MECHANISM (signed
threshold + direction convention — feature-agnostic) via a
CandidateSpecification whose feature identity is `oi_velocity`. Every
locked parameter is a module constant; NONE may change after results are
observed.

GOVERNANCE CEILING — DEFER, NEVER APPROVE. Open Interest has no
Hyperliquid historical source, so per docs/RESEARCH_PLAYBOOK.md section 5
the venue-replication check can never be satisfied and this hypothesis
"cannot be APPROVE -- it is REJECT or DEFER". `_record_governance` below
therefore emits only GovernanceDecisionType.REJECT (failed its own
pre-registered bar) or GovernanceDecisionType.DEFER (cleared its bar, but
promotion is structurally blocked pending Hyperliquid-native OI history).
APPROVE is unreachable by construction, not by convention.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from exchange_adapter import Symbol

from alpha_engine.candidates import CandidateSpecification
from alpha_engine.governance import GovernanceDecision, GovernanceDecisionType, record_governance_decision
from alpha_engine.historical import load
from alpha_engine.historical.models import MarkPriceObservation, OpenInterestObservation
from alpha_engine.historical.storage import series_filename
from alpha_engine.registry import ExperimentRegistry, FileRegistryStorage, LifecycleState
from alpha_engine.research import run_research_cycle

from .build_samples import build_samples, make_regime_labeler, FEATURE_NAME, FEATURE_VERSION

# ---- Pre-registered constants (LOCKED — docs/RESEARCH_CAMPAIGN_05_oi_velocity.md) ----
THRESHOLD = "0.037901"        # pooled 75th percentile of |oi_velocity|, Binance, OI>0-filtered
CANDIDATE_NAME = "funding_rate_threshold_rule"
CANDIDATE_TYPE = "rule_based"
SOURCE = "binance"            # Binance only — no Hyperliquid OI history exists
HORIZON_HOURS = 24
SAMPLE_SPACING_HOURS = 24
CADENCE_SECONDS = HORIZON_HOURS * 3600
MIN_HIT_RATE = 0.55
MIN_SIGNALED_SAMPLES = 100
N_FOLDS = 3                   # locked from feasibility: max folds clearing >=100 signalled/fold at p75
N_RESAMPLES = 1000
SEED = 7
_FIXED_CLOCK_TS = "2026-07-24T00:00:00+00:00"

_KNOWN_LIMITATIONS = (
    "GOVERNANCE CEILING -- DEFER, NEVER APPROVE: Open Interest has no Hyperliquid historical source "
    "(docs/HISTORICAL_DATA.md section 1), so the DEX-first venue-replication check of "
    "docs/RESEARCH_PLAYBOOK.md section 5 can never be satisfied. This is a standing structural blocker "
    "to promotion, not a checkbox to satisfy later. A passing result is validated KNOWLEDGE, never a "
    "promotable alpha.",
    "Single-venue (Binance) by necessity: no venue replication is possible, so any positive result is "
    "CEX-only and not venue-validated.",
    "Feature is oi_velocity (24h FRACTIONAL change of Open Interest); fractional form is required "
    "because Campaign 01 established raw OI is strongly non-stationary (~3.4x secular growth) -- a raw "
    "delta would inherit that non-stationarity. Threshold is the pooled 75th percentile of "
    "|oi_velocity| from Binance's own OI>0-filtered distribution.",
    "LOCKED OI>0 data-validity rule: a sample is constructed only if both endpoint OI observations are "
    "strictly positive. Zero-OI archive snapshots are impossible values (missing-data artifacts), not "
    "genuine market events; they are skipped, never fabricated or clamped.",
    "n_folds=3 (not 5): the max fold count clearing the 100-signalled/fold walk-forward floor at the "
    "p75 threshold; n_folds=5 was infeasible.",
    "High-|velocity| observations are ~57% bull-regime concentrated -- a regime confound the "
    "stratification stage scrutinizes.",
    "Single 18-month window; 24h forward-return horizon; non-overlapping daily samples. Residual daily "
    "|velocity| autocorrelation 0.02-0.13 (N_eff ~405-523).",
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


def _load_series(symbols, storage_root: str):
    oi_by_symbol = {}
    mark_by_symbol = {}
    root = Path(storage_root)
    for symbol in symbols:
        oi_by_symbol[symbol] = load(root / series_filename("open_interest", symbol, SOURCE), OpenInterestObservation)
        mark_by_symbol[symbol] = load(root / series_filename("mark_price", symbol, SOURCE), MarkPriceObservation)
    return oi_by_symbol, mark_by_symbol


def _spec(direction_convention: str, universe) -> CandidateSpecification:
    """Candidate MECHANISM is funding_rate_threshold_rule (feature-agnostic
    signed threshold); feature identity is oi_velocity."""
    return CandidateSpecification(
        name=CANDIDATE_NAME,
        version=f"{direction_convention}-{SOURCE}-v1",
        candidate_type=CANDIDATE_TYPE,
        universe=tuple(universe),
        feature_name=FEATURE_NAME,
        feature_version=FEATURE_VERSION,
        cadence_seconds=CADENCE_SECONDS,
        acceptance_criteria={"min_hit_rate": MIN_HIT_RATE, "min_signaled_samples": MIN_SIGNALED_SAMPLES},
        parameters={"threshold": THRESHOLD, "direction_convention": direction_convention},
    )


def _extract(pkg: Dict[str, Any], stage: str, key: str):
    vr = pkg.get("validation_results", {}).get(stage)
    return vr.get(key) if isinstance(vr, dict) else None


def _record_governance(registry, experiment_id, fingerprint, cleared_all_stages) -> str:
    """DEFER-ceiling enforced structurally: the only reachable decisions are
    REJECT (failed its own pre-registered bar) and DEFER (cleared the bar,
    but promotion is blocked because Open Interest has no Hyperliquid
    historical source -- RESEARCH_PLAYBOOK.md section 5). APPROVE is never
    constructed here."""
    registry.transition(experiment_id, LifecycleState.IN_REVIEW)
    if cleared_all_stages:
        decision = GovernanceDecisionType.DEFER
        rationale = (
            "Cleared all pre-registered acceptance criteria and validation stages on the Binance "
            "screen. DEFERRED, not approved: Open Interest has no Hyperliquid historical source, so "
            "the DEX-first venue-replication check (RESEARCH_PLAYBOOK.md section 5) cannot be "
            "satisfied -- a standing structural blocker to promotion. Recorded as validated "
            "knowledge, not a promotable alpha."
        )
    else:
        decision = GovernanceDecisionType.REJECT
        rationale = (
            "Failed pre-registered min_hit_rate and/or min_signaled_samples, or a validation stage: "
            "no reliable directional edge found in 24h fractional Open Interest velocity."
        )
    record = record_governance_decision(registry, GovernanceDecision(
        experiment_id=experiment_id, decision=decision, evidence_fingerprint=fingerprint,
        proposed_by="researcher-campaign05", reviewed_by="reviewer-campaign05",
        rationale=rationale, decided_at_utc=_FIXED_CLOCK_TS,
    ))
    return f"{record.lifecycle_state.value.upper()} (reviewer!=researcher, fingerprint verified)"


def _run_experiment(registry, experiment_id, direction_convention, samples, universe,
                    record_governance=False) -> ExperimentReport:
    spec = _spec(direction_convention, universe)
    base = ExperimentReport(
        experiment_id=experiment_id, direction_convention=direction_convention,
        source=SOURCE, total_samples=len(samples),
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

    cleared_all = bool(base.single_pass_passed and base.causality_passed
                       and base.walk_forward_passed and base.regime_passed)
    # "SUPPORTED" here means validated knowledge, promotion-blocked (DEFER-ceiling).
    base.overall_verdict = "SUPPORTED (DEFER — promotion structurally blocked)" if cleared_all else "REJECTED"
    if record_governance:
        base.governance_outcome = _record_governance(
            registry, experiment_id, result.record.evidence_fingerprint, cleared_all)
    return base


def run(*, symbols=_DEFAULT_SYMBOLS,
        storage_root="data/alpha_engine_historical",
        registry_path="data/alpha_engine_research/campaign_05.jsonl",
        label="combined", record_governance=False) -> CampaignReport:
    oi_by_symbol, mark_by_symbol = _load_series(symbols, storage_root)
    btc_mark = mark_by_symbol.get(Symbol("BTC"), ())
    labeler = make_regime_labeler(btc_mark) if btc_mark else None

    built = build_samples(
        oi_by_symbol, mark_by_symbol,
        horizon_hours=HORIZON_HOURS, sample_spacing_hours=SAMPLE_SPACING_HOURS,
        regime_labeler=labeler,
    )

    reg_path = registry_path.replace(".jsonl", f"_{SOURCE}_{label}.jsonl")
    Path(reg_path).parent.mkdir(parents=True, exist_ok=True)
    if Path(reg_path).exists():
        Path(reg_path).unlink()
    registry = ExperimentRegistry(FileRegistryStorage(reg_path))

    experiments = [
        _run_experiment(registry, f"camp05-{SOURCE}-{label}-contrarian", "contrarian",
                        built.samples, symbols, record_governance=record_governance),
        _run_experiment(registry, f"camp05-{SOURCE}-{label}-momentum", "momentum",
                        built.samples, symbols, record_governance=record_governance),
    ]
    return CampaignReport(sample_count=len(built.samples),
                          sample_diagnostics=built.diagnostics, experiments=experiments)


def run_all(storage_root="data/alpha_engine_historical"):
    """Per-symbol diagnostics + the pooled (combined) pre-registered analysis.
    Governance is recorded only for the combined dataset."""
    datasets = {"BTC": (Symbol("BTC"),), "ETH": (Symbol("ETH"),), "SOL": (Symbol("SOL"),),
                "combined": _DEFAULT_SYMBOLS}
    return {label: run(symbols=syms, storage_root=storage_root, label=label,
                       record_governance=(label == "combined"))
            for label, syms in datasets.items()}


def format_report(label: str, report: CampaignReport) -> str:
    lines = [f"=== Campaign 05 — OI Velocity [{label}] ===",
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
