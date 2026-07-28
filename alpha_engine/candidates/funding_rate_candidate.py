"""The first, and so far only, Funding-based candidate: its specification
factory (Milestone 3.1) and its rule evaluation logic (Milestone 3.2).

One concrete candidate, deliberately: per the roadmap, "a deliberately
simple rule-based candidate... chosen specifically to prove the
rule-based candidate type first, keeping the architecture's
model-agnosticism honest from the very first real candidate rather than
defaulting to an ML model." No candidate execution framework (no ABC, no
dispatch by candidate_type, no registry of candidate implementations) is
built here -- exactly the same restraint already applied to Feature
(Milestone 2.1) and to CandidateSpecification's own field shape
(Milestone 3.1): a framework extracted from one example risks being the
wrong one. That framework is warranted once a second, genuinely different
candidate type exists.

THE RULE (fixed mechanism; the actual hypothesis is declared, not coded):
a threshold-crossing rule over the raw funding rate. Funding rate
extremes are a well-known signal of crowding -- very positive funding
means longs are paying a premium to stay long (a crowded-long market);
very negative funding means the reverse. Which DIRECTION that implies is
not baked into this code: `parameters["direction_convention"]` selects
between "contrarian" (crowding is a reversal signal: extreme positive
funding -> SHORT, extreme negative -> LONG) and "momentum" (crowding
confirms the trend: extreme positive -> LONG, extreme negative ->
SHORT). Only the MECHANISM (compare against a threshold, in either of two
documented conventions) is code; the SPECIFIC belief (which convention,
what threshold) is data, carried entirely in CandidateSpecification.
parameters -- exactly what "the candidate should consume ... Candidate
Specification parameters" requires, and precisely the boundary that keeps
this a rule over declared parameters rather than a hardcoded strategy.

Why a fixed threshold, not "N standard deviations" (the roadmap's other
named example): alpha_engine.features has no historical windowing yet
(Milestone 2.1's own documented scope boundary) -- there is no
distribution to compute a standard deviation from. A fixed threshold
(parameters["threshold"]) is the honest mechanism available today; a
distribution-relative version is a natural extension once historical
feature data exists, not something to fake now.

Determinism: evaluate() is a pure function of its two arguments (a
FeatureValue and a CandidateSpecification) -- no wall-clock read, no
randomness, no historical state. Its own timestamp is taken from the
FeatureValue it evaluates, never freshly read.
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Tuple

from exchange_adapter import Symbol

from ..features import FeatureValue, FundingRateFeature
from .errors import CandidateError
from .models import CandidateSignal, CandidateSpecification, SignalDirection

_logger = logging.getLogger(__name__)

_CANDIDATE_NAME = "funding_rate_threshold_rule"
_CANDIDATE_TYPE = "rule_based"

_CONTRARIAN = "contrarian"
_MOMENTUM = "momentum"
_DEFAULT_DIRECTION_CONVENTION = _CONTRARIAN
_VALID_DIRECTION_CONVENTIONS = (_CONTRARIAN, _MOMENTUM)


def funding_rate_candidate_specification(
    *,
    version: str,
    universe: Tuple[Symbol, ...],
    cadence_seconds: int,
    parameters: Mapping[str, Any],
    acceptance_criteria: Mapping[str, Any],
) -> CandidateSpecification:
    """Builds a CandidateSpecification for the funding_rate_threshold_rule
    candidate family. feature_name/feature_version are read directly from
    FundingRateFeature.metadata() -- never passed by the caller -- so they
    can never silently desync from the real feature (Milestone 2.1).
    name is fixed to "funding_rate_threshold_rule" and candidate_type to
    "rule_based": this factory IS the funding-rate rule-based candidate
    family, not a generic candidate builder (see module docstring on why
    a generic candidate framework is not built at this milestone).

    parameters/acceptance_criteria are entirely caller-supplied and
    interpreted only by Milestone 3.2's candidate logic (parameters) or
    the validation gate (acceptance_criteria, Milestone 4.x) -- this
    factory does not inspect their contents beyond
    CandidateSpecification's own JSON-native validation."""
    feature_metadata = FundingRateFeature.metadata()
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


class FundingRateThresholdRuleCandidate:
    """The funding_rate_threshold_rule candidate's evaluation logic
    (Milestone 3.2). Stateless -- evaluate() is a staticmethod, mirroring
    FundingRateFeature's own shape exactly; there is nothing instance-
    specific to hold."""

    @staticmethod
    def evaluate(feature_value: FeatureValue, specification: CandidateSpecification) -> CandidateSignal:
        """Pure function of its two arguments. Raises CandidateError for
        a caller's own programming error: a feature_value/specification
        pair that do not actually belong together (wrong candidate
        family, or a feature reference mismatch), or a specification
        whose parameters this rule cannot interpret (missing/invalid
        threshold, unrecognized direction_convention) -- these are
        configuration errors, not runtime data conditions, and must
        surface immediately, not degrade into a flat signal. A genuine
        runtime data condition (the feature itself was unavailable)
        DOES degrade -- to an unavailable CandidateSignal, never a
        crash and never a fabricated direction."""
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
                "FundingRateThresholdRuleCandidate cannot evaluate a specification it does not own"
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

        rate = feature_value.value
        if rate > threshold:
            direction = SignalDirection.SHORT if direction_convention == _CONTRARIAN else SignalDirection.LONG
        elif rate < -threshold:
            direction = SignalDirection.LONG if direction_convention == _CONTRARIAN else SignalDirection.SHORT
        else:
            direction = SignalDirection.FLAT

        return CandidateSignal(
            candidate_name=specification.name, candidate_version=specification.version,
            symbol=feature_value.symbol, evaluated_at_utc=feature_value.computed_at_utc,
            available=True, direction=direction, feature_value=rate, threshold=threshold,
        )
