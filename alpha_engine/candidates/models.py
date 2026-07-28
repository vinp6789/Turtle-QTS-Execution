"""CandidateSpecification: the structural container for a hypothesis
(Architecture v0.2 SS3 "Proposed" state, SS6.1 pre-registration; Alpha
Engine Milestone 3.1).

Deliberately a plain, general-SHAPED value type -- NOT a candidate
behavior framework. It declares WHAT a hypothesis is (identity, universe,
feature reference, cadence, pre-registered acceptance criteria,
candidate-specific parameters); it has no compute()/evaluate() method and
enforces no model-family-specific logic. Per project direction, a
generic candidate behavior framework (an ABC, a type registry, dispatch
by candidate_type) is deliberately NOT built here -- exactly like
alpha_engine.features deferred a Feature ABC until a second feature
existed (see features/models.py's docstring), extracting a behavior
contract from a single candidate type would risk designing the wrong one.
That framework is warranted once a second, genuinely different candidate
type exists to inform what is actually common.

Why the SHAPE is general even though the framework is not: Architecture
v0.2's model-agnosticism principle (SS5) requires every candidate --
rule-based, statistical, optimization, ensemble -- to produce the SAME
evidence-package/attribution shape regardless of mechanism. A uniformly-
shaped specification (this type) is the declaration-time half of that
same requirement, and costs nothing extra to make general: candidate_type
is a plain string (not yet a closed enum -- there is only one value in
use, "rule_based", introduced by the concrete Milestone 3.2 candidate),
and acceptance_criteria/parameters are opaque JSON-native mappings this
module does not interpret -- exactly like alpha_engine.registry keeps a
specification opaque and alpha_engine.features keeps a specification's
downstream shape undefined. Each layer stays ignorant of the next layer's
internal shape; only the layer that actually needs to interpret a field
gets to define it.

Integration with the Experiment Registry (Milestone 0.2/0.3) and Feature
metadata (Milestone 2.1): to_specification_dict() produces exactly the
JSON-native Mapping ExperimentRegistry.create()'s `specification`
parameter expects, with feature_name/feature_version keys matching
FeatureMetadata's own field names verbatim -- so
ExperimentRegistry.find_by_specification_field("feature_name", ...) finds
every candidate built against a given feature with no registry change
required. See funding_rate_candidate.py for the concrete integration:
its factory reads FundingRateFeature.metadata() directly rather than
letting a caller hand-type (and risk desyncing) those two values.

Determinism: to_specification_dict() is a pure function of this object's
own fields -- no wall-clock read, no randomness -- so two specifications
built from identical inputs always produce byte-identical dicts, and
therefore (via the registry's own content-derived hashing, Milestone 0.2)
the same fingerprint. This is required for the registry's "two
experiments with an identical specification resolve to the same
fingerprint" guarantee to mean anything at the candidate layer.

Deliberately NOT built here (scope boundaries, not oversights):
  - No from_specification_dict() parser reconstructing a
    CandidateSpecification from a stored dict -- nothing yet needs to
    read a spec back out as a typed object; add this once a real caller
    does (avoiding speculative round-trip machinery).
  - No enforcement of what acceptance_criteria/parameters must contain --
    that belongs to whichever layer actually consumes them (Milestone 3.2
    for parameters; the validation gate, Milestone 4.x, for acceptance
    criteria).

This module also holds CandidateSignal/SignalDirection (Milestone 3.2):
the simple, deterministic output shape any rule-based (or future
statistical/optimization/ensemble) candidate produces, ready to enter
Validation. Grouped here for the same reason CandidateSpecification's
shape is general: Architecture v0.2 SS5 requires every candidate's output
to look the same to a downstream caller regardless of mechanism, and this
costs nothing extra to make general now -- unlike the actual rule
evaluation logic (funding_rate_candidate.py), which remains one concrete,
non-generic implementation.
"""

import json
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple

from exchange_adapter import Symbol

from .errors import CandidateError


def _validate_json_native_mapping(value: Any, field_name: str, *, allow_empty: bool) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CandidateError(f"CandidateSpecification.{field_name} must be a Mapping, got {type(value).__name__}")
    if not allow_empty and len(value) == 0:
        raise CandidateError(f"CandidateSpecification.{field_name} must not be empty")
    try:
        json.dumps(value)
    except TypeError as exc:
        raise CandidateError(
            f"CandidateSpecification.{field_name} must be JSON-serializable using only JSON-native "
            f"types (str, int, float, bool, None, list, dict) -- stringify anything else first: {exc}"
        ) from exc
    return dict(value)


@dataclass(frozen=True)
class CandidateSpecification:
    """A hypothesis's pre-registered declaration (Architecture v0.2
    SS6.1). Immutable; every field is fixed at construction, matching the
    project's pre-registration discipline -- amending any field means
    building a new CandidateSpecification (and, at the registry layer, a
    new experiment linked via parent_id), never mutating this one."""

    name: str
    version: str
    candidate_type: str
    universe: Tuple[Symbol, ...]
    feature_name: str
    feature_version: str
    cadence_seconds: int
    acceptance_criteria: Mapping[str, Any]
    parameters: Mapping[str, Any]

    def __post_init__(self):
        for field_name in ("name", "version", "candidate_type", "feature_name", "feature_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise CandidateError(f"CandidateSpecification.{field_name} must be a non-empty string")
        if not isinstance(self.universe, tuple) or len(self.universe) == 0:
            raise CandidateError("CandidateSpecification.universe must be a non-empty tuple")
        if not all(isinstance(s, Symbol) for s in self.universe):
            raise CandidateError("CandidateSpecification.universe must contain only Symbol instances")
        if not isinstance(self.cadence_seconds, int) or isinstance(self.cadence_seconds, bool) \
                or self.cadence_seconds <= 0:
            raise CandidateError("CandidateSpecification.cadence_seconds must be a positive int")
        # acceptance_criteria must be non-empty: a hypothesis with zero declared
        # success criteria is not meaningfully pre-registered (Architecture v0.2
        # constraint against post-hoc criteria invention). parameters MAY be
        # empty -- a candidate can legitimately have no configurable knobs.
        _validate_json_native_mapping(self.acceptance_criteria, "acceptance_criteria", allow_empty=False)
        _validate_json_native_mapping(self.parameters, "parameters", allow_empty=True)

    def to_specification_dict(self) -> Dict[str, Any]:
        """The JSON-native Mapping to pass as
        ExperimentRegistry.create()'s `specification` argument. Pure
        function of this object's own fields (see module docstring on
        determinism)."""
        return {
            "candidate_name": self.name,
            "candidate_version": self.version,
            "candidate_type": self.candidate_type,
            "universe": [symbol.value for symbol in self.universe],
            "feature_name": self.feature_name,
            "feature_version": self.feature_version,
            "cadence_seconds": self.cadence_seconds,
            "acceptance_criteria": dict(self.acceptance_criteria),
            "parameters": dict(self.parameters),
        }

    @classmethod
    def from_specification_dict(cls, data: Mapping[str, Any]) -> "CandidateSpecification":
        """Reconstructs a CandidateSpecification from a stored registry
        specification dict (the inverse of to_specification_dict). Added
        in R6, when its first real caller arrived: the execution bridge
        must rebuild APPROVED experiments' typed specifications from
        registry records to evaluate them live. Round-trip guarantee:
        from_specification_dict(spec.to_specification_dict()) == spec.
        Raises CandidateError on any missing/malformed field (all field
        validation is the constructor's own)."""
        if not isinstance(data, Mapping):
            raise CandidateError(f"data must be a Mapping, got {type(data).__name__}")
        try:
            universe_raw = data["universe"]
            if not isinstance(universe_raw, (list, tuple)):
                raise CandidateError(f"universe must be a list, got {type(universe_raw).__name__}")
            return cls(
                name=data["candidate_name"],
                version=data["candidate_version"],
                candidate_type=data["candidate_type"],
                universe=tuple(Symbol(s) for s in universe_raw),
                feature_name=data["feature_name"],
                feature_version=data["feature_version"],
                cadence_seconds=data["cadence_seconds"],
                acceptance_criteria=data["acceptance_criteria"],
                parameters=data["parameters"],
            )
        except KeyError as exc:
            raise CandidateError(f"specification dict is missing required field {exc}") from exc
        except (TypeError, ValueError) as exc:
            raise CandidateError(f"specification dict is malformed: {exc}") from exc


class SignalDirection(Enum):
    """The closed set of directions a candidate signal can take. FLAT is
    a genuine, available result (the rule evaluated and found no edge) --
    distinct from an unavailable CandidateSignal (the rule could not be
    evaluated at all, e.g. its input feature was unavailable)."""

    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


@dataclass(frozen=True)
class CandidateSignal:
    """One evaluate() call's outcome (Milestone 3.2) -- mirrors
    FundingRateReading (Milestone 1.1) and FeatureValue (Milestone 2.1)'s
    own availability discipline exactly, the third consecutive layer to
    repeat it: available=True requires direction/feature_value/threshold
    and forbids a reason; available=False forbids all three and requires
    a reason. This is the simple, deterministic, candidate-type-neutral
    shape Validation (Milestone 4.x) consumes -- not yet a TradeIntent
    (that translation is Milestone 6.3's job, much later, and gated by
    governance approval)."""

    candidate_name: str
    candidate_version: str
    symbol: Symbol
    evaluated_at_utc: str
    available: bool
    direction: Optional[SignalDirection] = None
    feature_value: Optional[Decimal] = None
    threshold: Optional[Decimal] = None
    reason: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.candidate_name, str) or not self.candidate_name.strip():
            raise CandidateError("CandidateSignal.candidate_name must be a non-empty string")
        if not isinstance(self.candidate_version, str) or not self.candidate_version.strip():
            raise CandidateError("CandidateSignal.candidate_version must be a non-empty string")
        if not isinstance(self.symbol, Symbol):
            raise CandidateError(f"CandidateSignal.symbol must be a Symbol, got {type(self.symbol).__name__}")
        if not isinstance(self.evaluated_at_utc, str) or not self.evaluated_at_utc.strip():
            raise CandidateError("CandidateSignal.evaluated_at_utc must be a non-empty string")
        if not isinstance(self.available, bool):
            raise CandidateError("CandidateSignal.available must be a bool")
        if self.available:
            if not isinstance(self.direction, SignalDirection):
                raise CandidateError("CandidateSignal.direction must be a SignalDirection when available is True")
            if not isinstance(self.feature_value, Decimal):
                raise CandidateError("CandidateSignal.feature_value must be a Decimal when available is True")
            if not isinstance(self.threshold, Decimal):
                raise CandidateError("CandidateSignal.threshold must be a Decimal when available is True")
            if self.reason is not None:
                raise CandidateError("CandidateSignal.reason must be None when available is True")
        else:
            if self.direction is not None or self.feature_value is not None or self.threshold is not None:
                raise CandidateError(
                    "CandidateSignal.direction/feature_value/threshold must all be None when "
                    "available is False -- never fabricate a value"
                )
            if not isinstance(self.reason, str) or not self.reason.strip():
                raise CandidateError("CandidateSignal.reason must be a non-empty string when available is False")
