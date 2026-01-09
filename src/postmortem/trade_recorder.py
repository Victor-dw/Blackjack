"""Trade record storage - persists execution results to PostgreSQL.

This module handles the L7 postmortem layer's core function:
recording trade execution results with decision-time snapshots for later analysis.

Input: execution.order.executed.v1 / execution.order.failed.v1 events
Output: postmortem.trade_record.created.v1 events
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional, Protocol
from enum import Enum


class TradeStatus(str, Enum):
    """Trade execution status."""
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


@dataclass
class OrderDetails:
    """Order details from execution."""
    order_id: str
    side: str  # BUY / SELL
    qty: float
    filled_qty: float
    avg_price: float
    broker: str


@dataclass
class DecisionSnapshot:
    """Snapshot of decision-time context for post-mortem analysis.

    This preserves the market/stock/signal state at decision time,
    allowing evaluation of decision quality independent of outcome.
    """
    market_vars: dict[str, Any] = field(default_factory=dict)
    stock_vars: dict[str, Any] = field(default_factory=dict)
    signal_snapshot: dict[str, Any] = field(default_factory=dict)
    regime_state: str = ""
    strategy_triggered: str = ""
    kelly_calculation: dict[str, Any] = field(default_factory=dict)
    risk_check_result: dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeRecord:
    """Complete trade record for post-mortem analysis.

    This structure captures everything needed to evaluate decision quality,
    following the principle of "屏蔽结果，只看决策".
    """
    trade_id: str
    trace_id: str
    symbol: str
    timestamp: datetime
    status: TradeStatus
    order: OrderDetails
    decision_snapshot: DecisionSnapshot
    # Outcome fields (hidden during quality evaluation)
    pnl: Optional[float] = None
    holding_period_minutes: Optional[int] = None
    max_drawdown: Optional[float] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage/serialization."""
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        d["created_at"] = self.created_at.isoformat()
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TradeRecord":
        """Create from dictionary."""
        return cls(
            trade_id=d["trade_id"],
            trace_id=d["trace_id"],
            symbol=d["symbol"],
            timestamp=datetime.fromisoformat(d["timestamp"]),
            status=TradeStatus(d["status"]),
            order=OrderDetails(**d["order"]),
            decision_snapshot=DecisionSnapshot(**d["decision_snapshot"]),
            pnl=d.get("pnl"),
            holding_period_minutes=d.get("holding_period_minutes"),
            max_drawdown=d.get("max_drawdown"),
            created_at=datetime.fromisoformat(d["created_at"]) if "created_at" in d else datetime.now(timezone.utc),
        )


class TradeRecordRepository(Protocol):
    """Interface for trade record persistence."""

    def save(self, record: TradeRecord) -> None:
        """Persist a trade record."""
        ...

    def get_by_id(self, trade_id: str) -> Optional[TradeRecord]:
        """Retrieve a trade record by ID."""
        ...

    def get_by_symbol(self, symbol: str, limit: int = 100) -> list[TradeRecord]:
        """Retrieve trade records for a symbol."""
        ...

    def get_recent(self, limit: int = 100) -> list[TradeRecord]:
        """Retrieve recent trade records."""
        ...


class InMemoryTradeRecordRepository:
    """In-memory implementation for testing."""

    def __init__(self) -> None:
        self._records: dict[str, TradeRecord] = {}

    def save(self, record: TradeRecord) -> None:
        self._records[record.trade_id] = record

    def get_by_id(self, trade_id: str) -> Optional[TradeRecord]:
        return self._records.get(trade_id)

    def get_by_symbol(self, symbol: str, limit: int = 100) -> list[TradeRecord]:
        records = [r for r in self._records.values() if r.symbol == symbol]
        records.sort(key=lambda x: x.timestamp, reverse=True)
        return records[:limit]

    def get_recent(self, limit: int = 100) -> list[TradeRecord]:
        records = list(self._records.values())
        records.sort(key=lambda x: x.timestamp, reverse=True)
        return records[:limit]


class PostgresTradeRecordRepository:
    """PostgreSQL implementation for production.

    Requires a table with the following schema:

    CREATE TABLE IF NOT EXISTS trade_records (
        trade_id VARCHAR(64) PRIMARY KEY,
        trace_id VARCHAR(64) NOT NULL,
        symbol VARCHAR(20) NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL,
        status VARCHAR(20) NOT NULL,
        order_details JSONB NOT NULL,
        decision_snapshot JSONB NOT NULL,
        pnl DECIMAL(18, 4),
        holding_period_minutes INTEGER,
        max_drawdown DECIMAL(10, 6),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_trade_records_symbol ON trade_records(symbol);
    CREATE INDEX IF NOT EXISTS idx_trade_records_timestamp ON trade_records(timestamp DESC);
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn = None

    def _get_conn(self):
        if self._conn is None:
            import psycopg2  # type: ignore
            self._conn = psycopg2.connect(self._dsn)
        return self._conn

    def save(self, record: TradeRecord) -> None:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO trade_records (
                    trade_id, trace_id, symbol, timestamp, status,
                    order_details, decision_snapshot, pnl,
                    holding_period_minutes, max_drawdown, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (trade_id) DO UPDATE SET
                    pnl = EXCLUDED.pnl,
                    holding_period_minutes = EXCLUDED.holding_period_minutes,
                    max_drawdown = EXCLUDED.max_drawdown
                """,
                (
                    record.trade_id,
                    record.trace_id,
                    record.symbol,
                    record.timestamp,
                    record.status.value,
                    json.dumps(asdict(record.order)),
                    json.dumps(asdict(record.decision_snapshot)),
                    record.pnl,
                    record.holding_period_minutes,
                    record.max_drawdown,
                    record.created_at,
                ),
            )
            conn.commit()

    def get_by_id(self, trade_id: str) -> Optional[TradeRecord]:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM trade_records WHERE trade_id = %s",
                (trade_id,),
            )
            row = cur.fetchone()
            if row:
                return self._row_to_record(row, cur.description)
        return None

    def get_by_symbol(self, symbol: str, limit: int = 100) -> list[TradeRecord]:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM trade_records WHERE symbol = %s ORDER BY timestamp DESC LIMIT %s",
                (symbol, limit),
            )
            return [self._row_to_record(row, cur.description) for row in cur.fetchall()]

    def get_recent(self, limit: int = 100) -> list[TradeRecord]:
        conn = self._get_conn()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM trade_records ORDER BY timestamp DESC LIMIT %s",
                (limit,),
            )
            return [self._row_to_record(row, cur.description) for row in cur.fetchall()]

    def _row_to_record(self, row: tuple, description) -> TradeRecord:
        cols = [d[0] for d in description]
        d = dict(zip(cols, row))
        return TradeRecord(
            trade_id=d["trade_id"],
            trace_id=d["trace_id"],
            symbol=d["symbol"],
            timestamp=d["timestamp"],
            status=TradeStatus(d["status"]),
            order=OrderDetails(**d["order_details"]),
            decision_snapshot=DecisionSnapshot(**d["decision_snapshot"]),
            pnl=float(d["pnl"]) if d.get("pnl") is not None else None,
            holding_period_minutes=d.get("holding_period_minutes"),
            max_drawdown=float(d["max_drawdown"]) if d.get("max_drawdown") is not None else None,
            created_at=d["created_at"],
        )


class TradeRecorder:
    """Records trade execution results and publishes postmortem events.

    This is the core class that:
    1. Receives execution.order.executed/failed.v1 events
    2. Persists trade records to PostgreSQL
    3. Publishes postmortem.trade_record.created.v1 events
    """

    def __init__(
        self,
        repository: TradeRecordRepository,
        message_bus=None,
    ) -> None:
        self._repository = repository
        self._bus = message_bus

    def record_execution(
        self,
        event_id: str,
        trace_id: str,
        payload: dict[str, Any],
        is_success: bool,
        decision_snapshot: Optional[DecisionSnapshot] = None,
    ) -> TradeRecord:
        """Record a trade execution from an execution event.

        Args:
            event_id: The event ID from the execution event
            trace_id: The trace ID for correlation
            payload: The execution event payload
            is_success: Whether the execution was successful
            decision_snapshot: Optional snapshot of decision-time context

        Returns:
            The created TradeRecord
        """
        from src.core.ids import new_event_id

        record = TradeRecord(
            trade_id=f"trd-{event_id}",
            trace_id=trace_id,
            symbol=payload["symbol"],
            timestamp=datetime.fromisoformat(payload["ts"].replace("Z", "+00:00")),
            status=TradeStatus.EXECUTED if is_success else TradeStatus.FAILED,
            order=OrderDetails(
                order_id=payload["order_id"],
                side=payload.get("side", "UNKNOWN"),
                qty=payload.get("qty", 0),
                filled_qty=payload["filled_qty"],
                avg_price=payload["avg_price"],
                broker=payload["broker"],
            ),
            decision_snapshot=decision_snapshot or DecisionSnapshot(),
        )

        self._repository.save(record)
        self._publish_trade_record_event(record)

        return record

    def _publish_trade_record_event(self, record: TradeRecord) -> None:
        """Publish postmortem.trade_record.created.v1 event."""
        if self._bus is None:
            return

        from src.core.ids import new_event_id, new_trace_id
        from src.core.models import EventEnvelope
        from src.contracts.streams import POSTMORTEM_TRADE_RECORD_CREATED_V1

        envelope = EventEnvelope(
            event_id=new_event_id(),
            trace_id=record.trace_id,
            produced_at=datetime.now(timezone.utc),
            schema=POSTMORTEM_TRADE_RECORD_CREATED_V1,
            schema_version=1,
            payload={
                "trade_id": record.trade_id,
                "symbol": record.symbol,
                "ts": record.timestamp.isoformat(),
                "status": record.status.value,
                "order": asdict(record.order),
                "decision_snapshot": asdict(record.decision_snapshot),
            },
            source_service="postmortem-service",
        )

        self._bus.publish(POSTMORTEM_TRADE_RECORD_CREATED_V1, envelope)

    def update_outcome(
        self,
        trade_id: str,
        pnl: float,
        holding_period_minutes: int,
        max_drawdown: float,
    ) -> Optional[TradeRecord]:
        """Update a trade record with outcome data after position is closed."""
        record = self._repository.get_by_id(trade_id)
        if record is None:
            return None

        # Create updated record with outcome data
        updated = TradeRecord(
            trade_id=record.trade_id,
            trace_id=record.trace_id,
            symbol=record.symbol,
            timestamp=record.timestamp,
            status=record.status,
            order=record.order,
            decision_snapshot=record.decision_snapshot,
            pnl=pnl,
            holding_period_minutes=holding_period_minutes,
            max_drawdown=max_drawdown,
            created_at=record.created_at,
        )

        self._repository.save(updated)
        return updated
