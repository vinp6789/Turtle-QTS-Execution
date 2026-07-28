"""Shared result/metadata shapes for Feature Engineering.

Deliberately minimal: with exactly one feature implemented so far
(funding_rate_feature.FundingRateFeature, Milestone 2.1), a formal
Feature ABC/protocol is NOT built here -- extracting one before a second,
genuinely different feature exists would risk designing the wrong
contract from a single example (avoiding exactly the kind of generic
abstraction the project asked not to introduce ahead of need).

FeatureValue and FeatureMetadata are the one piece of shared shape that
IS already justified: every feature's result and self-description should
look the same to a future caller (alpha_engine.candidates, Milestone
3.x), regardless of how many concrete feature classes exist behind them.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Tuple

from exchange_adapter import Symbol

from .errors import FeatureError


@dataclass(frozen=True)
class FeatureMetadata:
    """A feature's self-description: name, version, warmup, and which
    data sources it reads. Mirrors the registry's own opaque-
    specification pattern (alpha_engine.registry, Milestone 0.2/0.3): a
    Candidate's specification (Milestone 3.1) can record
    {"feature_name": ..., "feature_version": ...} using these exact
    values, later found via ExperimentRegistry.find_by_specification_field
    -- no registry change needed to support that."""

    name: str
    version: str
    warmup_periods: int
    input_data_sources: Tuple[str, ...]

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise FeatureError("FeatureMetadata.name must be a non-empty string")
        if not isinstance(self.version, str) or not self.version.strip():
            raise FeatureError("FeatureMetadata.version must be a non-empty string")
        if not isinstance(self.warmup_periods, int) or isinstance(self.warmup_periods, bool) \
                or self.warmup_periods < 0:
            raise FeatureError("FeatureMetadata.warmup_periods must be a non-negative int")
        if not isinstance(self.input_data_sources, tuple) or not all(
            isinstance(s, str) and s.strip() for s in self.input_data_sources
        ):
            raise FeatureError("FeatureMetadata.input_data_sources must be a tuple of non-empty strings")


@dataclass(frozen=True)
class FeatureValue:
    """One compute() call's outcome -- mirrors FundingRateReading's own
    availability discipline exactly (alpha_engine.data_sources, Milestone
    1.1): available=True requires a value and forbids a reason;
    available=False forbids a value (never fabricate) and requires a
    reason."""

    feature_name: str
    feature_version: str
    symbol: Symbol
    computed_at_utc: str
    available: bool
    value: Optional[Decimal] = None
    reason: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.feature_name, str) or not self.feature_name.strip():
            raise FeatureError("FeatureValue.feature_name must be a non-empty string")
        if not isinstance(self.feature_version, str) or not self.feature_version.strip():
            raise FeatureError("FeatureValue.feature_version must be a non-empty string")
        if not isinstance(self.symbol, Symbol):
            raise FeatureError(f"FeatureValue.symbol must be a Symbol, got {type(self.symbol).__name__}")
        if not isinstance(self.computed_at_utc, str) or not self.computed_at_utc.strip():
            raise FeatureError("FeatureValue.computed_at_utc must be a non-empty string")
        if not isinstance(self.available, bool):
            raise FeatureError("FeatureValue.available must be a bool")
        if self.available:
            if not isinstance(self.value, Decimal):
                raise FeatureError("FeatureValue.value must be a Decimal when available is True")
            if self.reason is not None:
                raise FeatureError("FeatureValue.reason must be None when available is True")
        else:
            if self.value is not None:
                raise FeatureError(
                    "FeatureValue.value must be None when available is False -- never fabricate a value"
                )
            if not isinstance(self.reason, str) or not self.reason.strip():
                raise FeatureError("FeatureValue.reason must be a non-empty string when available is False")
