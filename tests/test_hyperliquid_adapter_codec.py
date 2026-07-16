"""Tests for hyperliquid_adapter.codec (Module 10, WP-5).

Fixtures mirror the exact response shapes documented by Hyperliquid
(GitBook /for-developers/api/) as gathered during this work package.
Pure unit tests -- no network, no adapter, no transport.
"""

import unittest
from decimal import Decimal

from exchange_adapter import ExchangeAdapterError, OrderSide, OrderStatus, OrderType, Symbol

from hyperliquid_adapter import codec

NOW = "2026-01-01T00:00:00+00:00"


class MarkPrice(unittest.TestCase):
    def test_parses_matching_symbol(self):
        result = codec.parse_mark_price({"BTC": "50000.5", "ETH": "3000.1"}, Symbol("BTC"), NOW)
        self.assertEqual(result.price, Decimal("50000.5"))
        self.assertEqual(result.symbol.value, "BTC")
        self.assertEqual(result.timestamp_utc, NOW)

    def test_missing_symbol_raises(self):
        with self.assertRaises(ExchangeAdapterError):
            codec.parse_mark_price({"ETH": "3000.1"}, Symbol("BTC"), NOW)


class Positions(unittest.TestCase):
    def test_derives_mark_price_from_position_value(self):
        body = {
            "assetPositions": [
                {
                    "position": {
                        "coin": "ETH",
                        "entryPx": "2986.3",
                        "liquidationPx": "2866.26936529",
                        "positionValue": "100.02765",
                        "szi": "0.0335",
                        "unrealizedPnl": "-0.0134",
                    },
                    "type": "oneWay",
                }
            ]
        }
        positions = codec.parse_positions(body)
        self.assertEqual(len(positions), 1)
        p = positions[0]
        self.assertEqual(p.symbol.value, "ETH")
        self.assertEqual(p.quantity, Decimal("0.0335"))
        self.assertEqual(p.entry_price, Decimal("2986.3"))
        self.assertEqual(p.mark_price, Decimal("100.02765") / Decimal("0.0335"))
        self.assertEqual(p.unrealized_pnl, Decimal("-0.0134"))
        self.assertEqual(p.liquidation_price, Decimal("2866.26936529"))

    def test_zero_size_does_not_divide_by_zero(self):
        body = {
            "assetPositions": [
                {"position": {"coin": "BTC", "entryPx": "1", "positionValue": "0", "szi": "0", "unrealizedPnl": "0"}}
            ]
        }
        positions = codec.parse_positions(body)
        self.assertEqual(positions[0].mark_price, Decimal("0"))

    def test_no_liquidation_price_is_none(self):
        body = {
            "assetPositions": [
                {"position": {"coin": "BTC", "entryPx": "1", "positionValue": "1", "szi": "1", "unrealizedPnl": "0"}}
            ]
        }
        self.assertIsNone(codec.parse_positions(body)[0].liquidation_price)

    def test_empty_assets_returns_empty_tuple(self):
        self.assertEqual(codec.parse_positions({"assetPositions": []}), ())


class Balances(unittest.TestCase):
    def test_maps_margin_summary_to_synthetic_usdc_balance(self):
        body = {"marginSummary": {"accountValue": "13109.482328"}, "withdrawable": "13104.514502"}
        balances = codec.parse_balances(body)
        self.assertEqual(len(balances), 1)
        b = balances[0]
        self.assertEqual(b.asset.value, "USDC")
        self.assertEqual(b.total, Decimal("13109.482328"))
        self.assertEqual(b.available, Decimal("13104.514502"))
        self.assertEqual(b.reserved, Decimal("13109.482328") - Decimal("13104.514502"))


class OpenOrders(unittest.TestCase):
    def _entry(self, **overrides):
        base = {
            "coin": "BTC",
            "cloid": "0x1234567890abcdef1234567890abcdef",
            "limitPx": "29792.0",
            "oid": 91490942,
            "origSz": "5.0",
            "reduceOnly": False,
            "side": "A",
            "sz": "5.0",
            "timestamp": 1681247412573,
        }
        base.update(overrides)
        return base

    def test_entry_with_cloid_is_included(self):
        orders = codec.parse_open_orders([self._entry()])
        self.assertEqual(len(orders), 1)
        o = orders[0]
        self.assertEqual(o.client_order_id, "0x1234567890abcdef1234567890abcdef")
        self.assertEqual(o.exchange_order_id, "91490942")
        self.assertEqual(o.side, OrderSide.SELL)  # "A" = ask = sell
        self.assertEqual(o.order_type, OrderType.LIMIT)
        self.assertEqual(o.quantity, Decimal("5.0"))
        self.assertEqual(o.filled_quantity, Decimal("0"))
        self.assertEqual(o.status, OrderStatus.ACKNOWLEDGED)
        self.assertEqual(o.limit_price, Decimal("29792.0"))

    def test_entry_without_cloid_is_filtered_out(self):
        orders = codec.parse_open_orders([self._entry(cloid=None)])
        self.assertEqual(orders, ())

    def test_partial_fill_detected_from_sz_vs_orig_sz(self):
        orders = codec.parse_open_orders([self._entry(sz="2.0", origSz="5.0")])
        self.assertEqual(orders[0].filled_quantity, Decimal("3.0"))
        self.assertEqual(orders[0].status, OrderStatus.PARTIALLY_FILLED)

    def test_buy_side_mapping(self):
        orders = codec.parse_open_orders([self._entry(side="B")])
        self.assertEqual(orders[0].side, OrderSide.BUY)

    def test_reduce_only_is_preserved(self):
        orders = codec.parse_open_orders([self._entry(reduceOnly=True)])
        self.assertTrue(orders[0].reduce_only)


class UserFills(unittest.TestCase):
    def _entry(self, **overrides):
        base = {
            "closedPnl": "0.0",
            "cloid": "0xabcdef1234567890abcdef1234567890",
            "coin": "AVAX",
            "fee": "0.01",
            "oid": 90542681,
            "px": "18.435",
            "side": "B",
            "sz": "93.53",
            "tid": 118906512037719,
            "time": 1681222254710,
        }
        base.update(overrides)
        return base

    def test_entry_with_cloid_is_included(self):
        fills = codec.parse_user_fills([self._entry()])
        self.assertEqual(len(fills), 1)
        f = fills[0]
        self.assertEqual(f.client_order_id, "0xabcdef1234567890abcdef1234567890")
        self.assertEqual(f.exchange_order_id, "90542681")
        self.assertEqual(f.fill_id, "118906512037719")
        self.assertEqual(f.side, OrderSide.BUY)
        self.assertEqual(f.price, Decimal("18.435"))
        self.assertEqual(f.quantity, Decimal("93.53"))
        self.assertEqual(f.fee, Decimal("0.01"))

    def test_entry_without_cloid_is_filtered_out(self):
        fills = codec.parse_user_fills([self._entry(cloid=None)])
        self.assertEqual(fills, ())

    def test_missing_oid_raises(self):
        with self.assertRaises(ExchangeAdapterError):
            codec.parse_user_fills([self._entry(oid=None)])


class OrderStatusParsing(unittest.TestCase):
    def test_unknown_oid_returns_none(self):
        self.assertIsNone(codec.parse_order_status({"status": "unknownOid"}))

    def test_known_order_is_parsed(self):
        body = {
            "status": "order",
            "order": {
                "order": {
                    "coin": "BTC",
                    "cloid": "0x1234567890abcdef1234567890abcdef",
                    "limitPx": "29792.0",
                    "oid": 91490942,
                    "origSz": "5.0",
                    "reduceOnly": False,
                    "side": "A",
                    "sz": "5.0",
                    "timestamp": 1681247412573,
                },
                "status": "open",
                "statusTimestamp": 1724361546645,
            },
        }
        order = codec.parse_order_status(body)
        self.assertIsNotNone(order)
        self.assertEqual(order.exchange_order_id, "91490942")
        self.assertEqual(order.status, OrderStatus.ACKNOWLEDGED)
        self.assertEqual(order.client_order_id, "0x1234567890abcdef1234567890abcdef")

    def test_missing_cloid_yields_empty_client_order_id_not_a_crash(self):
        body = {
            "status": "order",
            "order": {
                "order": {"coin": "BTC", "oid": 1, "side": "A", "sz": "1", "origSz": "1", "timestamp": 1},
                "status": "filled",
            },
        }
        order = codec.parse_order_status(body)
        self.assertEqual(order.client_order_id, "")
        self.assertEqual(order.status, OrderStatus.FILLED)

    def test_rejected_status_maps_to_rejected(self):
        body = {
            "status": "order",
            "order": {
                "order": {"coin": "BTC", "oid": 1, "side": "A", "sz": "1", "origSz": "1", "timestamp": 1},
                "status": "minTradeNtlRejected",
            },
        }
        self.assertEqual(codec.parse_order_status(body).status, OrderStatus.REJECTED)

    def test_missing_required_fields_raises(self):
        body = {"status": "order", "order": {"order": {"side": "A"}, "status": "open"}}  # no coin, no oid
        with self.assertRaises(ExchangeAdapterError):
            codec.parse_order_status(body)


class FundingRateParsing(unittest.TestCase):
    def _body(self):
        return [
            {"universe": [{"name": "BTC"}, {"name": "ETH"}]},
            [{"funding": "0.0001", "markPx": "50000"}, {"funding": "-0.0002", "markPx": "3000"}],
        ]

    def test_finds_symbol_by_universe_index(self):
        rate = codec.parse_funding_rate(self._body(), Symbol("ETH"), NOW)
        self.assertEqual(rate.rate, Decimal("-0.0002"))
        self.assertEqual(rate.symbol.value, "ETH")
        self.assertEqual(rate.timestamp_utc, NOW)

    def test_next_funding_time_is_a_future_top_of_hour(self):
        rate = codec.parse_funding_rate(self._body(), Symbol("BTC"), NOW)
        self.assertTrue(rate.next_funding_time_utc.endswith(":00:00+00:00"))

    def test_unknown_symbol_raises(self):
        with self.assertRaises(ExchangeAdapterError):
            codec.parse_funding_rate(self._body(), Symbol("SOL"), NOW)

    def test_malformed_shape_raises(self):
        with self.assertRaises(ExchangeAdapterError):
            codec.parse_funding_rate({"not": "a list"}, Symbol("BTC"), NOW)


if __name__ == "__main__":
    unittest.main()
