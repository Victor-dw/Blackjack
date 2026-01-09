"""Market regime detection.

Consumes `variables.market.computed.v1` events (payload.variables) and produces
`signals.regime.detected.v1` with a coarse regime label.

The v1 payload contract for output is enforced by src/contracts/validation.py:
payload must be exactly {symbol, ts, regime}.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from src.contracts import streams
from src.core.ids import new_event_id
from src.core.models import EventEnvelope


BULL = "BULL"
BEAR = "BEAR"
CONSOLIDATION = "CONSOLIDATION"
TRANSITION = "TRANSITION"
UNKNOWN = "UNKNOWN"


def _num(m: Mapping[str, Any], k: str) -> float | None:
    v = m.get(k)
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def detect_regime(variables: Mapping[str, Any]) -> str:
    """Detect market regime from normalized market variables.

    Expected (best-effort) keys (see docs/ARCHITECTURE.md):
    - market_valuation_percentile: [0, 100]
    - volatility_compression: [0, 1]
    - money_flow_heat: [-1, 1]
    - foreign_capital_flow: [-1, 1]

    The algorithm is intentionally simple (MVP) and should be treated as a
    heuristic until L2 becomes richer.
    """

    vol_comp = _num(variables, "volatility_compression")
    if vol_comp is not None and vol_comp >= 0.85:
        # High compression often precedes a structural break / regime shift.
        return TRANSITION

    val_pct = _num(variables, "market_valuation_percentile")
    money_heat = _num(variables, "money_flow_heat")
    foreign_flow = _num(variables, "foreign_capital_flow")

    # Strong trend regimes (need at least valuation + foreign flow).
    if val_pct is not None and foreign_flow is not None:
        if val_pct >= 70 and foreign_flow >= 0.20 and (money_heat is None or money_heat >= 0.0):
            return BULL
        if val_pct <= 30 and foreign_flow <= -0.20 and (money_heat is None or money_heat <= 0.0):
            return BEAR

    # Sideways / consolidation when flows are not directional.
    if money_heat is not None and abs(money_heat) < 0.20:
        return CONSOLIDATION

    # Fallbacks.
    if money_heat is not None:
        return BULL if money_heat > 0 else BEAR

    return UNKNOWN


def build_regime_event(*, source: EventEnvelope, regime: str) -> EventEnvelope:
    payload = {
        "symbol": str(source.payload.get("symbol", "")),
        "ts": str(source.payload.get("ts", "")),
        "regime": str(regime),
    }
    return EventEnvelope(
        event_id=new_event_id(),
        trace_id=source.trace_id,
        produced_at=datetime.now(timezone.utc),
        schema=streams.SIGNALS_REGIME_DETECTED_V1,
        schema_version=1,
        payload=payload,
        source_service="signals-service",
    )


@dataclass
class RegimeDetector:
    """State-less wrapper around detect_regime()."""

    def process(self, ev: EventEnvelope) -> EventEnvelope:
        if ev.schema != streams.VARIABLES_MARKET_COMPUTED_V1:
            raise ValueError(f"RegimeDetector expects {streams.VARIABLES_MARKET_COMPUTED_V1}, got {ev.schema}")
        variables = ev.payload.get("variables")
        if not isinstance(variables, dict):
            variables = {}
        regime = detect_regime(variables)
        return build_regime_event(source=ev, regime=regime)

