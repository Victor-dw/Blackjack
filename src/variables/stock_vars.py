"""Stock factor computation (L2 variables: stock).

Consumes:
- perception.market_data.collected.v1

Produces:
- variables.stock.computed.v1
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.contracts import streams
from src.core.ids import new_event_id
from src.core.models import EventEnvelope

from .normalizer import FactorNormalizer, clamp, tanh_to_0_100


MAIN_FORCE_PUMP = "MAIN_FORCE_PUMP"
MAIN_FORCE_DUMP = "MAIN_FORCE_DUMP"
ACCUMULATION = "ACCUMULATION"
WEAK_RISE = "WEAK_RISE"
WEAK_DROP = "WEAK_DROP"
NORMAL = "NORMAL"


def _safe_div(n: float, d: float, *, default: float) -> float:
    if not isinstance(n, (int, float)) or not isinstance(d, (int, float)):
        return default
    if d == 0:
        return default
    return float(n) / float(d)


@dataclass
class _Ema:
    alpha: float
    value: float | None = None
    count: int = 0

    def update(self, x: float) -> float:
        xf = float(x)
        self.count += 1
        if self.value is None:
            self.value = xf
        else:
            self.value = self.alpha * xf + (1.0 - self.alpha) * self.value
        return float(self.value)


def _interpret(*, effort_ratio: float, result_ratio: float) -> str:
    er = float(effort_ratio)
    rr = float(result_ratio)
    if er > 1.5:
        if rr > 0.5:
            return MAIN_FORCE_PUMP
        if rr < -0.5:
            return MAIN_FORCE_DUMP
        if abs(rr) < 0.3:
            return ACCUMULATION
    if er < 0.7:
        if rr > 0:
            return WEAK_RISE
        return WEAK_DROP
    return NORMAL


class StockVarsCalculator:
    """Stateful stock variables calculator (per symbol)."""

    def __init__(self, *, normalizer: FactorNormalizer | None = None):
        self.normalizer = normalizer or FactorNormalizer()
        self._avg_volume: dict[str, _Ema] = {}
        self._avg_abs_change: dict[str, _Ema] = {}

    def _ema(self, d: dict[str, _Ema], symbol: str, *, alpha: float) -> _Ema:
        if symbol not in d:
            d[symbol] = _Ema(alpha=alpha)
        return d[symbol]

    def compute(self, ev: EventEnvelope) -> EventEnvelope:
        if ev.schema != streams.PERCEPTION_MARKET_DATA_COLLECTED_V1:
            raise ValueError(f"StockVarsCalculator expects {streams.PERCEPTION_MARKET_DATA_COLLECTED_V1}, got {ev.schema}")

        p = ev.payload
        symbol = str(p.get("symbol", ""))
        ts = str(p.get("ts", ""))
        o = float(p.get("open", 0.0))
        c = float(p.get("close", 0.0))
        v = float(p.get("volume", 0.0))

        pct_change = _safe_div(c - o, o if o != 0 else 1.0, default=0.0)

        avg_v = self._ema(self._avg_volume, symbol, alpha=0.05).update(max(v, 0.0))
        avg_abs = self._ema(self._avg_abs_change, symbol, alpha=0.05).update(abs(pct_change))

        effort = _safe_div(max(v, 0.0), avg_v if avg_v > 0 else 1.0, default=1.0)
        result = _safe_div(pct_change, avg_abs if avg_abs > 0 else 1.0, default=0.0)
        raw = effort * result

        volume_price_signal = tanh_to_0_100(raw, scale=2.0)
        main_force_behavior = _interpret(effort_ratio=effort, result_ratio=result)

        # Simple momentum proxy as "relative strength".
        relative_strength = tanh_to_0_100(pct_change, scale=0.02)

        fundamental_score = 50.0

        policy_intervention_prob = clamp(abs(pct_change) * 10.0, 0.0, 1.0)
        rule_change_alert = False

        variables: dict[str, Any] = {
            "volume_price_signal": float(volume_price_signal),
            "relative_strength": float(relative_strength),
            "fundamental_score": float(fundamental_score),
            "main_force_behavior": str(main_force_behavior),
            "policy_intervention_prob": float(policy_intervention_prob),
            "rule_change_alert": bool(rule_change_alert),
        }
        variables = self.normalizer.normalize_stock(variables)

        samples = self._avg_volume[symbol].count
        conf = 60.0 if samples < 5 else 75.0 if samples < 20 else 85.0
        quality = {"confidence": float(conf), "samples": int(samples)}

        out_payload = {
            "symbol": symbol,
            "ts": ts,
            "variables": variables,
            "quality": quality,
        }

        return EventEnvelope(
            event_id=new_event_id(),
            trace_id=ev.trace_id,
            produced_at=datetime.now(timezone.utc),
            schema=streams.VARIABLES_STOCK_COMPUTED_V1,
            schema_version=1,
            payload=out_payload,
            source_service="variables-service",
        )

