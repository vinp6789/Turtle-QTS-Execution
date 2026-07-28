"""Research Campaign 03: Funding Rate, venue-relative threshold.

Follows Campaign 02 (permanently closed, REJECTED). Genuinely different
operationalization of the same hypothesis family: Campaign 02 used one
absolute threshold value derived from Binance's own distribution and
applied it unchanged to Hyperliquid, which Campaign 02's own Production
Venue Validation showed does not transfer (Hyperliquid funding runs
~3-8x smaller in typical magnitude). Campaign 03 instead derives an
independent threshold per venue, from that venue's own historical
distribution -- the permanent methodology rule adopted after Campaign
02's review (docs/PROJECT_CONSTITUTION.md SS6, docs/RESEARCH_PLAYBOOK.md
SS2).

Reuses, unchanged, from research.campaign_02_funding_rate:
  - explore_distribution.py (already source-parameterized)
  - build_samples.py (already source-agnostic)

New in this package: threshold derivation per venue and a run_campaign
module that takes a per-source threshold rather than one shared constant.
"""
