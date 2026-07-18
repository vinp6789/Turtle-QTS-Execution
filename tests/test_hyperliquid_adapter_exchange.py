"""Tests for hyperliquid_adapter.exchange (WP-6 transport foundation).

Dependency-free (no eth-account, no network)."""

import unittest

from hyperliquid_adapter.exchange import EXCHANGE_PATH, NonceSource, build_exchange_request


class Nonces(unittest.TestCase):
    def test_strictly_increasing_even_with_a_stuck_clock(self):
        src = NonceSource(clock_ms=lambda: 1000)  # clock never advances
        values = [src.next() for _ in range(5)]
        self.assertEqual(values, [1000, 1001, 1002, 1003, 1004])
        self.assertEqual(sorted(set(values)), values)  # strictly increasing, unique

    def test_uses_clock_when_it_advances(self):
        t = {"ms": 5000}
        src = NonceSource(clock_ms=lambda: t["ms"])
        first = src.next()
        t["ms"] = 9000
        second = src.next()
        self.assertEqual(first, 5000)
        self.assertEqual(second, 9000)

    def test_never_goes_backward_on_clock_regression(self):
        t = {"ms": 8000}
        src = NonceSource(clock_ms=lambda: t["ms"])
        first = src.next()
        t["ms"] = 3000  # clock steps backward
        second = src.next()
        self.assertGreater(second, first)

    def test_thread_safe_uniqueness(self):
        import threading

        src = NonceSource(clock_ms=lambda: 1)  # maximal contention on the +1 path
        out = []
        lock = threading.Lock()

        def worker():
            v = src.next()
            with lock:
                out.append(v)

        threads = [threading.Thread(target=worker) for _ in range(200)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        self.assertEqual(len(set(out)), 200)  # no duplicates under contention


class Envelope(unittest.TestCase):
    def _sig(self):
        return {"r": "0x" + "a" * 64, "s": "0x" + "b" * 64, "v": 27}

    def test_builds_expected_body(self):
        action = {"type": "order", "orders": []}
        body = build_exchange_request(action, 1234, self._sig())
        self.assertEqual(body, {"action": action, "nonce": 1234, "signature": self._sig(), "vaultAddress": None})

    def test_vault_address_passthrough(self):
        body = build_exchange_request({"type": "cancel"}, 1, self._sig(), vault_address="0xabc")
        self.assertEqual(body["vaultAddress"], "0xabc")

    def test_rejects_non_positive_nonce(self):
        with self.assertRaises(ValueError):
            build_exchange_request({"type": "order"}, 0, self._sig())

    def test_rejects_bad_signature(self):
        with self.assertRaises(ValueError):
            build_exchange_request({"type": "order"}, 1, {"r": "0x1"})  # missing s, v

    def test_rejects_non_dict_action(self):
        with self.assertRaises(ValueError):
            build_exchange_request("not-a-dict", 1, self._sig())

    def test_exchange_path_constant(self):
        self.assertEqual(EXCHANGE_PATH, "/exchange")


if __name__ == "__main__":
    unittest.main()
