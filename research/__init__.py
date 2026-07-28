"""Research campaigns — NOT platform code.

Everything under research/ is campaign-specific analysis code: data
preparation, sample construction, and execution scripts that CONSUME the
frozen alpha_engine platform to answer a specific research question. It is
deliberately kept out of the alpha_engine package because it is not
reusable platform infrastructure — a new campaign writes new code here
against the same unchanged platform.

See docs/RESEARCH_CAMPAIGN_01_open_interest.md for the pre-registered
first campaign.
"""
