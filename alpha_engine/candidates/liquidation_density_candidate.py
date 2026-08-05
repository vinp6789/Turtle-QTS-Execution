"""liquidation_density_rule: the Campaign 08 candidate family
(Backlog 3.7 option (b)).

Mirrors `funding_rate_candidate.py` in structure, validation discipline
and failure semantics. Two deliberate differences, both semantic rather
than stylistic:

1. **Correct provenance.** feature_name/feature_version are read from
   `LiquidationDensityFeature.metadata()`, so an evidence package can
   never claim `funding_rate_raw` while testing liquidation density.
   That misstatement -- carried by CAMP-04 and CAMP-05, which reused the
   funding factory for `funding_delta` and `oi_velocity` -- is the entire
   reason this family exists.

2. **ONE-TAILED threshold.** Funding is signed, so its rule fires on
   `rate > threshold` (one direction) and `rate < -threshold` (the
   other). A liquidation count is **non-negative by construction**:
   there is no "negative extreme" and `-threshold` is unreachable.
   Copying the two-tailed comparison would leave permanently dead code
   and imply a signal that cannot exist. The rule is therefore
   `count >= threshold` -> signal, otherwise FLAT.

Direction mapping is the campaign's falsifiable assumption, not a known
fact: high liquidation density -> SHORT under `contrarian` (the cascade
exhausts) or LONG under `momentum` (the cascade continues). Liquidation
counts do not reveal which side was liquidated -- see
docs/RESEARCH_CAMPAIGN_08_liquidation_hourly.md.

No existing candidate family is modified, and none of this is reachable
from one: additive only.
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Tuple

from exchange_adapter import Symbol

from ..features import FeatureValue, LiquidationDensityFeature
from .errors import CandidateError
from .models import CandidateSignal, CandidateSpecification, SignalDirection

_CANDIDATE_NAME = "liquidation_density_rule"
_CANDIDATE_TYPE = "rule_based"
_CONTRARIAN = "contrarian"
_MOMENTUM = "momentum"
_DIRECTION_CONVENTIONS = (_CONTRARIAN, _MOMENTUM)

_logger = logging.getLogger(__name__)


def liquidation_density_candidate_specification(
    *,
    version: str,
    universe: Tuple[Symbol, ...],
    cadence_seconds: int,
    parameters: Mapping[str, Any],
    acceptance_criteria: Mapping[str, Any],
) -> CandidateSpecification:
    """Builds a CandidateSpecification for the liquidation_density_rule
    family. feature_name/feature_version are read directly from
    LiquidationDensityFeature.metadata() -- never passed by the caller --
    so they can never silently desync from the real feature, exactly as
    funding_rate_candidate_specification does for its own family."""
    feature_metadata = LiquidationDensityFeature.metadata()
    return CandidateSpecification(
        name=_CANDIDATE_NAME,
        version=version,
        candidate_type=_CANDIDATE_TYPE,
        universe=universe,
        feature_name=feature_metadata.name,
        feature_version=feature_metadata.version,
        cadence_seconds=cadence_seconds,
        parameters=dict(parameters),
        acceptance_criteria=dict(acceptance_criteria),
    )


def _extract_threshold(parameters: Mapping[str, Any]) -> Decimal:
    if "threshold" not in parameters:
        raise CandidateError("specification.parameters must contain 'threshold'")
    raw = parameters["threshold"]
    try:
        threshold = Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise CandidateError(f"threshold {raw!r} is not a valid decimal") from exc
    if threshold < 0:
        raise CandidateError(
            f"threshold must be non-negative for a liquidation count, got {threshold}"
        )
    return threshold


def _extract_direction_convention(parameters: Mapping[str, Any]) -> str:
    if "direction_convention" not in parameters:
        raise CandidateError("specification.parameters must contain 'direction_convention'")
    convention = parameters["direction_convention"]
    if convention not in _DIRECTION_CONVENTIONS:
        raise CandidateError(
            f"direction_convention {convention!r} is not one of {_DIRECTION_CONVENTIONS}"
        )
    return convention


class LiquidationDensityRuleCandidate:
    """Stateless; evaluate() is a staticmethod, mirroring
    FundingRateThresholdRuleCandidate exactly."""

    @staticmethod
    def evaluate(feature_value: FeatureValue, specification: CandidateSpecification) -> CandidateSignal:
        """Pure function of its two arguments. Raises CandidateError for a
        caller's own programming error (wrong family, feature mismatch,
        uninterpretable parameters) -- configuration errors must surface,
        not degrade into a flat signal. A genuine runtime data condition
        (the feature was unavailable) DOES degrade to an unavailable
        CandidateSignal, never a crash and never a fabricated direction."""
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
                "LiquidationDensityRuleCandidate cannot evaluate a specification it does not own"
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

        count = feature_value.value
        # ONE-TAILED: a count is non-negative, so there is no lower
        # extreme to test. See this module's docstring.
        if count >= threshold:
            direction = SignalDirection.SHORT if direction_convention == _CONTRARIAN else SignalDirection.LONG
        else:
            direction = SignalDirection.FLAT

        return CandidateSignal(
            candidate_name=specification.name, candidate_version=specification.version,
            symbol=feature_value.symbol, evaluated_at_utc=feature_value.computed_at_utc,
            available=True, direction=direction, feature_value=count, threshold=threshold,
        )
