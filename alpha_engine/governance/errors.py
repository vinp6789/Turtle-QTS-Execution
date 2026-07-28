"""Errors for the Governance layer."""


class GovernanceError(Exception):
    """Base for every governance failure: invalid decision construction,
    reviewer-separation violations, evidence-fingerprint mismatches, or a
    decision attempted against an experiment not ready for review."""
