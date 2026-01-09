from __future__ import annotations


import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from src.contracts import streams
from src.contracts.validation import validate_envelope_dict
from src.core.models import EventEnvelope
from src.variables.market_vars import MarketVarsCalculator
from src.variables.stock_vars import StockVarsCalculator


GOLDEN_DIR = Path("contracts") / "golden_events" / "v1"


def _wire(ev: EventEnvelope) -> dict:
    d = asdict(ev)
    d["produced_at"] = ev.produced_at.isoformat()
    return d


def _envelope_from_wire(d: dict) -> EventEnvelope:
    return EventEnvelope(
        event_id=str(d["event_id"]),
        trace_id=str(d["trace_id"]),
        produced_at=datetime.fromisoformat(str(d["produced_at"])),
        schema=str(d["schema"]),
        schema_version=int(d["schema_version"]),
        payload=dict(d["payload"]),
        source_service=d.get("source_service"),
    )


def test_market_vars_from_golden_perception_event_are_contract_valid() -> None:
    raw = json.loads((GOLDEN_DIR / "01_perception_market_data_valid.json").read_text(encoding="utf-8"))
    ev = _envelope_from_wire(raw)

    calc = MarketVarsCalculator()
    out = calc.compute(ev)
    assert out.schema == streams.VARIABLES_MARKET_COMPUTED_V1
    validate_envelope_dict(_wire(out))

    variables = out.payload["variables"]
    assert set(["market_valuation_percentile", "volatility_compression", "money_flow_heat", "foreign_capital_flow"]).issubset(
        set(variables.keys())
    )
    assert 0.0 <= float(variables["market_valuation_percentile"]) <= 100.0
    assert 0.0 <= float(variables["volatility_compression"]) <= 1.0
    assert -1.0 <= float(variables["money_flow_heat"]) <= 1.0
    assert -1.0 <= float(variables["foreign_capital_flow"]) <= 1.0


def test_stock_vars_from_golden_perception_event_are_contract_valid() -> None:
    raw = json.loads((GOLDEN_DIR / "01_perception_market_data_valid.json").read_text(encoding="utf-8"))
    ev = _envelope_from_wire(raw)

    calc = StockVarsCalculator()
    out = calc.compute(ev)
    assert out.schema == streams.VARIABLES_STOCK_COMPUTED_V1
    validate_envelope_dict(_wire(out))

    variables = out.payload["variables"]
    assert set(
        [
            "volume_price_signal",
            "relative_strength",
            "fundamental_score",
            "main_force_behavior",
            "policy_intervention_prob",
            "rule_change_alert",
        ]
    ).issubset(set(variables.keys()))
    assert 0.0 <= float(variables["volume_price_signal"]) <= 100.0
    assert 0.0 <= float(variables["relative_strength"]) <= 100.0
    assert 0.0 <= float(variables["fundamental_score"]) <= 100.0
    assert 0.0 <= float(variables["policy_intervention_prob"]) <= 1.0
    assert isinstance(variables["rule_change_alert"], bool)
