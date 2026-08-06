"""D6 execution-context extension: historical OHLCV candles.

Covers the three additive pieces and, just as importantly, PINS the
pre-existing MarketDataView behaviour so a future change to the candle
path cannot silently alter mark price / funding rate.

No network: the Hyperliquid path is exercised through an injected
transport stub, matching this repository's existing offline-test
discipline.
"""

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from exchange_adapter import (
    Candle,
    CandleInterval,
    CandleSource,
    MarkPrice,
    Symbol,
)
from hyperliquid_adapter import codec


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp() * 1000)


class TestCandleModel(unittest.TestCase):
    def _candle(self, **over):
        base = dict(
            symbol=Symbol("BTC"),
            interval=CandleInterval.H1,
            open_time_utc="2026-08-06T00:00:00+00:00",
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("95"),
            close=Decimal("105"),
            volume=Decimal("12.5"),
        )
        base.update(over)
        return Candle(**base)

    def test_valid_candle_constructs(self):
        self.assertEqual(self._candle().close, Decimal("105"))

    def test_immutable(self):
        c = self._candle()
        with self.assertRaises(Exception):
            c.close = Decimal("1")  # frozen dataclass

    def test_high_below_low_rejected(self):
        with self.assertRaises(ValueError):
            self._candle(high=Decimal("90"), low=Decimal("95"))

    def test_high_below_open_or_close_rejected(self):
        with self.assertRaises(ValueError):
            self._candle(high=Decimal("104"))  # close is 105

    def test_low_above_open_or_close_rejected(self):
        with self.assertRaises(ValueError):
            self._candle(low=Decimal("101"))  # open is 100

    def test_negative_volume_rejected(self):
        with self.assertRaises(ValueError):
            self._candle(volume=Decimal("-1"))

    def test_non_positive_price_rejected(self):
        with self.assertRaises(ValueError):
            self._candle(open=Decimal("0"))

    def test_float_rejected(self):
        with self.assertRaises(TypeError):
            self._candle(close=105.0)

    def test_zero_volume_is_legal(self):
        """A genuinely quiet closed bar has zero volume; that is data,
        not an error."""
        self.assertEqual(self._candle(volume=Decimal("0")).volume, Decimal("0"))


class TestParseCandles(unittest.TestCase):
    """The in-progress bar must never survive parsing -- it is the one
    input that could make an indicator non-deterministic on re-read."""

    def _body(self, n, step_ms, first_open_ms):
        return [
            {
                "t": first_open_ms + i * step_ms,
                "o": "100",
                "h": "110",
                "l": "95",
                "c": "105",
                "v": "1.5",
            }
            for i in range(n)
        ]

    def test_excludes_in_progress_bar(self):
        step = 3_600_000
        now = _ms("2026-08-06T05:30:00")  # halfway through the 05:00 bar
        body = self._body(6, step, _ms("2026-08-06T00:00:00"))
        out = codec.parse_candles(body, Symbol("BTC"), CandleInterval.H1, now)
        self.assertEqual(len(out), 5)  # 00,01,02,03,04 closed; 05 still forming
        self.assertEqual(out[-1].open_time_utc, "2026-08-06T04:00:00+00:00")

    def test_ordered_oldest_to_newest(self):
        step = 3_600_000
        now = _ms("2026-08-06T10:00:00")
        body = list(reversed(self._body(5, step, _ms("2026-08-06T00:00:00"))))
        out = codec.parse_candles(body, Symbol("BTC"), CandleInterval.H1, now)
        self.assertEqual([c.open_time_utc for c in out], sorted(c.open_time_utc for c in out))

    def test_duplicates_collapse(self):
        step = 3_600_000
        now = _ms("2026-08-06T10:00:00")
        body = self._body(3, step, _ms("2026-08-06T00:00:00"))
        out = codec.parse_candles(body + body, Symbol("BTC"), CandleInterval.H1, now)
        self.assertEqual(len(out), 3)
        self.assertEqual(len({c.open_time_utc for c in out}), 3)

    def test_empty_body_returns_empty(self):
        out = codec.parse_candles([], Symbol("BTC"), CandleInterval.H1, _ms("2026-08-06T10:00:00"))
        self.assertEqual(out, ())

    def test_non_list_body_raises(self):
        with self.assertRaises(Exception):
            codec.parse_candles({"nope": 1}, Symbol("BTC"), CandleInterval.H1, 0)

    def test_malformed_entry_raises_never_fabricates(self):
        with self.assertRaises(Exception):
            codec.parse_candles(
                [{"o": "1", "h": "1", "l": "1", "c": "1", "v": "1"}],  # no "t"
                Symbol("BTC"),
                CandleInterval.H1,
                _ms("2026-08-06T10:00:00"),
            )

    def test_all_intervals_map(self):
        for iv in CandleInterval:
            self.assertIsInstance(codec.hl_interval(iv), str)
            self.assertGreater(codec.interval_ms(iv), 0)


class TestCandleSourceProtocol(unittest.TestCase):
    def test_conforming_object_is_a_candle_source(self):
        class Src:
            def get_candles(self, symbol, interval, limit):
                return ()

        self.assertIsInstance(Src(), CandleSource)

    def test_non_conforming_object_is_not(self):
        class NotSrc:
            def get_mark_price(self, symbol):
                return None

        self.assertNotIsInstance(NotSrc(), CandleSource)


class TestMarketDataViewContract(unittest.TestCase):
    """MarketDataView requires a real composition_root.Engine, so these
    exercise the same logic against the facade's own guard conditions
    without constructing an engine."""

    def test_get_candles_raises_when_adapter_lacks_capability(self):
        from trading_system.market_data.facade import MarketDataView

        view = MarketDataView.__new__(MarketDataView)  # bypass __init__

        class NoCandles:
            def get_mark_price(self, symbol):
                return None

        view._adapter = NoCandles()
        self.assertFalse(view.supports_candles())
        with self.assertRaises(TypeError):
            view.get_candles(Symbol("BTC"), CandleInterval.H1, 10)

    def test_get_candles_delegates_when_supported(self):
        from trading_system.market_data.facade import MarketDataView

        view = MarketDataView.__new__(MarketDataView)
        sentinel = (
            Candle(
                symbol=Symbol("BTC"),
                interval=CandleInterval.H1,
                open_time_utc="2026-08-06T00:00:00+00:00",
                open=Decimal("1"),
                high=Decimal("2"),
                low=Decimal("1"),
                close=Decimal("2"),
                volume=Decimal("0"),
            ),
        )

        class WithCandles:
            def get_mark_price(self, symbol):
                return None

            def get_candles(self, symbol, interval, limit):
                return sentinel

        view._adapter = WithCandles()
        self.assertTrue(view.supports_candles())
        self.assertIs(view.get_candles(Symbol("BTC"), CandleInterval.H1, 5), sentinel)

    def test_existing_methods_unchanged(self):
        """Regression pin: the pre-existing pass-through behaviour must
        not have been altered by the D6 extension."""
        from trading_system.market_data.facade import MarketDataView

        view = MarketDataView.__new__(MarketDataView)
        mark = MarkPrice(symbol=Symbol("BTC"), price=Decimal("64000"), timestamp_utc="t")

        class Adapter:
            def get_mark_price(self, symbol):
                return mark

            def get_funding_rate(self, symbol):
                return "FUNDING_SENTINEL"

        view._adapter = Adapter()
        self.assertIs(view.get_mark_price(Symbol("BTC")), mark)
        self.assertEqual(view.get_funding_rate(Symbol("BTC")), "FUNDING_SENTINEL")


if __name__ == "__main__":
    unittest.main()
