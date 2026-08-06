"""Verification tests for the Alpha Engine package scaffold (Milestone 0.1).

Milestone 0.1 added no functional code -- only an empty, importable
package skeleton. These tests verify the properties that scope depended
on, updated milestone-by-milestone as layers gain real content (as
anticipated in this file's original docstring):

  1. Every layer package imports cleanly. Layers not yet touched by a
     later milestone still export nothing (`_STILL_EMPTY_MODULES`);
     `alpha_engine.registry` (Milestone 0.2), `alpha_engine.data_sources`
     (Milestone 1.1), `alpha_engine.features` (Milestone 2.1),
     `alpha_engine.candidates` (Milestone 3.1/3.2), and
     `alpha_engine.validation` (Milestone 4.1) gained real exports and are
     covered by their own dedicated test files instead.
  2. No layer package imports any FROZEN, mutation-capable Execution
     Engine package (`_FORBIDDEN_EXECUTION_ENGINE_PACKAGES` below).
     `exchange_adapter` (pure value types: Symbol, FundingRate, etc.) and
     `trading_system` (the public MarketDataView/Strategy/TradeIntent
     seam) are deliberately NOT in that forbidden set -- Architecture
     v0.2 explicitly designs the Alpha Engine to consume the Execution
     Engine only through exactly those two, from any layer that needs
     them (alpha_engine.data_sources.funding_rate does so starting
     Milestone 1.1, wrapping MarketDataView.get_funding_rate as the
     roadmap specifies). This test's job is narrower and more durable:
     prove no alpha_engine file ever reaches into a genuinely frozen,
     capital-moving, or mutation-capable module.
  3. Nothing in the existing, pre-Alpha-Engine codebase references
     alpha_engine yet (additivity is one-directional and not yet wired).
"""

import ast
import importlib
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ALPHA_ENGINE_DIR = _REPO_ROOT / "alpha_engine"

_LAYER_MODULES = (
    "alpha_engine",
    "alpha_engine.registry",
    "alpha_engine.data_sources",
    "alpha_engine.features",
    "alpha_engine.candidates",
    "alpha_engine.validation",
    "alpha_engine.governance",
    "alpha_engine.lifecycle",
    "alpha_engine.portfolio",
    "alpha_engine.execution_bridge",
    "alpha_engine.historical",
)

# Layers still exporting nothing as of Milestone 4.1. Each populated
# layer below gained a real public API, covered by its own test file
# (test_alpha_engine_registry.py, test_alpha_engine_funding_rate_provider.py,
# test_alpha_engine_funding_rate_feature.py,
# test_alpha_engine_funding_rate_candidate.py,
# test_alpha_engine_funding_rate_rule_candidate.py,
# test_alpha_engine_validation_runner.py).
_POPULATED_MODULES = (
    "alpha_engine.registry", "alpha_engine.data_sources",
    "alpha_engine.features", "alpha_engine.candidates", "alpha_engine.validation",
    "alpha_engine.governance", "alpha_engine.portfolio", "alpha_engine.execution_bridge",
    "alpha_engine.lifecycle", "alpha_engine.historical",
)
_STILL_EMPTY_MODULES = tuple(m for m in _LAYER_MODULES if m not in _POPULATED_MODULES)

# The genuinely frozen / mutation-capable / capital-moving Execution
# Engine packages. No alpha_engine file may import any of these at
# module scope, ever, at any milestone before governed production wiring
# (alpha_engine.execution_bridge, Milestone 6.3+, and even then only
# trading_system -- never this set).
_FORBIDDEN_EXECUTION_ENGINE_PACKAGES = frozenset({
    "app",
    "composition_root",
    "config",
    "event_store",
    "execution_state_machine",
    "hyperliquid_adapter",
    "orchestration",
    "order_manager",
    "portfolio_manager",
    "position_manager",
    "risk_manager",
    "secrets_boundary",
})

# Directories whose production source is scanned for a premature
# alpha_engine reference (excludes alpha_engine/ itself and tests/, which
# necessarily reference it).
_PRODUCTION_DIRS = (
    "app", "composition_root", "config", "event_store", "exchange_adapter",
    "execution_state_machine", "hyperliquid_adapter", "orchestration",
    "order_manager", "portfolio_manager", "position_manager", "risk_manager",
    "secrets_boundary", "trading_system",
)


def _imported_top_level_names(py_file: Path) -> set:
    """Returns every top-level package name a module imports at module
    scope (module-level Import/ImportFrom nodes only -- sufficient here
    since Milestone 0.1 files contain no functions to hide a deferred
    import inside)."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:  # ignore relative imports (level > 0)
                names.add(node.module.split(".")[0])
    return names


class TestLayerPackagesImportCleanly(unittest.TestCase):
    def test_every_layer_module_imports(self):
        for module_name in _LAYER_MODULES:
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                self.assertIsNotNone(module)

    def test_every_still_empty_layer_module_exports_nothing(self):
        for module_name in _STILL_EMPTY_MODULES:
            with self.subTest(module=module_name):
                module = importlib.import_module(module_name)
                self.assertEqual(
                    module.__all__, [],
                    f"{module_name} should still export nothing as of Milestone 0.2",
                )

    def test_registry_exports_its_milestone_0_2_public_api(self):
        module = importlib.import_module("alpha_engine.registry")
        self.assertEqual(
            set(module.__all__),
            {
                "ExperimentRegistry", "ExperimentRecord", "RegistryStorage",
                "FileRegistryStorage", "LifecycleState", "ALLOWED_TRANSITIONS",
                "GOVERNANCE_DECISION_STATES", "LIVE_STATES", "TERMINAL_STATES",
                "INITIAL_STATE", "is_legal_transition",
                "RegistryError", "DuplicateExperimentError",
                "ExperimentNotFoundError", "AlreadySealedError", "ExperimentNotSealedError",
                "EvidenceAlreadyAttachedError", "IllegalLifecycleTransitionError",
                "LifecycleGuardError", "GovernanceRequiredError",
                "InvalidSpecificationError", "MalformedRegistryLogError",
                "RegistryLockError",
            },
        )

    def test_data_sources_exports_its_milestone_1_2_public_api(self):
        module = importlib.import_module("alpha_engine.data_sources")
        self.assertEqual(
            set(module.__all__),
            {
                "FundingRateProvider", "FundingRateReading",
                "OpenInterestProvider", "OpenInterestReading", "DataSourceError",
            },
        )

    def test_features_exports_its_milestone_2_2_public_api(self):
        module = importlib.import_module("alpha_engine.features")
        self.assertEqual(
            set(module.__all__),
            {
                "FundingRateFeature", "OpenInterestFeature", "LiquidationDensityFeature",
                "TrendMomentumFeature",
                # Shared ATR primitive: one implementation used by both the
                # feature (normalisation) and the candle bridge (exit sizing).
                "atr_from_candles", "true_ranges", "wilder_atr", "ATR_PERIOD",
                "FeatureValue", "FeatureMetadata", "FeatureError",
                "percentile_rank_centered", "zscore",
                "PCTRANK_NAME", "PCTRANK_VERSION", "ZSCORE_NAME", "ZSCORE_VERSION",
            },
        )

    def test_candidates_exports_its_milestone_3_3_public_api(self):
        module = importlib.import_module("alpha_engine.candidates")
        self.assertEqual(
            set(module.__all__),
            {
                "CandidateSpecification", "funding_rate_candidate_specification",
                "liquidation_density_candidate_specification",
                "TrendMomentumRuleCandidate",
                "trend_momentum_candidate_specification",
                "LiquidationDensityRuleCandidate",
                "FundingRateThresholdRuleCandidate", "open_interest_candidate_specification",
                "OpenInterestThresholdRuleCandidate",
                "open_interest_extremeness_candidate_specification",
                "OpenInterestExtremenessRuleCandidate",
                "CandidateSignal", "SignalDirection",
                "CANDIDATE_CATALOG", "CatalogEntry", "list_candidate_types",
                "get_candidate_type", "CandidateError",
            },
        )

    def test_lifecycle_exports_its_r7_public_api(self):
        module = importlib.import_module("alpha_engine.lifecycle")
        self.assertEqual(
            set(module.__all__),
            {"assess_degradation", "DegradationAssessment", "freeze_degraded", "DegradationError"},
        )

    def test_portfolio_exports_its_r6_public_api(self):
        module = importlib.import_module("alpha_engine.portfolio")
        self.assertEqual(set(module.__all__), {"select_signals", "PortfolioError"})

    def test_execution_bridge_exports_its_r6_public_api(self):
        module = importlib.import_module("alpha_engine.execution_bridge")
        self.assertEqual(
            set(module.__all__),
            {
                "ApprovedFundingAlphaStrategy", "load_approved_specifications",
                "STRATEGY_NAME", "ExecutionBridgeError",
                # D6 candle-derived sibling bridge (EMA+MACD+ATR).
                "ApprovedCandleAlphaStrategy", "CANDLE_INTERVAL",
            },
        )

    def test_governance_exports_its_r3_public_api(self):
        module = importlib.import_module("alpha_engine.governance")
        self.assertEqual(
            set(module.__all__),
            {
                "GovernanceDecision", "GovernanceDecisionType",
                "record_governance_decision", "approved_experiments", "GovernanceError",
            },
        )

    def test_validation_exports_its_milestone_4_6_public_api(self):
        module = importlib.import_module("alpha_engine.validation")
        self.assertEqual(
            set(module.__all__),
            {
                "run_validation", "EvaluateFn", "ValidationSample", "ValidationResult",
                "CriterionCheck", "CriterionOutcome", "EvidencePackage",
                "evidence_package_from_validation_result", "run_causality_audit",
                "CausalityAuditResult", "run_walk_forward_validation", "WalkForwardResult",
                "run_bootstrap_resampling", "BootstrapResult",
                "run_regime_stratified_validation", "RegimeStratificationResult",
                "attach_evidence_package", "ValidationError",
            },
        )

    def test_historical_exports_its_public_api(self):
        module = importlib.import_module("alpha_engine.historical")
        self.assertEqual(
            set(module.__all__),
            {
                "FundingRateObservation", "OpenInterestObservation", "MarkPriceObservation",
                "LiquidationObservation",
                "assess_quality", "DataQualityReport", "verify_checksum",
                "series_filename", "load", "merge_and_write", "MergeResult",
                "collect_open_interest", "collect_mark_price", "collect_metrics",
                "collect_funding_rate", "collect_liquidations", "CollectionResult", "HistoricalDataError",
            },
        )


class TestNoFrozenModuleCoupling(unittest.TestCase):
    """No alpha_engine file may import a genuinely frozen, mutation-
    capable Execution Engine package -- proving the Alpha Engine stays
    additive as real logic lands. exchange_adapter (value types) and
    trading_system (the public MarketDataView/Strategy seam) are the
    sanctioned exception, not tested here (see module docstring)."""

    def test_no_alpha_engine_file_imports_forbidden_execution_engine_packages(self):
        py_files = sorted(_ALPHA_ENGINE_DIR.rglob("*.py"))
        self.assertGreater(len(py_files), 0, "expected at least one alpha_engine .py file")
        for py_file in py_files:
            with self.subTest(file=str(py_file.relative_to(_REPO_ROOT))):
                imported = _imported_top_level_names(py_file)
                offending = imported & _FORBIDDEN_EXECUTION_ENGINE_PACKAGES
                self.assertEqual(
                    offending, set(),
                    f"{py_file} imports frozen/mutation-capable Execution Engine "
                    f"package(s) {offending} -- not sanctioned at any milestone so far",
                )


class TestNotYetWiredIntoExistingCode(unittest.TestCase):
    """Confirms additivity is currently one-directional: nothing shipped
    before Milestone 0.1 references alpha_engine. This assertion is
    expected to flip for app/main.py specifically at Milestone 6.4."""

    def test_no_production_file_references_alpha_engine(self):
        offenders = []
        for dir_name in _PRODUCTION_DIRS:
            base = _REPO_ROOT / dir_name
            if not base.is_dir():
                continue
            for py_file in base.rglob("*.py"):
                if "alpha_engine" in py_file.read_text(encoding="utf-8"):
                    offenders.append(str(py_file.relative_to(_REPO_ROOT)))
        self.assertEqual(
            offenders, [],
            f"unexpected alpha_engine reference(s) before any wiring milestone: {offenders}",
        )


class TestDecisionRecordExists(unittest.TestCase):
    def test_decisions_file_present_and_non_empty(self):
        decisions_path = _ALPHA_ENGINE_DIR / "DECISIONS.md"
        self.assertTrue(decisions_path.is_file())
        self.assertGreater(len(decisions_path.read_text(encoding="utf-8").strip()), 0)

    def test_decisions_file_documents_registry_substrate_choice(self):
        content = (_ALPHA_ENGINE_DIR / "DECISIONS.md").read_text(encoding="utf-8")
        self.assertIn("D1", content)
        self.assertIn("Experiment Registry substrate", content)


if __name__ == "__main__":
    unittest.main()
