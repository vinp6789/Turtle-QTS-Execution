"""Research Campaign 05: Open Interest Velocity.

Tests a new mechanism in the Open Interest family: the 24h FRACTIONAL
change of OI (build-up / unwind velocity), distinct from the rejected OI
LEVEL (CAMP-01). Pre-registration and locked spec:
docs/RESEARCH_CAMPAIGN_05_oi_velocity.md (accepted as RD-08).

Governance ceiling: DEFER, never APPROVE — Open Interest has no
Hyperliquid historical source, so per docs/RESEARCH_PLAYBOOK.md section 5
a passing result is validated knowledge, not a promotable alpha. This is
a single-venue (Binance) knowledge campaign by construction; there is no
Hyperliquid replication step (none is possible).

Reuses, unchanged, the `funding_rate_threshold_rule` candidate MECHANISM
(signed threshold + direction convention — feature-agnostic) via a
CandidateSpecification whose feature identity is the new `oi_velocity`.
"""
