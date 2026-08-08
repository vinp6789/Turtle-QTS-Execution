"""The canonical launch surfaces: one construction path, three modes.

These tests exist because the audit of 2026-08-08 found a duplicated
engine constructor in scripts/run_platform.py that had silently lost the
durable emergency-stop restoration performed by AppState.create(), and a
launch-mode trap in which scripts/run_local.* auto-loaded a .env
containing TURTLE_EXEC_MODE=live -- so a launcher whose banner said
"paper mode" resolved deploy/engine.paper.toml to a real
HyperliquidAdapter bound to the live venue.

Every test below asserts a SAFETY property of the launch layer. None of
them tests strategy logic, metrics, research, or execution behaviour.

No network: every case uses the real paper config and MockExchangeAdapter.
"""

import tempfile
import unittest
from pathlib import Path

from config import ConfigValidationError, load_config

from app.runtime import AppSettings, AppState, build_engine_from_settings
from app.runtime.state import EmergencyStopActive
from exchange_adapter import MockExchangeAdapter

_SIGNING_ENV = {"TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1": "signing-secret-material"}
_PAPER_CONFIG = "deploy/engine.paper.toml"


def _env(store_path, **overrides):
    e = dict(_SIGNING_ENV)
    e["ENGINE_CONFIG_PATH"] = _PAPER_CONFIG
    e["ENGINE_STORE_PATH"] = str(store_path)
    e["WORKER_ENABLED"] = "false"
    e.update(overrides)
    return e


class _Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store_path = Path(self._tmp.name) / "events.log"


# ---------------------------------------------------------------- SURFACE A
class TestPaperCannotReachTheVenue(_Case):
    """A command advertised as paper must never submit an order."""

    def test_paper_config_wires_the_mock_adapter_not_hyperliquid(self):
        env = _env(self.store_path)
        state = AppState.create(AppSettings.from_env(env), env=env)
        self.addCleanup(state.shutdown)
        self.assertIsInstance(state.engine.adapter, MockExchangeAdapter)
        self.assertEqual(type(state.engine.adapter).__name__, "MockExchangeAdapter")

    def test_paper_adapter_has_no_transport_at_all(self):
        """The strongest available statement: there is no seam through
        which a paper adapter could reach a venue, because it holds no
        transport object to reach one with."""
        env = _env(self.store_path)
        state = AppState.create(AppSettings.from_env(env), env=env)
        self.addCleanup(state.shutdown)
        self.assertFalse(hasattr(state.engine.adapter, "_transport"))

    def test_run_local_scripts_force_paper_before_reading_any_env_file(self):
        """The ordering IS the safety property: the mode is asserted
        before .env is read, and the canonical loader never overwrites an
        already-set variable."""
        for script in ("scripts/run_local.sh", "scripts/run_local.ps1"):
            text = Path(script).read_text(encoding="utf-8")
            mode_at = text.find("TURTLE_EXEC_MODE")
            envfile_at = text.find("ENV_FILE")
            self.assertNotEqual(mode_at, -1, f"{script} must pin the mode")
            self.assertNotEqual(envfile_at, -1, f"{script} must use the canonical loader")
            self.assertLess(mode_at, envfile_at,
                            f"{script} must pin the mode BEFORE loading any env file")
            self.assertNotIn("app.main", text, f"{script} must use the canonical launcher")


# ------------------------------------------------------- THE MODE TRAP ITSELF
class TestModeCannotBeChangedByEnvironment(_Case):
    """config/loader.py must fail closed on contradiction, in both
    directions. This is what protects EVERY launcher at once, rather than
    each one defending itself."""

    def test_paper_file_plus_live_env_var_is_refused(self):
        with self.assertRaises(ConfigValidationError) as ctx:
            load_config(_PAPER_CONFIG, env={"TURTLE_EXEC_MODE": "live"})
        self.assertIn("mode conflict", str(ctx.exception))

    def test_agreement_is_permitted(self):
        config = load_config(_PAPER_CONFIG, env={"TURTLE_EXEC_MODE": "paper"})
        self.assertEqual(config.environment, "paper")

    def test_absent_variable_leaves_the_file_authoritative(self):
        self.assertEqual(load_config(_PAPER_CONFIG, env={}).environment, "paper")

    def test_the_exact_historical_trap_is_closed(self):
        """The literal reproduction: paper config + the repository's own
        .env content. This resolved to environment='live' before the fix."""
        with self.assertRaises(ConfigValidationError):
            load_config(_PAPER_CONFIG, env={
                "TURTLE_EXEC_MODE": "live",
                "TURTLE_DEPLOYMENT_ACCOUNT_ADDRESS": "0x" + "1" * 40,
            })


# ---------------------------------------------------------------- SURFACE D
class TestDockerDefaultIsSafe(unittest.TestCase):
    def test_dockerfile_uses_the_canonical_launcher_and_a_paper_config(self):
        text = Path("Dockerfile").read_text(encoding="utf-8")
        self.assertIn("scripts.run_platform", text)
        self.assertNotIn('CMD ["python", "-m", "app.main"]', text)
        self.assertIn("ENGINE_CONFIG_PATH=deploy/engine.paper.toml", text)

    def test_the_shipped_default_config_is_paper(self):
        self.assertEqual(load_config(_PAPER_CONFIG, env={}).environment, "paper")

    def test_every_deployment_surface_uses_the_canonical_launcher(self):
        """Dockerfile, Railway and the Procfile are all launch surfaces.
        Two of them were missed on the first pass of this consolidation;
        this test is what stops a third from being missed later."""
        for path in ("Dockerfile", "railway.json", "Procfile"):
            text = Path(path).read_text(encoding="utf-8")
            self.assertIn("scripts.run_platform", text,
                          f"{path} must use the canonical launcher")
            self.assertNotIn("-m app.main", text,
                             f"{path} must not launch the strategy-less variant")


# ------------------------------------------------------ THE EMERGENCY STOP
class TestEmergencyStopSurvivesRestart(_Case):
    """The regression the duplicated constructor already caused once.

    AppState.create() restores a durable emergency stop; the deleted copy
    in run_platform.py did not, so a restarted simulated engine resumed
    trading after an emergency stop. There is now one construction path,
    and this test proves it honours the durable state.
    """

    def test_emergency_stop_survives_a_restart_through_the_canonical_path(self):
        env = _env(self.store_path)

        # 1. enter emergency stop
        first = AppState.create(AppSettings.from_env(env), env=env)
        first.emergency_stop()
        self.assertTrue(first.emergency_stopped)
        first.shutdown()

        # 2. restart through the canonical constructor
        second = AppState.create(AppSettings.from_env(env), env=env)
        self.addCleanup(second.shutdown)

        # 3. the stop is still in force
        self.assertTrue(
            second.emergency_stopped,
            "a restarted engine must honour the durable emergency stop")

        # 4. and no cycle -- therefore no order -- may run
        with self.assertRaises(EmergencyStopActive):
            second.run_one_cycle()
        self.assertEqual(second.cycles_run, 0)


# ------------------------------------------------- ONE CONSTRUCTION PATH
class TestNoSecondConstructor(unittest.TestCase):
    """Guards the consolidation itself: if a second constructor is ever
    reintroduced, this fails rather than the emergency stop diverging
    again silently."""

    def test_the_launcher_contains_no_engine_construction(self):
        text = Path("scripts/run_platform.py").read_text(encoding="utf-8")
        for forbidden in ("build_engine(", "load_deployment_settings", "_risk_limits",
                          "AppState("):
            self.assertNotIn(
                forbidden, text,
                f"scripts/run_platform.py must not construct an engine ({forbidden})")
        self.assertIn("AppState.create(", text)

    def test_transport_factory_default_is_none_on_both_layers(self):
        """None must remain the default so every pre-existing caller keeps
        receiving the real transport, unchanged."""
        import inspect
        for fn in (build_engine_from_settings, AppState.create):
            sig = inspect.signature(fn)
            self.assertIn("transport_factory", sig.parameters)
            self.assertIsNone(sig.parameters["transport_factory"].default)


if __name__ == "__main__":
    unittest.main()
