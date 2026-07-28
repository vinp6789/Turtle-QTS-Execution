"""Unit tests for LiquidationObservation, the hyperliquid_s3 source, and
the incremental-sync checkpoint (RD-10 Step 2).

Fixtures replicate the schema MEASURED by the RD-10 Step 1 probe: NDJSON
blocks whose `events` are [address, fill] pairs, a fill carrying an
optional `liquidation` sub-object, and one liquidation surfacing as two
paired fills sharing a single `tid`.

No network access: S3 is exercised through a minimal fake client, so
these tests run identically on every platform and cost nothing.
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from exchange_adapter import Symbol
from alpha_engine.historical.errors import HistoricalDataError
from alpha_engine.historical.models import LiquidationObservation
from alpha_engine.historical.storage import load, merge_and_write, series_filename
from alpha_engine.historical.sources import hyperliquid_s3 as hls


# --------------------------------------------------------------------------
# fixtures mirroring the measured payload
# --------------------------------------------------------------------------

def _fill(coin="POL", side="A", direction="Close Long", tid=57521389497119,
          liq=True, time_ms=1767236420596, px="0.099304", sz="5790.0"):
    f = {
        "coin": coin, "px": px, "sz": sz, "side": side, "time": time_ms,
        "startPosition": "5790.0", "dir": direction, "closedPnl": "-119.0",
        "hash": "0x0b96", "oid": 283441759504, "crossed": True,
        "fee": "0.248387", "tid": tid, "feeToken": "USDC", "twapId": None,
    }
    if liq:
        f["liquidation"] = {
            "liquidatedUser": "0x4733784e931da8da819c2e8eb7ef97bea7b51197",
            "markPx": "0.099275", "method": "market",
        }
    return f


def _block(fills):
    return json.dumps({
        "local_time": "2026-01-01T03:00:00.081424397",
        "block_time": "2026-01-01T02:59:59.916315235",
        "block_number": 847036455,
        "events": [["0xuser", f] for f in fills],
    })


def _payload(blocks):
    return ("\n".join(blocks) + "\n").encode("utf-8")


class _FakeS3:
    """Minimal stand-in: records RequestPayer so the tests can assert it."""

    def __init__(self, listing=None, objects=None):
        self.listing = listing or {}
        self.objects = objects or {}
        self.request_payers = []

    def list_objects_v2(self, **kw):
        self.request_payers.append(kw.get("RequestPayer"))
        return self.listing.get(kw.get("Prefix"), {"Contents": []})

    def get_object(self, **kw):
        self.request_payers.append(kw.get("RequestPayer"))
        import io
        return {"Body": io.BytesIO(self.objects[kw["Key"]])}


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------

def _obs(**kw):
    base = dict(
        symbol=Symbol("BTC"), observed_at_utc="2026-01-01T03:00:20.596000+00:00",
        price=Decimal("0.099304"), size=Decimal("5790.0"), side="A",
        direction="Close Long", method="market", liquidated_user="0x4733",
        mark_price=Decimal("0.099275"), tid=57521389497119,
        source="hyperliquid_s3", source_detail="k.lz4",
        ingested_at_utc="2026-07-28T00:00:00+00:00",
    )
    base.update(kw)
    return LiquidationObservation(**base)


def test_model_accepts_measured_shape():
    o = _obs()
    assert o.tid == 57521389497119 and o.method == "market"


@pytest.mark.parametrize("field,bad", [
    ("size", Decimal("0")), ("price", Decimal("0")), ("mark_price", Decimal("0")),
])
def test_model_rejects_nonpositive_numbers(field, bad):
    with pytest.raises(HistoricalDataError):
        _obs(**{field: bad})


def test_model_rejects_bad_timestamp():
    with pytest.raises(HistoricalDataError):
        _obs(observed_at_utc="not-a-timestamp")


def test_model_rejects_non_decimal_price():
    with pytest.raises(HistoricalDataError):
        _obs(price=0.099)


def test_model_rejects_non_int_tid():
    with pytest.raises(HistoricalDataError):
        _obs(tid="57521389497119")


# --------------------------------------------------------------------------
# decode
# --------------------------------------------------------------------------

def test_decode_emits_only_liquidation_fills():
    payload = _payload([_block([_fill(liq=False), _fill(liq=True)])])
    out = hls.decode_liquidations(payload, key="k.lz4")
    assert len(out) == 1
    assert out[0].method == "market"
    assert out[0].liquidated_user.startswith("0x4733")


def test_decode_preserves_paired_fills_sharing_one_tid():
    """Measured: one liquidation = two fills, same tid, opposite sides."""
    payload = _payload([_block([
        _fill(side="B", direction="Open Long"),
        _fill(side="A", direction="Close Long"),
    ])])
    out = hls.decode_liquidations(payload, key="k.lz4")
    assert len(out) == 2
    assert {o.side for o in out} == {"A", "B"}
    assert len({o.tid for o in out}) == 1


def test_decode_maps_fields_from_measured_schema():
    out = hls.decode_liquidations(_payload([_block([_fill()])]), key="k.lz4")
    o = out[0]
    assert o.symbol == Symbol("POL")
    assert o.price == Decimal("0.099304")
    assert o.size == Decimal("5790.0")
    assert o.mark_price == Decimal("0.099275")
    assert o.direction == "Close Long"
    assert o.source == "hyperliquid_s3"
    assert o.source_detail == "k.lz4"
    assert o.observed_at_utc.startswith("2026-01-01T")


def test_decode_symbol_filter():
    payload = _payload([_block([_fill(coin="POL"), _fill(coin="BTC")])])
    out = hls.decode_liquidations(payload, key="k", symbols=(Symbol("BTC"),))
    assert [o.symbol.value for o in out] == ["BTC"]


def test_decode_ignores_empty_events_and_blank_lines():
    payload = (json.dumps({"events": []}) + "\n\n").encode("utf-8")
    assert hls.decode_liquidations(payload, key="k") == ()


def test_decode_raises_on_malformed_json():
    with pytest.raises(HistoricalDataError):
        hls.decode_liquidations(b"{not json}\n", key="k")


def test_decode_rejects_non_bytes():
    with pytest.raises(HistoricalDataError):
        hls.decode_liquidations("string", key="k")


# --------------------------------------------------------------------------
# S3 access: requester-pays and numeric hour ordering
# --------------------------------------------------------------------------

def test_list_hour_keys_sorts_hours_numerically_and_sets_requester_pays():
    prefix = "node_fills_by_block/hourly/20260101/"
    fake = _FakeS3(listing={prefix: {"Contents": [
        {"Key": prefix + "10.lz4"}, {"Key": prefix + "2.lz4"}, {"Key": prefix + "1.lz4"},
    ]}})
    keys = hls.list_hour_keys(date="20260101", client=fake)
    assert [k.rsplit("/", 1)[-1] for k in keys] == ["1.lz4", "2.lz4", "10.lz4"]
    assert fake.request_payers == ["requester"]


def test_list_hour_keys_rejects_bad_date():
    with pytest.raises(HistoricalDataError):
        hls.list_hour_keys(date="2026-01-01", client=_FakeS3())


def test_fetch_hour_sets_requester_pays():
    lz4 = pytest.importorskip("lz4.frame")
    key = "node_fills_by_block/hourly/20260101/3.lz4"
    fake = _FakeS3(objects={key: lz4.compress(_payload([_block([_fill()])]))})
    out = hls.fetch_hour(key, client=fake)
    assert len(out) == 1
    assert "requester" in fake.request_payers


# --------------------------------------------------------------------------
# checkpoint / incremental sync
# --------------------------------------------------------------------------

def test_checkpoint_roundtrip_and_absent_is_none(tmp_path):
    p = tmp_path / "cp" / "checkpoint.json"
    assert hls.read_checkpoint(p) is None
    hls.write_checkpoint(p, "node_fills_by_block/hourly/20260101/3.lz4")
    assert hls.read_checkpoint(p) == "node_fills_by_block/hourly/20260101/3.lz4"


def test_checkpoint_rejects_empty_key(tmp_path):
    with pytest.raises(HistoricalDataError):
        hls.write_checkpoint(tmp_path / "c.json", "")


def test_checkpoint_raises_on_corrupt_file(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(HistoricalDataError):
        hls.read_checkpoint(p)


def test_checkpoint_write_is_atomic_no_tmp_left(tmp_path):
    p = tmp_path / "c.json"
    hls.write_checkpoint(p, "a/b/20260101/1.lz4")
    assert not (tmp_path / "c.json.tmp").exists()


def test_sort_key_orders_by_date_then_numeric_hour():
    base = "node_fills_by_block/hourly/"
    keys = [base + "20260102/1.lz4", base + "20260101/10.lz4", base + "20260101/2.lz4"]
    assert [hls.sort_key(k) for k in sorted(keys, key=hls.sort_key)] == [
        ("20260101", 2), ("20260101", 10), ("20260102", 1),
    ]


def test_keys_after_checkpoint_returns_all_when_none():
    base = "node_fills_by_block/hourly/20260101/"
    keys = (base + "2.lz4", base + "1.lz4")
    assert hls.keys_after_checkpoint(keys, None) == (base + "1.lz4", base + "2.lz4")


def test_keys_after_checkpoint_never_redownloads_processed_hours():
    base = "node_fills_by_block/hourly/20260101/"
    keys = tuple(base + f"{h}.lz4" for h in (1, 2, 3, 10))
    out = hls.keys_after_checkpoint(keys, base + "2.lz4")
    assert out == (base + "3.lz4", base + "10.lz4")


def test_keys_after_checkpoint_is_exclusive_of_checkpoint_itself():
    base = "node_fills_by_block/hourly/20260101/"
    assert hls.keys_after_checkpoint((base + "1.lz4",), base + "1.lz4") == ()


def test_keys_after_checkpoint_crosses_date_boundary():
    a, b = "node_fills_by_block/hourly/20260101/", "node_fills_by_block/hourly/20260102/"
    out = hls.keys_after_checkpoint((a + "23.lz4", b + "0.lz4"), a + "23.lz4")
    assert out == (b + "0.lz4",)


def test_resume_after_interruption_is_deterministic(tmp_path):
    """Two identical runs from the same checkpoint select the same work."""
    base = "node_fills_by_block/hourly/20260101/"
    keys = tuple(base + f"{h}.lz4" for h in range(5))
    p = tmp_path / "c.json"
    hls.write_checkpoint(p, base + "1.lz4")
    first = hls.keys_after_checkpoint(keys, hls.read_checkpoint(p))
    second = hls.keys_after_checkpoint(keys, hls.read_checkpoint(p))
    assert first == second == (base + "2.lz4", base + "3.lz4", base + "4.lz4")


# --------------------------------------------------------------------------
# storage reuse (existing pipeline, extended additively)
# --------------------------------------------------------------------------

def test_storage_roundtrip_liquidations(tmp_path):
    path = tmp_path / series_filename("liquidation", Symbol("BTC"), "hyperliquid_s3")
    obs = (_obs(side="A"), _obs(side="B"))
    res = merge_and_write(path, LiquidationObservation, obs)
    assert res.added_count == 2
    back = load(path, LiquidationObservation)
    assert len(back) == 2
    assert {o.side for o in back} == {"A", "B"}
    assert back[0].price == Decimal("0.099304")


def test_storage_dedup_keeps_both_sides_of_one_liquidation(tmp_path):
    """The (symbol, time) key alone would collapse the measured pair --
    tid+side must be part of the identity."""
    path = tmp_path / "liq.csv"
    merge_and_write(path, LiquidationObservation, (_obs(side="A"), _obs(side="B")))
    assert len(load(path, LiquidationObservation)) == 2


def test_storage_rerun_is_idempotent(tmp_path):
    path = tmp_path / "liq.csv"
    obs = (_obs(side="A"), _obs(side="B"))
    merge_and_write(path, LiquidationObservation, obs)
    second = merge_and_write(path, LiquidationObservation, obs)
    assert second.added_count == 0
    assert len(load(path, LiquidationObservation)) == 2


def test_storage_load_absent_file_is_empty(tmp_path):
    assert load(tmp_path / "nope.csv", LiquidationObservation) == ()
