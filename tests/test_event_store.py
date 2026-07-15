import os
import struct
import tempfile
import unittest
from pathlib import Path

from event_store import (
    CorruptEventStoreError,
    Event,
    EventStore,
    EventStoreClosedError,
    EventStoreLockError,
    EventType,
    MalformedEventError,
    read_events,
)
from event_store.codec import CHECKSUM_SIZE, HEADER_SIZE, MAGIC, encode_record


def _tmp_path() -> Path:
    fd, name = tempfile.mkstemp(suffix=".log")
    os.close(fd)
    os.unlink(name)
    return Path(name)


class NormalOperation(unittest.TestCase):
    def test_append_and_replay_round_trip(self):
        path = _tmp_path()
        store = EventStore(path)
        try:
            e1 = store.append(EventType.SYSTEM_STARTED, {"pid": 123})
            e2 = store.append(EventType.ORDER_SUBMITTED, {"symbol": "BTC", "qty": 1})
            self.assertEqual(e1.event_id, 1)
            self.assertEqual(e2.event_id, 2)
            replayed = list(store.replay())
            self.assertEqual([e.event_id for e in replayed], [1, 2])
            self.assertEqual(replayed[1].payload["symbol"], "BTC")
        finally:
            store.close()

    def test_monotonic_ids_and_utc_timestamps(self):
        path = _tmp_path()
        store = EventStore(path)
        try:
            events = [store.append(EventType.HEALTH_ALERT, {"n": i}) for i in range(5)]
            ids = [e.event_id for e in events]
            self.assertEqual(ids, sorted(ids))
            self.assertEqual(len(set(ids)), len(ids))
            for e in events:
                self.assertTrue(e.timestamp_utc.endswith("+00:00") or "Z" in e.timestamp_utc)
        finally:
            store.close()

    def test_event_immutable(self):
        path = _tmp_path()
        store = EventStore(path)
        try:
            e = store.append(EventType.SYSTEM_STARTED, {"a": {"b": [1, 2]}})
            with self.assertRaises(Exception):
                e.event_id = 999
            with self.assertRaises(TypeError):
                e.payload["a"] = "mutated"
        finally:
            store.close()

    def test_reopen_after_clean_close_preserves_all_events(self):
        path = _tmp_path()
        store = EventStore(path)
        store.append(EventType.SYSTEM_STARTED, {})
        store.append(EventType.ORDER_SUBMITTED, {"x": 1})
        store.close()

        store2 = EventStore(path)
        try:
            self.assertEqual(store2.event_count, 2)
            self.assertFalse(store2.recovery_report.tail_truncated)
        finally:
            store2.close()

    def test_context_manager(self):
        path = _tmp_path()
        with EventStore(path) as store:
            store.append(EventType.SYSTEM_STARTED, {})
        with EventStore(path) as store2:
            self.assertEqual(store2.event_count, 1)

    def test_second_writer_blocked_by_lock(self):
        path = _tmp_path()
        store1 = EventStore(path)
        try:
            with self.assertRaises(EventStoreLockError):
                EventStore(path)
        finally:
            store1.close()

    def test_lock_released_on_close_allows_new_writer(self):
        path = _tmp_path()
        store1 = EventStore(path)
        store1.append(EventType.SYSTEM_STARTED, {})
        store1.close()
        store2 = EventStore(path)
        try:
            self.assertEqual(store2.event_count, 1)
        finally:
            store2.close()

    def test_closed_store_rejects_append_and_replay(self):
        path = _tmp_path()
        store = EventStore(path)
        store.close()
        with self.assertRaises(EventStoreClosedError):
            store.append(EventType.SYSTEM_STARTED, {})
        with self.assertRaises(EventStoreClosedError):
            list(store.replay())


class IdempotencyLedger(unittest.TestCase):
    def test_duplicate_idempotency_key_returns_original_event(self):
        path = _tmp_path()
        store = EventStore(path)
        try:
            e1 = store.append(EventType.ORDER_SUBMITTED, {"attempt": 1}, idempotency_key="order-42")
            e2 = store.append(EventType.ORDER_SUBMITTED, {"attempt": 2}, idempotency_key="order-42")
            self.assertEqual(e1.event_id, e2.event_id)
            self.assertEqual(e2.payload["attempt"], 1)  # original data, not the retry's
            self.assertEqual(store.event_count, 1)
        finally:
            store.close()

    def test_idempotency_survives_reopen(self):
        path = _tmp_path()
        store = EventStore(path)
        store.append(EventType.ORDER_SUBMITTED, {}, idempotency_key="order-99")
        store.close()

        store2 = EventStore(path)
        try:
            self.assertTrue(store2.has_idempotency_key("order-99"))
            e = store2.append(EventType.ORDER_SUBMITTED, {"retry": True}, idempotency_key="order-99")
            self.assertEqual(store2.event_count, 1)
            self.assertNotIn("retry", e.payload)
        finally:
            store2.close()

    def test_has_and_get_by_idempotency_key(self):
        path = _tmp_path()
        store = EventStore(path)
        try:
            self.assertFalse(store.has_idempotency_key("nope"))
            self.assertIsNone(store.get_by_idempotency_key("nope"))
            e = store.append(EventType.ORDER_SUBMITTED, {}, idempotency_key="k1")
            self.assertTrue(store.has_idempotency_key("k1"))
            self.assertEqual(store.get_by_idempotency_key("k1").event_id, e.event_id)
        finally:
            store.close()


class MalformedEvents(unittest.TestCase):
    def setUp(self):
        self.path = _tmp_path()
        self.store = EventStore(self.path)

    def tearDown(self):
        self.store.close()

    def test_rejects_non_enum_event_type(self):
        with self.assertRaises(MalformedEventError):
            self.store.append("ORDER_SUBMITTED", {})

    def test_rejects_non_dict_payload(self):
        with self.assertRaises(MalformedEventError):
            self.store.append(EventType.SYSTEM_STARTED, "not-a-dict")

    def test_rejects_non_serializable_payload(self):
        with self.assertRaises(MalformedEventError):
            self.store.append(EventType.SYSTEM_STARTED, {"bad": object()})

    def test_rejects_oversized_payload(self):
        from event_store.store import MAX_PAYLOAD_BYTES
        with self.assertRaises(MalformedEventError):
            self.store.append(EventType.SYSTEM_STARTED, {"blob": "x" * (MAX_PAYLOAD_BYTES + 1)})

    def test_rejects_secret_shaped_field_name(self):
        with self.assertRaises(MalformedEventError) as ctx:
            self.store.append(EventType.ORDER_SUBMITTED, {"api_key": "whatever"})
        self.assertIn("secret", str(ctx.exception))

    def test_rejects_nested_secret_shaped_field_name(self):
        with self.assertRaises(MalformedEventError):
            self.store.append(EventType.ORDER_SUBMITTED, {"meta": {"signing_key": "x"}})

    def test_rejects_empty_idempotency_key(self):
        with self.assertRaises(MalformedEventError):
            self.store.append(EventType.SYSTEM_STARTED, {}, idempotency_key="")

    def test_rejects_bad_schema_version(self):
        with self.assertRaises(MalformedEventError):
            self.store.append(EventType.SYSTEM_STARTED, {}, schema_version=0)

    def test_no_event_written_after_rejected_append(self):
        try:
            self.store.append(EventType.SYSTEM_STARTED, {"bad": object()})
        except MalformedEventError:
            pass
        self.assertEqual(self.store.event_count, 0)


class CrashRecovery(unittest.TestCase):
    def test_torn_tail_is_truncated_and_recovery_reported(self):
        path = _tmp_path()
        store = EventStore(path)
        store.append(EventType.SYSTEM_STARTED, {})
        store.append(EventType.ORDER_SUBMITTED, {"n": 1})
        store.close()

        # Simulate a crash mid-write: append a valid-looking but truncated
        # trailing record (as if the process died partway through os.write).
        good_bytes = path.read_bytes()
        with open(path, "ab") as f:
            f.write(MAGIC + b"\x01" + b"\x00" * 5)  # header started, then nothing

        store2 = EventStore(path)
        try:
            self.assertEqual(store2.event_count, 2)
            self.assertTrue(store2.recovery_report.tail_truncated)
            self.assertGreater(store2.recovery_report.discarded_byte_count, 0)
        finally:
            store2.close()

        # file was physically healed
        self.assertEqual(path.read_bytes(), good_bytes)

    def test_engine_resumes_writing_cleanly_after_recovery(self):
        path = _tmp_path()
        store = EventStore(path)
        store.append(EventType.SYSTEM_STARTED, {})
        store.close()
        with open(path, "ab") as f:
            f.write(MAGIC)  # torn: only magic bytes made it

        store2 = EventStore(path)
        try:
            e = store2.append(EventType.ORDER_SUBMITTED, {"post_recovery": True})
            self.assertEqual(e.event_id, 2)
        finally:
            store2.close()

        store3 = EventStore(path)
        try:
            self.assertEqual(store3.event_count, 2)
            self.assertEqual([e.event_type for e in store3.replay()],
                              [EventType.SYSTEM_STARTED, EventType.ORDER_SUBMITTED])
        finally:
            store3.close()

    def test_zero_byte_file_is_treated_as_empty_store(self):
        path = _tmp_path()
        path.touch()
        store = EventStore(path)
        try:
            self.assertEqual(store.event_count, 0)
            self.assertFalse(store.recovery_report.tail_truncated)
        finally:
            store.close()

    def test_read_only_replay_never_mutates_file_on_torn_tail(self):
        path = _tmp_path()
        store = EventStore(path)
        store.append(EventType.SYSTEM_STARTED, {})
        store.close()
        with open(path, "ab") as f:
            f.write(MAGIC + b"\x01")
        before = path.read_bytes()

        events, report = read_events(path)
        self.assertEqual(len(events), 1)
        self.assertTrue(report.tail_truncated)
        after = path.read_bytes()
        self.assertEqual(before, after)  # untouched


class CorruptionDetection(unittest.TestCase):
    def _write_two_valid_events(self, path: Path):
        store = EventStore(path)
        store.append(EventType.SYSTEM_STARTED, {})
        store.append(EventType.ORDER_SUBMITTED, {"n": 1})
        store.close()

    def test_bad_magic_in_middle_of_file_is_hard_error(self):
        path = _tmp_path()
        self._write_two_valid_events(path)
        data = bytearray(path.read_bytes())
        data[0:4] = b"XXXX"  # corrupt the first record's magic
        path.write_bytes(bytes(data))

        with self.assertRaises(CorruptEventStoreError):
            EventStore(path)
        with self.assertRaises(CorruptEventStoreError):
            read_events(path)

    def test_checksum_corruption_with_trailing_valid_data_is_hard_error(self):
        path = _tmp_path()
        self._write_two_valid_events(path)
        data = bytearray(path.read_bytes())
        # flip a byte inside the FIRST record's payload region (not the
        # last record), so valid bytes still follow it in the file.
        flip_at = HEADER_SIZE + 2
        data[flip_at] ^= 0xFF
        path.write_bytes(bytes(data))

        with self.assertRaises(CorruptEventStoreError):
            EventStore(path)

    def test_checksum_corruption_at_true_tail_is_recovered(self):
        path = _tmp_path()
        self._write_two_valid_events(path)
        data = bytearray(path.read_bytes())
        data[-1] ^= 0xFF  # flip last checksum byte of the LAST record
        path.write_bytes(bytes(data))

        store = EventStore(path)
        try:
            self.assertEqual(store.event_count, 1)  # first event survives
            self.assertTrue(store.recovery_report.tail_truncated)
        finally:
            store.close()

    def test_unsupported_format_version_is_hard_error(self):
        path = _tmp_path()
        self._write_two_valid_events(path)
        data = bytearray(path.read_bytes())
        data[len(MAGIC)] = 99  # format_version byte of first record
        path.write_bytes(bytes(data))

        with self.assertRaises(CorruptEventStoreError):
            EventStore(path)

    def test_duplicate_event_id_on_disk_is_hard_error(self):
        path = _tmp_path()
        store = EventStore(path)
        store.append(EventType.SYSTEM_STARTED, {})
        store.close()

        # Manually fabricate a second, well-formed record that reuses
        # event_id 1 -- something a normal writer could never produce.
        envelope = b'{"event_type":"ORDER_SUBMITTED","idempotency_key":null,"payload":{},"schema_version":1,"timestamp_utc":"2026-01-01T00:00:00+00:00"}'
        forged = encode_record(1, envelope)
        with open(path, "ab") as f:
            f.write(forged)

        with self.assertRaises(CorruptEventStoreError):
            EventStore(path)

    def test_out_of_order_event_id_on_disk_is_hard_error(self):
        path = _tmp_path()
        store = EventStore(path)
        store.append(EventType.SYSTEM_STARTED, {})
        store.append(EventType.SYSTEM_STARTED, {})
        store.close()

        # Swap the two records' declared event_ids by re-encoding with IDs
        # reversed, to produce a non-monotonic sequence.
        events, _ = read_events(path)
        env1 = b'{"event_type":"SYSTEM_STARTED","idempotency_key":null,"payload":{},"schema_version":1,"timestamp_utc":"2026-01-01T00:00:00+00:00"}'
        env2 = b'{"event_type":"SYSTEM_STARTED","idempotency_key":null,"payload":{},"schema_version":1,"timestamp_utc":"2026-01-01T00:00:01+00:00"}'
        forged = encode_record(2, env1) + encode_record(1, env2)
        path.write_bytes(forged)

        with self.assertRaises(CorruptEventStoreError):
            EventStore(path)


class LargeReplay(unittest.TestCase):
    def test_large_number_of_events_replay_identically(self):
        path = _tmp_path()
        n = 5000
        store = EventStore(path)
        try:
            for i in range(n):
                store.append(EventType.HEALTH_ALERT, {"seq": i}, idempotency_key=f"health-{i}")
        finally:
            store.close()

        store2 = EventStore(path)
        try:
            self.assertEqual(store2.event_count, n)
            replayed = list(store2.replay())
            self.assertEqual([e.payload["seq"] for e in replayed], list(range(n)))
            self.assertEqual([e.event_id for e in replayed], list(range(1, n + 1)))
        finally:
            store2.close()

        events_from_disk, report = read_events(path)
        self.assertEqual(len(events_from_disk), n)
        self.assertFalse(report.tail_truncated)

    def test_replay_from_middle(self):
        path = _tmp_path()
        store = EventStore(path)
        try:
            for i in range(100):
                store.append(EventType.HEALTH_ALERT, {"seq": i})
            tail = list(store.replay(from_event_id=91))
            self.assertEqual(len(tail), 10)
            self.assertEqual(tail[0].event_id, 91)
        finally:
            store.close()


class WriteIntegrity(unittest.TestCase):
    """Covers the two gaps found in the final audit: short-write handling
    and resource cleanup on any __init__ failure, not just corruption."""

    def test_write_full_loops_over_short_writes(self):
        from event_store.store import _write_full

        path = _tmp_path()
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
        real_write = os.write
        calls = []

        def flaky_write(fd_, data):
            # Simulate the OS accepting only 3 bytes at a time.
            chunk = bytes(data)[:3]
            calls.append(len(chunk))
            return real_write(fd_, chunk)

        try:
            os.write = flaky_write
            _write_full(fd, b"0123456789")
        finally:
            os.write = real_write
            os.close(fd)

        self.assertGreater(len(calls), 1)  # actually exercised the loop
        self.assertEqual(path.read_bytes(), b"0123456789")

    def test_write_full_raises_on_zero_progress(self):
        from event_store.store import _write_full

        path = _tmp_path()
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
        real_write = os.write
        try:
            os.write = lambda fd_, data: 0
            with self.assertRaises(OSError):
                _write_full(fd, b"data")
        finally:
            os.write = real_write
            os.close(fd)

    def test_failed_write_truncates_back_and_leaves_no_stranded_record(self):
        path = _tmp_path()
        store = EventStore(path)
        try:
            store.append(EventType.SYSTEM_STARTED, {})
            size_after_first = path.stat().st_size

            real_write_full = __import__("event_store.store", fromlist=["_write_full"])._write_full

            def failing_write_full(fd, data):
                raise OSError("simulated disk failure mid-write")

            import event_store.store as store_module
            store_module._write_full = failing_write_full
            try:
                with self.assertRaises(OSError):
                    store.append(EventType.ORDER_SUBMITTED, {"n": 1})
            finally:
                store_module._write_full = real_write_full

            # file must be exactly back to where it was before the failed append
            self.assertEqual(path.stat().st_size, size_after_first)
            # in-memory state must not have advanced either
            self.assertEqual(store.event_count, 1)
            self.assertEqual(store.next_event_id, 2)
        finally:
            store.close()

        # a fresh open must see only the one successful event, cleanly
        store2 = EventStore(path)
        try:
            self.assertEqual(store2.event_count, 1)
            self.assertFalse(store2.recovery_report.tail_truncated)
        finally:
            store2.close()

    def test_next_append_after_failed_write_gets_correct_id(self):
        path = _tmp_path()
        store = EventStore(path)
        try:
            store.append(EventType.SYSTEM_STARTED, {})

            import event_store.store as store_module
            real_write_full = store_module._write_full
            store_module._write_full = lambda fd, data: (_ for _ in ()).throw(OSError("simulated"))
            try:
                with self.assertRaises(OSError):
                    store.append(EventType.ORDER_SUBMITTED, {})
            finally:
                store_module._write_full = real_write_full

            e = store.append(EventType.ORDER_SUBMITTED, {"retry": True})
            self.assertEqual(e.event_id, 2)  # not 3 -- the failed attempt must not consume an id
        finally:
            store.close()

    def test_init_failure_after_lock_acquired_releases_lock(self):
        path = _tmp_path()
        store = EventStore(path)
        store.append(EventType.SYSTEM_STARTED, {})
        store.close()

        # Force a torn tail so __init__ takes the ftruncate/fsync branch,
        # then make ftruncate fail to exercise the cleanup path.
        with open(path, "ab") as f:
            f.write(MAGIC + b"\x01")

        import event_store.store as store_module
        real_ftruncate = os.ftruncate
        os.ftruncate = lambda fd, length: (_ for _ in ()).throw(OSError("simulated ftruncate failure"))
        try:
            with self.assertRaises(OSError):
                EventStore(path)
        finally:
            os.ftruncate = real_ftruncate

        # lock must have been released despite the failure -- a new
        # EventStore on the same path must be able to acquire it.
        store2 = EventStore(path)
        try:
            self.assertEqual(store2.event_count, 1)
        finally:
            store2.close()


class BinaryModeIntegrity(unittest.TestCase):
    """Regression for the Module 3.1 critical-defect fix: on Windows the log
    must be opened with O_BINARY, or the C runtime opens it in text mode and
    translates 0x0A bytes in the binary record framing to 0x0D 0x0A, silently
    corrupting the fsync'd log (detected only as CorruptEventStoreError on the
    next open). On POSIX O_BINARY does not exist and there is no translation,
    so this test simply passes there too."""

    def test_record_framing_with_newline_bytes_survives_reopen(self):
        # event_id 10 is 0x00000000_0000000A: its 8-byte big-endian id field
        # contains a literal 0x0A. If the log were opened in text mode, that
        # byte would be rewritten to 0x0D 0x0A, changing the bytes the record
        # checksum was computed over, so reopening would fail. Append well
        # past id 10 so at least one record deterministically carries a 0x0A.
        path = _tmp_path()
        store = EventStore(path)
        try:
            for i in range(20):
                store.append(EventType.HEALTH_ALERT, {"seq": i})
        finally:
            store.close()

        # Bytes written must be exactly the bytes on disk -- no insertion.
        on_disk = path.read_bytes()
        events_direct, report = read_events(path)
        self.assertEqual(len(events_direct), 20)
        self.assertFalse(report.tail_truncated)
        self.assertEqual(report.discarded_byte_count, 0)

        # And a full reopen must reconstruct every event with no corruption.
        store2 = EventStore(path)
        try:
            self.assertEqual(store2.event_count, 20)
            self.assertFalse(store2.recovery_report.tail_truncated)
            self.assertEqual([e.event_id for e in store2.replay()], list(range(1, 21)))
        finally:
            store2.close()
        self.assertEqual(path.read_bytes(), on_disk)  # reopen left bytes intact


if __name__ == "__main__":
    unittest.main()
