"""REST routers for the Turtle Execution Engine.

Every handler is a thin call into app.api.service (read-only) or an
AppState control method (run cycle / emergency stop). No trading logic, no
engine internals -- routers only translate HTTP <-> service dicts.
"""

from fastapi import APIRouter, Depends, Request, Response

from app.api import service
from app.api.schemas import ControlResponse, CycleRunResponse, HealthResponse
from app.api.security import require_api_key
from app.observability import render_metrics
from app.runtime.state import AppState

router = APIRouter()


def get_state(request: Request) -> AppState:
    return request.app.state.app_state


@router.get("/health", response_model=HealthResponse, tags=["monitoring"])
def health(state: AppState = Depends(get_state)) -> HealthResponse:
    """Liveness/readiness. Cheap -- no reconciliation run."""
    return HealthResponse(**service.health_dict(state))


@router.get("/status", tags=["monitoring"])
def status(state: AppState = Depends(get_state)) -> dict:
    """Full engine status: health, portfolio, positions, reconciliation,
    and last-cycle summary (runs a read-only reconciliation)."""
    return service.status_dict(state)


@router.get("/portfolio", tags=["monitoring"])
def portfolio(state: AppState = Depends(get_state)) -> dict:
    """Portfolio figures only (equity, cash, margin, exposure, heat, PnL)."""
    return service.portfolio_dict(state)


@router.get("/reports", tags=["monitoring"])
def reports(state: AppState = Depends(get_state)) -> dict:
    """The five human-readable summaries (portfolio/execution/cycle/risk/
    reconciliation) as plain strings."""
    return service.reports_dict(state)


@router.get("/metrics", response_class=Response, tags=["monitoring"])
def metrics(state: AppState = Depends(get_state)) -> Response:
    """Prometheus text-exposition metrics."""
    return Response(content=render_metrics(state), media_type="text/plain; version=0.0.4")


@router.post("/cycle/run", response_model=CycleRunResponse, tags=["control"],
             dependencies=[Depends(require_api_key)])
def run_cycle(state: AppState = Depends(get_state)) -> CycleRunResponse:
    """Manually trigger one trading cycle now (in addition to the worker's
    schedule). Protected by API key when one is configured."""
    result = state.run_one_cycle()
    return CycleRunResponse(
        ok=True,
        cycles_run=state.cycles_run,
        started=result.started,
        intents=len(result.intents),
        approved=len(result.construction.approved),
        rejected=len(result.construction.rejected),
        skipped=len(result.construction.skipped),
        executions=len(result.executions),
        completed_at_utc=state.last_cycle_completed_at_utc,
    )


@router.post("/control/emergency-stop", response_model=ControlResponse, tags=["control"],
             dependencies=[Depends(require_api_key)])
def emergency_stop(state: AppState = Depends(get_state)) -> ControlResponse:
    """Emergency Kill: best-effort cancel of resting venue orders FIRST
    (while signing is still valid), then revoke all signing. One-way.
    Requires the API key (fail-closed when none is configured)."""
    cancelled = state.emergency_stop()
    detail = (
        f"Cancelled {len(cancelled)} venue-confirmed resting order(s), then revoked all "
        "signing capability; no further mutations can be authorized."
    )
    if state.last_error and "cancel_all before revocation failed" in state.last_error:
        detail += f" WARNING: {state.last_error}"
    return ControlResponse(
        ok=True, action="emergency_stop", detail=detail,
        emergency_stopped=state.emergency_stopped,
    )
