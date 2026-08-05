"""Research Campaign 07 — Longer-Horizon Open Interest.

Pre-registered in docs/RESEARCH_CAMPAIGN_07_oi_long_horizon.md. Tests the
one dimension every prior campaign held fixed: the forward-return horizon
(72h and 120h instead of 24h), with strictly non-overlapping outcome
windows.

Deliberately reuses `research.campaign_01_open_interest.build_samples`
UNCHANGED -- identical feature construction, identical point-in-time and
non-overlap guarantees, already unit-tested. Only the horizon and
threshold constants differ, and those live in run_campaign.py where they
are the pre-registration.
"""
