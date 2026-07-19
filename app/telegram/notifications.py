"""Telegram notification service (outbound).

Thin wrapper over the Telegram Bot HTTP API using stdlib-friendly
`requests`. Fully guarded: if telegram is disabled or the token/chat_id is
missing, send() is a silent no-op that returns False -- so the rest of the
app can call notifier.send(...) unconditionally without caring whether
Telegram is configured.

Never raises on a network error: a failed notification must never crash a
trading cycle. Failures are swallowed and reported via the return value.
"""

from typing import Optional

import requests

from app.runtime.settings import AppSettings

_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    def __init__(self, settings: AppSettings, session: Optional["requests.Session"] = None, timeout: float = 10.0):
        self._enabled = bool(settings.telegram_enabled and settings.telegram_bot_token and settings.telegram_chat_id)
        self._token = settings.telegram_bot_token
        self._chat_id = settings.telegram_chat_id
        self._session = session or requests.Session()
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return self._enabled

    def send(self, text: str) -> bool:
        """Send a message to the configured chat. Returns True on a 2xx
        response, False if disabled or on any failure. Never raises."""
        if not self._enabled:
            return False
        try:
            resp = self._session.post(
                _API.format(token=self._token),
                json={"chat_id": self._chat_id, "text": text},
                timeout=self._timeout,
            )
            return 200 <= resp.status_code < 300
        except Exception:  # noqa: BLE001 -- a notification must never crash the caller
            return False
