"""Register the frozen EMA+MACD+ATR experiment (trend_momentum_rule v1).

Builds point-in-time ValidationSamples from Hyperliquid's own 1h candles,
runs the five-stage validation gate, and seals an immutable evidence
package -- leaving the experiment in IN_REVIEW, ready for a governance
decision by a reviewer who is NOT the researcher.

WHY THIS STEP EXISTS AT ALL. Governance is not a formality that can be
skipped for a testnet run: record_governance_decision() refuses any
experiment not in IN_REVIEW, and IN_REVIEW is reachable only through a
sealed evidence package. There is no path to an approved, live-tradeable
specification that does not pass through this gate. That is deliberate.

WHAT THIS IS NOT. This is not parameter search. Every value below was
frozen BEFORE this file existed: the threshold by the outcome-blind
percentile study (0.40 = p95.5 of |value| across BTC/ETH/SOL), the ATR
multiples by convention (2.0 stop / 3.0 T1 / 4.0 T2), the indicator
periods by the feature version. Nothing here is tuned, and re-running
this script cannot change any of them.

DRY RUN. Pass --dry-run to execute the identical sequence against a
throwaway registry in a temp directory. Nothing touches the permanent
record and no governance decision is recorded -- it answers only "what
would the gate decide?", which is worth knowing before an irreversible
REJECT enters the ledger forever.

Run:
    python -m scripts.register_trend_momentum_v1 --dry-run
    python -m scripts.register_trend_momentum_v1
"""

import argparse
import json
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import List, Tuple

from exchange_adapter import CandleInterval, Symbol

from alpha_engine.candidates import trend_momentum_candidate_specification
from alpha_engine.features import TrendMomentumFeature
from alpha_engine.registry import ExperimentRegistry, FileRegistryStorage, LifecycleState
from alpha_engine.research import run_research_cycle
from alpha_engine.validation import ValidationSample
from alpha_engine.watchlist import Watchlist
from hyperliquid_adapter import codec

# ---------------------------------------------------------------- FROZEN
EXPERIMENT_ID = "trend-momentum-v1-btc-eth-sol"
FAMILY = "trend_momentum_rule"
VERSION = "v1"
SYMBOLS = (Symbol("BTC"), Symbol("ETH"), Symbol("SOL"))
CADENCE_SECONDS = 3600
HORIZON_HOURS = 1

PARAMETERS = {
    "threshold": "0.40",            # p95.5 of |value|, outcome-blind study
    "direction_convention": "momentum",
    "atr_stop_mult": "2.0",
    "atr_t1_mult": "3.0",
    "atr_t2_mult": "4.0",
}
ACCEPTANCE_CRITERIA = {"min_hit_rate": 0.55, "min_signaled_samples": 100}

N_FOLDS = 3
N_RESAMPLES = 1000
SEED = 7

KNOWN_LIMITATIONS = (
    "Window is bounded by VENUE RETENTION, not by data: Hyperliquid serves ~208 days of 1h "
    "candles, so ~4,800 samples per symbol. Regime coverage is correspondingly narrow.",
    "Cross-symbol dependence is NOT haircut in the platform's own single-pass statistics. "
    "BTC/ETH/SOL daily returns are highly correlated (rho_bar ~ +0.86 measured), so pooled "
    "signalled counts overstate independent information; N_eff is far below the raw count.",
    "Threshold derivation scope (RD-11 A): the 0.40 threshold is a FULL-SAMPLE percentile of "
    "the same 208-day window scored here -- a recorded methodological impurity (RD-11 E), the "
    "same scope CAMP-02/03/08 carried.",
    "Contrarian and momentum are algebraically complementary (RD-17 D). Only the momentum "
    "convention is registered here; its mirror carries no independent information.",
    "Exits are NOT modelled in these statistics. The gate scores the SIGNAL (direction over a "
    "1h horizon). Live trading applies ATR stops/targets, so realised outcomes will differ "
    "from these hit rates in both directions.",
    "Backtests flatter. Single-pass results are the most optimistic number here and should "
    "carry the least weight. Walk-forward checks one fixed pre-registered rule across "
    "chronological periods -- it is NOT an out-of-sample generalisation test: no parameter is "
    "refit per fold. Treat every number as an upper bound on live trading, before fees, "
    "slippage, funding and taxes -- none of which are modelled.",
)

_HL_INFO = "https://api.hyperliquid.xyz/info"


def _fetch_candles(symbol: Symbol, days: int = 250):
    now_ms = int(time.time() * 1000)
    req = {"type": "candleSnapshot", "req": {
        "coin": symbol.value, "interval": "1h",
        "startTime": now_ms - days * 86_400_000, "endTime": now_ms}}
    request = urllib.request.Request(
        _HL_INFO, data=json.dumps(req).encode(), headers={"Content-Type": "application/json"})
    body = json.loads(urllib.request.urlopen(request, timeout=60).read())
    return codec.parse_candles(body, symbol, CandleInterval.H1, now_ms)


def _regime_labeler(btc_closes):
    """BTC trailing-return regime, price-derived and independent of the
    feature -- the convention every prior campaign used."""
    lookback = 24 * 7
    keys = sorted(btc_closes)

    def label(open_time_utc: str) -> str:
        if open_time_utc not in btc_closes:
            return "unknown"
        idx = keys.index(open_time_utc) if open_time_utc in keys else -1
        if idx < lookback:
            return "unknown"
        prior = btc_closes[keys[idx - lookback]]
        if prior <= 0:
            return "unknown"
        ret = (btc_closes[open_time_utc] - prior) / prior
        if ret > Decimal("0.05"):
            return "bull"
        if ret < Decimal("-0.05"):
            return "bear"
        return "chop"
    return label


def build_samples() -> Tuple[Tuple[ValidationSample, ...], dict]:
    """Point-in-time samples. NO LOOK-AHEAD: the feature at bar t uses only
    candles up to and including t; the outcome is the return from bar t's
    close to bar t+HORIZON's close, strictly after."""
    warmup = TrendMomentumFeature.WARMUP_PERIODS
    per_symbol = {s: _fetch_candles(s) for s in SYMBOLS}
    btc_closes = {c.open_time_utc: c.close for c in per_symbol[Symbol("BTC")]}
    label = _regime_labeler(btc_closes)

    samples: List[ValidationSample] = []
    diag = {"grid": 0, "built": 0, "skip_unavailable": 0, "skip_no_forward": 0}
    for symbol in SYMBOLS:
        candles = per_symbol[symbol]
        for i in range(warmup, len(candles) - HORIZON_HOURS):
            diag["grid"] += 1
            window = candles[i - warmup:i]
            here, forward = candles[i - 1], candles[i - 1 + HORIZON_HOURS]
            if here.close <= 0:
                diag["skip_no_forward"] += 1
                continue
            fv = TrendMomentumFeature.compute(symbol, here.open_time_utc, window)
            if not fv.available:
                diag["skip_unavailable"] += 1
                continue
            samples.append(ValidationSample(
                feature_value=fv,
                realized_outcome=(forward.close - here.close) / here.close,
                outcome_observed_at_utc=forward.open_time_utc,
                regime_label=label(here.open_time_utc),
            ))
            diag["built"] += 1
    return tuple(samples), diag


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="throwaway registry; nothing touches the permanent record")
    ap.add_argument("--registry", default="data/alpha_engine_research/live_trend_momentum.jsonl")
    args = ap.parse_args()

    spec = trend_momentum_candidate_specification(
        version=VERSION, universe=SYMBOLS, cadence_seconds=CADENCE_SECONDS,
        parameters=PARAMETERS, acceptance_criteria=ACCEPTANCE_CRITERIA,
    )
    print(f"specification : {spec.name} {spec.version}")
    print(f"feature       : {spec.feature_name} {spec.feature_version}")
    print(f"parameters    : {dict(spec.parameters)}")
    print(f"criteria      : {dict(spec.acceptance_criteria)}")
    print()

    print("building point-in-time samples from Hyperliquid 1h candles ...")
    samples, diag = build_samples()
    print(f"  {diag}")
    if not samples:
        print("FATAL: no samples built", file=sys.stderr)
        return 1
    print()

    if args.dry_run:
        tmp = Path(tempfile.mkdtemp()) / "dry_run.jsonl"
        path = str(tmp)
        print(f"DRY RUN -- throwaway registry at {path}")
    else:
        path = args.registry
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        if Path(path).exists():
            print(f"FATAL: {path} already exists. An experiment is registered once, ever; "
                  f"re-running would create a second record for the same frozen spec.",
                  file=sys.stderr)
            return 1
        print(f"PERMANENT registry at {path}")

    registry = ExperimentRegistry(FileRegistryStorage(path))
    result = run_research_cycle(
        registry, FAMILY, EXPERIMENT_ID, spec, samples,
        n_folds=N_FOLDS, n_resamples=N_RESAMPLES, seed=SEED,
        known_limitations=KNOWN_LIMITATIONS,
        watchlist=Watchlist(name="trend-momentum-v1", symbols=SYMBOLS),
    )
    pkg = result.package.to_dict()
    vr = pkg.get("validation_results", {})
    single = vr.get("single_pass", {})
    boot = vr.get("bootstrap_resampling", {})

    print()
    print("=" * 66)
    print("VALIDATION RESULT")
    print("=" * 66)
    print(f"  samples            : {len(samples):,}")
    print(f"  signalled          : {single.get('signaled_samples')}")
    print(f"  hit_rate           : {single.get('hit_rate')}")
    print(f"  mean_dir_return    : {single.get('mean_directional_return')}")
    print(f"  bootstrap mean hit : {boot.get('mean_hit_rate')}")
    print(f"  frac >= bar        : {boot.get('fraction_meeting_min_hit_rate')}")
    print()
    for stage in ("single_pass", "leakage_causality_audit", "walk_forward",
                  "regime_stratification"):
        st = vr.get(stage, {})
        passed = st.get("overall_passed", st.get("passed"))
        print(f"  {stage:<26}: {passed}")
    print()
    print(f"  evidence fingerprint: {result.record.evidence_fingerprint}")
    print(f"  lifecycle state     : {registry.get(EXPERIMENT_ID).lifecycle_state.value}")

    all_passed = all(
        (vr.get(s, {}).get("overall_passed", vr.get(s, {}).get("passed")))
        for s in ("single_pass", "leakage_causality_audit", "walk_forward",
                  "regime_stratification")
    )
    print()
    print(f"  GATE VERDICT        : {'WOULD APPROVE' if all_passed else 'WOULD REJECT'}")

    if not args.dry_run:
        registry.transition(EXPERIMENT_ID, LifecycleState.IN_REVIEW)
        print(f"  transitioned to     : {registry.get(EXPERIMENT_ID).lifecycle_state.value}")
        print()
        print("Next: python -m scripts.approve_trend_momentum_v1 --reviewer <identity> "
              "--decision approve|reject")
    return 0


if __name__ == "__main__":
    sys.exit(main())
