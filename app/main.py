"""Production entrypoint: `python -m app.main`.

Builds the app from the environment and serves it with uvicorn on
AppSettings.host:port. This is the SAME command whether on a Windows
laptop or on Railway (Railway just injects PORT). No deployment-specific
code lives here.

For process managers that import an ASGI app object (uvicorn app.main:app,
gunicorn, etc.), `app` is also exposed at module level.
"""

import uvicorn

from app.api import create_app
from app.runtime import AppSettings

settings = AppSettings.from_env()
app = create_app(settings=settings)


def main() -> None:
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)


if __name__ == "__main__":
    main()
