"""Pipeline Validation smoke test -- TRACK B (ENGINEERING, NOT RESEARCH).

WHAT THIS IS NOT
================
This is NOT alpha validation. The EMA+MACD+ATR specification exercised
here was REJECTED by the five-stage research gate on 2026-08-06
(hit rate 0.4353 vs a pre-registered bar of 0.55, mean directional return
-0.86 bp, walk-forward and regime both failed). It is used here ONLY as a
signal generator that produces genuine, deterministic TradeIntents so the
execution stack can be exercised end to end.

Nothing in this file, and nothing it writes, is evidence of alpha. It
creates no Research Decision, no Alpha Library entry, and no record in
the research registry. The strategy is constructed with registry=None,
so governance is not involved and cannot be implied.

The strategy is EXPECTED TO LOSE. That is irrelevant to this track.

WHAT THIS CHECKS
================
Twelve engineering checks, in dependency order. Checks that need no
credentials run first, so a misconfiguration is caught before any
signing key is touched. Each prints PASS / FAIL / SKIP with a reason;
the process exit code is 0 only if nothing FAILED.

Run:
    python -m scripts.pipeline_validation_smoke                 # offline checks
    python -m scripts.pipeline_validation_smoke --with-venue    # + live testnet
"""

import argparse
import json
import os
import sys
import time
import traceback
import urllib.request
from decimal import Decimal
from pathlib import Path

RESULTS = []


def check(name):
    """Decorator: run a check, capture PASS/FAIL/SKIP, never crash the run."""
    def wrap(fn):
        def run(*a, **kw):
            try:
                detail = fn(*a, **kw)
                if detail is None:
                    RESULTS.append(("SKIP", name, "not applicable"))
                elif detail is False:
                    RESULTS.append(("FAIL", name, "returned False"))
                else:
                    RESULTS.append(("PASS", name, detail if isinstance(detail, str) else ""))
            except SkipCheck as exc:
                RESULTS.append(("SKIP", name, str(exc)))
            except Exception as exc:  # noqa: BLE001 -- a check must never abort the suite
                RESULTS.append(("FAIL", name, f"{type(exc).__name__}: {exc}"))
        return run
    return wrap


class SkipCheck(Exception):
    pass


# ------------------------------------------------------------------ 1-6: offline

@check("01 configuration loads and declares testnet")
def check_config(config_path):
    from config import load_config
    if not Path(config_path).exists():
        raise SkipCheck(f"{config_path} not present -- create it from config/example.toml")
    cfg = load_config(config_path)
    network = cfg.exchange.network
    if network != "testnet":
        return False
    return f"network={network} mode={getattr(cfg, 'mode', '?')}"


@check("02 event store path is durable and testnet-separated")
def check_store_path():
    path = os.environ.get("ENGINE_STORE_PATH")
    if not path:
        raise SkipCheck("ENGINE_STORE_PATH unset")
    p = Path(path)
    if "testnet" not in str(p).lower():
        return False  # mainnet/testnet must never share a store
    p.parent.mkdir(parents=True, exist_ok=True)
    return f"{p} (testnet-scoped)"


@check("03 candidate catalog loads; candle family registered")
def check_catalog():
    from alpha_engine.candidates import CANDIDATE_CATALOG, get_candidate_type
    entry = get_candidate_type("trend_momentum_rule")
    if entry.feature_fn is None or not entry.warmup_periods:
        return False
    return (f"{len(CANDIDATE_CATALOG)} families; trend_momentum_rule "
            f"feature={entry.feature_name} warmup={entry.warmup_periods}")


@check("04 specification builds with frozen parameters")
def check_specification():
    spec = _spec()
    p = dict(spec.parameters)
    expected = {"threshold": "0.40", "atr_stop_mult": "2.0",
                "atr_t1_mult": "3.0", "atr_t2_mult": "4.0"}
    for k, v in expected.items():
        if p.get(k) != v:
            return False
    return f"{spec.name}/{spec.version} feature={spec.feature_name}"


@check("05 execution bridge constructs (registry=None -> no governance)")
def check_bridge():
    from alpha_engine.execution_bridge import ApprovedCandleAlphaStrategy
    from alpha_engine.watchlist import Watchlist
    spec = _spec()
    strategy = ApprovedCandleAlphaStrategy(
        (spec,), registry=None,
        watchlist=Watchlist(name="pipeline-validation", symbols=spec.universe),
    )
    return f"name={strategy.name} (NOT governance-approved -- by design)"


@check("06 full regression suite green")
def check_regression():
    import subprocess
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                       capture_output=True, text=True, timeout=900)
    tail = (r.stderr or r.stdout).strip().splitlines()[-1:]
    if r.returncode != 0:
        return False
    return " ".join(tail)


# ------------------------------------------------------------------ 7-9: venue, read-only

@check("07 venue reachable (testnet /info)")
def check_venue():
    body = _info({"type": "meta"})
    n = len(body.get("universe", []))
    if n <= 0:
        return False
    return f"testnet meta: {n} perp markets"


@check("08 candle retrieval returns closed bars, oldest->newest")
def check_candles():
    from exchange_adapter import CandleInterval, Symbol
    from hyperliquid_adapter import codec
    from alpha_engine.features import TrendMomentumFeature
    warmup = TrendMomentumFeature.WARMUP_PERIODS
    now = int(time.time() * 1000)
    step = codec.interval_ms(CandleInterval.H1)
    body = _info({"type": "candleSnapshot", "req": {
        "coin": "BTC", "interval": "1h",
        "startTime": now - step * (warmup + 2), "endTime": now}})
    candles = codec.parse_candles(body, Symbol("BTC"), CandleInterval.H1, now)
    times = [c.open_time_utc for c in candles]
    if times != sorted(times) or len(set(times)) != len(times):
        return False
    if len(candles) < warmup:
        return False
    return f"{len(candles)} closed candles (need {warmup}); no dupes; ordered"


@check("09 funding retrieval")
def check_funding():
    body = _info({"type": "metaAndAssetCtxs"})
    ctxs = body[1] if isinstance(body, list) and len(body) > 1 else []
    if not ctxs:
        return False
    return f"{len(ctxs)} asset contexts with funding"


# ------------------------------------------------------------------ 10-12: end-to-end

@check("10 signal generation produces a deterministic decision")
def check_signal():
    from exchange_adapter import CandleInterval, Symbol
    from hyperliquid_adapter import codec
    from alpha_engine.candidates import get_candidate_type
    entry = get_candidate_type("trend_momentum_rule")
    spec = _spec()
    now = int(time.time() * 1000)
    step = codec.interval_ms(CandleInterval.H1)
    out = []
    for sym in ("BTC", "ETH", "SOL"):
        body = _info({"type": "candleSnapshot", "req": {
            "coin": sym, "interval": "1h",
            "startTime": now - step * (entry.warmup_periods + 2), "endTime": now}})
        candles = codec.parse_candles(body, Symbol(sym), CandleInterval.H1, now)
        fv = entry.feature_fn(Symbol(sym), candles[-1].open_time_utc, candles)
        a = entry.evaluate_fn(fv, spec)
        b = entry.evaluate_fn(fv, spec)   # determinism
        if a.direction is not b.direction:
            return False
        out.append(f"{sym}={a.direction.value}")
    return " ".join(out)


@check("11 ATR exit geometry derivable and non-degenerate")
def check_exits():
    from exchange_adapter import CandleInterval, Symbol
    from hyperliquid_adapter import codec
    from alpha_engine.features import ATR_PERIOD, atr_from_candles
    now = int(time.time() * 1000)
    step = codec.interval_ms(CandleInterval.H1)
    body = _info({"type": "candleSnapshot", "req": {
        "coin": "BTC", "interval": "1h",
        "startTime": now - step * 220, "endTime": now}})
    candles = codec.parse_candles(body, Symbol("BTC"), CandleInterval.H1, now)
    atr = atr_from_candles(candles, ATR_PERIOD)
    if atr is None or atr <= 0:
        return False
    mark = candles[-1].close
    stop = mark - Decimal("2.0") * atr
    t1 = mark + Decimal("3.0") * atr
    if stop <= 0 or t1 <= 0 or stop >= mark or t1 <= mark:
        return False
    return f"mark={mark} atr={atr:.4f} stop={stop:.2f} t1={t1:.2f}"


@check("12 credentials present for order submission")
def check_credentials():
    need = ["TURTLE_DEPLOYMENT_ACCOUNT_ADDRESS", "TURTLE_SECRET_HYPERLIQUID_WALLET_KEY_V1"]
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        raise SkipCheck(f"missing {missing} -- required before any order can be placed")
    return "deployment account and signing key present"


# ------------------------------------------------------------------ helpers

_TESTNET_INFO = "https://api.hyperliquid-testnet.xyz/info"


def _info(payload):
    req = urllib.request.Request(
        _TESTNET_INFO, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def _spec():
    from exchange_adapter import Symbol
    from alpha_engine.candidates import trend_momentum_candidate_specification
    return trend_momentum_candidate_specification(
        version="pipeline-validation-v1",
        universe=(Symbol("BTC"), Symbol("ETH"), Symbol("SOL")),
        cadence_seconds=3600,
        parameters={"threshold": "0.40", "direction_convention": "momentum",
                    "atr_stop_mult": "2.0", "atr_t1_mult": "3.0", "atr_t2_mult": "4.0"},
        acceptance_criteria={"min_hit_rate": 0.55, "min_signaled_samples": 100},
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-venue", action="store_true",
                    help="also run live testnet connectivity checks")
    ap.add_argument("--config", default="config/testnet.toml")
    ap.add_argument("--skip-regression", action="store_true")
    args = ap.parse_args()

    print("=" * 72)
    print("PIPELINE VALIDATION SMOKE TEST -- TRACK B (ENGINEERING)")
    print("This exercises a strategy the research gate REJECTED.")
    print("It is NOT evidence of alpha and creates no research record.")
    print("=" * 72)
    print()

    check_config(args.config)
    check_store_path()
    check_catalog()
    check_specification()
    check_bridge()
    if not args.skip_regression:
        check_regression()
    else:
        RESULTS.append(("SKIP", "06 full regression suite green", "--skip-regression"))

    if args.with_venue:
        check_venue()
        check_candles()
        check_funding()
        check_signal()
        check_exits()
    else:
        for n in ("07 venue reachable (testnet /info)",
                  "08 candle retrieval returns closed bars, oldest->newest",
                  "09 funding retrieval",
                  "10 signal generation produces a deterministic decision",
                  "11 ATR exit geometry derivable and non-degenerate"):
            RESULTS.append(("SKIP", n, "--with-venue not set"))
    check_credentials()

    print(f"  {'':<4}{'check':<58}{'result'}")
    for status, name, detail in RESULTS:
        mark = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "skip"}[status]
        print(f"  {mark:<6}{name:<58}{detail}")
    failed = [r for r in RESULTS if r[0] == "FAIL"]
    skipped = [r for r in RESULTS if r[0] == "SKIP"]
    passed = [r for r in RESULTS if r[0] == "PASS"]
    print()
    print(f"  PASS {len(passed)}   FAIL {len(failed)}   SKIP {len(skipped)}")
    if failed:
        print()
        print("  VERDICT: NOT READY -- resolve the FAIL rows above.")
        return 1
    if skipped:
        print()
        print("  VERDICT: READY for the checks that ran. Skipped rows still gate deployment.")
        return 0
    print()
    print("  VERDICT: ALL CHECKS PASSED -- ready to arm.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
