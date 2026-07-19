"""Pure Telegram command router: text in -> reply string out.

No network, no `requests`, no bot framework -- this is the entire
"business logic" of the bot and is fully unit-testable. The polling
adapter (app.telegram.bot) and notifier (app.telegram.notifications) are
thin shells around it. Every command is read-only EXCEPT /stop, which is
gated on `authorized` (the polling adapter sets this only when the message
comes from the configured chat id).

Commands reuse the exact same reporting/service functions the REST API
uses, so the two interfaces can never report different numbers.
"""

from typing import Callable, Dict

from app.api import service
from app.runtime.state import AppState

HELP_TEXT = (
    "Turtle Execution Engine\n"
    "/status - full status summary\n"
    "/portfolio - portfolio figures\n"
    "/risk - risk & kill-switch summary\n"
    "/reconcile - reconciliation state\n"
    "/health - quick liveness\n"
    "/cycle - run one cycle now\n"
    "/stop - EMERGENCY STOP (revoke signing)\n"
    "/help - this message"
)


def _health(state: AppState) -> str:
    h = service.health_dict(state)
    return (
        f"Health: {h['status']}\n"
        f"Engine started: {h['engine_started']}\n"
        f"State: {h['current_state']}\n"
        f"Connection: {h['connection_state']}\n"
        f"Emergency stopped: {h['emergency_stopped']}\n"
        f"Cycles run: {h['cycles_run']}"
    )


def _status(state: AppState) -> str:
    reports = service.reports_dict(state)
    return f"{reports['portfolio']}\n\n{reports['cycle']}\n\n{reports['risk']}"


def _portfolio(state: AppState) -> str:
    return service.reports_dict(state)["portfolio"]


def _risk(state: AppState) -> str:
    return service.reports_dict(state)["risk"]


def _reconcile(state: AppState) -> str:
    return service.reports_dict(state)["reconciliation"]


def _cycle(state: AppState) -> str:
    result = state.run_one_cycle()
    return (
        f"Cycle complete (#{state.cycles_run}).\n"
        f"Intents: {len(result.intents)}, Approved: {len(result.construction.approved)}, "
        f"Rejected: {len(result.construction.rejected)}, Executions: {len(result.executions)}"
    )


_READONLY: Dict[str, Callable[[AppState], str]] = {
    "/health": _health,
    "/status": _status,
    "/portfolio": _portfolio,
    "/risk": _risk,
    "/reconcile": _reconcile,
    "/cycle": _cycle,
    "/help": lambda state: HELP_TEXT,
    "/start": lambda state: HELP_TEXT,
}


def handle_command(text: str, state: AppState, *, authorized: bool = False) -> str:
    """Route one message. `authorized` must be True for /stop to act
    (the polling adapter sets it only for the configured chat id)."""
    if not text or not text.strip():
        return HELP_TEXT
    # Telegram sends "/cmd@botname args"; take the first token, strip @suffix.
    command = text.strip().split()[0].split("@")[0].lower()

    if command == "/stop":
        if not authorized:
            return "Not authorized: /stop is restricted to the configured chat."
        state.emergency_stop()
        return "EMERGENCY STOP executed. All signing revoked; no further orders can be authorized."

    handler = _READONLY.get(command)
    if handler is None:
        return f"Unknown command {command!r}.\n\n{HELP_TEXT}"
    return handler(state)
