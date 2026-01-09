from __future__ import annotations


from dataclasses import asdict
from datetime import datetime, timezone

from src.contracts import streams
from src.contracts.validation import validate_envelope_dict
from src.core.models import EventEnvelope
from src.signals.signal_composer import SignalComposer


def _wire(ev: EventEnvelope) -> dict:
    d = asdict(ev)
    d["produced_at"] = ev.produced_at.isoformat()
    return d


def test_signal_composer_emits_contract_valid_opportunity_event() -> None:
    composer = SignalComposer()

    market_ev = EventEnvelope(
        event_id="evt-mkt-1",
        trace_id="trace-1",
        produced_at=datetime.now(timezone.utc),
        schema=streams.VARIABLES_MARKET_COMPUTED_V1,
        schema_version=1,
        payload={
            "symbol": "MARKET",
            "ts": "2026-01-01T00:00:00+00:00",
            "variables": {
                "market_valuation_percentile": 80,
                "volatility_compression": 0.2,
                "money_flow_heat": 0.3,
                "foreign_capital_flow": 0.4,
            },
            "quality": {"confidence": 80},
        },
        source_service="variables-service",
    )
    composer.update_market(market_ev)

    stock_ev = EventEnvelope(
        event_id="evt-stk-1",
        trace_id="trace-1",
        produced_at=datetime.now(timezone.utc),
        schema=streams.VARIABLES_STOCK_COMPUTED_V1,
        schema_version=1,
        payload={
            "symbol": "AAPL",
            "ts": "2026-01-01T00:00:00+00:00",
            "variables": {
                "volume_price_signal": 85,
                "relative_strength": 70,
                "fundamental_score": 60,
                "main_force_behavior": "MAIN_FORCE_PUMP",
                "policy_intervention_prob": 0.1,
                "rule_change_alert": False,
            },
            "quality": {"confidence": 75},
        },
        source_service="variables-service",
    )

    out = composer.compose_from_stock(stock_ev)
    assert out is not None
    validate_envelope_dict(_wire(out))
    assert out.schema == streams.SIGNALS_OPPORTUNITY_SCORED_V1
    assert out.payload["symbol"] == "AAPL"
    assert 0 <= out.payload["opportunity_score"] <= 100
    assert 0 <= out.payload["confidence"] <= 100
    assert isinstance(out.payload["components"], dict)
