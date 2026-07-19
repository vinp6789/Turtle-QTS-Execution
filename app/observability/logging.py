"""Structured logging setup for the app layer.

stdlib logging only (no third-party dep). LOG_FORMAT=json emits one JSON
object per line (ideal for Railway/Docker log aggregation); LOG_FORMAT=text
emits a compact human line for local runs. Logs go to stdout so a container
runtime captures them without file plumbing.

The engine itself never logs through this -- the frozen modules have no
logging dependency. This configures logging only for app.* code.
"""

import json
import logging
import sys
from typing import Optional


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for key, value in getattr(record, "extra_fields", {}).items():
            payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", fmt: str = "json") -> logging.Logger:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Replace handlers so re-invocation (e.g. in tests) does not duplicate.
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)
    return logging.getLogger("turtle.app")


def log_event(logger: logging.Logger, level: int, message: str, **fields) -> None:
    """Emit a log record carrying structured extra fields."""
    logger.log(level, message, extra={"extra_fields": fields})
