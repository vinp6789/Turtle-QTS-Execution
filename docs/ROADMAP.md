# ROADMAP.md

Future work for the Turtle Execution Engine. The repository does **not**
define a roadmap, a "Module 10", or numbering for future work. Items below
are the future-work hooks **explicitly named in the source**; "Module 10"
denotes only the next integer after the frozen 1–9 sequence and is a
convention, not a repository fact. No priorities, scopes, or module-number
assignments are invented.

## Module 10 (next in sequence) — candidate

- **Concrete Exchange Adapter.** Implement the abstract `ExchangeAdapter`
  contract for a real venue. The source explicitly names Hyperliquid,
  Lighter, Variational, or any future exchange as concrete-adapter targets,
  and states there are no real network calls today (only
  `MockExchangeAdapter`). This is the largest gap between the current
  release and live trading.

## Further source-attested future work (unnumbered in the repository)

- **Live orchestration / engine entrypoint.** No top-level module wires
  Modules 1–9 into a running loop; a live engine would add this.
- **Audit Trail reader.** `event_store.read_events()` is documented as a
  lock-free, read-only API intended for a future separate-process Audit
  Trail reader.
- **Additional signing backends.** `SigningBackend` is documented as the
  extension point for future hardware or KMS backends beyond the current
  `EnvironmentHmacBackend`.
- **Windows runtime validation — COMPLETED (v1.0.1 / Module 3.1).** The
  Module 3 `msvcrt` locking path and the `O_BINARY` binary-open fix have been
  runtime-executed on a real Windows host; the full suite passes (306 on
  CPython 3.13), including a dedicated binary-framing regression test. This
  run surfaced and corrected the critical text-mode log-corruption defect —
  see `CHANGELOG.md` (v1.0.1). No further Windows validation is outstanding
  for Module 3.

## Integration rules for any future module

Per `DEVELOPMENT_WORKFLOW.md` and `CLAUDE_ONBOARDING.md`:

- Additive-only; no changes to any frozen module's public API.
- Depend only on already-frozen, lower-numbered modules via their `__all__`.
- Persist state through the event store and drive lifecycle through the
  relevant state machine rather than inventing a parallel mechanism.
- Ship its own `tests/test_<package>.py`; do not modify existing tests.
- No dependency cycles or upward edges.
- Full regression green and explicit approval before freeze.

> Everything in this roadmap is a candidate grounded in source comments;
> none of it is committed, scheduled, or prioritized by the repository.
