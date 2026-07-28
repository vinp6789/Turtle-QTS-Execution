"""Historical data source clients.

    binance       -- PRIMARY source: data.binance.vision bulk archive,
                     both open interest and funding rate, deep history,
                     free, checksummed.
    hyperliquid   -- SECONDARY source: the live execution venue's own
                     fundingHistory endpoint, venue-consistent but
                     shallow history; no open-interest history exists.
    hyperliquid_s3 -- LIQUIDATION source: the venue's own official S3
                     archive of block-batched fills (Requester Pays).
                     Liquidations are an optional field ON FILLS, not a
                     separate stream -- see RD-06/RD-10 and that module's
                     docstring for the live-measured layout and schema.

See docs/HISTORICAL_DATA.md for the full comparison and recommendation.
"""
