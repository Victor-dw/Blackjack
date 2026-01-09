"""Layer 1: Perception.

This module is responsible for collecting market data from external sources
(API/QMT/etc), applying minimal cleaning/standardization, and emitting
contract-valid v1 events into the compute-plane bus.

Output stream (v1):
- perception.market_data.collected.v1

Contract rules:
- Strict v1 envelope + payload validation (no extra fields)
- Payload schema enforced by src/contracts/validation.py
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable, Protocol

from src.contracts import streams
from src.contracts.validation import validate_envelope_dict
from src.core.ids import new_trace_id
from src.core.message_bus import MessageBus, RedisStreamBus
from src.core.models import EventEnvelope
from src.core.settings import load_settings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketBar:
    """Normalized OHLCV bar used as the internal representation in L1.

    NOTE: This is not a contract type; the contract type is the EventEnvelope
    published to the stream.
    """

    symbol: str
    ts: datetime
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str


class MarketDataSource(Protocol):
    """Pluggable market data source."""

    def fetch(self) -> Iterable[MarketBar]:
        """Return a batch of bars to publish."""


def _ensure_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _iso(dt: datetime) -> str:
    return _ensure_tz(dt).isoformat()


def stable_market_event_id(*, bar: MarketBar) -> str:
    """Deterministic idempotency key for the same (symbol, timeframe, ts, source)."""

    name = "|".join(
        [
            streams.PERCEPTION_MARKET_DATA_COLLECTED_V1,
            bar.source,
            bar.symbol,
            bar.timeframe,
            _iso(bar.ts),
        ]
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))


def build_market_data_event(
    *,
    bar: MarketBar,
    trace_id: str,
    produced_at: datetime | None = None,
    source_service: str = "perception-service",
    event_id: str | None = None,
) -> EventEnvelope:
    """Build a v1 contract event for perception.market_data.collected.v1."""

    produced_at = produced_at or datetime.now(timezone.utc)
    event_id = event_id or stable_market_event_id(bar=bar)

    payload = {
        "symbol": bar.symbol,
        "ts": _iso(bar.ts),
        "timeframe": bar.timeframe,
        "open": float(bar.open),
        "high": float(bar.high),
        "low": float(bar.low),
        "close": float(bar.close),
        "volume": float(bar.volume),
        "source": bar.source,
    }

    return EventEnvelope(
        event_id=event_id,
        trace_id=trace_id,
        produced_at=_ensure_tz(produced_at),
        schema=streams.PERCEPTION_MARKET_DATA_COLLECTED_V1,
        schema_version=1,
        payload=payload,
        source_service=source_service,
    )


def _to_wire_dict(ev: EventEnvelope) -> dict:
    """Convert EventEnvelope to strict v1 wire dict for validation/testing."""

    d = asdict(ev)
    d["produced_at"] = _iso(ev.produced_at)
    return d


@dataclass(frozen=True)
class CollectStats:
    published: int
    skipped_invalid: int


class DemoMarketDataSource:
    """A dependency-free demo source for local smoke tests.

    It emits a single 1m bar for one symbol at the current minute.
    """

    def __init__(self, *, symbol: str = "AAPL", timeframe: str = "1m", base_price: float = 100.0):
        self.symbol = symbol
        self.timeframe = timeframe
        self.base_price = float(base_price)

    def fetch(self) -> Iterable[MarketBar]:
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        p = self.base_price
        yield MarketBar(
            symbol=self.symbol,
            ts=now,
            timeframe=self.timeframe,
            open=p,
            high=p,
            low=p,
            close=p,
            volume=0.0,
            source="demo",
        )


class MarketDataCollector:
    """Collect bars from a source and publish contract-valid events."""

    def __init__(
        self,
        *,
        bus: MessageBus,
        source: MarketDataSource,
        source_service: str = "perception-service",
    ):
        self.bus = bus
        self.source = source
        self.source_service = source_service

    def collect_once(self) -> CollectStats:
        trace_id = new_trace_id()
        published = 0
        skipped_invalid = 0

        for bar in self.source.fetch():
            ev = build_market_data_event(bar=bar, trace_id=trace_id, source_service=self.source_service)
            try:
                # Validate *before* publish so tests can use a fake bus.
                validate_envelope_dict(_to_wire_dict(ev))
                self.bus.publish(streams.PERCEPTION_MARKET_DATA_COLLECTED_V1, ev)
                published += 1
            except Exception as e:
                skipped_invalid += 1
                logger.warning("skip_invalid_market_data", extra={"error": str(e), "symbol": bar.symbol, "ts": _iso(bar.ts)})

        return CollectStats(published=published, skipped_invalid=skipped_invalid)

    def run_forever(self, *, poll_interval_seconds: float = 1.0) -> None:
        while True:
            self.collect_once()
            time.sleep(poll_interval_seconds)


def collect() -> None:
    """Default entrypoint used by the perception service.

    For now we keep this dependency-free and safe by default:
    - If no external source is configured, we emit a single demo bar and exit.
    """

    s = load_settings()
    bus = RedisStreamBus(s.redis_url)

    symbol = os.getenv("PERCEPTION_DEMO_SYMBOL", "AAPL")
    source: MarketDataSource = DemoMarketDataSource(symbol=symbol)
    collector = MarketDataCollector(bus=bus, source=source)
    collector.collect_once()

