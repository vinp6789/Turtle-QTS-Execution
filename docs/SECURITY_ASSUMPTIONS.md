# SECURITY_ASSUMPTIONS.md

Security posture and assumptions for the Turtle Execution Engine, grounded
in repository facts. This documents what the code enforces and what it
relies on the environment/operator to provide.

## What the engine enforces (repository facts)

- **Single signing surface.** Only `SigningBoundary.sign(ref, purpose,
  message)` is exposed; raw key material never crosses a module boundary
  (`secrets_boundary/boundary.py`).
- **HMAC-SHA256 signing.** `EnvironmentHmacBackend` signs with HMAC-SHA256
  using an environment-provided secret (`secrets_boundary/backend.py`).
- **Purpose and domain separation.** `SigningPurpose` plus `build_preimage`
  and `ENGINE_ID` separate signed messages by purpose/domain
  (`secrets_boundary/domain.py`).
- **Bounded signing input.** `MAX_SIGNING_PAYLOAD_BYTES` caps message size
  (`PayloadTooLargeError`).
- **One-way revocation.** A revoked reference cannot be un-revoked or have
  its material replaced on a live instance (`SecretRevokedError`,
  `UnknownSecretReferenceError`).
- **No secrets in the event log.** Event payload field names are scanned for
  secret-suggestive names and rejected (`_FORBIDDEN_KEY_SUBSTRINGS`,
  `_scan_forbidden_keys` in `event_store/store.py`).
- **Least-privilege log file.** The event log is opened with mode `0o600`
  (owner read/write only).
- **Integrity/tamper detection.** SHA-256-checksummed records; bad magic,
  unsupported version, mid-file corruption, and non-monotonic ids are hard
  errors distinct from a recoverable torn tail (`event_store/codec.py`,
  `store.py`).
- **Config carries references, not secrets.** Configuration holds only named
  secret references, resolved later by the secrets boundary (`config`).

## Assumptions the engine relies on

- **Environment provides secrets securely.** `EnvironmentHmacBackend` reads
  secrets from environment variables (per `backend.py`); the confidentiality
  of that environment (process env, host, deployment) is assumed, not
  enforced by this code.
- **File-mode enforcement by the OS.** The `0o600` mode assumes a filesystem
  and OS that honor POSIX permission bits. On Windows these bits are not
  enforced the same way (standard-library behavior).
- **Single-writer discipline.** Capital-safety of the event log assumes
  exactly one writer process per log path; this is enforced by an exclusive
  lock (advisory on POSIX via `fcntl`, mandatory on Windows via `msvcrt`).
- **Windows lock path is unverified at runtime here.** The `msvcrt` branch
  in `event_store/_locking.py` is code-reviewed but has not been executed on
  a real Windows host in this environment; its guarantees should be
  validated on Windows before it protects live capital. The Windows sentinel
  lock assumes the event log never approaches offset `2**62`.
- **Field-name heuristic, not value scanning.** The secret-leak guard scans
  field *names*, not values (by design, to avoid false positives on
  0x-prefixed hashes); it is best-effort and does not guarantee that no
  secret value can ever be placed in a payload under a non-suggestive name.
- **No transport security in scope here.** There are no real network calls
  in this release (only a mock adapter); TLS, endpoint authentication, and
  network posture belong to a future concrete adapter and its environment.
- **Payload trust.** Modules that append events are responsible for the
  semantic correctness of payloads; the event store validates structure and
  size, not business meaning.

## Out of scope for this release (repository facts)

- Live exchange authentication/connectivity (no concrete adapter).
- Key management systems / hardware backends (only `EnvironmentHmacBackend`;
  `SigningBackend` is the documented future extension point).
- Any orchestration-level access control (no entrypoint exists).

> This document describes the security properties and assumptions that are
> observable in the source. It is not a security audit certification and
> asserts nothing beyond what the repository demonstrates.
