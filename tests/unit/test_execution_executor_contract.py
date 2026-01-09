from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from src.contracts.streams import RISK_ORDER_APPROVED_V1
from src.contracts.validation import validate_envelope_dict
from src.core.models import EventEnvelope
from src.execution.executor import Executor
from src.execution.qmt_broker import QMTBroker


def _to_wire(ev: EventEnvelope) -> dict:
    d = asdict(ev)
    d["produced_at"] = ev.produced_at.isoformat()
    return d


def test_executor_emits_executed_event_validates_contract() -> None:
    ex = Executor(broker=QMTBroker(dry_run=True))
    approved = EventEnvelope(
        event_id="evt-risk-1",
        trace_id="trace-1",
        produced_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        schema=RISK_ORDER_APPROVED_V1,
        schema_version=1,
        payload={
            "symbol": "AAPL",
            "ts": "2026-01-01T01:00:00+00:00",
            "can_trade": True,
            "final_position_frac": 0.1,
            "risk_per_trade": 0.01,
            "reason": "within_limits",
            "order": {"order_id": "ord-1", "symbol": "AAPL", "side": "BUY", "qty": 10},
        },
        source_service="risk-service",
    )
    validate_envelope_dict(_to_wire(approved))

    out = ex.handle_risk_approved(approved)
    validate_envelope_dict(_to_wire(out))
    assert out.schema == "execution.order.executed.v1"
    assert out.payload["status"] == "EXECUTED"


def test_executor_emits_failed_on_invalid_order() -> None:
    ex = Executor(broker=QMTBroker(dry_run=True))
    approved = EventEnvelope(
        event_id="evt-risk-2",
        trace_id="trace-2",
        produced_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        schema=RISK_ORDER_APPROVED_V1,
        schema_version=1,
        payload={
            "symbol": "AAPL",
            "ts": "2026-01-01T01:00:00+00:00",
            "can_trade": True,
            "final_position_frac": 0.1,
            "risk_per_trade": 0.01,
            "reason": "within_limits",
            "order": {"order_id": "ord-2", "symbol": "AAPL", "side": "BUY", "qty": 0},
        },
        source_service="risk-service",
    )
    out = ex.handle_risk_approved(approved)
    validate_envelope_dict(_to_wire(out))
    assert out.schema == "execution.order.failed.v1"
