"""Errors for Feature Engineering."""


class FeatureError(Exception):
    """Base for every Feature Engineering failure. Raised only for
    caller-error validation (invalid constructor/compute arguments) --
    never for a missing/stale input, which degrades to an unavailable
    FeatureValue instead (see models.FeatureValue)."""
