"""Errors for Candidate Data Sources.

Deliberately minimal: a provider's fetch() methods are designed to never
raise (Architecture v0.2 SS8 -- any problem degrades to an unavailable
reading, not an exception). This error class exists only for
constructor-time / caller-error validation (bad argument types), never
for a data-fetch failure."""


class DataSourceError(Exception):
    """Base for every Candidate Data Source failure. Raised only for
    caller misuse (invalid constructor arguments, wrong argument types)
    -- never for a failed or stale fetch, which degrades to an
    unavailable reading instead (see e.g. funding_rate.FundingRateReading)."""
