"""Candidate Alpha Models (Architecture v0.2 SS3, SS5; Alpha Engine
Milestone 3.1: specification scaffold; Milestone 3.2: the first
Funding-based rule candidate; Milestone 3.3: the first Open Interest
rule candidate -- a second, independent strategy family reusing this
entire sub-package, and every downstream layer, unchanged).

Public API:
    CandidateSpecification            -- deterministic, immutable,
                                         versioned pre-registered
                                         hypothesis declaration; converts
                                         to the Experiment Registry's
                                         opaque specification shape via
                                         to_specification_dict()
    funding_rate_candidate_specification -- factory for the
                                         funding_rate_threshold_rule
                                         candidate family, cross-
                                         referencing FundingRateFeature's
                                         own metadata (Milestone 2.1) so
                                         the two can never drift apart
    FundingRateThresholdRuleCandidate  -- the funding candidate's
                                         evaluation logic: a pure,
                                         deterministic, SIGNED-value
                                         threshold-crossing rule
    open_interest_candidate_specification -- factory for the
                                         open_interest_threshold_rule
                                         candidate family, cross-
                                         referencing OpenInterestFeature's
                                         own metadata (Milestone 2.2)
    OpenInterestThresholdRuleCandidate -- the open-interest candidate's
                                         evaluation logic: a pure,
                                         deterministic, single-sided
                                         (UNSIGNED-value) threshold-
                                         crossing rule -- see
                                         open_interest_candidate.py's
                                         docstring on why this differs
                                         from the funding rule rather
                                         than copying it verbatim
    CandidateSignal                   -- one evaluate() call's outcome;
                                         the simple, deterministic,
                                         candidate-type-neutral shape
                                         ready to enter Validation
                                         (Milestone 4.x) -- shared,
                                         unchanged, by both candidate
                                         families
    SignalDirection                   -- LONG / SHORT / FLAT
    CandidateError                    -- this sub-package's error base

Deliberately model-agnostic in field/output SHAPE (Architecture v0.2 SS5)
but NOT yet a candidate behavior framework -- no ABC, no type dispatch, no
registry of candidate types. Two candidates now share an identical rule
SHAPE (specification factory + threshold-crossing evaluate()), but they
are NOT identical in mechanism (signed vs. single-sided thresholds) --
this is itself evidence that extracting a shared behavior contract from
rule-based candidates alone would still be premature; the real trigger
remains a genuinely different candidate TYPE (statistical, optimization,
ensemble), not a second rule-based instance.
"""

from .catalog import CANDIDATE_CATALOG, CatalogEntry, get_candidate_type, list_candidate_types
from .errors import CandidateError
from .funding_rate_candidate import (
    FundingRateThresholdRuleCandidate,
    funding_rate_candidate_specification,
)
from .liquidation_density_candidate import (
    LiquidationDensityRuleCandidate,
    liquidation_density_candidate_specification,
)
from .models import CandidateSignal, CandidateSpecification, SignalDirection
from .open_interest_candidate import (
    OpenInterestThresholdRuleCandidate,
    open_interest_candidate_specification,
)
from .open_interest_extremeness_candidate import (
    OpenInterestExtremenessRuleCandidate,
    open_interest_extremeness_candidate_specification,
)

__all__ = [
    "CandidateSpecification",
    "funding_rate_candidate_specification",
    "FundingRateThresholdRuleCandidate",
    "liquidation_density_candidate_specification",
    "LiquidationDensityRuleCandidate",
    "open_interest_candidate_specification",
    "OpenInterestThresholdRuleCandidate",
    "open_interest_extremeness_candidate_specification",
    "OpenInterestExtremenessRuleCandidate",
    "CandidateSignal",
    "SignalDirection",
    "CANDIDATE_CATALOG",
    "CatalogEntry",
    "list_candidate_types",
    "get_candidate_type",
    "CandidateError",
]
