"""Deep-history backfill — gates the next funding/OI campaign only.

Not scoped to any single campaign (unlike campaign_01/campaign_02's own
collect_backfill.py drivers): extends funding-rate and OI/mark-price
coverage back to the earliest dates confirmed available on Binance's
public archive, per docs/ROADMAP.md Section 1.2. Orthogonal to Campaign
06 (the liquidation campaign) -- does not gate it.
"""
