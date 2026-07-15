import copy
import hashlib
import hmac
import pickle
import unittest
from typing import FrozenSet, List

from secrets_boundary import (
    ENGINE_ID,
    MAX_SIGNING_PAYLOAD_BYTES,
    EnvironmentHmacBackend,
    PayloadTooLargeError,
    SecretRevokedError,
    SecretsConfigurationError,
    SecretsStartupError,
    SigningBackend,
    SigningBoundary,
    SigningPurpose,
    build_preimage,
    UnknownSecretReferenceError,
)
from secrets_boundary.backend import _env_var_name

SIGNING_REF = "hyperliquid_signing_key_v1"
TELEGRAM_REF = "telegram_bot_token_v1"
CANARY = "CANARY-SECRET-VALUE-DO-NOT-LEAK-9f8e7d6c"
ENGINE_VERSION = "1.0.0"
EXCHANGE = "hyperliquid"


def _boundary(refs, env=None, backend=None, engine_version=ENGINE_VERSION, exchange=EXCHANGE):
    return SigningBoundary(
        refs, engine_version=engine_version, exchange_name=exchange, backend=backend, env=env
    )


def _env_with(**refs_to_values):
    return {_env_var_name(ref): value for ref, value in refs_to_values.items()}


class HappyPath(unittest.TestCase):
    def test_loads_and_signs(self):
        env = _env_with(**{SIGNING_REF: "secret-material-one", TELEGRAM_REF: "secret-material-two"})
        boundary = _boundary([SIGNING_REF, TELEGRAM_REF], env=env)
        sig = boundary.sign(SIGNING_REF, SigningPurpose.ORDER, b"order-payload")
        preimage = build_preimage(ENGINE_VERSION, EXCHANGE, SigningPurpose.ORDER, b"order-payload")
        expected = hmac.new(b"secret-material-one", preimage, hashlib.sha256).digest()
        self.assertEqual(sig, expected)
        # the raw message is NOT what gets signed
        naive = hmac.new(b"secret-material-one", b"order-payload", hashlib.sha256).digest()
        self.assertNotEqual(sig, naive)

    def test_different_refs_produce_different_signatures(self):
        env = _env_with(**{SIGNING_REF: "material-a", TELEGRAM_REF: "material-b"})
        boundary = _boundary([SIGNING_REF, TELEGRAM_REF], env=env)
        sig_a = boundary.sign(SIGNING_REF, SigningPurpose.ORDER, b"same-message")
        sig_b = boundary.sign(TELEGRAM_REF, SigningPurpose.ORDER, b"same-message")
        self.assertNotEqual(sig_a, sig_b)

    def test_has_reference(self):
        env = _env_with(**{SIGNING_REF: "material"})
        boundary = _boundary([SIGNING_REF], env=env)
        self.assertTrue(boundary.has_reference(SIGNING_REF))
        self.assertFalse(boundary.has_reference("unregistered_ref_v1"))

    def test_single_ref_works_standalone(self):
        env = _env_with(**{SIGNING_REF: "solo-material"})
        boundary = _boundary([SIGNING_REF], env=env)
        self.assertEqual(len(boundary.sign(SIGNING_REF, SigningPurpose.ORDER, b"x")), 32)  # sha256 digest length


class FailurePaths(unittest.TestCase):
    def test_missing_secret_raises_startup_error(self):
        with self.assertRaises(SecretsStartupError) as ctx:
            _boundary([SIGNING_REF], env={})
        self.assertIn("missing secret", str(ctx.exception))

    def test_empty_secret_raises_startup_error(self):
        env = _env_with(**{SIGNING_REF: ""})
        with self.assertRaises(SecretsStartupError) as ctx:
            _boundary([SIGNING_REF], env=env)
        self.assertIn("empty secret", str(ctx.exception))

    def test_duplicate_reference_raises_configuration_error(self):
        env = _env_with(**{SIGNING_REF: "material"})
        with self.assertRaises(SecretsConfigurationError) as ctx:
            _boundary([SIGNING_REF, SIGNING_REF], env=env)
        self.assertIn("duplicate secret reference", str(ctx.exception))

    def test_invalid_format_raises_configuration_error(self):
        for bad_ref in ["HyperliquidKey", "hyperliquid_key", "hyperliquid_key_v", "hyperliquid key v1", ""]:
            with self.subTest(bad_ref=bad_ref):
                with self.assertRaises(SecretsConfigurationError) as ctx:
                    _boundary([bad_ref], env={})
                self.assertIn("invalid format", str(ctx.exception))

    def test_unknown_reference_raises_at_sign_time(self):
        env = _env_with(**{SIGNING_REF: "material"})
        boundary = _boundary([SIGNING_REF], env=env)
        with self.assertRaises(UnknownSecretReferenceError):
            boundary.sign("never_registered_v1", SigningPurpose.ORDER, b"msg")

    def test_unknown_reference_raises_on_revoke(self):
        env = _env_with(**{SIGNING_REF: "material"})
        boundary = _boundary([SIGNING_REF], env=env)
        with self.assertRaises(UnknownSecretReferenceError):
            boundary.revoke("never_registered_v1")

    def test_revoked_reference_cannot_sign(self):
        env = _env_with(**{SIGNING_REF: "material"})
        boundary = _boundary([SIGNING_REF], env=env)
        boundary.revoke(SIGNING_REF)
        with self.assertRaises(SecretRevokedError):
            boundary.sign(SIGNING_REF, SigningPurpose.ORDER, b"msg")

    def test_revoke_all_blocks_every_reference(self):
        env = _env_with(**{SIGNING_REF: "material-a", TELEGRAM_REF: "material-b"})
        boundary = _boundary([SIGNING_REF, TELEGRAM_REF], env=env)
        boundary.revoke_all()
        with self.assertRaises(SecretRevokedError):
            boundary.sign(SIGNING_REF, SigningPurpose.ORDER, b"msg")
        with self.assertRaises(SecretRevokedError):
            boundary.sign(TELEGRAM_REF, SigningPurpose.ORDER, b"msg")

    def test_revoke_is_idempotent(self):
        env = _env_with(**{SIGNING_REF: "material"})
        boundary = _boundary([SIGNING_REF], env=env)
        boundary.revoke(SIGNING_REF)
        boundary.revoke(SIGNING_REF)  # must not raise
        self.assertTrue(boundary.is_revoked(SIGNING_REF))

    def test_duplicate_secret_value_across_refs_raises_startup_error(self):
        env = _env_with(**{SIGNING_REF: "identical-value", TELEGRAM_REF: "identical-value"})
        with self.assertRaises(SecretsStartupError) as ctx:
            _boundary([SIGNING_REF, TELEGRAM_REF], env=env)
        self.assertIn("identical secret material", str(ctx.exception))

    def test_all_missing_secrets_reported_together(self):
        with self.assertRaises(SecretsStartupError) as ctx:
            _boundary([SIGNING_REF, TELEGRAM_REF], env={})
        self.assertEqual(len(ctx.exception.issues), 2)


class SecurityProperties(unittest.TestCase):
    def _boundary_with_canary(self):
        env = _env_with(**{SIGNING_REF: CANARY})
        return _boundary([SIGNING_REF], env=env)

    def test_canary_never_appears_in_repr_or_str(self):
        boundary = self._boundary_with_canary()
        self.assertNotIn(CANARY, repr(boundary))
        self.assertNotIn(CANARY, str(boundary))

    def test_canary_never_appears_in_backend_repr(self):
        env = _env_with(**{SIGNING_REF: CANARY})
        backend = EnvironmentHmacBackend(env=env)
        backend.validate_and_load(frozenset([SIGNING_REF]))
        self.assertNotIn(CANARY, repr(backend))

    def test_canary_never_appears_in_any_failure_exception(self):
        cases = []

        try:
            _boundary([SIGNING_REF], env={})
        except SecretsStartupError as exc:
            cases.append(str(exc))

        try:
            _boundary([SIGNING_REF, SIGNING_REF], env=_env_with(**{SIGNING_REF: CANARY}))
        except SecretsConfigurationError as exc:
            cases.append(str(exc))

        try:
            _boundary([SIGNING_REF, TELEGRAM_REF], env=_env_with(**{SIGNING_REF: CANARY, TELEGRAM_REF: CANARY}),
            )
        except SecretsStartupError as exc:
            cases.append(str(exc))

        boundary = self._boundary_with_canary()
        try:
            boundary.sign("unknown_ref_v1", SigningPurpose.ORDER, b"msg")
        except UnknownSecretReferenceError as exc:
            cases.append(str(exc))

        boundary.revoke(SIGNING_REF)
        try:
            boundary.sign(SIGNING_REF, SigningPurpose.ORDER, b"msg")
        except SecretRevokedError as exc:
            cases.append(str(exc))

        self.assertGreater(len(cases), 0)
        for message in cases:
            self.assertNotIn(CANARY, message)

    def test_pickling_boundary_raises(self):
        boundary = self._boundary_with_canary()
        with self.assertRaises(TypeError):
            pickle.dumps(boundary)

    def test_deepcopy_boundary_raises(self):
        boundary = self._boundary_with_canary()
        with self.assertRaises(TypeError):
            copy.deepcopy(boundary)

    def test_pickling_backend_raises(self):
        env = _env_with(**{SIGNING_REF: CANARY})
        backend = EnvironmentHmacBackend(env=env)
        backend.validate_and_load(frozenset([SIGNING_REF]))
        with self.assertRaises(TypeError):
            pickle.dumps(backend)

    def test_immutable_cannot_set_existing_attribute(self):
        boundary = self._boundary_with_canary()
        with self.assertRaises(AttributeError):
            boundary._expected_refs = frozenset()

    def test_immutable_cannot_set_new_attribute(self):
        boundary = self._boundary_with_canary()
        with self.assertRaises(AttributeError):
            boundary.some_new_field = "value"

    def test_discard_zeroizes_material(self):
        env = _env_with(**{SIGNING_REF: CANARY})
        backend = EnvironmentHmacBackend(env=env)
        backend.validate_and_load(frozenset([SIGNING_REF]))
        buf = backend._materials[SIGNING_REF]
        self.assertIn(ord("C"), buf)  # canary's material is present pre-discard
        backend.discard(SIGNING_REF)
        # the same buffer object must now be all zero bytes
        self.assertTrue(all(b == 0 for b in buf))

    def test_revoke_removes_material_from_backend(self):
        env = _env_with(**{SIGNING_REF: CANARY})
        boundary = self._boundary_with_canary()
        boundary.revoke(SIGNING_REF)
        self.assertNotIn(SIGNING_REF, boundary._backend._materials)


class PluggableBackend(unittest.TestCase):
    """Proves a future hardware/KMS backend can be substituted through the
    same SigningBackend interface with no change to SigningBoundary."""

    class _FakeKmsBackend(SigningBackend):
        """Test double standing in for a future KMS backend: holds no
        material in this process at all, just an opaque handle name, and
        signs by delegating to a fixed, deterministic scheme so the test
        can assert on the outcome."""

        def __init__(self):
            self._known_refs = set()

        def validate_and_load(self, refs: FrozenSet[str]) -> List[str]:
            self._known_refs = set(refs)
            return []

        def sign(self, ref: str, message: bytes) -> bytes:
            return hashlib.sha256(ref.encode() + b":" + message).digest()

        def discard(self, ref: str) -> None:
            self._known_refs.discard(ref)

    def test_boundary_works_with_alternate_backend(self):
        backend = self._FakeKmsBackend()
        boundary = _boundary([SIGNING_REF], backend=backend, env={})
        sig = boundary.sign(SIGNING_REF, SigningPurpose.ORDER, b"payload")
        preimage = build_preimage(ENGINE_VERSION, EXCHANGE, SigningPurpose.ORDER, b"payload")
        self.assertEqual(sig, hashlib.sha256(SIGNING_REF.encode() + b":" + preimage).digest())

    def test_alternate_backend_still_honors_revocation(self):
        backend = self._FakeKmsBackend()
        boundary = _boundary([SIGNING_REF], backend=backend, env={})
        boundary.revoke(SIGNING_REF)
        with self.assertRaises(SecretRevokedError):
            boundary.sign(SIGNING_REF, SigningPurpose.ORDER, b"payload")


class DomainSeparation(unittest.TestCase):
    """Item 1: every signature is bound to engine, version, exchange, purpose."""

    def _b(self, engine_version=ENGINE_VERSION, exchange=EXCHANGE):
        return _boundary([SIGNING_REF], env=_env_with(**{SIGNING_REF: "material"}),
                         engine_version=engine_version, exchange=exchange)

    def test_different_purpose_yields_different_signature(self):
        b = self._b()
        order = b.sign(SIGNING_REF, SigningPurpose.ORDER, b"payload")
        cancel = b.sign(SIGNING_REF, SigningPurpose.CANCEL, b"payload")
        self.assertNotEqual(order, cancel)

    def test_every_purpose_pair_is_distinct(self):
        b = self._b()
        sigs = {p: b.sign(SIGNING_REF, p, b"same") for p in SigningPurpose}
        self.assertEqual(len(set(sigs.values())), len(SigningPurpose))

    def test_different_exchange_yields_different_signature(self):
        a = self._b(exchange="hyperliquid").sign(SIGNING_REF, SigningPurpose.ORDER, b"p")
        c = self._b(exchange="lighter").sign(SIGNING_REF, SigningPurpose.ORDER, b"p")
        self.assertNotEqual(a, c)

    def test_different_engine_version_yields_different_signature(self):
        a = self._b(engine_version="1.0.0").sign(SIGNING_REF, SigningPurpose.ORDER, b"p")
        c = self._b(engine_version="1.0.1").sign(SIGNING_REF, SigningPurpose.ORDER, b"p")
        self.assertNotEqual(a, c)

    def test_preimage_contains_engine_id(self):
        pre = build_preimage(ENGINE_VERSION, EXCHANGE, SigningPurpose.ORDER, b"p")
        self.assertIn(ENGINE_ID, pre)

    def test_preimage_encoding_is_unambiguous(self):
        # field-boundary confusion must not be possible: moving a character
        # from one domain field to the next must change the preimage.
        a = build_preimage("1.0", "hyperliquidX", SigningPurpose.ORDER, b"p")
        c = build_preimage("1.0X", "hyperliquid", SigningPurpose.ORDER, b"p")
        self.assertNotEqual(a, c)

    def test_string_purpose_rejected(self):
        b = self._b()
        with self.assertRaises(TypeError):
            b.sign(SIGNING_REF, "ORDER", b"payload")

    def test_non_bytes_message_rejected(self):
        b = self._b()
        with self.assertRaises(TypeError):
            b.sign(SIGNING_REF, SigningPurpose.ORDER, "not-bytes")

    def test_empty_engine_version_rejected_at_startup(self):
        with self.assertRaises(SecretsConfigurationError) as ctx:
            self._b(engine_version="")
        self.assertIn("engine_version", str(ctx.exception))

    def test_empty_exchange_name_rejected_at_startup(self):
        with self.assertRaises(SecretsConfigurationError) as ctx:
            self._b(exchange="")
        self.assertIn("exchange_name", str(ctx.exception))


class PayloadSizeLimit(unittest.TestCase):
    """Item 3: signing requests above the bound are rejected."""

    def _b(self):
        return _boundary([SIGNING_REF], env=_env_with(**{SIGNING_REF: "material"}))

    def test_payload_at_limit_is_accepted(self):
        b = self._b()
        sig = b.sign(SIGNING_REF, SigningPurpose.ORDER, b"x" * MAX_SIGNING_PAYLOAD_BYTES)
        self.assertEqual(len(sig), 32)

    def test_payload_over_limit_is_rejected(self):
        b = self._b()
        with self.assertRaises(PayloadTooLargeError):
            b.sign(SIGNING_REF, SigningPurpose.ORDER, b"x" * (MAX_SIGNING_PAYLOAD_BYTES + 1))

    def test_oversize_rejected_before_touching_key_material(self):
        # size check must precede reference/revocation lookup, so an abusive
        # payload is dropped without any key access at all
        b = self._b()
        with self.assertRaises(PayloadTooLargeError):
            b.sign("unknown_ref_v1", SigningPurpose.ORDER, b"x" * (MAX_SIGNING_PAYLOAD_BYTES + 1))

    def test_oversize_error_does_not_leak_payload_or_secret(self):
        b = _boundary([SIGNING_REF], env=_env_with(**{SIGNING_REF: CANARY}))
        try:
            b.sign(SIGNING_REF, SigningPurpose.ORDER, b"P" * (MAX_SIGNING_PAYLOAD_BYTES + 1))
        except PayloadTooLargeError as exc:
            msg = str(exc)
            self.assertNotIn(CANARY, msg)
            self.assertNotIn("PPPP", msg)


if __name__ == "__main__":
    unittest.main()
