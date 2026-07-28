"""Research Campaign 04: Funding Delta (change in funding).

Tests a new mechanism in the Funding family: the first difference of
consecutive funding settlements (a shock / rate-of-change feature), not
its level (CAMP-02/03, rejected) or its persistence (deferred, N_eff too
low). Pre-registration and locked spec:
docs/RESEARCH_CAMPAIGN_04_funding_delta.md.

Reuses, unchanged, the `funding_rate_threshold_rule` candidate MECHANISM
(signed threshold + direction convention — feature-agnostic) via a
CandidateSpecification whose feature identity is the new `funding_delta`.
Sample construction mirrors Campaign 02/03's PIT scaffolding, with the
feature value computed as the delta of the latest settlement at-or-before
the sample time.
"""
