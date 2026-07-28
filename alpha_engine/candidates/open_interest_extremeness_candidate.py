"""open_interest_extremeness_rule — a candidate that trades a NORMALIZED
Open-Interest extremeness score (Research Campaign 01).

WHY A NEW CANDIDATE FAMILY, not the existing open_interest_threshold_rule
(Milestone 3.3): that candidate is SINGLE-SIDED (fires only when raw OI
exceeds a fixed absolute threshold) and bound to the raw OI feature.
Research Campaign 01 established empirically that (a) raw OI is too
non-stationary for a fixed absolute threshold to mean "extreme", and
(b) a genuine test of OI extremes must fire at BOTH tails (unusually high
AND unusually low OI relative to recent history). This candidate consumes
a SIGNED, rolling-normalized extremeness score (centered at 0: positive =
current OI high vs. its trailing window, negative = low) and applies a
TWO-SIDED rule — structurally identical to the funding-rate candidate
(Milestone 3.2), whose signed-value two-sided logic is exactly what a
signed extremeness score needs. It reuses that proven shape rather than
inventing a third pattern.

WHY THE FEATURE IS PASSED EXPLICITLY (unlike the other factories, which
read it from a single Feature.metadata()): Campaign 01 pre-registers TWO
normalizations of the same idea — a percentile-rank (primary) and a
z-score (robustness) feature — that this one candidate family serves
identically. The factory therefore takes feature_name/feature_version as
arguments, but validates them against the two canonical rolling-feature
identities (features.open_interest_rolling) so a typo or an unrelated
feature can never be silently accepted — the same anti-drift guarantee
the metadata-reading factories provide, achieved by validation instead of
by a single hardcoded source.

THE RULE (fixed mechanism; the belief is declared, not coded):
  score > threshold   → upper-tail extreme (OI unusually high)
  score < -threshold  → lower-tail extreme (OI unusually low)
  otherwise           → FLAT
Direction per parameters["direction_convention"]:
  contrarian (mean reversion): upper-tail → SHORT, lower-tail → LONG
  momentum   (continuation):   upper-tail → LONG,  lower-tail → SHORT

HONEST LIMITATION (carried over and sharpened from
open_interest_candidate.py): OI magnitude does not reveal which side
(longs or shorts) built the interest, so mapping an OI extreme to a price
direction is a TESTED STRUCTURAL ASSUMPTION, not a known fact. That is
precisely what Campaign 01's two separate experiments (contrarian vs.
momentum) exist to falsify. This module encodes the mechanism; the
validation gate decides whether either mapping carries real information.

Determinism: evaluate() is a pure function of its two arguments — no
wall-clock read, no randomness, no history; its timestamp comes from the
FeatureValue it evaluates.
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Tuple

from exchange_adapter import Symbol

from ..features import (
    PCTRANK_NAME,
    PCTRANK_VERSION,
    ZSCORE_NAME,
    ZSCORE_VERSION,
    FeatureValue,
)
from .errors import CandidateError
from .models import CandidateSignal, CandidateSpecification, SignalDirection

_logger = logging.getLogger(__name__)

_CANDIDATE_NAME = "open_interest_extremeness_rule"
_CANDIDATE_TYPE = "rule_based"

_CONTRARIAN = "contrarian"
_MOMENTUM = "momentum"
_DEFAULT_DIRECTION_CONVENTION = _CONTRARIAN
_VALID_DIRECTION_CONVENTIONS = (_CONTRARIAN, _MOMENTUM)

# The only two features this candidate family is allowed to consume — the
# canonical rolling-normalization identities from Campaign 01.
_ALLOWED_FEATURES = (
    (PCTRANK_NAME, PCTRANK_VERSION),
    (ZSCORE_NAME, ZSCORE_VERSION),
)


def open_interest_extremeness_candidate_specification(
    *,
    version: str,
    universe: Tuple[Symbol, ...],
    feature_name: str,
    feature_version: str,
    cadence_seconds: int,
    parameters: Mapping[str, Any],
    acceptance_criteria: Mapping[str, Any],
) -> CandidateSpecification:
    """Builds a CandidateSpecification for the open_interest_extremeness_
    rule family against one of the two canonical rolling OI features.
    Raises CandidateError if (feature_name, feature_version) is not one of
    the pre-registered rolling-feature identities — preventing a typo'd or
    unrelated feature from being silently accepted."""
    if (feature_name, feature_version) not in _ALLOWED_FEATURES:
        raise CandidateError(
            f"feature ({feature_name!r}, {feature_version!r}) is not a recognized OI extremeness "
            f"feature; allowed: {_ALLOWED_FEATURES}"
        )
    return CandidateSpecification(
        name=_CANDIDATE_NAME,
        version=version,
        candidate_type=_CANDIDATE_TYPE,
        universe=universe,
        feature_name=feature_name,
        feature_version=feature_version,
        cadence_seconds=cadence_seconds,
        acceptance_criteria=acceptance_criteria,
        parameters=parameters,
    )


def _extract_threshold(parameters: Mapping[str, Any]) -> Decimal:
    raw = parameters.get("threshold")
    if not isinstance(raw, str) or not raw.strip():
        raise CandidateError(
            "parameters['threshold'] must be present and a non-empty string (a string-encoded "
            "Decimal -- CandidateSpecification.parameters is JSON-native only)"
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


class OpenInterestExtremenessRuleCandidate:
    """The open_interest_extremeness_rule evaluation logic. Stateless --
    evaluate() is a staticmethod, mirroring every other candidate's shape.
    A signed, rolling-normalized extremeness score in, a two-sided
    directional signal out."""

    @staticmethod
    def evaluate(feature_value: FeatureValue, specification: CandidateSpecification) -> CandidateSignal:
        """Pure function of its two arguments. Raises CandidateError for a
        caller error (mismatched candidate family or feature reference,
        malformed parameters). Degrades an unavailable feature to an
        unavailable CandidateSignal (never a crash, never a fabricated
        direction)."""
        if not isinstance(feature_value, FeatureValue):
            raise CandidateError(f"feature_value must be a FeatureValue, got {type(feature_value).__name__}")
        if not isinstance(specification, CandidateSpecification):
            raise CandidateError(
                f"specification must be a CandidateSpecification, got {type(specification).__name__}"
            )
        if specification.name != _CANDIDATE_NAME or specification.candidate_type != _CANDIDATE_TYPE:
            raise CandidateError(
                f"specification is for candidate {specification.name!r}/{specification.candidate_type!r}, "
                f"not {_CANDIDATE_NAME!r}/{_CANDIDATE_TYPE!r} -- "
                "OpenInterestExtremenessRuleCandidate cannot evaluate a specification it does not own"
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

        score = feature_value.value
        if score > threshold:  # upper-tail extreme (OI unusually high)
            direction = SignalDirection.SHORT if direction_convention == _CONTRARIAN else SignalDirection.LONG
        elif score < -threshold:  # lower-tail extreme (OI unusually low)
            direction = SignalDirection.LONG if direction_convention == _CONTRARIAN else SignalDirection.SHORT
        else:
            direction = SignalDirection.FLAT

        return CandidateSignal(
            candidate_name=specification.name, candidate_version=specification.version,
            symbol=feature_value.symbol, evaluated_at_utc=feature_value.computed_at_utc,
            available=True, direction=direction, feature_value=score, threshold=threshold,
        )
