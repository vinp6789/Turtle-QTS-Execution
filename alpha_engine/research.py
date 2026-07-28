"""Research cycle orchestration (Alpha Engine R5).

Integrates the already-built layers into the one call a continuous
research process repeats per hypothesis:

    run_research_cycle:
        catalog lookup -> register (PROPOSED) -> seal -> VALIDATING
        -> all five validation stages -> EvidencePackage
        -> attach (integrity-checked) -> EVIDENCE_SEALED

and the cross-hypothesis view governance reads before deciding:

    compare_experiments: a deterministic, informational ranking of
    experiments' evidence. It RANKS, it never DECIDES -- promotion
    remains exclusively a governance act (R3), and the ranking key is
    fully documented so a reviewer knows exactly what "rank 1" does and
    does not mean.

Everything here is a pure composition of existing, individually tested
pieces: no new metric logic, no new state semantics, no I/O beyond the
injected registry storage. Determinism: given the same registry
contents, specification, samples, seed, n_folds/n_resamples, and a fixed
clock, the resulting EvidencePackage fingerprint is identical across
runs and machines.

Canonical stage names (the fixed vocabulary this orchestrator writes and
compare_experiments reads back):
    single_pass, leakage_causality_audit, walk_forward,
    bootstrap_resampling, regime_stratification

Failure posture: a stage raising (configuration error) aborts the cycle
mid-flight, leaving the experiment durably in VALIDATING with no
evidence -- visibly incomplete, never silently passed. The operator
either fixes the configuration and re-runs as a NEW experiment, or
withdraws the stranded one (PROPOSED/VALIDATING -> WITHDRAWN is a legal
transition for exactly this reason).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from .candidates import CandidateSpecification, get_candidate_type
from .registry import ExperimentRecord, ExperimentRegistry, LifecycleState
from .validation import (
    EvidencePackage,
    ValidationSample,
    attach_evidence_package,
    evidence_package_from_validation_result,
    run_bootstrap_resampling,
    run_causality_audit,
    run_regime_stratified_validation,
    run_validation,
    run_walk_forward_validation,
)
from .watchlist import Watchlist

STAGE_SINGLE_PASS = "single_pass"
STAGE_CAUSALITY = "leakage_causality_audit"
STAGE_WALK_FORWARD = "walk_forward"
STAGE_BOOTSTRAP = "bootstrap_resampling"
STAGE_REGIME = "regime_stratification"


class ResearchError(Exception):
    """Raised for orchestration-level caller errors (mismatched catalog
    entry/specification, wrong argument types). Underlying registry/
    validation errors propagate unchanged -- this module adds no failure
    masking."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ResearchCycleResult:
    record: ExperimentRecord
    package: EvidencePackage
    stage_passed: Mapping[str, Optional[bool]]  # bootstrap maps to None (diagnostic, not gating)


def run_research_cycle(
    registry: ExperimentRegistry,
    candidate_type_name: str,
    experiment_id: str,
    specification: CandidateSpecification,
    samples: Tuple[ValidationSample, ...],
    *,
    n_folds: int,
    n_resamples: int,
    seed: int,
    known_limitations: Tuple[str, ...] = (),
    parent_id: Optional[str] = None,
    watchlist: Optional[Watchlist] = None,
    clock: Callable[[], str] = _now,
) -> ResearchCycleResult:
    """One complete research cycle for one hypothesis. See module
    docstring for the sequence, determinism, and failure posture.

    `watchlist` (optional, audit finding C4): the Watchlist type existed
    (alpha_engine.watchlist) but was never actually enforced anywhere --
    "generate alpha only from a configurable watchlist" was a stated
    system objective with no code checking it. When supplied, every
    symbol in specification.universe must already be a member of
    watchlist; a specification reaching outside the sanctioned watchlist
    is a configuration error (ResearchError), not a data condition to
    silently narrow. Optional and defaults to None so a caller not yet
    wiring a watchlist keeps the exact prior, unconstrained behavior."""
    if not isinstance(registry, ExperimentRegistry):
        raise ResearchError(f"registry must be an ExperimentRegistry, got {type(registry).__name__}")
    if not isinstance(specification, CandidateSpecification):
        raise ResearchError(
            f"specification must be a CandidateSpecification, got {type(specification).__name__}"
        )
    entry = get_candidate_type(candidate_type_name)
    if specification.name != entry.name:
        raise ResearchError(
            f"specification is for candidate family {specification.name!r} but the catalog entry "
            f"requested is {entry.name!r} -- refusing a mismatched pairing"
        )
    if watchlist is not None:
        if not isinstance(watchlist, Watchlist):
            raise ResearchError(f"watchlist must be a Watchlist or None, got {type(watchlist).__name__}")
        outside = [symbol.value for symbol in specification.universe if symbol not in watchlist]
        if outside:
            raise ResearchError(
                f"specification universe includes symbol(s) {sorted(outside)} outside watchlist "
                f"{watchlist.name!r} -- research may only run on the configured watchlist"
            )

    registry.create(experiment_id, specification.to_specification_dict(), parent_id=parent_id)
    registry.seal(experiment_id)
    registry.transition(experiment_id, LifecycleState.VALIDATING)

    single = run_validation(entry.evaluate_fn, specification, samples, clock=clock)
    causality = run_causality_audit(samples, clock=clock)
    walk_forward = run_walk_forward_validation(
        entry.evaluate_fn, specification, samples, n_folds=n_folds, clock=clock,
    )
    bootstrap = run_bootstrap_resampling(
        entry.evaluate_fn, specification, samples, n_resamples=n_resamples, seed=seed, clock=clock,
    )
    regime = run_regime_stratified_validation(entry.evaluate_fn, specification, samples, clock=clock)

    package = evidence_package_from_validation_result(
        specification, STAGE_SINGLE_PASS, single,
        known_limitations=known_limitations, clock=clock,
    )
    package = package.with_stage_result(STAGE_CAUSALITY, causality.to_dict(), clock=clock)
    package = package.with_stage_result(STAGE_WALK_FORWARD, walk_forward.to_dict(), clock=clock)
    package = package.with_stage_result(STAGE_BOOTSTRAP, bootstrap.to_dict(), clock=clock)
    package = package.with_stage_result(STAGE_REGIME, regime.to_dict(), clock=clock)

    attach_evidence_package(registry, experiment_id, package)
    record = registry.transition(experiment_id, LifecycleState.EVIDENCE_SEALED)

    return ResearchCycleResult(
        record=record,
        package=package,
        stage_passed={
            STAGE_SINGLE_PASS: single.overall_passed,
            STAGE_CAUSALITY: causality.passed,
            STAGE_WALK_FORWARD: walk_forward.overall_passed,
            STAGE_BOOTSTRAP: None,
            STAGE_REGIME: regime.overall_passed,
        },
    )


def _stage_flag(evidence: Optional[Mapping[str, Any]], stage: str, key: str) -> Optional[bool]:
    if evidence is None:
        return None
    stage_result = evidence.get("validation_results", {}).get(stage)
    if not isinstance(stage_result, Mapping):
        return None
    value = stage_result.get(key)
    return value if isinstance(value, bool) else None


def _hit_rate(evidence: Optional[Mapping[str, Any]]) -> Optional[Decimal]:
    if evidence is None:
        return None
    stage_result = evidence.get("validation_results", {}).get(STAGE_SINGLE_PASS)
    if not isinstance(stage_result, Mapping):
        return None
    raw = stage_result.get("hit_rate")
    return Decimal(raw) if isinstance(raw, str) else None


def compare_experiments(
    registry: ExperimentRegistry,
    experiment_ids: Tuple[str, ...],
) -> Tuple[Dict[str, Any], ...]:
    """A deterministic, informational ranking of experiments by their
    attached evidence. Ranking key, in order: single-pass passed,
    causality passed, walk-forward passed, regime passed (True before
    False before unknown), then hit rate (higher first, unknown last),
    then experiment_id (stable tiebreak). Experiments without evidence
    rank last. This function INFORMS a governance review; it never
    promotes, and a high rank is NOT a claim of real edge -- only of
    clearing the pre-registered bars."""
    if not isinstance(registry, ExperimentRegistry):
        raise ResearchError(f"registry must be an ExperimentRegistry, got {type(registry).__name__}")
    if not isinstance(experiment_ids, tuple) or len(experiment_ids) == 0:
        raise ResearchError("experiment_ids must be a non-empty tuple")

    rows = []
    for experiment_id in experiment_ids:
        record = registry.get(experiment_id)  # raises for unknown ids -- never silently skipped
        evidence = registry.get_evidence(experiment_id)
        spec = dict(record.specification)
        rows.append({
            "experiment_id": experiment_id,
            "candidate_name": spec.get("candidate_name"),
            "candidate_version": spec.get("candidate_version"),
            "lifecycle_state": record.lifecycle_state.value,
            "has_evidence": evidence is not None,
            "single_pass_passed": _stage_flag(evidence, STAGE_SINGLE_PASS, "overall_passed"),
            "causality_passed": _stage_flag(evidence, STAGE_CAUSALITY, "passed"),
            "walk_forward_passed": _stage_flag(evidence, STAGE_WALK_FORWARD, "overall_passed"),
            "regime_passed": _stage_flag(evidence, STAGE_REGIME, "overall_passed"),
            "hit_rate": _hit_rate(evidence),
        })

    def _flag_key(value: Optional[bool]) -> int:
        return {True: 0, False: 1, None: 2}[value]

    rows.sort(key=lambda r: (
        0 if r["has_evidence"] else 1,
        _flag_key(r["single_pass_passed"]),
        _flag_key(r["causality_passed"]),
        _flag_key(r["walk_forward_passed"]),
        _flag_key(r["regime_passed"]),
        -(r["hit_rate"] if r["hit_rate"] is not None else Decimal("-1")),
        r["experiment_id"],
    ))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
        row["hit_rate"] = str(row["hit_rate"]) if row["hit_rate"] is not None else None
    return tuple(rows)
