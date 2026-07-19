"""Pre-deploy environment validator.

Loads AppSettings from the environment, builds the engine once (which
validates the TOML config, secrets, and network/signer consistency), then
closes it. Exits 0 on success, 1 with a clear message on any problem. Run
this in CI or before a deploy to fail fast on misconfiguration.

Usage:  python scripts/validate_env.py
"""

import sys
import tempfile
from pathlib import Path

# Allow running as `python scripts/validate_env.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    try:
        from app.runtime import AppSettings, build_engine_from_settings
    except Exception as exc:  # noqa: BLE001
        print(f"IMPORT ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        settings = AppSettings.from_env()
    except Exception as exc:  # noqa: BLE001
        print(f"SETTINGS ERROR: {exc}", file=sys.stderr)
        return 1

    # Build against a throwaway store path so validation never touches the
    # real event log or contends for its lock.
    with tempfile.TemporaryDirectory() as tmp:
        import os

        env = dict(os.environ)
        env["ENGINE_STORE_PATH"] = str(Path(tmp) / "validate.log")
        try:
            engine, universe, risk_profile = build_engine_from_settings(settings, env=env)
        except Exception as exc:  # noqa: BLE001
            print(f"ENGINE BUILD ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        try:
            print("OK: configuration is valid.")
            print(f"  engine_config_path : {settings.engine_config_path}")
            print(f"  universe           : {[s.value for s in universe]}")
            print(f"  risk profile       : max_positions={risk_profile.max_positions} "
                  f"sizing_mode={risk_profile.sizing_mode}")
            print(f"  worker_enabled     : {settings.worker_enabled} "
                  f"(interval {settings.cycle_interval_seconds}s)")
            print(f"  api_key protection : {'ON' if settings.api_key else 'OFF (open control endpoints)'}")
            print(f"  telegram           : {'ON' if settings.telegram_enabled else 'off'}")
        finally:
            engine.event_store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
