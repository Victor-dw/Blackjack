from __future__ import annotations

import os

from src.contracts.streams import STRATEGY_CANDIDATE_ACTION_GENERATED_V1
from src.core.message_bus import RedisStreamBus
from src.core.settings import load_settings

from .position_allocator import PositionAllocator


def main() -> None:
    s = load_settings()
    bus = RedisStreamBus(s.redis_url)

    allocator = PositionAllocator()
    group = "risk-group"
    consumer = os.getenv("HOSTNAME", "risk-1")

    def handle(ev) -> None:
        out = allocator.handle_candidate_action(ev)
        # Stream name equals schema name in v1.
        bus.publish(out.schema, out)

    bus.run_worker(stream=STRATEGY_CANDIDATE_ACTION_GENERATED_V1, group=group, consumer=consumer, handler=handle)


if __name__ == "__main__":
    main()
