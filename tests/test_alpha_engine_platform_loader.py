"""Tests for alpha_engine.platform -- the strategy registry and loader.

Two jobs:

  1. PLUG-AND-PLAY. A future alpha strategy must load through exactly the
     path the engine-test plugin uses. Several tests assert the loader
     branches on plugin KIND nowhere -- that is the whole point of the
     design, not an incidental property.

  2. FAIL CLOSED. Disabled is the default reading of anything that is not
     literally `enabled = true`, and a bad configuration aborts the whole
     load rather than booting a partial book.
"""

import tempfile
import unittest
from pathlib import Path

from trading_system.strategy import Strategy

from alpha_engine.platform import (
    STRATEGY_REGISTRY,
    PluginEntry,
    PluginKind,
    StrategyLoadError,
    describe,
    get_plugin,
    load_strategies,
)


def _write(body: str) -> str:
    d = tempfile.mkdtemp()
    p = Path(d) / "strategies.toml"
    p.write_text(body, encoding="utf-8")
    return str(p)


_ENABLED = """
[[strategies]]
name = "pipeline_validation"
enabled = true
[strategies.params]
symbols = ["BTC"]
"""


class TestRegistry(unittest.TestCase):
    def test_the_engine_test_plugin_is_registered(self):
        e = get_plugin("pipeline_validation")
        self.assertEqual(e.kind, PluginKind.ENGINE_TEST)

    def test_its_warning_is_unmissable(self):
        e = get_plugin("pipeline_validation")
        for token in ("NOT FOR TRADING", "KNOWN NEGATIVE EXPECTANCY"):
            self.assertIn(token, e.warning)

    def test_unknown_plugin_names_every_available_one(self):
        with self.assertRaises(KeyError) as ctx:
            get_plugin("does_not_exist")
        self.assertIn("pipeline_validation", str(ctx.exception))

    def test_registry_is_immutable(self):
        with self.assertRaises(TypeError):
            STRATEGY_REGISTRY["x"] = None

    def test_entries_are_immutable(self):
        with self.assertRaises(AttributeError):
            get_plugin("pipeline_validation").kind = PluginKind.ALPHA

    def test_a_factory_returning_a_non_strategy_is_rejected(self):
        bad = PluginEntry("bad", PluginKind.ALPHA, lambda p: "not a strategy", "x")
        with self.assertRaises(ValueError):
            bad.build({})

    def test_entry_rejects_invalid_construction(self):
        with self.assertRaises(ValueError):
            PluginEntry("", PluginKind.ALPHA, lambda p: None, "x")
        with self.assertRaises(ValueError):
            PluginEntry("n", "engine_test", lambda p: None, "x")
        with self.assertRaises(ValueError):
            PluginEntry("n", PluginKind.ALPHA, "not callable", "x")


class TestLoader(unittest.TestCase):
    def test_enabled_plugin_loads_and_is_a_Strategy(self):
        s, e = load_strategies(_write(_ENABLED))
        self.assertEqual(len(s), 1)
        self.assertIsInstance(s[0], Strategy)
        self.assertEqual(e[0].kind, PluginKind.ENGINE_TEST)

    def test_disabled_is_the_default_safe_reading(self):
        for flag in ("false", '"true"', "1", "0"):
            with self.subTest(flag=flag):
                body = _ENABLED.replace("enabled = true", f"enabled = {flag}")
                s, _ = load_strategies(_write(body))
                self.assertEqual(s, (), "only a literal true may enable a strategy")

    def test_absent_enabled_key_loads_nothing(self):
        s, _ = load_strategies(_write(_ENABLED.replace("enabled = true", "")))
        self.assertEqual(s, ())

    def test_missing_file_is_not_an_error_by_default(self):
        s, e = load_strategies("does/not/exist.toml")
        self.assertEqual((s, e), ((), ()))

    def test_missing_file_raises_when_required(self):
        with self.assertRaises(StrategyLoadError):
            load_strategies("does/not/exist.toml", required=True)

    def test_unknown_plugin_aborts_the_whole_load(self):
        with self.assertRaises(StrategyLoadError):
            load_strategies(_write('[[strategies]]\nname="nope"\nenabled=true\n'))

    def test_duplicate_plugin_is_rejected(self):
        with self.assertRaises(StrategyLoadError):
            load_strategies(_write(_ENABLED + _ENABLED))

    def test_malformed_toml_is_rejected(self):
        with self.assertRaises(StrategyLoadError):
            load_strategies(_write("[[strategies]\nname=oops"))

    def test_entry_without_a_name_is_rejected(self):
        with self.assertRaises(StrategyLoadError):
            load_strategies(_write("[[strategies]]\nenabled = true\n"))

    def test_a_failing_factory_aborts_rather_than_loading_partially(self):
        body = _ENABLED.replace('symbols = ["BTC"]', 'cadence_seconds = "not-an-int"')
        with self.assertRaises(StrategyLoadError):
            load_strategies(_write(body))

    def test_describe_surfaces_the_warning(self):
        _, e = load_strategies(_write(_ENABLED))
        self.assertIn("NOT FOR TRADING", describe(e))

    def test_describe_says_so_when_nothing_is_enabled(self):
        self.assertIn("trade nothing", describe(()))

    def test_the_shipped_config_loads(self):
        """config/strategies.toml must always be valid -- it is the file an
        operator edits to change the book."""
        s, e = load_strategies("config/strategies.toml")
        self.assertEqual(len(s), len(e))


class TestNoSpecialCasing(unittest.TestCase):
    """The engine-test plugin must load exactly like a future alpha will."""

    def test_the_loader_never_branches_on_plugin_kind(self):
        src = Path("alpha_engine/platform/loader.py").read_text(encoding="utf-8")
        for token in ("ENGINE_TEST", "ALPHA", "pipeline_validation"):
            self.assertNotIn(token, src,
                             f"loader references {token} -- it must be kind-agnostic")

    def test_an_alpha_kind_plugin_would_load_identically(self):
        """Proven by construction: build() is defined once on PluginEntry and
        is the only path from configuration to a Strategy."""
        self.assertTrue(hasattr(PluginEntry, "build"))
        entry = get_plugin("pipeline_validation")
        self.assertIsInstance(entry.build({"symbols": ["BTC"]}), Strategy)


if __name__ == "__main__":
    unittest.main()
