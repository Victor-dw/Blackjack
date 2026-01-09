from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

import pytest

from src.contracts.streams import STRATEGY_CANDIDATE_ACTION_GENERATED_V1
from src.contracts.validation import validate_envelope_dict
from src.core.models import EventEnvelope
from src.risk.defense import DefenseInputs
from src.risk.position_allocator import PositionAllocator


def _to_wire(ev: EventEnvelope) -> dict:
    d = asdict(ev)
    d["produced_at"] = ev.produced_at.isoformat()
    return d


def test_allocator_approved_event_validates_contract() -> None:
    allocator = PositionAllocator()
    ca = EventEnvelope(
        event_id="evt-1",
        trace_id="trace-1",
        produced_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        schema=STRATEGY_CANDIDATE_ACTION_GENERATED_V1,
        schema_version=1,
        payload={
            "symbol": "AAPL",
            "ts": "2026-01-01T01:00:00+00:00",
            "action": "BUY",
            "strategy": "test",
            "target_position_frac": 0.25,
            "rationale": "unit",
        },
        source_service="strategy",
    )
    validate_envelope_dict(_to_wire(ca))

    out = allocator.handle_candidate_action(ca)
    validate_envelope_dict(_to_wire(out))
    assert out.schema == "risk.order.approved.v1"
    assert out.payload["can_trade"] is True


def test_allocator_freeze_rejects() -> None:
    allocator = PositionAllocator()
    schema, payload = allocator.allocate(
        symbol="AAPL",
        ts="2026-01-01T01:00:00+00:00",
        action="BUY",
        strategy="test",
        target_position_frac=0.25,
        rationale="unit",
        defense_inputs=DefenseInputs(rule_change_alert=True, regime_state="TRANSITION"),
    )
    assert schema == "risk.order.rejected.v1"
    assert payload["can_trade"] is False
    assert payload["reason"] == "defense_freeze"
