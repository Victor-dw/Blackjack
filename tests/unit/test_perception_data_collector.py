from __future__ import annotations


from dataclasses import asdict
from datetime import datetime, timezone

from src.contracts import streams
from src.contracts.validation import validate_envelope_dict
from src.core.models import EventEnvelope
from src.perception.data_collector import (
    MarketBar,
    MarketDataCollector,
    build_market_data_event,
    stable_market_event_id,
)


def _wire(ev: EventEnvelope) -> dict:
    d = asdict(ev)
    d["produced_at"] = ev.produced_at.isoformat()
    return d


class _FakeBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, EventEnvelope]] = []

    def publish(self, stream: str, event: EventEnvelope) -> None:
        self.published.append((stream, event))


class _ListSource:
    def __init__(self, bars: list[MarketBar]) -> None:
        self._bars = bars

    def fetch(self):
        yield from self._bars


def test_build_market_data_event_is_contract_valid() -> None:
    bar = MarketBar(
        symbol="AAPL",
        ts=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        timeframe="1m",
        open=100.0,
        high=101.0,
        low=99.5,
        close=100.5,
        volume=1234,
        source="demo",
    )
    ev = build_market_data_event(bar=bar, trace_id="trace-1", source_service="perception-service")
    assert ev.schema == streams.PERCEPTION_MARKET_DATA_COLLECTED_V1
    validate_envelope_dict(_wire(ev))


def test_stable_market_event_id_is_deterministic() -> None:
    bar = MarketBar(
        symbol="AAPL",
        ts=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        timeframe="1m",
        open=100,
        high=101,
        low=99,
        close=100,
        volume=1,
        source="demo",
    )
    assert stable_market_event_id(bar=bar) == stable_market_event_id(bar=bar)


def test_collector_publishes_only_valid_events() -> None:
    ok = MarketBar(
        symbol="AAPL",
        ts=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
        timeframe="1m",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1.0,
        source="demo",
    )
    bad_open_zero = MarketBar(
        symbol="AAPL",
        ts=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
        timeframe="1m",
        open=0.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1.0,
        source="demo",
    )

    bus = _FakeBus()
    src = _ListSource([ok, bad_open_zero])
    collector = MarketDataCollector(bus=bus, source=src)
    stats = collector.collect_once()

    assert stats.published == 1
    assert stats.skipped_invalid == 1
    assert len(bus.published) == 1
    assert bus.published[0][0] == streams.PERCEPTION_MARKET_DATA_COLLECTED_V1
