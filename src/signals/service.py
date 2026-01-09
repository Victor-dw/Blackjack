from __future__ import annotations

import os
import threading

from src.contracts import streams
from src.core.message_bus import RedisStreamBus
from src.core.settings import load_settings

from .regime_detector import RegimeDetector
from .signal_composer import SignalComposer


def main() -> None:
    s = load_settings()
    group = "signals-group"
    base_consumer = os.getenv("HOSTNAME", "signals-1")

    # Two workers (two streams). Each uses its own Redis client for simplicity.
    market_bus = RedisStreamBus(s.redis_url)
    stock_bus = RedisStreamBus(s.redis_url)

    composer = SignalComposer()
    regime = RegimeDetector()

    def on_market(ev) -> None:
        # Update composer state first, then publish regime.
        composer.update_market(ev)
        out = regime.process(ev)
        market_bus.publish(streams.SIGNALS_REGIME_DETECTED_V1, out)

    def on_stock(ev) -> None:
        out = composer.compose_from_stock(ev)
        if out is None:
            return
        stock_bus.publish(streams.SIGNALS_OPPORTUNITY_SCORED_V1, out)

    t_market = threading.Thread(
        target=lambda: market_bus.run_worker(
            stream=streams.VARIABLES_MARKET_COMPUTED_V1,
            group=group,
            consumer=f"{base_consumer}-market",
            handler=on_market,
        ),
        daemon=True,
        name="signals-market-worker",
    )
    t_stock = threading.Thread(
        target=lambda: stock_bus.run_worker(
            stream=streams.VARIABLES_STOCK_COMPUTED_V1,
            group=group,
            consumer=f"{base_consumer}-stock",
            handler=on_stock,
        ),
        daemon=True,
        name="signals-stock-worker",
    )

    t_market.start()
    t_stock.start()
    t_market.join()
    t_stock.join()


if __name__ == "__main__":
    main()
