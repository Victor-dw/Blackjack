"""Market factor computation (L2 variables: market).

Consumes:
- perception.market_data.collected.v1

Produces:
- variables.market.computed.v1

This module intentionally uses simple, dependency-free heuristics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.contracts import streams
from src.core.ids import new_event_id
from src.core.models import EventEnvelope

from .normalizer import FactorNormalizer, clamp, tanh_to_minus1_1


def _safe_div(n: float, d: float, *, default: float) -> float:
    if not isinstance(n, (int, float)) or not isinstance(d, (int, float)):
        return default
    if d == 0:
        return default
    return float(n) / float(d)


@dataclass
class _RollingMinMax:
    min_v: float | None = None
    max_v: float | None = None
    count: int = 0

    def update(self, x: float) -> None:
        xf = float(x)
        self.count += 1
        self.min_v = xf if self.min_v is None else min(self.min_v, xf)
        self.max_v = xf if self.max_v is None else max(self.max_v, xf)

    def percentile_0_100(self, x: float) -> float:
        if self.min_v is None or self.max_v is None or self.max_v == self.min_v:
            return 50.0
        return clamp(((float(x) - self.min_v) / (self.max_v - self.min_v)) * 100.0, 0.0, 100.0)


class MarketVarsCalculator:
    """Stateful market variables calculator."""

    def __init__(self, *, normalizer: FactorNormalizer | None = None, market_symbol: str = "MARKET"):
        self.normalizer = normalizer or FactorNormalizer()
        self.market_symbol = market_symbol
        self._close_range = _RollingMinMax()

    def compute(self, ev: EventEnvelope) -> EventEnvelope:
        if ev.schema != streams.PERCEPTION_MARKET_DATA_COLLECTED_V1:
            raise ValueError(f"MarketVarsCalculator expects {streams.PERCEPTION_MARKET_DATA_COLLECTED_V1}, got {ev.schema}")

        p = ev.payload
        ts = str(p.get("ts", ""))
        o = float(p.get("open", 0.0))
        h = float(p.get("high", 0.0))
        l = float(p.get("low", 0.0))
        c = float(p.get("close", 0.0))
        v = float(p.get("volume", 0.0))

        self._close_range.update(c)
        valuation_pct = self._close_range.percentile_0_100(c)

        # Volatility compression: smaller intrabar range => higher compression.
        range_pct = _safe_div(h - l, c if c != 0 else 1.0, default=0.0)
        # 3% daily-ish bar range as baseline; adjust as we move to richer inputs.
        vol_comp = clamp(1.0 - range_pct / 0.03, 0.0, 1.0)

        pct_change = _safe_div(c - o, o if o != 0 else 1.0, default=0.0)
        # Flow proxies (placeholders): compress to [-1, 1] robustly.
        money_flow_heat = tanh_to_minus1_1(pct_change * math.log1p(max(v, 0.0)), scale=2.0)
        foreign_flow = clamp(pct_change * 10.0, -1.0, 1.0)

        variables: dict[str, Any] = {
            "market_valuation_percentile": float(valuation_pct),
            "volatility_compression": float(vol_comp),
            "money_flow_heat": float(money_flow_heat),
            "foreign_capital_flow": float(foreign_flow),
        }
        variables = self.normalizer.normalize_market(variables)

        quality = {
            "confidence": float(clamp(50.0 + min(50.0, self._close_range.count * 5.0), 0.0, 100.0))
        }

        out_payload = {
            "symbol": self.market_symbol,
            "ts": ts,
            "variables": variables,
            "quality": quality,
        }

        return EventEnvelope(
            event_id=new_event_id(),
            trace_id=ev.trace_id,
            produced_at=datetime.now(timezone.utc),
            schema=streams.VARIABLES_MARKET_COMPUTED_V1,
            schema_version=1,
            payload=out_payload,
            source_service="variables-service",
        )

