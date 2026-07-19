"""In-process smoke test: boot the FastAPI app against a throwaway paper
engine and exercise the core endpoints. No socket, no network. Exits 0 on
success. Suitable for CI as a fast end-to-end sanity check.

Usage:  python scripts/smoke_test.py
"""

import sys
import tempfile
from pathlib import Path

# Allow running as `python scripts/smoke_test.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    from fastapi.testclient import TestClient

    from app.api import create_app
    from app.runtime import AppSettings, AppState, CycleWorker

    with tempfile.TemporaryDirectory() as tmp:
        env = {
            "TURTLE_SECRET_HYPERLIQUID_SIGNING_KEY_V1": "smoke-secret",
            "ENGINE_CONFIG_PATH": "deploy/engine.paper.toml",
            "ENGINE_STORE_PATH": str(Path(tmp) / "events.log"),
        }
        state = AppState.create(AppSettings.from_env(env), env=env)
        app = create_app(state, CycleWorker(state), start_worker=False, run_startup_cycle=True)
        with TestClient(app) as client:
            checks = [
                ("GET /health", client.get("/health")),
                ("GET /status", client.get("/status")),
                ("GET /portfolio", client.get("/portfolio")),
                ("GET /reports", client.get("/reports")),
                ("GET /metrics", client.get("/metrics")),
                ("GET /openapi.json", client.get("/openapi.json")),
                ("POST /cycle/run", client.post("/cycle/run")),
            ]
            failed = [(name, r.status_code) for name, r in checks if r.status_code != 200]
            for name, r in checks:
                print(f"  {name}: {r.status_code}")
            if failed:
                print(f"SMOKE FAILED: {failed}", file=sys.stderr)
                return 1
    print("OK: smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
