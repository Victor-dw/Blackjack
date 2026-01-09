"""L6 Execution engine.

Must be purely mechanical:
- reads approved commands (risk.order.approved.v1)
- sends orders to broker adapter
- publishes execution result (execution.order.executed/failed.v1)

No additional risk logic is allowed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.contracts.streams import EXECUTION_ORDER_EXECUTED_V1, EXECUTION_ORDER_FAILED_V1
from src.core.ids import new_event_id
from src.core.models import EventEnvelope

from .qmt_broker import BrokerExecutionResult, QMTBroker


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ExecutionOutcome:
    schema: str
    payload: Dict[str, Any]


class Executor:
    def __init__(self, *, broker: Optional[QMTBroker] = None) -> None:
        self._broker = broker or QMTBroker(dry_run=True)

    def _result_to_outcome(self, *, order: Dict[str, Any], ts: str, symbol: str, result: BrokerExecutionResult) -> ExecutionOutcome:
        order_id = str(order.get("order_id") or "")
        status = str(result.status)
        schema = EXECUTION_ORDER_EXECUTED_V1 if status == "EXECUTED" else EXECUTION_ORDER_FAILED_V1
        payload = {
            "order_id": order_id,
            "symbol": symbol,
            "ts": ts,
            "status": status,
            "filled_qty": float(result.filled_qty),
            "avg_price": float(result.avg_price),
            "broker": str(result.broker),
        }
        return ExecutionOutcome(schema=schema, payload=payload)

    def handle_risk_approved(self, ev: EventEnvelope) -> EventEnvelope:
        """Execute one approved order envelope and return the execution event."""

        p = ev.payload
        ts = str(p["ts"])
        symbol = str(p["symbol"])
        order = p["order"]
        if not isinstance(order, dict):
            raise ValueError("approved payload.order must be object")

        try:
            result = self._broker.place_order(order)
        except Exception as e:
            # Mechanical failure: report failure, do not attempt retries here
            # to avoid duplicate submission.
            result = BrokerExecutionResult(
                status="FAILED",
                filled_qty=0.0,
                avg_price=0.0,
                broker=getattr(self._broker, "name", "unknown"),
                message=str(e),
            )

        outcome = self._result_to_outcome(order=order, ts=ts, symbol=symbol, result=result)
        return EventEnvelope(
            event_id=new_event_id(),
            trace_id=ev.trace_id,
            produced_at=_now_utc(),
            schema=outcome.schema,
            schema_version=1,
            payload=outcome.payload,
            source_service="execution-service",
        )

