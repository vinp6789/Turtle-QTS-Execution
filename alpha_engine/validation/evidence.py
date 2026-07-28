"""EvidencePackage: the immutable destination artifact for validation
outputs (Architecture v0.2 SS2.1; Alpha Engine Milestone 4.2).

"A structured, immutable bundle produced by the validation gate for
exactly one hypothesis... The pre-registered criteria and the measurement
per criterion. Not a narrative -- a mapping from each declared threshold
to the observed value, with an explicit pass/fail." This module builds
exactly that, and nothing more: capturing today's one validation stage
(run_validation()'s ValidationResult, Milestone 4.1) in a shape future
validation stages EXTEND rather than force a redesign of.

Structure, deliberately minimal yet extensible:
  - candidate_specification: the full pre-registered declaration
    (CandidateSpecification.to_specification_dict(), Milestone 3.1) --
    WHAT was validated.
  - validation_results: a Mapping from STAGE NAME to that stage's own
    JSON-native result dict. Today holds exactly one entry (this
    milestone's single-pass validation). A future walk-forward, Monte
    Carlo, attribution, or calibration stage (real, named future work,
    same as alpha_engine.validation's own module docstrings already
    state) adds ANOTHER named entry via with_stage_result() -- this type
    never needs to change shape to accommodate a new stage, because it
    was never coupled to what any one stage's result looks like.
    Exactly the same "this layer stays opaque to the next layer's
    internal shape" discipline already used for CandidateSpecification.
    parameters and ExperimentRegistry's specification.
  - known_limitations: caller-supplied caveats (e.g. "N synthetic
    samples, not real market data") -- Architecture v0.2 SS2.1 names
    this explicitly; it costs nothing to support now.
  - fingerprint: content-derived (SHA-256 over the canonical JSON of
    candidate_specification + validation_results), mirroring the
    Experiment Registry's own fingerprinting exactly (registry/
    registry.py's _fingerprint) -- two packages built from identical
    inputs resolve to the same fingerprint; adding a stage changes it.

Deliberately NOT built here (scope boundaries, not oversights, per
explicit project direction):
  - No governance or promotion logic -- no approve/reject/defer, no
    "Approved" state, no shakedown. This is a value type; deciding what
    to do with one is Governance's job (Milestone 5.x).
  - No sealing into, or attachment onto, an Experiment Registry record --
    that integration (and the one-way "sealed" semantics the registry
    already has for its own records, Milestone 0.2) is future wiring,
    not redesigned or duplicated here.
  - No reproducibility manifest (code/data source version capture) --
    no such versioning mechanism exists anywhere in the Alpha Engine yet;
    building one now would be exactly the kind of generic abstraction
    not yet justified. candidate_specification already carries
    feature_name/feature_version (Milestone 3.1/2.1); that is today's
    honest scope.

Determinism: fingerprinting and to_dict() are pure functions of this
object's own fields -- no wall-clock read inside them. assembled_at_utc
is a record-keeping timestamp taken from an injectable clock, exactly
like every other timestamped type in this codebase.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Callable, Dict, Mapping, Tuple

from ..candidates import CandidateSpecification
from .errors import ValidationError
from .models import ValidationResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_json_native_mapping(value: Any, field_name: str, *, allow_empty: bool) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{field_name} must be a Mapping, got {type(value).__name__}")
    if not allow_empty and len(value) == 0:
        raise ValidationError(f"{field_name} must not be empty")
    try:
        # dict(value) first: __post_init__ may already hold a MappingProxyType
        # (this object's own fields, wrapped for immutability -- see
        # _freeze_nested), and json.dumps() does not natively serialize that
        # type even though it IS a Mapping.
        json.dumps(dict(value))
    except TypeError as exc:
        raise ValidationError(
            f"{field_name} must be JSON-serializable using only JSON-native types "
            f"(str, int, float, bool, None, list, dict): {exc}"
        ) from exc
    return dict(value)


def _fingerprint(
    candidate_specification: Mapping[str, Any],
    validation_results: Mapping[str, Any],
    known_limitations: Tuple[str, ...],
) -> str:
    """Content-derived, mirroring alpha_engine.registry's own fingerprint
    function exactly: canonical (sorted-key) JSON, SHA-256 hex digest.

    B2: known_limitations is part of the package's evidentiary content --
    a caveat added or removed changes what the evidence actually claims,
    so it must change the fingerprint too. Previously it was silently
    excluded: two packages differing only in known_limitations (e.g. one
    honestly disclosing "synthetic data only" and one not) fingerprinted
    identically, which is exactly the kind of undetectable content drift
    a content-derived fingerprint exists to prevent. assembled_at_utc
    remains excluded -- it is a record-keeping timestamp, not evidentiary
    content, so two packages built from identical inputs at different
    times still resolve to the same fingerprint, as intended."""
    canonical = json.dumps(
        {
            "candidate_specification": candidate_specification,
            "validation_results": validation_results,
            "known_limitations": list(known_limitations),
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _freeze_nested(mapping: Dict[str, Any]) -> Mapping[str, Any]:
    """MappingProxyType at both levels (outer dict of stage_name ->
    stage_dict, and each stage_dict itself) -- genuine immutability, not
    just naming, matching ExperimentRecord's own MappingProxyType
    discipline (registry/registry.py's _snapshot)."""
    return MappingProxyType({key: MappingProxyType(dict(value)) for key, value in mapping.items()})


@dataclass(frozen=True)
class EvidencePackage:
    """Immutable. Amending it (a new validation stage, a corrected
    specification) means building a NEW EvidencePackage via
    with_stage_result() or the factory below -- never mutating this one,
    matching every other immutable value type in this codebase."""

    candidate_name: str
    candidate_version: str
    candidate_specification: Mapping[str, Any]
    validation_results: Mapping[str, Mapping[str, Any]]
    known_limitations: Tuple[str, ...]
    assembled_at_utc: str
    fingerprint: str

    def __post_init__(self):
        if not isinstance(self.candidate_name, str) or not self.candidate_name.strip():
            raise ValidationError("EvidencePackage.candidate_name must be a non-empty string")
        if not isinstance(self.candidate_version, str) or not self.candidate_version.strip():
            raise ValidationError("EvidencePackage.candidate_version must be a non-empty string")
        _validate_json_native_mapping(
            self.candidate_specification, "EvidencePackage.candidate_specification", allow_empty=False
        )
        if not isinstance(self.validation_results, Mapping) or len(self.validation_results) == 0:
            raise ValidationError("EvidencePackage.validation_results must be a non-empty Mapping")
        for stage_name, stage_result in self.validation_results.items():
            if not isinstance(stage_name, str) or not stage_name.strip():
                raise ValidationError("EvidencePackage.validation_results keys must be non-empty strings")
            _validate_json_native_mapping(
                stage_result, f"EvidencePackage.validation_results[{stage_name!r}]", allow_empty=False
            )
        if not isinstance(self.known_limitations, tuple) or not all(
            isinstance(item, str) and item.strip() for item in self.known_limitations
        ):
            raise ValidationError("EvidencePackage.known_limitations must be a tuple of non-empty strings")
        if not isinstance(self.assembled_at_utc, str) or not self.assembled_at_utc.strip():
            raise ValidationError("EvidencePackage.assembled_at_utc must be a non-empty string")
        if not isinstance(self.fingerprint, str) or not self.fingerprint.strip():
            raise ValidationError("EvidencePackage.fingerprint must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        """The JSON-native Mapping a future Registry/Governance
        integration would archive verbatim. Pure function of this
        object's own fields."""
        return {
            "candidate_name": self.candidate_name,
            "candidate_version": self.candidate_version,
            "candidate_specification": dict(self.candidate_specification),
            "validation_results": {
                stage_name: dict(stage_result) for stage_name, stage_result in self.validation_results.items()
            },
            "known_limitations": list(self.known_limitations),
            "assembled_at_utc": self.assembled_at_utc,
            "fingerprint": self.fingerprint,
        }

    def with_stage_result(
        self,
        stage_name: str,
        stage_result: Mapping[str, Any],
        clock: Callable[[], str] = _now,
    ) -> "EvidencePackage":
        """Returns a NEW EvidencePackage with stage_name added to
        validation_results -- this object is unchanged. This is the
        mechanism by which a future validation stage (walk-forward, Monte
        Carlo, attribution, calibration) extends an Evidence Package
        rather than requiring a redesign. Refuses to overwrite an
        existing stage_name (raises ValidationError) -- re-validating the
        same stage is a conscious decision (a new EvidencePackage),
        never a silent overwrite of prior evidence."""
        if not isinstance(stage_name, str) or not stage_name.strip():
            raise ValidationError("stage_name must be a non-empty string")
        if stage_name in self.validation_results:
            raise ValidationError(
                f"stage {stage_name!r} is already present in this EvidencePackage -- "
                "build a new package rather than silently overwriting existing evidence"
            )
        stage_dict = _validate_json_native_mapping(
            stage_result, f"stage_result[{stage_name!r}]", allow_empty=False
        )
        new_validation_results = {**{k: dict(v) for k, v in self.validation_results.items()}, stage_name: stage_dict}
        return EvidencePackage(
            candidate_name=self.candidate_name,
            candidate_version=self.candidate_version,
            candidate_specification=self.candidate_specification,
            validation_results=_freeze_nested(new_validation_results),
            known_limitations=self.known_limitations,
            assembled_at_utc=clock(),
            fingerprint=_fingerprint(
                dict(self.candidate_specification), new_validation_results, self.known_limitations
            ),
        )


def evidence_package_from_validation_result(
    candidate_specification: CandidateSpecification,
    stage_name: str,
    validation_result: ValidationResult,
    known_limitations: Tuple[str, ...] = (),
    clock: Callable[[], str] = _now,
) -> EvidencePackage:
    """Builds the first EvidencePackage for a candidate: exactly one
    validation stage, from today's single-pass run_validation() output
    (Milestone 4.1). A later validation stage extends this result via
    EvidencePackage.with_stage_result(), never by calling this factory
    again for the same candidate run."""
    if not isinstance(candidate_specification, CandidateSpecification):
        raise ValidationError(
            f"candidate_specification must be a CandidateSpecification, got "
            f"{type(candidate_specification).__name__}"
        )
    if not isinstance(stage_name, str) or not stage_name.strip():
        raise ValidationError("stage_name must be a non-empty string")
    if not isinstance(validation_result, ValidationResult):
        raise ValidationError(
            f"validation_result must be a ValidationResult, got {type(validation_result).__name__}"
        )

    spec_dict = candidate_specification.to_specification_dict()
    validation_results = {stage_name: validation_result.to_dict()}
    return EvidencePackage(
        candidate_name=candidate_specification.name,
        candidate_version=candidate_specification.version,
        candidate_specification=MappingProxyType(spec_dict),
        validation_results=_freeze_nested(validation_results),
        known_limitations=known_limitations,
        assembled_at_utc=clock(),
        fingerprint=_fingerprint(spec_dict, validation_results, known_limitations),
    )
