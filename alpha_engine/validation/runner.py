"""run_validation(): the first end-to-end validation loop (Alpha Engine
Milestone 4.1).

Deliberately a single function, not a framework: `evaluate_fn` is a plain
callable (Callable[[FeatureValue, CandidateSpecification],
CandidateSignal]), the same "plain callable, not a new ABC or protocol
class" pattern this repository's own hyperliquid_adapter.transport.
TransportFn already uses for exactly this reason -- a candidate-execution
ABC/registry/dispatch mechanism is not built here, matching the same
restraint already applied to Feature (Milestone 2.1) and to a candidate
behavior framework (Milestone 3.1/3.2's own docstrings): extracting one
from a single candidate type would risk designing the wrong contract.
Any future candidate sharing FundingRateThresholdRuleCandidate.evaluate's
shape (feature_value, specification) -> CandidateSignal already works
with this same run_validation() unmodified.

Determinism: run_validation() calls evaluate_fn once per sample, in the
given order, and performs only Decimal arithmetic over already-supplied
values -- no randomness, no wall-clock read in the METRICS themselves
(validated_at_utc is a record-keeping field taken from an injectable
clock, exactly like every other timestamped type in this codebase).
Identical (evaluate_fn, specification, samples) always produce an
identical ValidationResult (up to validated_at_utc, which a fixed clock
in a test pins down too).
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Tuple

from ..candidates import CandidateSignal, CandidateSpecification, SignalDirection
from ..features import FeatureValue
from .errors import ValidationError
from .models import (
    CriterionCheck,
    CriterionOutcome,
    ValidationResult,
    ValidationSample,
    fingerprint_samples,
)

_logger = logging.getLogger(__name__)

EvaluateFn = Callable[[FeatureValue, CandidateSpecification], CandidateSignal]

_MIN_HIT_RATE_KEY = "min_hit_rate"
_MIN_SIGNALED_SAMPLES_KEY = "min_signaled_samples"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_min_hit_rate(required: Any, hit_rate: Decimal) -> CriterionCheck:
    try:
        required_decimal = Decimal(str(required))
    except InvalidOperation as exc:
        raise ValidationError(
            f"acceptance_criteria[{_MIN_HIT_RATE_KEY!r}] must be numeric, got {required!r}"
        ) from exc
    if not (Decimal("0") <= required_decimal <= Decimal("1")):
        raise ValidationError(
            f"acceptance_criteria[{_MIN_HIT_RATE_KEY!r}] must be in [0, 1], got {required!r}"
        )
    if hit_rate is None:
        return CriterionCheck(_MIN_HIT_RATE_KEY, required, None, CriterionOutcome.NOT_EVALUATED)
    outcome = CriterionOutcome.PASS if hit_rate >= required_decimal else CriterionOutcome.FAIL
    return CriterionCheck(_MIN_HIT_RATE_KEY, required, str(hit_rate), outcome)


def _check_min_signaled_samples(required: Any, signaled_samples: int) -> CriterionCheck:
    if not isinstance(required, int) or isinstance(required, bool) or required < 0:
        raise ValidationError(
            f"acceptance_criteria[{_MIN_SIGNALED_SAMPLES_KEY!r}] must be a non-negative int, got {required!r}"
        )
    outcome = CriterionOutcome.PASS if signaled_samples >= required else CriterionOutcome.FAIL
    return CriterionCheck(_MIN_SIGNALED_SAMPLES_KEY, required, signaled_samples, outcome)


def run_validation(
    evaluate_fn: EvaluateFn,
    specification: CandidateSpecification,
    samples: Tuple[ValidationSample, ...],
    clock: Callable[[], str] = _now,
) -> ValidationResult:
    """Evaluates evaluate_fn against every sample, aggregates hit rate and
    mean directional return over the signals that actually took a
    position (excluding unavailable and FLAT signals, which made no
    directional bet), and checks each of specification.acceptance_
    criteria's declared keys against those metrics.

    Recognized criteria keys today: "min_hit_rate" (numeric, [0, 1]),
    "min_signaled_samples" (non-negative int). Any other declared key is
    reported NOT_EVALUATED, never silently ignored and never assumed to
    pass -- this is exactly how new validation techniques get "layered on
    incrementally" later: a new recognized key here, nothing else
    changes. A malformed value under a RECOGNIZED key raises
    ValidationError (a configuration error); an unrecognized key does
    not (nothing was declared wrong, this harness just doesn't check it
    yet).

    overall_passed is True only if every declared criterion evaluated to
    PASS -- a criterion that could not be evaluated, or that failed,
    means the candidate has not cleared validation.
    """
    if not callable(evaluate_fn):
        raise ValidationError(f"evaluate_fn must be callable, got {type(evaluate_fn).__name__}")
    if not isinstance(specification, CandidateSpecification):
        raise ValidationError(
            f"specification must be a CandidateSpecification, got {type(specification).__name__}"
        )
    if not isinstance(samples, tuple) or len(samples) == 0:
        raise ValidationError("samples must be a non-empty tuple of ValidationSample")
    if not all(isinstance(s, ValidationSample) for s in samples):
        raise ValidationError("samples must contain only ValidationSample instances")

    unavailable = 0
    flat = 0
    hits = 0
    directional_returns = []

    for sample in samples:
        signal = evaluate_fn(sample.feature_value, specification)
        if not isinstance(signal, CandidateSignal):
            raise ValidationError(
                f"evaluate_fn must return a CandidateSignal, got {type(signal).__name__}"
            )
        if not signal.available:
            unavailable += 1
            continue
        if signal.direction is SignalDirection.FLAT:
            flat += 1
            continue

        # Signaled (LONG or SHORT): fold direction into a signed
        # directional return where positive always means "the bet paid
        # off" -- a SHORT profits from a negative realized_outcome, so
        # its contribution is negated.
        directional_return = (
            sample.realized_outcome if signal.direction is SignalDirection.LONG else -sample.realized_outcome
        )
        directional_returns.append(directional_return)
        if directional_return > 0:
            hits += 1
        # directional_return == 0 (no move, or an exact wash) counts as
        # signaled but not a hit -- a flat outcome is not evidence the
        # direction was correct.

    total = len(samples)
    signaled = len(directional_returns)
    hit_rate = (Decimal(hits) / Decimal(signaled)) if signaled > 0 else None
    mean_directional_return = (sum(directional_returns) / Decimal(signaled)) if signaled > 0 else None

    criteria_results = []
    for key, required in specification.acceptance_criteria.items():
        if key == _MIN_HIT_RATE_KEY:
            criteria_results.append(_check_min_hit_rate(required, hit_rate))
        elif key == _MIN_SIGNALED_SAMPLES_KEY:
            criteria_results.append(_check_min_signaled_samples(required, signaled))
        else:
            criteria_results.append(CriterionCheck(key, required, None, CriterionOutcome.NOT_EVALUATED))

    overall_passed = all(c.outcome is CriterionOutcome.PASS for c in criteria_results)

    if not overall_passed:
        failing = [c.criterion_key for c in criteria_results if c.outcome is not CriterionOutcome.PASS]
        _logger.warning(
            "validation failed: candidate=%s/%s failing_criteria=%s hit_rate=%s signaled_samples=%d",
            specification.name, specification.version, failing, hit_rate, signaled,
        )

    return ValidationResult(
        candidate_name=specification.name,
        candidate_version=specification.version,
        validated_at_utc=clock(),
        total_samples=total,
        unavailable_samples=unavailable,
        flat_samples=flat,
        signaled_samples=signaled,
        hits=hits,
        hit_rate=hit_rate,
        mean_directional_return=mean_directional_return,
        criteria_results=tuple(criteria_results),
        overall_passed=overall_passed,
        sample_set_fingerprint=fingerprint_samples(samples),
    )
