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
from typing import Callable, Tuple

from ..features import (
    PCTRANK_NAME,
    PCTRANK_VERSION,
    FundingRateFeature,
    OpenInterestFeature,
)
from .errors import CandidateError
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

    def __post_init__(self):
        for field_name in ("name", "candidate_type", "feature_name", "feature_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise CandidateError(f"CatalogEntry.{field_name} must be a non-empty string")
        if not callable(self.specification_factory):
            raise CandidateError("CatalogEntry.specification_factory must be callable")
        if not callable(self.evaluate_fn):
            raise CandidateError("CatalogEntry.evaluate_fn must be callable")


_FUNDING_METADATA = FundingRateFeature.metadata()
_OI_METADATA = OpenInterestFeature.metadata()

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
