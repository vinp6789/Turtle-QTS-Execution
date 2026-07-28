"""Research Campaign 01 — Open Interest as a directional signal.

Pre-registered in docs/RESEARCH_CAMPAIGN_01_open_interest.md. This package
holds the campaign's sample-construction logic (build_samples.py, unit-
tested for point-in-time correctness) and its execution script
(run_campaign.py). It builds ValidationSamples from the historical OI +
mark-price series and runs the four pre-registered experiments through the
frozen alpha_engine validation platform.
"""
