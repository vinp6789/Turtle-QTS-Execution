# MASTER_INDEX.md

Index of every document in this repository. All entries reflect actual
repository contents. **Start at `PROJECT_STATE.md`** for the current
execution state, or `PROJECT_CONSTITUTION.md` for the project's
unchanging vision and principles — this index is for finding a specific
document, not for understanding current state.

## Documentation hierarchy (Core / Reference / Archive)

**Core — load these into context for almost any task; read in this order:**

| Order | Document | Why it's Core |
|---|---|---|
| 1 | `PROJECT_STATE.md` | The single authoritative execution-state document — current phase, active track, blockers, risks, decision register, next actions. Read this first, always. |
| 2 | `PROJECT_CONSTITUTION.md` | Vision, principles, architecture, philosophy, frozen components. Rarely changes; everything else must be consistent with it. |
| 3 | `ROADMAP.md` | Forward-looking only — organised by track (A–E), ordered by value. |
| 4 | `RESEARCH_PLAYBOOK.md` | The process every campaign must follow — pre-registration, five-stage validation, governance. |
| 5 | `RESEARCH_DECISIONS.md` | Append-only organizational memory — the *why* behind every cross-campaign methodology decision (RD-01 onward). |

## Track ownership

Work is organised into five tracks (`ROADMAP.md`). Tracks are **ownership
boundaries, not parallel workstreams** — exactly one is active at a time,
and `PROJECT_STATE.md` records which. Deliberately recorded once, here,
rather than as a column on every table below.

| Track | Owns (code) | Owns (docs) |
|---|---|---|
| **A · Research Framework** | `alpha_engine/{validation,governance,registry,lifecycle}/`, `alpha_engine/feasibility.py` | `RESEARCH_PLAYBOOK.md`, `RESEARCH_DECISIONS.md`, `REVIEW_PROTOCOL.md` |
| **B · Alpha Discovery** | `alpha_engine/{features,candidates}/`, `research/campaign_*` | `MECHANISMS.md`, `RESEARCH_BACKLOG.md`, `RESEARCH_LEDGER.md`, `ALPHA_LIBRARY.md`, `RESEARCH_CAMPAIGN_*.md`, `RESEARCH_PLAN.md` |
| **C · Trading Engineering** | Modules 1–10, `app/`, `trading_system/`, `orchestration/`, `composition_root/`, `alpha_engine/{execution_bridge,portfolio}/` | All Execution Engine docs (frozen), `DEPLOYMENT.md`, `OPERATIONS.md`, `PRODUCTION_CHECKLIST.md` |
| **D · Reverse Engineering** | *(none by design — produces `MECHANISMS.md` rows only)* | `WATCHLIST.md` Part 2 |
| **E · Data Platform** | `alpha_engine/{historical,data_sources}/`, collection scripts | `HISTORICAL_DATA.md`, `WATCHLIST.md` Part 1, `LONG_RUNNING_JOBS.md` |
| *(cross-track)* | — | `PROJECT_STATE.md`, `ROADMAP.md`, `MASTER_INDEX.md`, `PROJECT_CONSTITUTION.md`, `CHANGELOG.md` |

**Reference — open only the specific document a task needs:**

| Document | Purpose |
|----------|---------|
| `REVIEW_PROTOCOL.md` | Implementation → Independent Review → Security Audit → Approval → Merge; responsibilities by actor |
| `ALPHA_ENGINE.md` | Architecture, layer map, operating workflow, known limitations, deployment checklist |
| `RESEARCH_PLAN.md` | Original research execution plan — §1/§2 still accurate reference; §3/§4 executed, see its own status banner |
| `RESEARCH_LEDGER.md` | Permanent scientific record — one entry per completed campaign; rejected hypotheses never deleted |
| `MECHANISMS.md` | **The master mechanism table.** Every future research action comes from it. Mechanism ≠ information class ≠ indicator |
| `RESEARCH_BACKLOG.md` | Power/cost/tax audit of the closed record, ranked mechanism backlog, twelve-month plan, and the ten pre-registration gates |
| `RESEARCH_CAMPAIGN_01_open_interest.md` … `_08_liquidation_hourly.md` | Full pre-registration + methodology + results per campaign (detail behind the ledger's condensed entries) |
| `ALPHA_LIBRARY.md` | Catalog of approved/rejected/retired/experimental/future-candidate alpha models |
| `WATCHLIST.md` | Two lists: Part 1 the executable trading universe (Track E, enforced in code); Part 2 the Reverse Engineering study targets (Track D, a reading list) |
| `HISTORICAL_DATA.md` | Historical data pipeline: source comparison, update frequency, limitations, point-in-time considerations, biases |
| `STRATEGIC_GAP_ANALYSIS.md` | Point-in-time (2026-07-23, pre-Campaign-01) item-by-item assessment against the long-term vision — see its status banner; completion-estimate headline now lives in `PROJECT_STATE.md` |
| `../alpha_engine/DECISIONS.md` | Alpha Engine decision log (D1 onward) |
| `RELEASE_NOTES_v1.0.md` | First stable release summary |
| `CHANGELOG.md` | Recorded changes, starting at v1.0 |
| `ARCHITECTURE_DECISIONS.md` | Frozen Execution Engine design decisions (AD-1 onward), evidenced in source |
| `ADR_ACCOUNTING_CRASH_WINDOWS.md` | AD-25 full analysis: accepted venue-ACK ↔ EventStore crash windows |
| `SECURITY_ASSUMPTIONS.md` | Security posture and assumptions |
| `MODULE_INVENTORY.md` | Per-module table: API, deps, test file, test count |
| `DEPENDENCY_GRAPH.md` | Import graph, layering, responsibilities |
| `ARCHITECTURE_VERSION.md` | Version, frozen modules, baseline, platform |
| `REPOSITORY_STRUCTURE.md` | Repository tree |
| `DEVELOPMENT_WORKFLOW.md` | Feature/security/freeze/regression workflow (Execution-Engine-specific) |
| `CLAUDE_ONBOARDING.md` | Standing onboarding prompt for Execution Engine sessions |
| `DEPLOYMENT.md` | How to run the app layer (Windows/Docker/VPS/Railway) |
| `OPERATIONS.md` | Runbook: endpoints, monitoring, emergency stop, Telegram, backups |
| `LONG_RUNNING_JOBS.md` | Runbook for jobs that outlive a chat session: detached start, reattach/monitor, recovery after any interruption, reboot behaviour. Read before starting or recovering a multi-hour/multi-day collection job. |
| `PRODUCTION_CHECKLIST.md` | Pre-deploy / pre-live-trading checklist |
| `../FINAL_PRODUCTION_AUDIT.md` | Final independent production audit (2026-07-21) — regression, fix-by-fix verification, verdict. Still active reference: outstanding SEC-1/OBS-1 items are cited directly by `ROADMAP.md` Track C. |
| `../MODULE_10_FREEZE.md` | Module 10 (Hyperliquid Adapter) freeze package — architecture, known limitations, runbook, validation evidence. Still the authoritative Module 10 reference. |

**Archive — superseded snapshots, kept for history only, never authoritative:**

| Document | Status |
|----------|--------|
| `PROJECT_STATUS.md` | **Deprecated 2026-07-29** — superseded by `PROJECT_STATE.md`. Body replaced with a banner + pointer; full history retained in git. |
| `PROJECT_DASHBOARD.md` | **Deprecated 2026-07-29** — superseded by `PROJECT_STATE.md`. Body replaced with a banner + pointer; full history retained in git. |
| `../AUDIT_HISTORY.md` | Superseded snapshot, self-marked — see its own banner. Left at its current path; every cross-reference to it already treats it as historical. |
| `../PROJECT_HANDOVER.md` | Superseded snapshot, self-marked — see its own banner. Left at its current path for the same reason. |

*(These four are logically archived — kept only for their historical
value, never read to determine current state — but are not physically
relocated to a separate folder: each already carries an explicit
supersession banner, each is referenced by a small number of "see also"
mentions elsewhere in the docs, and moving them would add path-rewriting
risk without changing what a reader learns. If the repository later
adopts a real `docs/archive/` convention, these four are the migration
candidates.)*

## Project-wide documentation (spans both subsystems)

| Document | Purpose |
|----------|---------|
| `PROJECT_STATE.md` | **Start here.** Single authoritative execution state — current phase, backlog, blockers, risks, decision register, next tasks. |
| `PROJECT_CONSTITUTION.md` | Vision, principles, architecture, philosophy, frozen components, what must never change. Rarely changes. |
| `ROADMAP.md` | Future work only, ordered by value, organised by track (A Research Framework · B Alpha Discovery · C Trading Engineering · D Reverse Engineering · E Data Platform) |
| `REVIEW_PROTOCOL.md` | Implementation → Independent Review → Security Audit → Approval → Merge; responsibilities by actor |
| `PROJECT_STATUS.md` | *(deprecated — see Archive tier above)* |
| `PROJECT_DASHBOARD.md` | *(deprecated — see Archive tier above)* |

## Alpha Engine documentation

| Document | Purpose |
|----------|---------|
| `ALPHA_ENGINE.md` | Architecture, layer map, operating workflow, known limitations, audit remediation record, deployment checklist |
| `RESEARCH_PLAN.md` | Original research execution plan (data-source evaluation, campaign design) — see its status banner for what's superseded |
| `RESEARCH_PLAYBOOK.md` | Process guide: Idea → Registration → Validation → Evidence → Governance → Promotion → Retirement → Post-mortem |
| `RESEARCH_LEDGER.md` | Permanent scientific record — one entry per completed campaign; rejected hypotheses never deleted |
| `MECHANISMS.md` | Master mechanism table — tested/untested, evidence strength, deployability, next action |
| `RESEARCH_BACKLOG.md` | Power audit, ranked backlog, twelve-month plan, pre-registration gates |
| `RESEARCH_CAMPAIGN_01_open_interest.md` | Full pre-registration + methodology + results for Campaign 01 (detail behind the ledger's condensed entry) |
| `RESEARCH_CAMPAIGN_02_funding_rate.md` | Campaign 02 — Funding Rate, absolute threshold (closed, rejected) |
| `RESEARCH_CAMPAIGN_03_funding_rate_venue_relative.md` | Campaign 03 — Funding Rate, venue-relative threshold (closed, rejected) |
| `RESEARCH_CAMPAIGN_04_funding_delta.md` | Campaign 04 — Funding Delta (closed, rejected) |
| `RESEARCH_CAMPAIGN_05_oi_velocity.md` | Campaign 05 — Open Interest Velocity (closed, rejected; carried a DEFER-ceiling — no Hyperliquid OI history) |
| `ALPHA_LIBRARY.md` | Catalog of approved/rejected/retired/experimental/future-candidate alpha models |
| `WATCHLIST.md` | Two lists: Part 1 the executable trading universe (Track E, enforced in code); Part 2 the Reverse Engineering study targets (Track D, a reading list) |
| `HISTORICAL_DATA.md` | Historical data pipeline: source comparison, update frequency, limitations, point-in-time considerations, biases |
| `STRATEGIC_GAP_ANALYSIS.md` | Point-in-time (2026-07-23) item-by-item assessment against the long-term vision — see its status banner |
| `RESEARCH_DECISIONS.md` | Research-program decision log (RD-01 onward) — organizational memory: the *why* behind cross-campaign prioritize/defer/retire decisions; descriptive, non-normative, no predictions |
| `../alpha_engine/DECISIONS.md` | Alpha Engine decision log (D1 onward) — evolves as research/platform work proceeds |

## Execution Engine documentation (frozen subsystem)

| Document | Purpose |
|----------|---------|
| `RELEASE_NOTES_v1.0.md` | First stable release summary (features, baseline, roadmap, credits) |
| `CHANGELOG.md` | Recorded changes, starting at v1.0 |
| `ARCHITECTURE_DECISIONS.md` | Frozen Execution Engine design decisions (AD-1 onward), evidenced in source |
| `ADR_ACCOUNTING_CRASH_WINDOWS.md` | AD-25 full analysis: the accepted venue-ACK ↔ EventStore crash windows |
| `SECURITY_ASSUMPTIONS.md` | Security posture and assumptions |
| `MODULE_INVENTORY.md` | Per-module table: API, deps, test file, test count |
| `DEPENDENCY_GRAPH.md` | Import graph, layering, responsibilities |
| `ARCHITECTURE_VERSION.md` | Version, frozen modules, baseline, platform |
| `REPOSITORY_STRUCTURE.md` | Repository tree |
| `DEVELOPMENT_WORKFLOW.md` | Feature/security/freeze/regression workflow (Execution-Engine-specific; `REVIEW_PROTOCOL.md` is the project-wide layer above this) |
| `CLAUDE_ONBOARDING.md` | Standing onboarding prompt for Execution Engine sessions |
| `DEPLOYMENT.md` | How to run the app layer (Windows/Docker/VPS/Railway) |
| `OPERATIONS.md` | Runbook: endpoints, monitoring, emergency stop, Telegram, backups |
| `PRODUCTION_CHECKLIST.md` | Pre-deploy / pre-live-trading checklist |
| `../FINAL_PRODUCTION_AUDIT.md` | Final independent production audit (2026-07-21) — regression, fix-by-fix verification, verdict |
| `../MODULE_10_FREEZE.md` | Module 10 (Hyperliquid Adapter) freeze package: architecture, known limitations, runbook, validation evidence |
| `../AUDIT_HISTORY.md` | *(superseded — see banner in the file; use `PROJECT_STATE.md`)* |
| `../PROJECT_HANDOVER.md` | *(superseded — see banner in the file; use `PROJECT_STATE.md`)* |

## Modules (frozen, 1–10)

| # | Package | Test file | # Tests |
|---|---------|-----------|--------|
| 1 | `config` | `tests/test_config.py`, `tests/test_config_wallet_ref.py` | 35 |
| 2 | `secrets_boundary` | `tests/test_secrets_boundary.py` | 41 |
| 3 | `event_store` | `tests/test_event_store.py` | 38 |
| 4 | `execution_state_machine` | `tests/test_execution_state_machine.py` | 42 |
| 5 | `exchange_adapter` | `tests/test_exchange_adapter.py` | 41 |
| 6 | `order_manager` | `tests/test_order_manager.py` | 23 |
| 7 | `position_manager` | `tests/test_position_manager.py` | 22 |
| 8 | `portfolio_manager` | `tests/test_portfolio_manager.py` | 21 |
| 9 | `risk_manager` | `tests/test_risk_manager.py` | 56 |
| 10 | `hyperliquid_adapter` | 14 test files (see `MODULE_10_FREEZE.md`) | 206 |
| | **Execution Engine total** | | **~820** (see `FINAL_PRODUCTION_AUDIT.md`) |

Alpha Engine, historical pipeline, and research-harness tests bring the
**full suite to 1,921 passing, 0 failed** (re-verified 2026-08-06 — see
`PROJECT_STATE.md` Executive Summary for the current authoritative figure;
this is a living number, don't hardcode it elsewhere).

## Recommended reading order

**New to the project:**
1. `PROJECT_STATE.md` — current execution state, read first, always.
2. `PROJECT_CONSTITUTION.md` — the vision and the rules that don't change.
3. `ROADMAP.md` — where it's going.

**Working on the Execution Engine:**
1. `CLAUDE_ONBOARDING.md` → `ARCHITECTURE_VERSION.md` → `MODULE_INVENTORY.md`
   → `DEPENDENCY_GRAPH.md` → `REPOSITORY_STRUCTURE.md` →
   `DEVELOPMENT_WORKFLOW.md`.

**Working on Alpha Engine research:**
1. `PROJECT_CONSTITUTION.md` → `ALPHA_ENGINE.md` → `RESEARCH_PLAYBOOK.md`
   → `RESEARCH_DECISIONS.md` → `RESEARCH_LEDGER.md` → `MECHANISMS.md` →
   `RESEARCH_BACKLOG.md` → `ALPHA_LIBRARY.md` → `WATCHLIST.md` →
   `HISTORICAL_DATA.md` → `ROADMAP.md` Track A/B.

**Reviewing any change:** `REVIEW_PROTOCOL.md`.

**Do not reconstruct current project status by reading multiple
documents and cross-referencing them.** `PROJECT_STATE.md` is the single
authoritative source for execution state; every other document here is
either unchanging principle, forward-only planning, a permanent
scientific/decision record, or point-in-time technical reference.
