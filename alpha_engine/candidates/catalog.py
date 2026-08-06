"""Candidate catalog (Alpha Engine R4): the explicit, enumerable map of
every candidate family this repository ships.

Before this module, "what strategies exist" was answerable only by
reading import statements -- unusable by any future orchestration or
continuous-research process. The catalog makes families DISCOVERABLE
without making them DYNAMIC: entries are registered here explicitly, in
source, at import time -- no filesystem scanning, no entry-point magic,
no runtime registration API. Determinism and reviewability beat
convenience: adding a family to the platform is a reviewed source change
that touches exactly this mapping plus its own module.

This is deliberately NOT a candidate behavior framework (still no ABC,
still no dispatch by candidate_type -- see candidates/__init__.py):
a CatalogEntry only NAMES a family and points at its two existing plain
callables (the specification factory and evaluate_fn), both already
shaped identically across families by convention. If a genuinely
different candidate TYPE ever ships, the catalog shape itself needs
nothing new -- only the entry.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Optional, Tuple

from ..features import (
    TrendMomentumFeature,
    PCTRANK_NAME,
    PCTRANK_VERSION,
    FundingRateFeature,
    LiquidationDensityFeature,
    OpenInterestFeature,
)
from .errors import CandidateError
from .trend_momentum_candidate import (
    TrendMomentumRuleCandidate,
    trend_momentum_candidate_specification,
)
from .liquidation_density_candidate import (
    LiquidationDensityRuleCandidate,
    liquidation_density_candidate_specification,
)
from .funding_rate_candidate import (
    FundingRateThresholdRuleCandidate,
    funding_rate_candidate_specification,
)
from .open_interest_candidate import (
    OpenInterestThresholdRuleCandidate,
    open_interest_candidate_specification,
)
from .open_interest_extremeness_candidate import (
    OpenInterestExtremenessRuleCandidate,
    open_interest_extremeness_candidate_specification,
)


@dataclass(frozen=True)
class CatalogEntry:
    """One candidate family: its stable name, type, feature reference,
    and the two plain callables every family already exposes."""

    name: str
    candidate_type: str
    feature_name: str
    feature_version: str
    specification_factory: Callable
    evaluate_fn: Callable
    # D6 (candle-derived families only). When set, this family's feature is
    # computed FROM CANDLES by a generic execution bridge that never imports
    # the family: feature_fn(symbol, computed_at_utc, candles) -> FeatureValue.
    # Families whose feature comes from a single provider reading (funding,
    # open interest) leave both None and are served by their own bridge.
    feature_fn: Optional[Callable] = None
    warmup_periods: Optional[int] = None

    def __post_init__(self):
        for field_name in ("name", "candidate_type", "feature_name", "feature_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise CandidateError(f"CatalogEntry.{field_name} must be a non-empty string")
        if not callable(self.specification_factory):
            raise CandidateError("CatalogEntry.specification_factory must be callable")
        if not callable(self.evaluate_fn):
            raise CandidateError("CatalogEntry.evaluate_fn must be callable")
        # feature_fn and warmup_periods are declared together or not at all:
        # a bridge that knows how to compute the feature but not how much
        # history it needs would have to guess, and guessing a warmup
        # silently changes what the indicator measures.
        if (self.feature_fn is None) != (self.warmup_periods is None):
            raise CandidateError(
                "CatalogEntry.feature_fn and warmup_periods must be declared together"
            )
        if self.feature_fn is not None:
            if not callable(self.feature_fn):
                raise CandidateError("CatalogEntry.feature_fn must be callable")
            if not isinstance(self.warmup_periods, int) or isinstance(self.warmup_periods, bool)                     or self.warmup_periods <= 0:
                raise CandidateError(
                    f"CatalogEntry.warmup_periods must be a positive int, "
                    f"got {self.warmup_periods!r}"
                )


_FUNDING_METADATA = FundingRateFeature.metadata()
_OI_METADATA = OpenInterestFeature.metadata()
_LIQUIDATION_METADATA = LiquidationDensityFeature.metadata()
_TREND_MOMENTUM_METADATA = TrendMomentumFeature.metadata()

CANDIDATE_CATALOG = MappingProxyType({
    "funding_rate_threshold_rule": CatalogEntry(
        name="funding_rate_threshold_rule",
        candidate_type="rule_based",
        feature_name=_FUNDING_METADATA.name,
        feature_version=_FUNDING_METADATA.version,
        specification_factory=funding_rate_candidate_specification,
        evaluate_fn=FundingRateThresholdRuleCandidate.evaluate,
    ),
    "open_interest_threshold_rule": CatalogEntry(
        name="open_interest_threshold_rule",
        candidate_type="rule_based",
        feature_name=_OI_METADATA.name,
        feature_version=_OI_METADATA.version,
        specification_factory=open_interest_candidate_specification,
        evaluate_fn=OpenInterestThresholdRuleCandidate.evaluate,
    ),
    # Research Campaign 01. This family serves TWO canonical rolling
    # features (percentile-rank primary, z-score robustness); the catalog
    # records the primary as its descriptive feature_name, but the actual
    # feature binding lives in each CandidateSpecification (the factory
    # validates it against both allowed identities), and evaluate_fn works
    # for either.
    # Research Campaign 08. Its own family rather than a reuse of
    # funding_rate_threshold_rule: the funding factory stamps
    # feature_name from FundingRateFeature.metadata(), so reusing it
    # would record "funding_rate_raw" in every evidence package while
    # actually testing liquidation density (the misstatement CAMP-04 and
    # CAMP-05 carry). Campaign 08 could be promotion-eligible, so its
    # provenance must be exact.
    # First candle-derived family (D6 context extension). Its own family
    # rather than a reuse: every other factory stamps its own feature
    # identity, so reusing one would record the wrong feature_name in
    # every evidence package -- the exact defect RD-19 made a rule.
    "trend_momentum_rule": CatalogEntry(
        name="trend_momentum_rule",
        candidate_type="rule_based",
        feature_name=_TREND_MOMENTUM_METADATA.name,
        feature_version=_TREND_MOMENTUM_METADATA.version,
        specification_factory=trend_momentum_candidate_specification,
        evaluate_fn=TrendMomentumRuleCandidate.evaluate,
        feature_fn=TrendMomentumFeature.compute,
        warmup_periods=TrendMomentumFeature.WARMUP_PERIODS,
    ),
    "liquidation_density_rule": CatalogEntry(
        name="liquidation_density_rule",
        candidate_type="rule_based",
        feature_name=_LIQUIDATION_METADATA.name,
        feature_version=_LIQUIDATION_METADATA.version,
        specification_factory=liquidation_density_candidate_specification,
        evaluate_fn=LiquidationDensityRuleCandidate.evaluate,
    ),
    "open_interest_extremeness_rule": CatalogEntry(
        name="open_interest_extremeness_rule",
        candidate_type="rule_based",
        feature_name=PCTRANK_NAME,
        feature_version=PCTRANK_VERSION,
        specification_factory=open_interest_extremeness_candidate_specification,
        evaluate_fn=OpenInterestExtremenessRuleCandidate.evaluate,
    ),
})


def list_candidate_types() -> Tuple[str, ...]:
    """Every registered family name, sorted (deterministic)."""
    return tuple(sorted(CANDIDATE_CATALOG))


def get_candidate_type(name: str) -> CatalogEntry:
    """Raises CandidateError for an unknown name -- never a silent None."""
    if not isinstance(name, str) or not name.strip():
        raise CandidateError("name must be a non-empty string")
    entry = CANDIDATE_CATALOG.get(name)
    if entry is None:
        raise CandidateError(
            f"unknown candidate type {name!r}; registered types: {list_candidate_types()}"
        )
    return entry
