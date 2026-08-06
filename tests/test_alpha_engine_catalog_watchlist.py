"""Verification tests for the candidate catalog and Watchlist (Alpha
Engine R4)."""

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from exchange_adapter import Symbol

from alpha_engine.candidates import (
    CANDIDATE_CATALOG,
    CandidateError,
    CatalogEntry,
    get_candidate_type,
    list_candidate_types,
)
from alpha_engine.features import FeatureValue
from alpha_engine.watchlist import Watchlist, WatchlistError, load_watchlist


class TestCatalog(unittest.TestCase):
    def test_all_families_registered(self):
        self.assertEqual(
            list_candidate_types(),
            (
                "funding_rate_threshold_rule",
                "liquidation_density_rule",   # Campaign 08, Backlog 3.7(b)
                "open_interest_extremeness_rule",
                "open_interest_threshold_rule",
                "trend_momentum_rule",        # EMA+MACD+ATR, D6 candle-derived
            ),
        )

    def test_catalog_is_read_only(self):
        with self.assertRaises(TypeError):
            CANDIDATE_CATALOG["new_family"] = None

    def test_entry_names_match_their_keys(self):
        for name, entry in CANDIDATE_CATALOG.items():
            self.assertEqual(entry.name, name)

    def test_entry_feature_references_match_real_feature_metadata(self):
        from alpha_engine.features import FundingRateFeature, OpenInterestFeature
        self.assertEqual(
            get_candidate_type("funding_rate_threshold_rule").feature_name,
            FundingRateFeature.metadata().name,
        )
        self.assertEqual(
            get_candidate_type("open_interest_threshold_rule").feature_name,
            OpenInterestFeature.metadata().name,
        )

    def test_unknown_name_raises_with_registered_types_listed(self):
        with self.assertRaises(CandidateError) as ctx:
            get_candidate_type("ghost_family")
        self.assertIn("funding_rate_threshold_rule", str(ctx.exception))

    def test_blank_name_raises(self):
        with self.assertRaises(CandidateError):
            get_candidate_type("  ")

    def test_catalog_entry_validation(self):
        with self.assertRaises(CandidateError):
            CatalogEntry(name=" ", candidate_type="rule_based", feature_name="f",
                         feature_version="v1", specification_factory=lambda: None,
                         evaluate_fn=lambda: None)
        with self.assertRaises(CandidateError):
            CatalogEntry(name="x", candidate_type="rule_based", feature_name="f",
                         feature_version="v1", specification_factory="not-callable",
                         evaluate_fn=lambda: None)

    def test_catalog_entry_is_actually_usable_end_to_end(self):
        entry = get_candidate_type("funding_rate_threshold_rule")
        spec = entry.specification_factory(
            version="v1", universe=(Symbol("BTC"),), cadence_seconds=60,
            parameters={"threshold": "0.0005"}, acceptance_criteria={"min_hit_rate": 0.5},
        )
        feature = FeatureValue(
            feature_name=entry.feature_name, feature_version=entry.feature_version,
            symbol=Symbol("BTC"), computed_at_utc="2026-01-01T00:00:00+00:00",
            available=True, value=Decimal("0.0010"),
        )
        signal = entry.evaluate_fn(feature, spec)
        self.assertTrue(signal.available)


class TestWatchlist(unittest.TestCase):
    def test_valid_watchlist_constructs(self):
        wl = Watchlist(name="core", symbols=(Symbol("BTC"), Symbol("ETH")))
        self.assertEqual(len(wl), 2)
        self.assertIn(Symbol("BTC"), wl)
        self.assertNotIn(Symbol("DOGE"), wl)

    def test_blank_name_raises(self):
        with self.assertRaises(WatchlistError):
            Watchlist(name=" ", symbols=(Symbol("BTC"),))

    def test_empty_symbols_raises(self):
        with self.assertRaises(WatchlistError):
            Watchlist(name="core", symbols=())

    def test_non_symbol_members_raise(self):
        with self.assertRaises(WatchlistError):
            Watchlist(name="core", symbols=("BTC",))

    def test_duplicate_symbols_raise(self):
        with self.assertRaises(WatchlistError):
            Watchlist(name="core", symbols=(Symbol("BTC"), Symbol("BTC")))

    def test_order_preserved(self):
        wl = Watchlist(name="core", symbols=(Symbol("SOL"), Symbol("BTC"), Symbol("ETH")))
        self.assertEqual([s.value for s in wl.symbols], ["SOL", "BTC", "ETH"])


class TestLoadWatchlist(unittest.TestCase):
    def _write(self, tmp, content):
        path = Path(tmp) / "watchlist.json"
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
        return path

    def test_load_valid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, {"name": "core-perps", "symbols": ["BTC", "ETH", "SOL"]})
            wl = load_watchlist(path)
            self.assertEqual(wl.name, "core-perps")
            self.assertEqual([s.value for s in wl.symbols], ["BTC", "ETH", "SOL"])

    def test_missing_file_raises(self):
        with self.assertRaises(WatchlistError):
            load_watchlist("does/not/exist.json")

    def test_invalid_json_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "NOT JSON")
            with self.assertRaises(WatchlistError):
                load_watchlist(path)

    def test_non_object_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, ["BTC"])
            with self.assertRaises(WatchlistError):
                load_watchlist(path)

    def test_missing_or_blank_fields_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            for content in ({"symbols": ["BTC"]}, {"name": "x"}, {"name": "x", "symbols": []},
                            {"name": "x", "symbols": ["BTC", "  "]}):
                path = self._write(tmp, content)
                with self.subTest(content=content):
                    with self.assertRaises(WatchlistError):
                        load_watchlist(path)

    def test_duplicate_symbols_in_file_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, {"name": "x", "symbols": ["BTC", "BTC"]})
            with self.assertRaises(WatchlistError):
                load_watchlist(path)


if __name__ == "__main__":
    unittest.main()
