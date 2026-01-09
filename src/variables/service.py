from __future__ import annotations


import os

from src.contracts import streams
from src.core.message_bus import RedisStreamBus
from src.core.settings import load_settings

from .market_vars import MarketVarsCalculator
from .stock_vars import StockVarsCalculator


def main() -> None:
    """Variables streaming service.

    Consumes perception.market_data.collected.v1 and publishes:
    - variables.market.computed.v1
    - variables.stock.computed.v1
    """

    s = load_settings()
    bus = RedisStreamBus(s.redis_url)

    group = os.getenv("CONSUMER_GROUP", "variables-group")
    consumer = os.getenv("CONSUMER_NAME", "variables-1")
    market_symbol = os.getenv("MARKET_SYMBOL", "MARKET")
    market_proxy = os.getenv("MARKET_PROXY_SYMBOL", "")

    market_calc = MarketVarsCalculator(market_symbol=market_symbol)
    stock_calc = StockVarsCalculator()

    def handler(ev):
        # Always publish stock vars.
        bus.publish(streams.VARIABLES_STOCK_COMPUTED_V1, stock_calc.compute(ev))

        # Publish market vars when symbol matches configured proxy, or if no proxy configured.
        sym = str(ev.payload.get("symbol", ""))
        if (not market_proxy) or (sym == market_proxy):
            bus.publish(streams.VARIABLES_MARKET_COMPUTED_V1, market_calc.compute(ev))

    bus.run_worker(
        stream=streams.PERCEPTION_MARKET_DATA_COLLECTED_V1,
        group=group,
        consumer=consumer,
        handler=handler,
    )


if __name__ == "__main__":
    main()
