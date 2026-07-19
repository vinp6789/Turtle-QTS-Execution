"""Pydantic response models (OpenAPI typing).

Flat, high-value responses are typed here so /docs shows real schemas.
The larger nested status/reports payloads are returned as dicts from the
service layer (FastAPI serializes them directly) to avoid brittle
model-mirroring; their shape is documented in app.api.service.
"""

from typing import Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    engine_started: bool
    connection_state: str
    rest_reachable: bool
    current_state: str
    emergency_stopped: bool
    cycles_run: int
    checked_at_utc: str


class ControlResponse(BaseModel):
    ok: bool
    action: str
    detail: str
    emergency_stopped: bool


class CycleRunResponse(BaseModel):
    ok: bool
    cycles_run: int
    started: bool
    intents: int
    approved: int
    rejected: int
    skipped: int
    executions: int
    completed_at_utc: Optional[str] = None
