"""Postmortem service - subscribes to execution events and persists trade records.

This service:
1. Subscribes to execution.order.executed.v1 and execution.order.failed.v1
2. Records trades to PostgreSQL via TradeRecorder
3. Publishes postmortem.trade_record.created.v1 events

Network: compute-network only
Consumer Group: postmortem-group
"""

from __future__ import annotations

import os
import logging

from src.core.message_bus import RedisStreamBus
from src.core.models import EventEnvelope
from src.contracts import streams
from src.postmortem.trade_recorder import (
    TradeRecorder,
    InMemoryTradeRecordRepository,
    PostgresTradeRecordRepository,
    DecisionSnapshot,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_repository():
    """Create the appropriate repository based on environment."""
    dsn = os.getenv("BLACKJACK_POSTGRES_DSN")
    if dsn:
        logger.info("Using PostgreSQL repository")
        return PostgresTradeRecordRepository(dsn)
    else:
        logger.info("Using in-memory repository (dev mode)")
        return InMemoryTradeRecordRepository()


def handle_execution_event(
    envelope: EventEnvelope,
    recorder: TradeRecorder,
) -> None:
    """Handle an execution event and record the trade."""
    schema = envelope.schema
    payload = envelope.payload

    is_success = schema == streams.EXECUTION_ORDER_EXECUTED_V1

    logger.info(
        f"Recording trade: order_id={payload.get('order_id')}, "
        f"symbol={payload.get('symbol')}, success={is_success}"
    )

    # TODO: In production, fetch decision snapshot from a snapshot store
    # For now, we create an empty snapshot
    snapshot = DecisionSnapshot()

    record = recorder.record_execution(
        event_id=envelope.event_id,
        trace_id=envelope.trace_id,
        payload=payload,
        is_success=is_success,
        decision_snapshot=snapshot,
    )

    logger.info(f"Trade recorded: trade_id={record.trade_id}")


def main() -> None:
    """Run the postmortem service."""
    redis_url = os.getenv("BLACKJACK_REDIS_URL", "redis://localhost:6379/0")

    logger.info("Starting postmortem service...")
    logger.info(f"Redis URL: {redis_url}")

    bus = RedisStreamBus(redis_url)
    repository = create_repository()
    recorder = TradeRecorder(repository, message_bus=bus)

    # Subscribe to both executed and failed streams
    consumed_streams = [
        streams.EXECUTION_ORDER_EXECUTED_V1,
        streams.EXECUTION_ORDER_FAILED_V1,
    ]

    def handler(envelope: EventEnvelope) -> None:
        handle_execution_event(envelope, recorder)

    logger.info(f"Subscribing to streams: {consumed_streams}")

    # Run workers for each stream
    # In production, you might use threading or async
    for stream in consumed_streams:
        try:
            bus.run_worker(
                stream=stream,
                group="postmortem-group",
                consumer="postmortem-1",
                handler=handler,
            )
        except KeyboardInterrupt:
            logger.info("Shutting down postmortem service...")
            break


if __name__ == "__main__":
    main()
