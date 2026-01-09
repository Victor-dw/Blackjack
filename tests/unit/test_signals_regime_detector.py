from __future__ import annotations


from dataclasses import asdict
from datetime import datetime, timezone

from src.contracts import streams
from src.contracts.validation import validate_envelope_dict
from src.core.models import EventEnvelope
from src.signals.regime_detector import (
    BEAR,
    BULL,
    CONSOLIDATION,
    TRANSITION,
    RegimeDetector,
    detect_regime,
)


def _wire(ev: EventEnvelope) -> dict:
    d = asdict(ev)
    d["produced_at"] = ev.produced_at.isoformat()
    return d


def test_detect_regime_transition_by_volatility_compression() -> None:
    assert detect_regime({"volatility_compression": 0.9}) == TRANSITION


def test_detect_regime_bull() -> None:
    vars_ = {
        "market_valuation_percentile": 80,
        "foreign_capital_flow": 0.4,
        "money_flow_heat": 0.1,
        "volatility_compression": 0.2,
    }
    assert detect_regime(vars_) == BULL


def test_detect_regime_bear() -> None:
    vars_ = {
        "market_valuation_percentile": 20,
        "foreign_capital_flow": -0.4,
        "money_flow_heat": -0.1,
        "volatility_compression": 0.2,
    }
    assert detect_regime(vars_) == BEAR


def test_detect_regime_consolidation() -> None:
    assert detect_regime({"money_flow_heat": 0.0, "volatility_compression": 0.3}) == CONSOLIDATION


def test_regime_detector_emits_contract_valid_event() -> None:
    detector = RegimeDetector()
    inp = EventEnvelope(
        event_id="evt-1",
        trace_id="trace-1",
        produced_at=datetime.now(timezone.utc),
        schema=streams.VARIABLES_MARKET_COMPUTED_V1,
        schema_version=1,
        payload={
            "symbol": "MARKET",
            "ts": "2026-01-01T00:00:00+00:00",
            "variables": {"volatility_compression": 0.9},
            "quality": {},
        },
        source_service="variables-service",
    )
    out = detector.process(inp)
    validate_envelope_dict(_wire(out))
    assert out.schema == streams.SIGNALS_REGIME_DETECTED_V1
    assert out.payload["regime"] == TRANSITION
