"""Exceptions raised by the Secrets & Signing Boundary.

None of these exceptions ever include raw secret material in their message.
Every message references only reference names and environment-variable
names, which are not secret.
"""


class SecretsError(Exception):
    """Base exception for all Secrets & Signing Boundary failures."""


class SecretsConfigurationError(SecretsError):
    """Raised when the set of secret references supplied to the boundary is
    itself malformed -- invalid reference format or duplicate reference
    names. Raised before any environment variable is ever read."""

    def __init__(self, issues):
        self.issues = list(issues)
        message = "Secret reference configuration is invalid ({} issue(s)):\n{}".format(
            len(self.issues),
            "\n".join(f"  - {issue}" for issue in self.issues),
        )
        super().__init__(message)


class SecretsStartupError(SecretsError):
    """Raised when a structurally valid secret reference could not be
    resolved to usable material at startup -- missing environment variable,
    empty value, or two references resolving to identical material."""

    def __init__(self, issues):
        self.issues = list(issues)
        message = "Secret material could not be loaded at startup ({} issue(s)):\n{}".format(
            len(self.issues),
            "\n".join(f"  - {issue}" for issue in self.issues),
        )
        super().__init__(message)


class UnknownSecretReferenceError(SecretsError):
    """Raised when sign() or revoke() is called with a reference name that
    was not registered with this boundary at construction time."""


class PayloadTooLargeError(SecretsError):
    """Raised when a signing request's payload exceeds
    MAX_SIGNING_PAYLOAD_BYTES. A legitimate order/cancel/auth payload is a
    few hundred bytes; anything near the bound is a bug or an abuse attempt,
    and must be rejected before any key material is touched."""


class SecretRevokedError(SecretsError):
    """Raised when sign() is called with a reference that has been revoked.
    Revocation is permanent for the lifetime of the boundary instance."""
