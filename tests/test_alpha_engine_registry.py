"""Verification tests for the Experiment Registry write path (Alpha
Engine Milestone 0.2).

Covers: the RegistryStorage abstraction (including a non-file test
double, to prove ExperimentRegistry's business logic is genuinely
storage-agnostic), FileRegistryStorage as one concrete backend,
ExperimentRegistry's create()/seal()/get()/exists() write path, lineage,
fingerprint determinism, immutability, durability/replay across a
simulated process restart, corrupt-log handling, and basic thread-safety.
"""

import json
import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path
from typing import Any, List, Mapping

from alpha_engine.registry import (
    AlreadySealedError,
    DuplicateExperimentError,
    ExperimentNotFoundError,
    ExperimentRecord,
    ExperimentRegistry,
    FileRegistryStorage,
    InvalidSpecificationError,
    MalformedRegistryLogError,
    RegistryStorage,
)


class _InMemoryStorage(RegistryStorage):
    """Minimal, non-file test double. Its only purpose is to prove
    ExperimentRegistry depends on nothing but the RegistryStorage
    contract -- if the registry's tests below pass identically against
    this and against FileRegistryStorage, the abstraction is doing its
    job."""

    def __init__(self):
        self._entries: List[Mapping[str, Any]] = []

    def append(self, entry: Mapping[str, Any]) -> None:
        self._entries.append(dict(entry))

    def read_all(self) -> List[Mapping[str, Any]]:
        return list(self._entries)


# -- FileRegistryStorage: isolated unit tests --

class TestFileRegistryStorage(unittest.TestCase):
    def test_read_all_on_nonexistent_file_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = FileRegistryStorage(Path(tmp) / "does_not_exist.jsonl")
            self.assertEqual(storage.read_all(), [])

    def test_append_then_read_all_round_trips_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = FileRegistryStorage(Path(tmp) / "registry.jsonl")
            storage.append({"type": "a", "n": 1})
            storage.append({"type": "b", "n": 2})
            storage.append({"type": "c", "n": 3})
            self.assertEqual(
                storage.read_all(),
                [{"type": "a", "n": 1}, {"type": "b", "n": 2}, {"type": "c", "n": 3}],
            )

    def test_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "a" / "b" / "c" / "registry.jsonl"
            storage = FileRegistryStorage(nested)
            storage.append({"type": "x"})
            self.assertTrue(nested.is_file())

    def test_one_json_object_per_line_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.jsonl"
            storage = FileRegistryStorage(path)
            storage.append({"type": "a"})
            storage.append({"type": "b"})
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            for line in lines:
                json.loads(line)  # must not raise

    def test_malformed_json_line_raises_with_line_number(self):
        # Malformed JSON NOT on the trailing line cannot be explained by a
        # crash during append (earlier lines are already fsync'd before a
        # later append begins) -- must still raise (B3: torn-tail
        # tolerance applies ONLY to the true last line; see
        # test_malformed_trailing_line_is_tolerated_as_torn_tail below).
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.jsonl"
            path.write_text('{"type": "a"}\nNOT JSON\n{"type": "c"}\n', encoding="utf-8")
            storage = FileRegistryStorage(path)
            with self.assertRaises(MalformedRegistryLogError) as ctx:
                storage.read_all()
            self.assertIn("line 2", str(ctx.exception))

    def test_malformed_trailing_line_is_tolerated_as_torn_tail(self):
        # B3: an interrupted final flush (crash mid-append) is a normal,
        # recoverable condition -- discarded silently, not raised.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.jsonl"
            path.write_text('{"type": "a"}\n{"type": "b"}\nNOT JS', encoding="utf-8")
            storage = FileRegistryStorage(path)
            self.assertEqual(storage.read_all(), [{"type": "a"}, {"type": "b"}])

    def test_checksum_round_trips_and_is_not_exposed_to_callers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.jsonl"
            storage = FileRegistryStorage(path)
            storage.append({"type": "a", "n": 1})
            raw_line = json.loads(path.read_text(encoding="utf-8").strip())
            self.assertIn("_checksum", raw_line)
            self.assertEqual(storage.read_all(), [{"type": "a", "n": 1}])

    def test_corrupted_non_trailing_checksum_raises(self):
        # B3: a line that still parses as JSON but whose content was
        # altered after being written (bit-level corruption, not a torn
        # write) must be caught even though it is syntactically valid.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.jsonl"
            storage = FileRegistryStorage(path)
            storage.append({"type": "a", "n": 1})
            storage.append({"type": "b", "n": 2})
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            tampered = json.loads(lines[0])
            tampered["n"] = 999  # content changed, checksum now stale
            lines[0] = json.dumps(tampered, sort_keys=True)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with self.assertRaises(MalformedRegistryLogError):
                storage.read_all()

    def test_corrupted_trailing_checksum_is_tolerated_as_torn_tail(self):
        # A checksum-verified-corrupt LAST line is just as recoverable a
        # torn write as an unparseable one.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.jsonl"
            storage = FileRegistryStorage(path)
            storage.append({"type": "a", "n": 1})
            storage.append({"type": "b", "n": 2})
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            tampered = json.loads(lines[-1])
            tampered["n"] = 999
            lines[-1] = json.dumps(tampered, sort_keys=True)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.assertEqual(storage.read_all(), [{"type": "a", "n": 1}])

    def test_pre_checksum_log_line_is_accepted_unverified(self):
        # Backward compatibility: a line written before B3 (no
        # "_checksum" key at all) must still load cleanly.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.jsonl"
            path.write_text('{"type": "a", "n": 1}\n', encoding="utf-8")
            storage = FileRegistryStorage(path)
            self.assertEqual(storage.read_all(), [{"type": "a", "n": 1}])

    def test_concurrent_append_is_mutually_exclusive(self):
        # B3: a second writer holding the lock on the same file at the
        # same instant must be rejected, not silently interleaved. This
        # test acquires the lock using the same stdlib primitive
        # storage.py uses internally (fcntl/msvcrt directly, NOT an
        # import from alpha_engine.registry.storage or event_store --
        # alpha_engine keeps its locking implementation local per its
        # standing no-frozen-coupling architecture boundary, and a test
        # simulating an independent external locker should not reach into
        # storage.py's private helpers either).
        import os

        from alpha_engine.registry import RegistryLockError

        try:
            import fcntl
        except ImportError:
            fcntl = None
        try:
            import msvcrt
        except ImportError:
            msvcrt = None

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.jsonl"
            storage = FileRegistryStorage(path)
            storage.append({"type": "a"})  # ensures the file exists

            fd = os.open(str(path), os.O_WRONLY | getattr(os, "O_BINARY", 0))
            try:
                if fcntl is not None:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:
                    offset = 1 << 62
                    os.lseek(fd, offset, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    os.lseek(fd, 0, os.SEEK_SET)
                with self.assertRaises(RegistryLockError):
                    storage.append({"type": "b"})
            finally:
                os.close(fd)

    def test_blank_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.jsonl"
            path.write_text('{"type": "a"}\n\n\n{"type": "b"}\n', encoding="utf-8")
            storage = FileRegistryStorage(path)
            self.assertEqual(storage.read_all(), [{"type": "a"}, {"type": "b"}])


class TestRegistryStorageAbstraction(unittest.TestCase):
    def test_cannot_instantiate_abstract_base_directly(self):
        with self.assertRaises(TypeError):
            RegistryStorage()  # abstract methods not implemented


# -- ExperimentRegistry write path: parameterized over BOTH storage backends --

class _ExperimentRegistryWritePathMixin:
    """Every test in this mixin runs against both FileRegistryStorage and
    the in-memory test double via the two concrete subclasses below --
    proving ExperimentRegistry's behavior does not depend on which
    storage backend is injected."""

    def _make_storage(self) -> RegistryStorage:
        raise NotImplementedError

    def _make_registry(self) -> ExperimentRegistry:
        return ExperimentRegistry(self._make_storage())

    def test_create_returns_unsealed_record(self):
        registry = self._make_registry()
        record = registry.create("exp-1", {"a": 1})
        self.assertIsInstance(record, ExperimentRecord)
        self.assertEqual(record.experiment_id, "exp-1")
        self.assertEqual(dict(record.specification), {"a": 1})
        self.assertIsNone(record.parent_id)
        self.assertFalse(record.sealed)
        self.assertIsNone(record.sealed_at_utc)
        self.assertTrue(record.created_at_utc)
        self.assertTrue(record.fingerprint)

    def test_duplicate_experiment_id_raises(self):
        registry = self._make_registry()
        registry.create("exp-1", {"a": 1})
        with self.assertRaises(DuplicateExperimentError):
            registry.create("exp-1", {"a": 2})

    def test_create_with_unknown_parent_raises(self):
        registry = self._make_registry()
        with self.assertRaises(ExperimentNotFoundError):
            registry.create("child", {"a": 1}, parent_id="does-not-exist")

    def test_create_with_known_parent_links_lineage(self):
        registry = self._make_registry()
        registry.create("parent", {"a": 1})
        child = registry.create("child", {"a": 2}, parent_id="parent")
        self.assertEqual(child.parent_id, "parent")

    def test_non_mapping_specification_raises(self):
        registry = self._make_registry()
        with self.assertRaises(InvalidSpecificationError):
            registry.create("exp-1", ["not", "a", "mapping"])

    def test_non_json_native_specification_raises(self):
        registry = self._make_registry()
        with self.assertRaises(InvalidSpecificationError):
            registry.create("exp-1", {"risk_pct": Decimal("0.01")})

    def test_blank_experiment_id_raises(self):
        registry = self._make_registry()
        with self.assertRaises(ValueError):
            registry.create("   ", {"a": 1})

    def test_fingerprint_is_deterministic_for_identical_specification(self):
        registry = self._make_registry()
        r1 = registry.create("exp-1", {"a": 1, "b": 2})
        r2 = registry.create("exp-2", {"b": 2, "a": 1})  # same content, different key order
        self.assertEqual(r1.fingerprint, r2.fingerprint)

    def test_fingerprint_differs_for_different_specification(self):
        registry = self._make_registry()
        r1 = registry.create("exp-1", {"a": 1})
        r2 = registry.create("exp-2", {"a": 2})
        self.assertNotEqual(r1.fingerprint, r2.fingerprint)

    def test_seal_marks_sealed_with_timestamp(self):
        registry = self._make_registry()
        registry.create("exp-1", {"a": 1})
        sealed = registry.seal("exp-1")
        self.assertTrue(sealed.sealed)
        self.assertIsNotNone(sealed.sealed_at_utc)

    def test_seal_unknown_experiment_raises(self):
        registry = self._make_registry()
        with self.assertRaises(ExperimentNotFoundError):
            registry.seal("does-not-exist")

    def test_seal_twice_raises(self):
        registry = self._make_registry()
        registry.create("exp-1", {"a": 1})
        registry.seal("exp-1")
        with self.assertRaises(AlreadySealedError):
            registry.seal("exp-1")

    def test_get_unknown_experiment_raises(self):
        registry = self._make_registry()
        with self.assertRaises(ExperimentNotFoundError):
            registry.get("does-not-exist")

    def test_exists_true_and_false(self):
        registry = self._make_registry()
        self.assertFalse(registry.exists("exp-1"))
        registry.create("exp-1", {"a": 1})
        self.assertTrue(registry.exists("exp-1"))

    def test_get_reflects_latest_state(self):
        registry = self._make_registry()
        registry.create("exp-1", {"a": 1})
        registry.seal("exp-1")
        self.assertTrue(registry.get("exp-1").sealed)

    def test_len_counts_registered_experiments(self):
        registry = self._make_registry()
        self.assertEqual(len(registry), 0)
        registry.create("exp-1", {"a": 1})
        registry.create("exp-2", {"a": 2})
        self.assertEqual(len(registry), 2)

    def test_experiment_record_is_immutable(self):
        registry = self._make_registry()
        record = registry.create("exp-1", {"a": 1})
        with self.assertRaises(Exception):
            record.sealed = True  # frozen dataclass -> raises

    def test_experiment_record_specification_is_read_only(self):
        registry = self._make_registry()
        record = registry.create("exp-1", {"a": 1})
        with self.assertRaises(TypeError):
            record.specification["a"] = 999  # MappingProxyType -> raises


class TestExperimentRegistryWithFileStorage(_ExperimentRegistryWritePathMixin, unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._path = Path(self._tmp.name) / "registry.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def _make_storage(self) -> RegistryStorage:
        return FileRegistryStorage(self._path)


class TestExperimentRegistryWithInMemoryStorage(_ExperimentRegistryWritePathMixin, unittest.TestCase):
    def _make_storage(self) -> RegistryStorage:
        return _InMemoryStorage()


# -- Durability: replay across a simulated process restart (file backend only) --

class TestReplayDurability(unittest.TestCase):
    def test_new_registry_instance_reconstructs_full_state_from_same_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.jsonl"

            first = ExperimentRegistry(FileRegistryStorage(path))
            first.create("parent", {"family": "funding_rate"})
            first.seal("parent")
            first.create("child", {"family": "funding_rate", "variant": 2}, parent_id="parent")
            # "child" deliberately left unsealed.

            # Simulate a process restart: brand-new instance, same file.
            second = ExperimentRegistry(FileRegistryStorage(path))

            self.assertEqual(len(second), 2)
            parent = second.get("parent")
            self.assertTrue(parent.sealed)
            self.assertIsNotNone(parent.sealed_at_utc)
            child = second.get("child")
            self.assertFalse(child.sealed)
            self.assertEqual(child.parent_id, "parent")
            self.assertEqual(dict(child.specification), {"family": "funding_rate", "variant": 2})

            # Same fingerprint reproduced across the restart.
            self.assertEqual(parent.fingerprint, first.get("parent").fingerprint)

    def test_restarted_registry_still_enforces_duplicate_and_seal_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.jsonl"
            first = ExperimentRegistry(FileRegistryStorage(path))
            first.create("exp-1", {"a": 1})
            first.seal("exp-1")

            second = ExperimentRegistry(FileRegistryStorage(path))
            with self.assertRaises(DuplicateExperimentError):
                second.create("exp-1", {"a": 2})
            with self.assertRaises(AlreadySealedError):
                second.seal("exp-1")


# -- Corrupt-log handling --

class TestCorruptLogHandling(unittest.TestCase):
    def _write_raw(self, path: Path, entries) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    def test_duplicate_created_entry_raises_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.jsonl"
            entry = {
                "type": "experiment_created", "experiment_id": "exp-1",
                "fingerprint": "f", "parent_id": None, "specification": {},
                "created_at_utc": "t",
            }
            self._write_raw(path, [entry, entry])
            with self.assertRaises(MalformedRegistryLogError):
                ExperimentRegistry(FileRegistryStorage(path))

    def test_sealed_entry_for_unknown_experiment_raises_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.jsonl"
            self._write_raw(path, [
                {"type": "experiment_sealed", "experiment_id": "ghost", "sealed_at_utc": "t"},
            ])
            with self.assertRaises(MalformedRegistryLogError):
                ExperimentRegistry(FileRegistryStorage(path))

    def test_duplicate_sealed_entry_raises_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.jsonl"
            self._write_raw(path, [
                {
                    "type": "experiment_created", "experiment_id": "exp-1",
                    "fingerprint": "f", "parent_id": None, "specification": {},
                    "created_at_utc": "t",
                },
                {"type": "experiment_sealed", "experiment_id": "exp-1", "sealed_at_utc": "t1"},
                {"type": "experiment_sealed", "experiment_id": "exp-1", "sealed_at_utc": "t2"},
            ])
            with self.assertRaises(MalformedRegistryLogError):
                ExperimentRegistry(FileRegistryStorage(path))

    def test_unrecognized_entry_type_raises_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.jsonl"
            self._write_raw(path, [{"type": "something_unknown", "experiment_id": "exp-1"}])
            with self.assertRaises(MalformedRegistryLogError):
                ExperimentRegistry(FileRegistryStorage(path))

    def test_missing_required_field_raises_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.jsonl"
            # missing "fingerprint", "specification", "created_at_utc"
            self._write_raw(path, [{"type": "experiment_created", "experiment_id": "exp-1"}])
            with self.assertRaises(MalformedRegistryLogError):
                ExperimentRegistry(FileRegistryStorage(path))

    def test_created_entry_with_unknown_parent_raises_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.jsonl"
            self._write_raw(path, [
                {
                    "type": "experiment_created", "experiment_id": "child",
                    "fingerprint": "f", "parent_id": "ghost-parent", "specification": {},
                    "created_at_utc": "t",
                },
            ])
            with self.assertRaises(MalformedRegistryLogError):
                ExperimentRegistry(FileRegistryStorage(path))


# -- Thread-safety smoke test --

class TestConcurrentWrites(unittest.TestCase):
    def test_concurrent_create_calls_all_land_without_loss_or_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.jsonl"
            registry = ExperimentRegistry(FileRegistryStorage(path))
            n_threads = 20
            errors = []

            def worker(i):
                try:
                    registry.create(f"exp-{i}", {"i": i})
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(errors, [])
            self.assertEqual(len(registry), n_threads)

            # A fresh instance over the same file must also see all writes --
            # proves the concurrent appends were durably and correctly persisted,
            # not just correct in the original instance's in-memory state.
            reloaded = ExperimentRegistry(FileRegistryStorage(path))
            self.assertEqual(len(reloaded), n_threads)
            for i in range(n_threads):
                self.assertTrue(reloaded.exists(f"exp-{i}"))


if __name__ == "__main__":
    unittest.main()
