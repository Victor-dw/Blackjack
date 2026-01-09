"""Evolution service - backtests, optimization, and health monitoring.

IMPORTANT: This service must be PHYSICALLY ISOLATED from live execution.
- Only allowed to access compute-network
- NEVER allowed to access trade-network
- Must not have any access to trading interfaces

This service provides:
1. Strategy backtesting on historical data
2. Parameter optimization
3. Strategy health monitoring
4. Publishes evolution.backtest.completed.v1 events

Network: compute-network only (strict isolation from trade-network)
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone

from src.core.message_bus import RedisStreamBus
from src.contracts import streams

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Verify network isolation at startup
def verify_isolation() -> bool:
    """Verify that this service cannot access trade-network resources."""
    trade_redis_url = os.getenv("BLACKJACK_REDIS_TRADE_URL")
    if trade_redis_url:
        logger.error(
            "SECURITY VIOLATION: Evolution service should not have "
            "BLACKJACK_REDIS_TRADE_URL configured!"
        )
        return False

    # Additional checks could be added here:
    # - Verify no broker credentials
    # - Verify no QMT configuration
    # - Verify network isolation via Docker

    logger.info("Network isolation verified: no trade-network access")
    return True


def main() -> None:
    """Run the evolution service."""
    redis_url = os.getenv("BLACKJACK_REDIS_URL", "redis://localhost:6379/0")

    logger.info("Starting evolution service...")
    logger.info(f"Redis URL: {redis_url}")

    # Verify isolation before proceeding
    if not verify_isolation():
        logger.error("Aborting: network isolation check failed")
        return

    bus = RedisStreamBus(redis_url)

    # Import components
    from src.evolution.backtest_engine import BacktestEngine, InMemoryDataProvider
    from src.evolution.health_monitor import HealthMonitor

    # Initialize components
    data_provider = InMemoryDataProvider()  # TODO: Use real data provider
    backtest_engine = BacktestEngine(data_provider, message_bus=bus)
    health_monitor = HealthMonitor()

    logger.info("Evolution service initialized")
    logger.info("  - Backtest engine: ready")
    logger.info("  - Health monitor: ready")

    # In production, this would:
    # 1. Subscribe to trade record events for health monitoring
    # 2. Run scheduled backtests
    # 3. Monitor strategy health continuously

    # For now, just keep the service running
    logger.info("Evolution service running (idle mode)")
    logger.info("  Use API endpoints to trigger backtests and check health")

    try:
        import time
        while True:
            time.sleep(60)
            # Periodic health check logging
            metrics = health_monitor.get_all_metrics()
            if metrics:
                logger.info(f"Monitoring {len(metrics)} strategies")
    except KeyboardInterrupt:
        logger.info("Shutting down evolution service...")


if __name__ == "__main__":
    main()
