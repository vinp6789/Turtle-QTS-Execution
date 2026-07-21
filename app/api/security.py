"""API-key protection for mutating/control endpoints -- FAIL CLOSED (H1).

Policy:
  - API_KEY set:   mutating endpoints require it, presented via
                   `X-API-Key: <key>` or `Authorization: Bearer <key>`.
                   Compared in constant time (hmac.compare_digest).
  - API_KEY unset: mutating endpoints are DISABLED (HTTP 503) -- they
                   NEVER execute for an unauthenticated caller. This is the
                   fail-closed default: a public deployment with no key
                   configured cannot trigger a cycle or a one-way
                   emergency stop. (Earlier this branch failed OPEN -- it
                   returned success and let the endpoint run; audit
                   finding H1.)

Read-only endpoints (/health, /status, /portfolio, /reports, /metrics) do
NOT use this dependency and remain open: they expose no secrets and mutate
nothing, so monitoring is unaffected by this change.
"""

import hmac
from typing import Optional

from fastapi import Header, HTTPException, Request, status


def _configured_key(request: Request) -> Optional[str]:
    key = request.app.state.app_state.settings.api_key
    # Treat a whitespace-only key as unset -- a config typo must never be
    # mistaken for an enabled credential.
    if key is not None and not key.strip():
        return None
    return key


def require_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> None:
    configured = _configured_key(request)
    if not configured:
        # FAIL CLOSED: no credential configured -> the action is disabled,
        # not open. 503 (not 401) because the fix is operator-side: set
        # API_KEY to enable control endpoints.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "control endpoints are disabled: no API_KEY is configured. "
                "Set API_KEY to enable /cycle/run and /control/emergency-stop."
            ),
        )
    presented = x_api_key
    if presented is None and authorization and authorization.lower().startswith("bearer "):
        presented = authorization[7:].strip()
    if presented is None or not hmac.compare_digest(presented, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid API key",
        )
