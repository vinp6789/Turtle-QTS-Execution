"""Concurrency regression for the HyperliquidWalletSigner sign/revoke race
(Issue 1). Under many concurrent signers plus a concurrent revoke, the only
permitted outcomes are a valid signature dict or ExchangeAuthenticationError
-- never AttributeError or any other exception outside the closed hierarchy.

Requires eth-account; skipped if absent.
"""

import threading
import unittest

from exchange_adapter import ExchangeAuthenticationError

try:
    from eth_account import Account
    from eth_utils import keccak
    from hyperliquid_adapter.signing import HyperliquidWalletSigner
    _HAVE = True
except ImportError:
    _HAVE = False

WALLET_REF = "hyperliquid_wallet_key_v1"
ENV = {"TURTLE_SECRET_HYPERLIQUID_WALLET_KEY_V1": "0x" + "77" * 32}
CONN = keccak(b"action") if _HAVE else b"\x00" * 32


def _is_valid_sig(x):
    return (isinstance(x, dict) and set(x) == {"r", "s", "v"}
            and x["r"].startswith("0x") and x["s"].startswith("0x") and isinstance(x["v"], int))


@unittest.skipUnless(_HAVE, "eth-account not installed")
class SignRevokeRace(unittest.TestCase):
    def _run_once(self, n_signers=32):
        signer = HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env=ENV)
        address = Account.from_key(ENV["TURTLE_SECRET_HYPERLIQUID_WALLET_KEY_V1"]).address
        results = []
        errors = []
        barrier = threading.Barrier(n_signers + 1)  # +1 for the revoker
        lock = threading.Lock()

        def sign_worker():
            barrier.wait()  # release all at once, maximizing overlap with revoke
            try:
                sig = signer.sign_connection_id(CONN)
                with lock:
                    results.append(sig)
            except ExchangeAuthenticationError:
                with lock:
                    results.append("REVOKED")
            except BaseException as exc:  # anything else is a defect
                with lock:
                    errors.append(exc)

        def revoke_worker():
            barrier.wait()
            signer.revoke()

        threads = [threading.Thread(target=sign_worker) for _ in range(n_signers)]
        threads.append(threading.Thread(target=revoke_worker))
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return results, errors, address

    def test_no_unexpected_exception_across_many_runs(self):
        # Repeated runs to shake out the interleaving; each run has 32 signers
        # racing one revoke.
        for _ in range(60):
            results, errors, address = self._run_once()
            self.assertEqual(errors, [], f"unexpected exception(s) escaped: {errors!r}")
            # Every outcome is either a valid signature or a clean revocation.
            for r in results:
                if r == "REVOKED":
                    continue
                self.assertTrue(_is_valid_sig(r), f"non-signature result: {r!r}")
                # Any produced signature must recover to the wallet address.
                raw = int(r["r"], 16).to_bytes(32, "big") + int(r["s"], 16).to_bytes(32, "big") + bytes([r["v"]])
                self._assert_recovers(raw, address)

    def _assert_recovers(self, raw, address):
        from eth_account.messages import encode_typed_data
        typed = {
            "domain": {"name": "Exchange", "version": "1", "chainId": 1337, "verifyingContract": "0x" + "00" * 20},
            "types": {"Agent": [{"name": "source", "type": "string"}, {"name": "connectionId", "type": "bytes32"}],
                      "EIP712Domain": [{"name": "name", "type": "string"}, {"name": "version", "type": "string"},
                                       {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"}]},
            "primaryType": "Agent", "message": {"source": "b", "connectionId": CONN}}
        self.assertEqual(Account.recover_message(encode_typed_data(full_message=typed), signature=raw), address)

    def test_all_signs_after_revoke_are_rejected(self):
        # Once revoke has fully happened, EVERY subsequent sign is a clean
        # ExchangeAuthenticationError (never AttributeError).
        signer = HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env=ENV)
        signer.revoke()
        for _ in range(50):
            with self.assertRaises(ExchangeAuthenticationError):
                signer.sign_connection_id(CONN)

    def test_concurrent_revokes_are_safe(self):
        # Many threads revoking at once must not raise or corrupt state.
        signer = HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env=ENV)
        errs = []
        barrier = threading.Barrier(16)

        def revoke_worker():
            barrier.wait()
            try:
                signer.revoke()
            except BaseException as exc:  # pragma: no cover
                errs.append(exc)

        ts = [threading.Thread(target=revoke_worker) for _ in range(16)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(errs, [])
        self.assertTrue(signer.is_revoked)


if __name__ == "__main__":
    unittest.main()
