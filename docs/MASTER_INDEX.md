# MASTER_INDEX.md

Index of every document in this repository. All entries reflect actual
repository contents. **Start at `PROJECT_DASHBOARD.md`** for the current
executive summary, or `PROJECT_CONSTITUTION.md` for the project's
unchanging vision and principles — this index is for finding a specific
document, not for understanding current state.

## Project-wide documentation (spans both subsystems)

| Document | Purpose |
|----------|---------|
| `PROJECT_CONSTITUTION.md` | Vision, principles, architecture, philosophy, frozen components, what must never change. Rarely changes. |
| `PROJECT_DASHBOARD.md` | Single-page executive summary — read this first for current state |
| `PROJECT_STATUS.md` | Living document: current phase, completion, blockers, risks, priorities |
| `ROADMAP.md` | Future work only, ordered by value, split Research/Engineering/Operations/Deployment/Long-term |
| `REVIEW_PROTOCOL.md` | Implementation → Independent Review → Security Audit → Approval → Merge; responsibilities by actor |

## Alpha Engine documentation

| Document | Purpose |
|----------|---------|
| `ALPHA_ENGINE.md` | Architecture, layer map, operating workflow, known limitations, audit remediation record, deployment checklist |
| `RESEARCH_PLAN.md` | Original research execution plan (data-source evaluation, campaign design) — see its status banner for what's superseded |
| `RESEARCH_PLAYBOOK.md` | Process guide: Idea → Registration → Validation → Evidence → Governance → Promotion → Retirement → Post-mortem |
| `RESEARCH_LEDGER.md` | Permanent scientific record — one entry per completed campaign; rejected hypotheses never deleted |
| `RESEARCH_CAMPAIGN_01_open_interest.md` | Full pre-registration + methodology + results for Campaign 01 (detail behind the ledger's condensed entry) |
| `RESEARCH_CAMPAIGN_02_funding_rate.md` | Campaign 02 — Funding Rate, absolute threshold (closed, rejected) |
| `RESEARCH_CAMPAIGN_03_funding_rate_venue_relative.md` | Campaign 03 — Funding Rate, venue-relative threshold (closed, rejected) |
| `RESEARCH_CAMPAIGN_04_funding_delta.md` | Campaign 04 — Funding Delta (closed, rejected) |
| `RESEARCH_CAMPAIGN_05_oi_velocity.md` | Campaign 05 — Open Interest Velocity (closed, rejected; carried a DEFER-ceiling — no Hyperliquid OI history) |
| `ALPHA_LIBRARY.md` | Catalog of approved/rejected/retired/experimental/future-candidate alpha models |
| `WATCHLIST.md` | Current watchlist, selection philosophy, inclusion/removal rules, automation plan |
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
| `../AUDIT_HISTORY.md` | *(superseded — see banner in the file; use `PROJECT_STATUS.md`)* |
| `../PROJECT_HANDOVER.md` | *(superseded — see banner in the file; use `PROJECT_STATUS.md`)* |

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

Alpha Engine adds **747** further tests (`alpha_engine/`, `research/`,
and the historical pipeline) — **1,585 total**, verified passing, zero
failures, as of this writing.

## Recommended reading order

**New to the project:**
1. `PROJECT_CONSTITUTION.md` — the vision and the rules that don't change.
2. `PROJECT_DASHBOARD.md` — where things stand right now.
3. `PROJECT_STATUS.md` — the same, in more detail.
4. `ROADMAP.md` — where it's going.

**Working on the Execution Engine:**
1. `CLAUDE_ONBOARDING.md` → `ARCHITECTURE_VERSION.md` → `MODULE_INVENTORY.md`
   → `DEPENDENCY_GRAPH.md` → `REPOSITORY_STRUCTURE.md` →
   `DEVELOPMENT_WORKFLOW.md`.

**Working on Alpha Engine research:**
1. `PROJECT_CONSTITUTION.md` → `ALPHA_ENGINE.md` → `RESEARCH_PLAYBOOK.md`
   → `RESEARCH_LEDGER.md` → `ALPHA_LIBRARY.md` → `WATCHLIST.md` →
   `HISTORICAL_DATA.md` → `ROADMAP.md` §1.

**Reviewing any change:** `REVIEW_PROTOCOL.md`.
