from __future__ import annotations

import os

from src.contracts.streams import RISK_ORDER_APPROVED_V1
from src.core.message_bus import RedisStreamBus
from src.core.settings import load_settings

from .executor import Executor


def main() -> None:
    s = load_settings()
    bus = RedisStreamBus(s.redis_url)

    executor = Executor()
    group = "execution-group"
    consumer = os.getenv("HOSTNAME", "execution-1")

    def handle(ev) -> None:
        out = executor.handle_risk_approved(ev)
        bus.publish(out.schema, out)

    bus.run_worker(stream=RISK_ORDER_APPROVED_V1, group=group, consumer=consumer, handler=handle)


if __name__ == "__main__":
    main()
