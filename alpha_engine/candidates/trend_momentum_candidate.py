"""trend_momentum_rule: the EMA+MACD+ATR candidate family.

Mirrors `funding_rate_candidate.py` in structure, validation discipline
and failure semantics. It is TWO-TAILED like the funding family (and
unlike liquidation_density_rule): the feature value is a SIGNED,
ATR-normalised MACD histogram, so both a positive and a negative extreme
are real, reachable states -- there is no dead branch.

    value >=  threshold  -> LONG  (momentum) / SHORT (contrarian)
    value <= -threshold  -> SHORT (momentum) / LONG  (contrarian)
    otherwise            -> FLAT

PROVENANCE. feature_name/feature_version are read from
TrendMomentumFeature.metadata(), never from the caller -- so an evidence
package can never claim a feature it did not measure. That misstatement,
carried by CAMP-04 and CAMP-05 (which reused the funding factory for
`funding_delta` and `oi_velocity`), is why RD-19 made exact provenance a
rule, and why this family exists rather than a reuse.

DIRECTION CONVENTION IS THE FALSIFIABLE ASSUMPTION, not a known fact.
`momentum` says a strong trend-aligned impulse continues; `contrarian`
says it exhausts. Constitution Section 6 requires both to be registered
as SEPARATE experiments so no one can pick the winning direction after
seeing results.

ONE THRESHOLD ACROSS SYMBOLS IS LEGITIMATE HERE, unusually. The feature
is already divided by ATR, so it is scale-free: a value of 0.5 means
"half an ATR of momentum" on BTC and on SOL alike. Constitution Section
6's venue/instrument-relative requirement is satisfied by the
normalisation itself rather than by a per-symbol threshold table.

No existing candidate family is modified, and none of this is reachable
from one: additive only.
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Tuple

from exchange_adapter import Symbol

from ..features import FeatureValue, TrendMomentumFeature
from .errors import CandidateError
from .models import CandidateSignal, CandidateSpecification, SignalDirection

_CANDIDATE_NAME = "trend_momentum_rule"
_CANDIDATE_TYPE = "rule_based"
_CONTRARIAN = "contrarian"
_MOMENTUM = "momentum"
_DIRECTION_CONVENTIONS = (_CONTRARIAN, _MOMENTUM)

_logger = logging.getLogger(__name__)


def trend_momentum_candidate_specification(
    *,
    version: str,
    universe: Tuple[Symbol, ...],
    cadence_seconds: int,
    parameters: Mapping[str, Any],
    acceptance_criteria: Mapping[str, Any],
) -> CandidateSpecification:
    """Builds a CandidateSpecification for the trend_momentum_rule family.
    feature_name/feature_version are read directly from
    TrendMomentumFeature.metadata() -- never passed by the caller -- so
    they can never silently desync from the real feature."""
    feature_metadata = TrendMomentumFeature.metadata()
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
    if threshold <= 0:
        raise CandidateError(
            f"threshold must be positive -- the rule is two-tailed on |value|, "
            f"so a non-positive threshold would fire on every evaluation, got {threshold}"
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


class TrendMomentumRuleCandidate:
    """Stateless; evaluate() is a staticmethod, mirroring
    FundingRateThresholdRuleCandidate exactly."""

    @staticmethod
    def evaluate(
        feature_value: FeatureValue, specification: CandidateSpecification
    ) -> CandidateSignal:
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
                f"specification must be a CandidateSpecification, "
                f"got {type(specification).__name__}"
            )
        if specification.name != _CANDIDATE_NAME or specification.candidate_type != _CANDIDATE_TYPE:
            raise CandidateError(
                f"specification is for candidate {specification.name!r}/"
                f"{specification.candidate_type!r}, not {_CANDIDATE_NAME!r}/{_CANDIDATE_TYPE!r} "
                "-- TrendMomentumRuleCandidate cannot evaluate a specification it does not own"
            )
        if feature_value.feature_name != specification.feature_name \
                or feature_value.feature_version != specification.feature_version:
            raise CandidateError(
                f"feature_value is for {feature_value.feature_name!r}/"
                f"{feature_value.feature_version!r}, but specification declares "
                f"{specification.feature_name!r}/{specification.feature_version!r} "
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
                candidate_name=specification.name,
                candidate_version=specification.version,
                symbol=feature_value.symbol,
                evaluated_at_utc=feature_value.computed_at_utc,
                available=False,
                reason=f"feature unavailable: {feature_value.reason}",
            )

        value = feature_value.value
        # TWO-TAILED: the normalised histogram is signed, so both
        # extremes are reachable states.
        if value >= threshold:
            direction = (
                SignalDirection.SHORT if direction_convention == _CONTRARIAN
                else SignalDirection.LONG
            )
        elif value <= -threshold:
            direction = (
                SignalDirection.LONG if direction_convention == _CONTRARIAN
                else SignalDirection.SHORT
            )
        else:
            direction = SignalDirection.FLAT

        return CandidateSignal(
            candidate_name=specification.name,
            candidate_version=specification.version,
            symbol=feature_value.symbol,
            evaluated_at_utc=feature_value.computed_at_utc,
            available=True,
            direction=direction,
            feature_value=value,
            threshold=threshold,
        )
