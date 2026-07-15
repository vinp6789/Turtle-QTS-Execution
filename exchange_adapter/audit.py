"""Deterministic outbound audit record construction.

Each helper below whitelists exactly the fields safe to audit from a
request -- it does not filter a full request object, so there is no way
for a secret-shaped field to slip through by omission. Money/quantity
fields are stringified (not left as Decimal) so the payload is trivially
JSON-serializable and its hash is stable across processes.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .models import AmendRequest, AuditRecord, CancelAllRequest, CancelRequest, OrderRequest


def order_request_audit_payload(request: OrderRequest) -> Dict[str, Any]:
    return {
        "client_order_id": request.client_order_id,
        "symbol": request.symbol.value,
        "side": request.side.value,
        "order_type": request.order_type.value,
        "quantity": str(request.quantity),
        "limit_price": str(request.limit_price) if request.limit_price is not None else None,
        "time_in_force": request.time_in_force.value,
        "reduce_only": request.reduce_only,
    }


def amend_request_audit_payload(request: AmendRequest) -> Dict[str, Any]:
    return {
        "request_id": request.request_id,
        "exchange_order_id": request.exchange_order_id,
        "new_quantity": str(request.new_quantity) if request.new_quantity is not None else None,
        "new_limit_price": str(request.new_limit_price) if request.new_limit_price is not None else None,
    }


def cancel_request_audit_payload(request: CancelRequest) -> Dict[str, Any]:
    return {"request_id": request.request_id, "exchange_order_id": request.exchange_order_id}


def cancel_all_request_audit_payload(request: CancelAllRequest) -> Dict[str, Any]:
    return {"request_id": request.request_id, "symbol": request.symbol.value if request.symbol else None}


def compute_audit_record(
    request_id: str,
    logical_action: str,
    exchange_name: str,
    adapter_version: str,
    idempotency_key: str,
    payload: Dict[str, Any],
) -> AuditRecord:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    payload_hash = hashlib.sha256(canonical).hexdigest()
    return AuditRecord(
        request_id=request_id,
        logical_action=logical_action,
        exchange_name=exchange_name,
        adapter_version=adapter_version,
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        payload_hash=payload_hash,
        idempotency_key=idempotency_key,
    )
