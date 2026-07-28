"""Errors for the historical data collection pipeline.

Mirrors alpha_engine.data_sources.errors' own discipline: this class is
for CALLER errors (bad argument types/shapes) and genuine CONFIGURATION
problems only. A single day/month file that is unavailable from a
source (before the source's earliest coverage, or not yet published) is
NOT an error -- it is a normal, expected, logged-and-skipped condition
(see historical.sources.binance/hyperliquid). A file that IS present but
fails its checksum, or a row that fails a structural parse, IS an
integrity error and does raise.
"""


class HistoricalDataError(Exception):
    """Base for every historical-pipeline failure: bad arguments, a
    checksum mismatch, a malformed row from an otherwise-present source
    file, or an unsupported source/metric combination."""
