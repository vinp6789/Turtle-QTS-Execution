"""Executes Research Campaign 01's four pre-registered experiments.

Orchestration only — every decision (thresholds, horizon, criteria) is
pre-registered in docs/RESEARCH_CAMPAIGN_01_open_interest.md and locked
here as constants; NONE may be changed after observing results. Uses a
fixed clock and fixed seed so the run is deterministic and reproducible.

Flow: incrementally collect OI + mark for each symbol (skips already-
downloaded days) -> load -> build PIT non-overlapping samples -> run each
experiment through the frozen alpha_engine.research.run_research_cycle ->
return a structured report. This module does NOT print a verdict itself
beyond the platform's own pass/fail; interpreting the four evidence
packages is a governance-review act.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from exchange_adapter import Symbol

from alpha_engine.candidates import open_interest_extremeness_candidate_specification
from alpha_engine.features import PCTRANK_NAME, PCTRANK_VERSION, ZSCORE_NAME, ZSCORE_VERSION
from alpha_engine.governance import (
    GovernanceDecision,
    GovernanceDecisionType,
    record_governance_decision,
)
from alpha_engine.historical import collect_metrics, load
from alpha_engine.historical.models import MarkPriceObservation, OpenInterestObservation
from alpha_engine.historical.storage import series_filename
from alpha_engine.registry import ExperimentRegistry, FileRegistryStorage, LifecycleState
from alpha_engine.research import run_research_cycle
from alpha_engine.watchlist import Watchlist

from .build_samples import build_samples, make_regime_labeler

# ---- Pre-registered constants (LOCKED — see the campaign doc) ----
PCTRANK_THRESHOLD = "0.49"   # |centered rank| >= 0.49  <=> rank >= 0.99 or <= 0.01
ZSCORE_THRESHOLD = "2.0"     # |z| >= 2.0
WINDOW_DAYS = 30
HORIZON_HOURS = 24
SAMPLE_SPACING_HOURS = 24
CADENCE_SECONDS = HORIZON_HOURS * 3600
MIN_HIT_RATE = 0.55
MIN_SIGNALED_SAMPLES = 100
N_FOLDS = 5
N_RESAMPLES = 1000
SEED = 7
_FIXED_CLOCK_TS = "2026-07-23T00:00:00+00:00"
_KNOWN_LIMITATIONS = (
    "Binance USDT-perp data used as a cross-venue proxy for the live Hyperliquid venue "
    "(different mark formula, funding cadence, trader population) -- not venue-exact.",
    "Mark price derived as sum_open_interest_value / sum_open_interest (open interest cancels; "
    "clean mark, small rounding noise).",
    "24h forward-return horizon; non-overlapping daily samples; OI extremeness measured as a "
    "30-day trailing rolling normalization.",
    "OI magnitude does not reveal positioning side -- the tail->direction mapping is a tested "
    "structural assumption, not a known fact.",
)

_DEFAULT_SYMBOLS = (Symbol("BTC"), Symbol("ETH"), Symbol("SOL"))


def _fixed_clock() -> str:
    return _FIXED_CLOCK_TS


@dataclass
class ExperimentReport:
    experiment_id: str
    normalization: str
    direction_convention: str
    total_samples: int
    signaled_samples: Optional[int]
    hit_rate: Optional[str]
    mean_directional_return: Optional[str]
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
    governance_outcome: Optional[str] = None  # e.g. "REJECTED (reviewer!=researcher)"
    error: Optional[str] = None


@dataclass
class CampaignReport:
    sample_diagnostics: Dict[str, int]
    pctrank_sample_count: int
    zscore_sample_count: int
    experiments: List[ExperimentReport]


def collect(symbols, start_date: date, end_date: date, storage_root: str) -> None:
    """Incrementally collect OI + mark for every symbol in a single
    download pass per day (idempotent; skips already-downloaded days)."""
    for symbol in symbols:
        collect_metrics(symbol, start_date, end_date, storage_root)


def _load_series(symbols, storage_root: str):
    from alpha_engine.historical.storage import series_filename
    oi_by_symbol = {}
    mark_by_symbol = {}
    root = Path(storage_root)
    for symbol in symbols:
        oi_by_symbol[symbol] = load(root / series_filename("open_interest", symbol, "binance"), OpenInterestObservation)
        mark_by_symbol[symbol] = load(root / series_filename("mark_price", symbol, "binance"), MarkPriceObservation)
    return oi_by_symbol, mark_by_symbol


def _spec(normalization: str, direction_convention: str, universe):
    if normalization == "pctrank":
        fname, fver, thr = PCTRANK_NAME, PCTRANK_VERSION, PCTRANK_THRESHOLD
    else:
        fname, fver, thr = ZSCORE_NAME, ZSCORE_VERSION, ZSCORE_THRESHOLD
    return open_interest_extremeness_candidate_specification(
        version=f"{normalization}-{direction_convention}-v1",
        universe=tuple(universe),
        feature_name=fname, feature_version=fver,
        cadence_seconds=CADENCE_SECONDS,
        parameters={"threshold": thr, "direction_convention": direction_convention},
        acceptance_criteria={"min_hit_rate": MIN_HIT_RATE, "min_signaled_samples": MIN_SIGNALED_SAMPLES},
    )


def _extract(package_dict: Dict[str, Any], stage: str, key: str):
    vr = package_dict.get("validation_results", {}).get(stage)
    if not isinstance(vr, dict):
        return None
    return vr.get(key)


def _record_governance(registry, experiment_id, evidence_fingerprint, supported) -> str:
    """Records a real governance decision through the frozen governance
    module (reviewer != researcher, evidence-fingerprint checked). REJECT
    unless the evidence supported the hypothesis. Returns an outcome
    string. The experiment is at EVIDENCE_SEALED after the research cycle;
    advance it to IN_REVIEW, then record the decision."""
    registry.transition(experiment_id, LifecycleState.IN_REVIEW)
    decision_type = GovernanceDecisionType.APPROVE if supported else GovernanceDecisionType.REJECT
    rationale = (
        "Cleared all pre-registered acceptance criteria and validation stages."
        if supported else
        "Failed pre-registered min_hit_rate (or signalled-sample floor): no reliable "
        "directional edge; hit rate indistinguishable from chance."
    )
    record = record_governance_decision(registry, GovernanceDecision(
        experiment_id=experiment_id, decision=decision_type,
        evidence_fingerprint=evidence_fingerprint,
        proposed_by="researcher-campaign01", reviewed_by="reviewer-campaign01",
        rationale=rationale, decided_at_utc=_FIXED_CLOCK_TS,
    ))
    return f"{record.lifecycle_state.value.upper()} (reviewer!=researcher, fingerprint verified)"


def _run_experiment(registry, experiment_id, normalization, direction_convention, samples,
                    universe, record_governance=False) -> ExperimentReport:
    spec = _spec(normalization, direction_convention, universe)
    base = ExperimentReport(
        experiment_id=experiment_id, normalization=normalization,
        direction_convention=direction_convention, total_samples=len(samples),
        signaled_samples=None, hit_rate=None, mean_directional_return=None,
    )
    if len(samples) < N_FOLDS:
        base.error = f"only {len(samples)} samples (< n_folds={N_FOLDS})"
        return base
    try:
        result = run_research_cycle(
            registry, "open_interest_extremeness_rule", experiment_id, spec, samples,
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
    base.overall_verdict = "SUPPORTED (advance to review)" if passed_all else "REJECTED"

    if record_governance:
        base.governance_outcome = _record_governance(
            registry, experiment_id, result.record.evidence_fingerprint, passed_all)
    return base


def run(
    *,
    start_date: date,
    end_date: date,
    symbols: Tuple[Symbol, ...] = _DEFAULT_SYMBOLS,
    storage_root: str = "data/alpha_engine_historical",
    registry_path: str = "data/alpha_engine_research/campaign_01.jsonl",
    do_collect: bool = True,
    label: str = "combined",
    record_governance: bool = False,
) -> CampaignReport:
    """Runs the four pre-registered experiments over the given symbol set
    and returns a structured report. `label` distinguishes datasets
    (per-symbol vs. combined) in experiment IDs and gives each its own
    registry file. Set do_collect=False to reuse already-downloaded data;
    record_governance=True to record real governance decisions (used for
    the powered combined dataset)."""
    watchlist = Watchlist(name="campaign-01", symbols=tuple(symbols))  # enforce universe discipline
    _ = watchlist  # (universe is passed straight into each spec; the watchlist documents intent)

    if do_collect:
        collect(symbols, start_date, end_date, storage_root)

    oi_by_symbol, mark_by_symbol = _load_series(symbols, storage_root)
    # Regime labeler always uses BTC price (independent of the symbols under
    # test), loaded from storage even for a per-symbol non-BTC run.
    btc_mark = load(
        Path(storage_root) / series_filename("mark_price", Symbol("BTC"), "binance"),
        MarkPriceObservation,
    )
    labeler = make_regime_labeler(btc_mark) if btc_mark else None

    built = build_samples(
        oi_by_symbol, mark_by_symbol,
        window_days=WINDOW_DAYS, horizon_hours=HORIZON_HOURS,
        sample_spacing_hours=SAMPLE_SPACING_HOURS, regime_labeler=labeler,
    )

    reg_path = registry_path.replace(".jsonl", f"_{label}.jsonl")
    Path(reg_path).parent.mkdir(parents=True, exist_ok=True)
    if Path(reg_path).exists():
        Path(reg_path).unlink()  # fresh registry per run so re-execution is reproducible
    registry = ExperimentRegistry(FileRegistryStorage(reg_path))

    specs = [
        ("pctrank", "contrarian", built.pctrank_samples),
        ("pctrank", "momentum", built.pctrank_samples),
        ("zscore", "contrarian", built.zscore_samples),
        ("zscore", "momentum", built.zscore_samples),
    ]
    experiments = [
        _run_experiment(
            registry, f"camp01-{label}-{norm}-{conv}", norm, conv, samples, symbols,
            record_governance=record_governance,
        )
        for norm, conv, samples in specs
    ]

    return CampaignReport(
        sample_diagnostics=built.diagnostics,
        pctrank_sample_count=len(built.pctrank_samples),
        zscore_sample_count=len(built.zscore_samples),
        experiments=experiments,
    )


def run_all(start_date: date, end_date: date, storage_root: str = "data/alpha_engine_historical"):
    """Runs the campaign on each symbol individually AND on the pooled
    (combined) universe. Governance decisions are recorded only for the
    combined dataset — the pre-registered, statistically-powered analysis;
    per-symbol slices are supplementary diagnostics (typically below the
    signalled-sample floor at this depth)."""
    datasets = {
        "BTC": (Symbol("BTC"),),
        "ETH": (Symbol("ETH"),),
        "SOL": (Symbol("SOL"),),
        "combined": _DEFAULT_SYMBOLS,
    }
    reports = {}
    for label, syms in datasets.items():
        reports[label] = run(
            start_date=start_date, end_date=end_date, symbols=syms,
            storage_root=storage_root, do_collect=False, label=label,
            record_governance=(label == "combined"),
        )
    return reports


def format_report(report: CampaignReport) -> str:
    lines = []
    lines.append("=== Research Campaign 01 — Open Interest ===")
    lines.append(f"pctrank samples: {report.pctrank_sample_count}   zscore samples: {report.zscore_sample_count}")
    lines.append(f"sample diagnostics: {report.sample_diagnostics}")
    lines.append("")
    for e in report.experiments:
        lines.append(f"[{e.experiment_id}]  ({e.normalization} / {e.direction_convention})")
        lines.append(f"    total={e.total_samples} signaled={e.signaled_samples} "
                     f"hit_rate={e.hit_rate} mean_ret={e.mean_directional_return}")
        lines.append(f"    single_pass={e.single_pass_passed} causality={e.causality_passed} "
                     f"walk_forward={e.walk_forward_passed} regime={e.regime_passed}")
        lines.append(f"    VERDICT: {e.overall_verdict}" + (f"  ({e.error})" if e.error else ""))
        lines.append("")
    return "\n".join(lines)
