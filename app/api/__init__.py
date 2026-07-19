"""HTTP interface: FastAPI app, routers, response schemas, and the
framework-agnostic service/serialization layer.

Public API:
    create_app -- the FastAPI application factory
    service    -- framework-agnostic dict serializers (also used by Telegram)
"""

from .app import create_app

__all__ = ["create_app"]
