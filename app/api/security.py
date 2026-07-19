"""API-key protection for mutating/control endpoints.

If AppSettings.api_key is set, protected routes require it via either
`X-API-Key: <key>` or `Authorization: Bearer <key>`. If it is unset
(local/paper convenience), protected routes are open -- create_app logs a
warning so this is never a silent surprise in production.

Read-only endpoints (/health, /status, /portfolio, /reports, /metrics) are
always open: they expose no secrets and mutate nothing.
"""

from typing import Optional

from fastapi import Header, HTTPException, Request, status


def _configured_key(request: Request) -> Optional[str]:
    state = request.app.state.app_state
    return state.settings.api_key


def require_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> None:
    configured = _configured_key(request)
    if not configured:
        return  # open by configuration
    presented = x_api_key
    if presented is None and authorization and authorization.lower().startswith("bearer "):
        presented = authorization[7:].strip()
    if presented != configured:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid API key",
        )
