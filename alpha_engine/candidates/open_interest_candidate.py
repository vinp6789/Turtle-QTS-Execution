"""The first, and so far only, Open Interest candidate: its
specification factory and its rule evaluation logic (Alpha Engine
Milestone 3.3).

Mirrors funding_rate_candidate.py's architecture deliberately -- same
CandidateSpecification factory pattern, same fail-loud (caller error) vs.
fail-safe (data condition) boundary, same direction_convention parameter
concept -- but with ONE necessary correction, not a blind copy: see
"WHY A SINGLE-SIDED THRESHOLD" below. This candidate exists to prove one
specific thing, requested explicitly: that an entirely new orthogonal
strategy family (Open Interest, Milestones 1.2/2.2) reuses
CandidateSpecification, run_validation, EvidencePackage, and every
validation stage (causality audit, walk-forward, bootstrap, regime
stratification) completely UNCHANGED. Nothing in validation/ or
evidence.py was modified for this milestone; only this file and
open_interest_feature.py (Milestone 2.2) are new. No candidate execution
framework is introduced here either -- exactly the same restraint applied
after the first candidate: a framework extracted from two examples of the
same shape is not appreciably better justified than from one; the real
trigger is a genuinely different candidate TYPE (statistical,
optimization, ensemble), not a second instance of the same rule-based
shape.

WHY A SINGLE-SIDED THRESHOLD (the one place this candidate does NOT
mirror FundingRateThresholdRuleCandidate verbatim): funding rate is a
SIGNED value -- positive means longs pay shorts, negative means the
reverse, so a symmetric "value > threshold OR value < -threshold" rule
has two economically meaningful branches. Open interest is an UNSIGNED
MAGNITUDE (a count of open contracts; Milestone 1.2's live verification
confirmed Hyperliquid returns it as a non-negative decimal) -- it can
never be negative. Copying the funding candidate's symmetric rule
verbatim would leave "value < -threshold" permanently unreachable dead
code, which would misrepresent the rule as testing two conditions when
only one can ever fire. This candidate therefore checks exactly one
crossing: value > threshold -> a directional signal (per
direction_convention); otherwise FLAT. This is the mechanism correctly
adapted to the feature's actual value domain, not a redesign of the
architecture.

HONEST LIMITATION, stated plainly (not hidden): unlike funding rate's
SIGN (which inherently indicates which side -- longs or shorts -- is
paying, and therefore crowded), a raw open interest magnitude alone does
not reveal which side of the market built that interest. "High OI"
could mean crowded longs, crowded shorts, or balanced positions with high
turnover -- this feature cannot distinguish those. direction_convention
here is therefore a much weaker, more speculative mapping than it is for
funding rate, and this candidate makes no claim that either convention
is more defensible than the other. That is exactly what the validation
gate (Milestone 4.x) exists to test empirically, not something this
module should paper over with false confidence.
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Tuple

from exchange_adapter import Symbol

from ..features import FeatureValue, OpenInterestFeature
from .errors import CandidateError
from .models import CandidateSignal, CandidateSpecification, SignalDirection

_logger = logging.getLogger(__name__)

_CANDIDATE_NAME = "open_interest_threshold_rule"
_CANDIDATE_TYPE = "rule_based"

_CONTRARIAN = "contrarian"
_MOMENTUM = "momentum"
_DEFAULT_DIRECTION_CONVENTION = _CONTRARIAN
_VALID_DIRECTION_CONVENTIONS = (_CONTRARIAN, _MOMENTUM)


def open_interest_candidate_specification(
    *,
    version: str,
    universe: Tuple[Symbol, ...],
    cadence_seconds: int,
    parameters: Mapping[str, Any],
    acceptance_criteria: Mapping[str, Any],
) -> CandidateSpecification:
    """Builds a CandidateSpecification for the
    open_interest_threshold_rule candidate family. feature_name/
    feature_version are read directly from OpenInterestFeature.metadata()
    -- never passed by the caller -- so they can never silently desync
    from the real feature (Milestone 2.2). name is fixed to
    "open_interest_threshold_rule" and candidate_type to "rule_based":
    this factory IS the open-interest rule-based candidate family, not a
    generic candidate builder (see module docstring).

    parameters/acceptance_criteria are entirely caller-supplied and
    interpreted only by this module's evaluate() (parameters) or the
    validation gate (acceptance_criteria) -- this factory does not
    inspect their contents beyond CandidateSpecification's own
    JSON-native validation, exactly mirroring
    funding_rate_candidate_specification()."""
    feature_metadata = OpenInterestFeature.metadata()
    return CandidateSpecification(
        name=_CANDIDATE_NAME,
        version=version,
        candidate_type=_CANDIDATE_TYPE,
        universe=universe,
        feature_name=feature_metadata.name,
        feature_version=feature_metadata.version,
        cadence_seconds=cadence_seconds,
        acceptance_criteria=acceptance_criteria,
        parameters=parameters,
    )


def _extract_threshold(parameters: Mapping[str, Any]) -> Decimal:
    raw = parameters.get("threshold")
    if not isinstance(raw, str) or not raw.strip():
        raise CandidateError(
            "parameters['threshold'] must be present and a non-empty string (a "
            "string-encoded Decimal -- CandidateSpecification.parameters is JSON-native only)"
        )
    try:
        threshold = Decimal(raw)
    except InvalidOperation as exc:
        raise CandidateError(f"parameters['threshold'] {raw!r} is not a valid decimal number") from exc
    if threshold <= 0:
        raise CandidateError(f"parameters['threshold'] must be positive, got {threshold}")
    return threshold


def _extract_direction_convention(parameters: Mapping[str, Any]) -> str:
    convention = parameters.get("direction_convention", _DEFAULT_DIRECTION_CONVENTION)
    if convention not in _VALID_DIRECTION_CONVENTIONS:
        raise CandidateError(
            f"parameters['direction_convention'] must be one of {_VALID_DIRECTION_CONVENTIONS}, "
            f"got {convention!r}"
        )
    return convention


class OpenInterestThresholdRuleCandidate:
    """The open_interest_threshold_rule candidate's evaluation logic.
    Stateless -- evaluate() is a staticmethod, mirroring
    FundingRateThresholdRuleCandidate's own shape exactly."""

    @staticmethod
    def evaluate(feature_value: FeatureValue, specification: CandidateSpecification) -> CandidateSignal:
        """Pure function of its two arguments. Raises CandidateError for
        a caller's own programming error: a feature_value/specification
        pair that do not actually belong together (wrong candidate
        family, or a feature reference mismatch), or a specification
        whose parameters this rule cannot interpret (missing/invalid
        threshold, unrecognized direction_convention) -- configuration
        errors, not runtime data conditions, and must surface
        immediately. A genuine runtime data condition (the feature itself
        was unavailable) DOES degrade -- to an unavailable
        CandidateSignal, never a crash and never a fabricated
        direction."""
        if not isinstance(feature_value, FeatureValue):
            raise CandidateError(
                f"feature_value must be a FeatureValue, got {type(feature_value).__name__}"
            )
        if not isinstance(specification, CandidateSpecification):
            raise CandidateError(
                f"specification must be a CandidateSpecification, got {type(specification).__name__}"
            )
        if specification.name != _CANDIDATE_NAME or specification.candidate_type != _CANDIDATE_TYPE:
            raise CandidateError(
                f"specification is for candidate {specification.name!r}/{specification.candidate_type!r}, "
                f"not {_CANDIDATE_NAME!r}/{_CANDIDATE_TYPE!r} -- "
                "OpenInterestThresholdRuleCandidate cannot evaluate a specification it does not own"
            )
        if feature_value.feature_name != specification.feature_name \
                or feature_value.feature_version != specification.feature_version:
            raise CandidateError(
                f"feature_value is for {feature_value.feature_name!r}/{feature_value.feature_version!r}, "
                f"but specification declares {specification.feature_name!r}/{specification.feature_version!r} "
                "-- refusing to evaluate a mismatched feature/specification pair"
            )

        threshold = _extract_threshold(specification.parameters)
        direction_convention = _extract_direction_convention(specification.parameters)

        if not feature_value.available:
            _logger.debug(
                "%s evaluate degraded to unavailable: symbol=%s reason=%s",
                specification.name, feature_value.symbol.value, feature_value.reason,
            )
            return CandidateSignal(
                candidate_name=specification.name, candidate_version=specification.version,
                symbol=feature_value.symbol, evaluated_at_utc=feature_value.computed_at_utc,
                available=False, reason=f"feature unavailable: {feature_value.reason}",
            )

        # Single-sided: open interest is a non-negative magnitude (see
        # module docstring) -- there is no symmetric "below negative
        # threshold" case the way there is for funding rate's signed value.
        value = feature_value.value
        if value > threshold:
            direction = SignalDirection.SHORT if direction_convention == _CONTRARIAN else SignalDirection.LONG
        else:
            direction = SignalDirection.FLAT

        return CandidateSignal(
            candidate_name=specification.name, candidate_version=specification.version,
            symbol=feature_value.symbol, evaluated_at_utc=feature_value.computed_at_utc,
            available=True, direction=direction, feature_value=value, threshold=threshold,
        )
