from __future__ import annotations

from datetime import datetime, timezone

from src.core.ids import new_event_id, new_trace_id
from src.core.message_bus import RedisStreamBus
from src.core.models import EventEnvelope
from src.core.settings import load_settings


def main() -> None:
    s = load_settings()
    bus = RedisStreamBus(s.redis_url)

    # Skeleton: publish a heartbeat sample event.
    ev = EventEnvelope(
        event_id=new_event_id(),
        trace_id=new_trace_id(),
        produced_at=datetime.now(timezone.utc),
        schema="perception.heartbeat.v1",
        schema_version=1,
        payload={"status": "ok"},
        source_service="perception-service",
    )
    bus.publish("perception.heartbeat.v1", ev)


if __name__ == "__main__":
    main()
