"""QMT broker adapter.

This is a stub implementation.

Architecture constraints (docs/ARCHITECTURE.md):
- Live execution must run on trade-network (physically isolated)
- QMT integration requires dual code review
- L6 execution must be purely mechanical (no "smart" decisions)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class BrokerExecutionResult:
    status: str  # e.g. EXECUTED / FAILED
    filled_qty: float
    avg_price: float
    broker: str
    message: str | None = None


class QMTBroker:
    """Stub broker adapter.

    In dry_run mode we simply echo a filled execution.
    """

    name = "qmt"

    def __init__(self, *, dry_run: bool = True) -> None:
        self.dry_run = dry_run

    def place_order(self, order: Dict[str, Any]) -> BrokerExecutionResult:
        # Mechanical validation only: presence checks.
        order_id = str(order.get("order_id") or "")
        symbol = str(order.get("symbol") or "")
        qty = float(order.get("qty") or 0)
        if not order_id or not symbol or qty <= 0:
            return BrokerExecutionResult(
                status="FAILED",
                filled_qty=0.0,
                avg_price=0.0,
                broker=self.name,
                message="invalid_order",
            )

        # Stub behavior: treat as executed. Real implementation will connect to QMT.
        return BrokerExecutionResult(
            status="EXECUTED",
            filled_qty=float(qty),
            avg_price=0.0,
            broker=self.name,
            message="dry_run" if self.dry_run else "stub",
        )

