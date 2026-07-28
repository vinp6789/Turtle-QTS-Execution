"""Errors for Candidate specifications."""


class CandidateError(Exception):
    """Base for every Candidate specification failure. Raised only for
    caller-error validation (invalid fields, non-JSON-native
    acceptance_criteria/parameters) -- there is no "unavailable" degraded
    state here (unlike data_sources/features): a CandidateSpecification
    either constructs validly or not at all, since it declares a
    hypothesis's identity rather than reading live, possibly-absent
    data."""
