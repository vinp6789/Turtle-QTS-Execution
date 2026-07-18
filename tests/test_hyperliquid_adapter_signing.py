"""Tests for hyperliquid_adapter.signing.HyperliquidWalletSigner (WP-6/7).

Requires eth-account (the approved dependency); skipped if absent so the
suite still runs on a stdlib-only checkout. Uses a fixed test key -- NOT a
real wallet -- and verifies signatures via eth-account's own recovery.
"""

import copy
import pickle
import unittest

try:
    from eth_account import Account
    from eth_account.messages import encode_typed_data
    from eth_utils import keccak
    _HAVE_ETH_ACCOUNT = True
except ImportError:
    _HAVE_ETH_ACCOUNT = False

from exchange_adapter import ExchangeAdapterError, ExchangeAuthenticationError

if _HAVE_ETH_ACCOUNT:
    from hyperliquid_adapter.signing import HyperliquidWalletSigner, _DOMAIN, _TYPES

TEST_KEY = "0x" + "11" * 32  # deterministic, non-secret test key
WALLET_REF = "hyperliquid_wallet_key_v1"
ENV_VAR = "TURTLE_SECRET_HYPERLIQUID_WALLET_KEY_V1"


def _env(key=TEST_KEY):
    return {ENV_VAR: key}


@unittest.skipUnless(_HAVE_ETH_ACCOUNT, "eth-account not installed")
class Construction(unittest.TestCase):
    def test_loads_key_and_exposes_address(self):
        signer = HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env=_env())
        expected = Account.from_key(TEST_KEY).address
        self.assertEqual(signer.wallet_address, expected)

    def test_missing_env_var_raises_authentication_error(self):
        with self.assertRaises(ExchangeAuthenticationError):
            HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env={})

    def test_blank_env_var_raises(self):
        with self.assertRaises(ExchangeAuthenticationError):
            HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env={ENV_VAR: "   "})

    def test_invalid_key_raises_authentication_error(self):
        with self.assertRaises(ExchangeAuthenticationError):
            HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env={ENV_VAR: "not-a-key"})

    def test_empty_ref_rejected(self):
        with self.assertRaises(ValueError):
            HyperliquidWalletSigner("", is_mainnet=False, env=_env())


@unittest.skipUnless(_HAVE_ETH_ACCOUNT, "eth-account not installed")
class Signing(unittest.TestCase):
    def setUp(self):
        self.signer = HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env=_env())
        self.address = Account.from_key(TEST_KEY).address

    def test_signature_recovers_to_wallet_address(self):
        conn = keccak(b"some-action-hash-input")
        sig = self.signer.sign_connection_id(conn)
        # Reconstruct the signature bytes and recover the signer.
        r = int(sig["r"], 16); s = int(sig["s"], 16); v = sig["v"]
        sig_bytes = r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([v])
        typed = {"domain": _DOMAIN, "types": _TYPES, "primaryType": "Agent",
                 "message": {"source": "b", "connectionId": conn}}
        recovered = Account.recover_message(encode_typed_data(full_message=typed), signature=sig_bytes)
        self.assertEqual(recovered, self.address)

    def test_signature_shape(self):
        sig = self.signer.sign_connection_id(keccak(b"x"))
        self.assertTrue(sig["r"].startswith("0x") and len(sig["r"]) == 66)
        self.assertTrue(sig["s"].startswith("0x") and len(sig["s"]) == 66)
        self.assertIn(sig["v"], (27, 28))

    def test_deterministic_for_same_input(self):
        conn = keccak(b"same")
        self.assertEqual(self.signer.sign_connection_id(conn), self.signer.sign_connection_id(conn))

    def test_mainnet_and_testnet_signatures_differ(self):
        conn = keccak(b"net-test")
        testnet = HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env=_env()).sign_connection_id(conn)
        mainnet = HyperliquidWalletSigner(WALLET_REF, is_mainnet=True, env=_env()).sign_connection_id(conn)
        self.assertNotEqual(testnet, mainnet)  # network is bound into the signature

    def test_non_32_byte_connection_id_rejected(self):
        with self.assertRaises(ValueError):
            self.signer.sign_connection_id(b"too-short")


@unittest.skipUnless(_HAVE_ETH_ACCOUNT, "eth-account not installed")
class EmergencyKill(unittest.TestCase):
    def test_revoke_blocks_signing(self):
        signer = HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env=_env())
        signer.revoke()
        self.assertTrue(signer.is_revoked)
        with self.assertRaises(ExchangeAuthenticationError):
            signer.sign_connection_id(b"\x00" * 32)

    def test_revoke_is_idempotent(self):
        signer = HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env=_env())
        signer.revoke()
        signer.revoke()  # must not raise
        self.assertTrue(signer.is_revoked)

    def test_revoke_drops_key_reference(self):
        signer = HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env=_env())
        signer.revoke()
        self.assertIsNone(signer._account)


@unittest.skipUnless(_HAVE_ETH_ACCOUNT, "eth-account not installed")
class NoKeyLeakage(unittest.TestCase):
    def setUp(self):
        self.signer = HyperliquidWalletSigner(WALLET_REF, is_mainnet=False, env=_env())

    def test_repr_does_not_contain_key(self):
        blob = repr(self.signer) + str(self.signer)
        self.assertNotIn("11" * 32, blob)
        self.assertNotIn(TEST_KEY, blob)
        self.assertIn(self.signer.wallet_address, blob)  # address is fine to show

    def test_cannot_pickle(self):
        with self.assertRaises(TypeError):
            pickle.dumps(self.signer)

    def test_cannot_deepcopy(self):
        with self.assertRaises(TypeError):
            copy.deepcopy(self.signer)


if __name__ == "__main__":
    unittest.main()
