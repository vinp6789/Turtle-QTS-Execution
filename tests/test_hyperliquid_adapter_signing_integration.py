"""WP-6/7 integration + backward-compatibility guarantees.

Proves (a) the frozen core and the read-only adapter path do NOT import
eth-account, and (b) a wallet signer can be held by the adapter and its
address exposed, while mutations remain fail-closed (WP-8 not begun).
"""

import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from event_store import EventStore
from secrets_boundary import EnvironmentHmacBackend, SigningBoundary

from exchange_adapter import (
    CancelAllRequest,
    ExchangeAdapterError,
    OrderRequest,
    OrderSide,
    OrderType,
    Symbol,
    TimeInForce,
)

from hyperliquid_adapter import HttpResponse, HyperliquidAdapter

try:
    from hyperliquid_adapter.signing import HyperliquidWalletSigner
    _HAVE_ETH_ACCOUNT = True
except Exception:  # pragma: no cover
    _HAVE_ETH_ACCOUNT = False

SIGNING_REF = "hyperliquid_signing_key_v1"
ACCOUNT = "0x1111111111111111111111111111111111111111"
TEST_KEY = "0x" + "22" * 32
WALLET_ENV = {"TURTLE_SECRET_HYPERLIQUID_WALLET_KEY_V1": TEST_KEY}


def _boundary():
    env = {"TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1": "test-material"}
    return SigningBoundary([SIGNING_REF], "1.0.0", "hyperliquid", backend=EnvironmentHmacBackend(env=env))


def _fake_transport(url, payload, timeout_seconds):
    return HttpResponse(status_code=200, body={"BTC": "1"})


def _package_init_text():
    init_path = Path(__file__).resolve().parent.parent / "hyperliquid_adapter" / "__init__.py"
    return init_path.read_text(encoding="utf-8")


class ReadOnlyPathIsEthAccountFree(unittest.TestCase):
    def test_package_init_does_not_import_signing_or_eth_account(self):
        # The package __init__ must never import the signing submodule (which
        # needs eth-account), so `import hyperliquid_adapter` and the whole
        # read-only path stay dependency-free.
        text = _package_init_text()
        self.assertNotIn("eth_account", text)
        self.assertNotIn("from .signing", text)
        self.assertNotIn("import signing", text)

    def test_adapter_module_does_not_import_signing(self):
        adapter_path = Path(__file__).resolve().parent.parent / "hyperliquid_adapter" / "adapter.py"
        text = adapter_path.read_text(encoding="utf-8")
        self.assertNotIn("eth_account", text)
        self.assertNotIn("from .signing", text)
        self.assertNotIn("import signing", text)

    def test_readonly_adapter_works_without_a_wallet_signer(self):
        a = HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT, transport=_fake_transport)
        a.connect()
        self.assertIsNone(a.wallet_address)  # no signer configured


@unittest.skipUnless(_HAVE_ETH_ACCOUNT, "eth-account not installed")
class AdapterExposesSignerAddress(unittest.TestCase):
    def setUp(self):
        fd, p = tempfile.mkstemp(suffix=".log")
        os.close(fd)
        os.unlink(p)
        self.path = Path(p)
        self.store = EventStore(p)
        self.signer = HyperliquidWalletSigner("hyperliquid_wallet_key_v1", is_mainnet=False, env=WALLET_ENV)
        from hyperliquid_adapter.transport import TESTNET_BASE_URL
        self.adapter = HyperliquidAdapter(
            _boundary(), SIGNING_REF, ACCOUNT, transport=_fake_transport,
            event_store=self.store, wallet_signer=self.signer, base_url=TESTNET_BASE_URL,
        )
        self.adapter.connect()

    def tearDown(self):
        self.store.close()
        if self.path.exists():
            self.path.unlink()

    def test_wallet_address_is_exposed(self):
        self.assertEqual(self.adapter.wallet_address, self.signer.wallet_address)

    def test_mutation_without_a_signer_still_fails_closed(self):
        # The fail-closed guarantee now applies specifically to the
        # no-signer case (WP-8 wires mutations only when a signer is present).
        no_signer = HyperliquidAdapter(_boundary(), SIGNING_REF, ACCOUNT, transport=_fake_transport)
        no_signer.connect()
        with self.assertRaises(ExchangeAdapterError):
            no_signer.cancel_all(CancelAllRequest(request_id="r1"))


if __name__ == "__main__":
    unittest.main()
