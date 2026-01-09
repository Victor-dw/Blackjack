from __future__ import annotations

import os

from src.contracts.streams import RISK_ORDER_APPROVED_V1
from src.core.message_bus import RedisStreamBus
from src.core.settings import load_settings


def main() -> None:
    s = load_settings()
    if not s.redis_trade_url:
        raise RuntimeError("redis_trade_url is required for trade-bridge (enable compose profile 'live')")

    compute_bus = RedisStreamBus(s.redis_url)
    trade_bus = RedisStreamBus(s.redis_trade_url)

    group = "trade-bridge"
    consumer = os.getenv("HOSTNAME", "trade-bridge-1")

    # Whitelist: only risk-approved orders cross into trade-plane.
    def forward(ev) -> None:
        trade_bus.publish(RISK_ORDER_APPROVED_V1, ev)

    compute_bus.run_worker(stream=RISK_ORDER_APPROVED_V1, group=group, consumer=consumer, handler=forward)


if __name__ == "__main__":
    main()
