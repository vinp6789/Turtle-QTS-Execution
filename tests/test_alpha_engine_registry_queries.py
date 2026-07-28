"""Verification tests for the Experiment Registry query path (Alpha
Engine Milestone 0.3).

Every query is read-only over ExperimentRegistry's already-replayed
in-memory state -- RegistryStorage is untouched by this milestone (see
TestStorageAbstractionUnchanged), and every query test below is
parameterized over both FileRegistryStorage and an in-memory test double
to prove that in-memory-only design decision holds in practice, not just
in prose.
"""

import tempfile
import unittest
from pathlib import Path
from typing import Any, List, Mapping

from alpha_engine.registry import (
    ExperimentNotFoundError,
    ExperimentRegistry,
    FileRegistryStorage,
    MalformedRegistryLogError,
    RegistryStorage,
)


class _InMemoryStorage(RegistryStorage):
    def __init__(self):
        self._entries: List[Mapping[str, Any]] = []

    def append(self, entry: Mapping[str, Any]) -> None:
        self._entries.append(dict(entry))

    def read_all(self) -> List[Mapping[str, Any]]:
        return list(self._entries)


class TestStorageAbstractionUnchanged(unittest.TestCase):
    """Milestone 0.3's explicit constraint: RegistryStorage stays exactly
    as Milestone 0.2 defined it. Richer query behavior lives in
    ExperimentRegistry instead."""

    def test_registry_storage_still_has_exactly_two_abstract_methods(self):
        self.assertEqual(RegistryStorage.__abstractmethods__, frozenset({"append", "read_all"}))


class _QueryTestMixin:
    """Every test below runs against both FileRegistryStorage and an
    in-memory double via the two concrete subclasses further down --
    proving the query path is genuinely storage-agnostic, as it must be
    since it only ever reads self._records."""

    def _make_storage(self) -> RegistryStorage:
        raise NotImplementedError

    def _make_registry(self) -> ExperimentRegistry:
        return ExperimentRegistry(self._make_storage())

    # -- list_experiments --

    def test_list_experiments_returns_everything_by_default(self):
        registry = self._make_registry()
        registry.create("a", {"x": 1})
        registry.create("b", {"x": 2})
        ids = [r.experiment_id for r in registry.list_experiments()]
        self.assertEqual(ids, ["a", "b"])

    def test_list_experiments_filters_by_sealed_true(self):
        registry = self._make_registry()
        registry.create("a", {"x": 1})
        registry.create("b", {"x": 2})
        registry.seal("a")
        ids = [r.experiment_id for r in registry.list_experiments(sealed=True)]
        self.assertEqual(ids, ["a"])

    def test_list_experiments_filters_by_sealed_false(self):
        registry = self._make_registry()
        registry.create("a", {"x": 1})
        registry.create("b", {"x": 2})
        registry.seal("a")
        ids = [r.experiment_id for r in registry.list_experiments(sealed=False)]
        self.assertEqual(ids, ["b"])

    def test_list_experiments_on_empty_registry_returns_empty_tuple(self):
        registry = self._make_registry()
        self.assertEqual(registry.list_experiments(), ())

    def test_list_experiments_invalid_sealed_type_raises(self):
        registry = self._make_registry()
        with self.assertRaises(ValueError):
            registry.list_experiments(sealed="yes")

    # -- get_roots --

    def test_get_roots_returns_only_parentless_experiments(self):
        registry = self._make_registry()
        registry.create("root-1", {})
        registry.create("root-2", {})
        registry.create("child", {}, parent_id="root-1")
        ids = {r.experiment_id for r in registry.get_roots()}
        self.assertEqual(ids, {"root-1", "root-2"})

    def test_get_roots_on_empty_registry_returns_empty_tuple(self):
        registry = self._make_registry()
        self.assertEqual(registry.get_roots(), ())

    # -- get_children --

    def test_get_children_unknown_id_raises(self):
        registry = self._make_registry()
        with self.assertRaises(ExperimentNotFoundError):
            registry.get_children("does-not-exist")

    def test_get_children_of_leaf_is_empty(self):
        registry = self._make_registry()
        registry.create("a", {})
        self.assertEqual(registry.get_children("a"), ())

    def test_get_children_returns_only_direct_children(self):
        registry = self._make_registry()
        registry.create("root", {})
        registry.create("child-1", {}, parent_id="root")
        registry.create("child-2", {}, parent_id="root")
        registry.create("grandchild", {}, parent_id="child-1")
        ids = {r.experiment_id for r in registry.get_children("root")}
        self.assertEqual(ids, {"child-1", "child-2"})  # not grandchild

    # -- get_ancestors --

    def test_get_ancestors_unknown_id_raises(self):
        registry = self._make_registry()
        with self.assertRaises(ExperimentNotFoundError):
            registry.get_ancestors("does-not-exist")

    def test_get_ancestors_of_root_is_empty(self):
        registry = self._make_registry()
        registry.create("root", {})
        self.assertEqual(registry.get_ancestors("root"), ())

    def test_get_ancestors_returns_root_first_chain(self):
        registry = self._make_registry()
        registry.create("grandparent", {})
        registry.create("parent", {}, parent_id="grandparent")
        registry.create("child", {}, parent_id="parent")
        ids = [r.experiment_id for r in registry.get_ancestors("child")]
        self.assertEqual(ids, ["grandparent", "parent"])

    # -- get_descendants --

    def test_get_descendants_unknown_id_raises(self):
        registry = self._make_registry()
        with self.assertRaises(ExperimentNotFoundError):
            registry.get_descendants("does-not-exist")

    def test_get_descendants_of_leaf_is_empty(self):
        registry = self._make_registry()
        registry.create("a", {})
        self.assertEqual(registry.get_descendants("a"), ())

    def test_get_descendants_includes_full_subtree(self):
        registry = self._make_registry()
        registry.create("root", {})
        registry.create("child-1", {}, parent_id="root")
        registry.create("child-2", {}, parent_id="root")
        registry.create("grandchild", {}, parent_id="child-1")
        registry.create("unrelated-root", {})  # must not appear
        ids = {r.experiment_id for r in registry.get_descendants("root")}
        self.assertEqual(ids, {"child-1", "child-2", "grandchild"})

    # -- find_by_fingerprint --

    def test_find_by_fingerprint_returns_every_experiment_sharing_content(self):
        registry = self._make_registry()
        registry.create("exp-1", {"a": 1, "b": 2})
        registry.create("exp-2", {"b": 2, "a": 1})  # identical content, different key order
        registry.create("exp-3", {"a": 1, "b": 3})  # different content
        fp = registry.get("exp-1").fingerprint
        ids = {r.experiment_id for r in registry.find_by_fingerprint(fp)}
        self.assertEqual(ids, {"exp-1", "exp-2"})

    def test_find_by_fingerprint_no_match_returns_empty_tuple(self):
        registry = self._make_registry()
        registry.create("exp-1", {"a": 1})
        self.assertEqual(registry.find_by_fingerprint("0" * 64), ())

    def test_find_by_fingerprint_blank_raises(self):
        registry = self._make_registry()
        with self.assertRaises(ValueError):
            registry.find_by_fingerprint("   ")

    # -- find_by_specification_field --

    def test_find_by_specification_field_matches_across_experiments(self):
        registry = self._make_registry()
        registry.create("exp-1", {"data_source": "funding_rate", "version": 1})
        registry.create("exp-2", {"data_source": "funding_rate", "version": 2})
        registry.create("exp-3", {"data_source": "open_interest", "version": 1})
        ids = {r.experiment_id for r in registry.find_by_specification_field("data_source", "funding_rate")}
        self.assertEqual(ids, {"exp-1", "exp-2"})

    def test_find_by_specification_field_no_match_returns_empty_tuple(self):
        registry = self._make_registry()
        registry.create("exp-1", {"data_source": "funding_rate"})
        self.assertEqual(registry.find_by_specification_field("data_source", "on_chain"), ())

    def test_find_by_specification_field_missing_key_returns_empty_tuple(self):
        registry = self._make_registry()
        registry.create("exp-1", {"data_source": "funding_rate"})
        self.assertEqual(registry.find_by_specification_field("nonexistent_key", "anything"), ())

    def test_find_by_specification_field_blank_key_raises(self):
        registry = self._make_registry()
        with self.assertRaises(ValueError):
            registry.find_by_specification_field("  ", "value")

    def test_find_by_specification_field_matches_non_string_values(self):
        registry = self._make_registry()
        registry.create("exp-1", {"enabled": True, "count": 3, "label": None})
        registry.create("exp-2", {"enabled": False, "count": 3, "label": None})
        self.assertEqual(
            {r.experiment_id for r in registry.find_by_specification_field("enabled", True)},
            {"exp-1"},
        )
        self.assertEqual(
            {r.experiment_id for r in registry.find_by_specification_field("count", 3)},
            {"exp-1", "exp-2"},
        )
        self.assertEqual(
            {r.experiment_id for r in registry.find_by_specification_field("label", None)},
            {"exp-1", "exp-2"},
        )


class TestQueriesWithFileStorage(_QueryTestMixin, unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._path = Path(self._tmp.name) / "registry.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def _make_storage(self) -> RegistryStorage:
        return FileRegistryStorage(self._path)


class TestQueriesWithInMemoryStorage(_QueryTestMixin, unittest.TestCase):
    def _make_storage(self) -> RegistryStorage:
        return _InMemoryStorage()


# -- Cycle-guard white-box tests: a cycle is structurally unreachable
# through create()'s own parent-must-already-exist validation, so these
# tests deliberately poke at internal state to prove the defensive guard
# in get_ancestors()/get_descendants() actually works, not just that it
# reads as though it should. --

class TestCycleGuards(unittest.TestCase):
    def _registry_with_two_nodes(self) -> ExperimentRegistry:
        registry = ExperimentRegistry(_InMemoryStorage())
        registry.create("a", {})
        registry.create("b", {}, parent_id="a")
        return registry

    def test_get_ancestors_raises_on_injected_cycle(self):
        registry = self._registry_with_two_nodes()
        # Directly corrupt in-memory state to form a 2-cycle: a -> b -> a.
        registry._records["a"]["parent_id"] = "b"
        with self.assertRaises(MalformedRegistryLogError):
            registry.get_ancestors("a")

    def test_get_descendants_raises_on_injected_cycle(self):
        registry = self._registry_with_two_nodes()
        registry._records["a"]["parent_id"] = "b"
        with self.assertRaises(MalformedRegistryLogError):
            registry.get_descendants("b")


if __name__ == "__main__":
    unittest.main()
