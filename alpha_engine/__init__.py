"""Alpha Engine (new subsystem; Architecture v0.2, Roadmap v1.0).

Sits between the frozen Research repository (`../Turtle-QTS-Research-`,
offline validation lab) and the Execution Engine (this repository's
`trading_system`/`app`/frozen Modules 1-10). Produces `TradeIntent`s for
the Execution Engine's existing, unmodified `trading_system.strategy`
seam -- it is a *consumer* of that public interface, never a modification
of it.

Layer map (Architecture v0.2 SS4; each populated by its own roadmap
milestone, not by this one):

    alpha_engine.registry          -- Experiment Registry (M0.2, M0.3)
    alpha_engine.data_sources      -- Candidate Data Sources (M1.x)
    alpha_engine.features          -- Feature Engineering (M2.x)
    alpha_engine.candidates        -- Candidate Alpha Models (M3.x)
    alpha_engine.validation        -- Research Validation Gates (M4.x)
    alpha_engine.governance        -- Governance Layer (M5.x)
    alpha_engine.lifecycle         -- Candidate lifecycle/shakedown/
                                       auto-freeze/retirement (M6.1, M6.6, M6.7)
    alpha_engine.portfolio         -- Portfolio Construction (M6.2)
    alpha_engine.execution_bridge  -- TradeIntent emission + attribution
                                       manifest; the one seam that touches
                                       trading_system.strategy (M6.3, M6.4)

Milestone 0.1 scope: package scaffolding only. No functional code exists
yet in any sub-package above; each is an empty, importable placeholder
until its own milestone lands. No frozen Execution Engine module is
imported, modified, or depended upon by this package at this milestone.

Substrate/decision log: see `alpha_engine/DECISIONS.md`.
"""

__all__: list = []
