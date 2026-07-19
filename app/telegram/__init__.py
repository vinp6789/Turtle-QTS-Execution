"""Telegram interface: pure command router + notifier + polling bot.

Public API:
    handle_command(text, state, *, authorized) -- pure text->reply router
    TelegramNotifier -- guarded outbound sender (no-op if unconfigured)
    TelegramBot      -- thin long-polling adapter (daemon thread)
    HELP_TEXT
"""

from .bot import TelegramBot
from .commands import HELP_TEXT, handle_command
from .notifications import TelegramNotifier

__all__ = ["handle_command", "TelegramNotifier", "TelegramBot", "HELP_TEXT"]
