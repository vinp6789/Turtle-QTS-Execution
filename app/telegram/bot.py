"""Telegram polling bot: a thin adapter that long-polls getUpdates and
dispatches each message to the pure command router.

All logic lives in app.telegram.commands (pure) and
app.telegram.notifications (send). This module only owns the getUpdates
polling loop and the "is this message from the authorized chat" check. It
runs in its own daemon thread; like the cycle worker, it uses an Event for
an interruptible sleep and never lets a transient network error kill the
loop.

Not exercised by the automated test suite (it requires a live bot token
and network); its two testable pieces -- command routing and notification
formatting -- are covered separately.
"""

import threading
from typing import Optional

import requests

from app.runtime.settings import AppSettings
from app.runtime.state import AppState
from app.telegram.commands import handle_command
from app.telegram.notifications import TelegramNotifier

_GET_UPDATES = "https://api.telegram.org/bot{token}/getUpdates"


class TelegramBot:
    def __init__(self, state: AppState, settings: AppSettings,
                 notifier: Optional[TelegramNotifier] = None,
                 session: Optional["requests.Session"] = None):
        self._state = state
        self._settings = settings
        self._enabled = bool(settings.telegram_enabled and settings.telegram_bot_token and settings.telegram_chat_id)
        self._token = settings.telegram_bot_token
        self._authorized_chat = str(settings.telegram_chat_id) if settings.telegram_chat_id else None
        self._notifier = notifier or TelegramNotifier(settings, session=session)
        self._session = session or requests.Session()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._offset = 0

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if not self._enabled or self.is_running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="telegram-bot", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._thread = None

    def _reply(self, text: str) -> None:
        self._notifier.send(text)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                resp = self._session.get(
                    _GET_UPDATES.format(token=self._token),
                    params={"offset": self._offset, "timeout": 25},
                    timeout=30,
                )
                if resp.status_code == 200:
                    for update in resp.json().get("result", []):
                        self._offset = update["update_id"] + 1
                        self._dispatch(update)
            except Exception:  # noqa: BLE001 -- resilience: never let the loop die
                self._stop.wait(3)

    def _dispatch(self, update: dict) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return
        text = message.get("text", "")
        chat_id = str(message.get("chat", {}).get("id", ""))
        authorized = self._authorized_chat is not None and chat_id == self._authorized_chat
        if self._authorized_chat is not None and chat_id != self._authorized_chat:
            return  # ignore messages from any chat but the configured one
        reply = handle_command(text, self._state, authorized=authorized)
        self._reply(reply)
