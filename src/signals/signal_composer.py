"""Opportunity signal composer.

Consumes variable events:
- variables.market.computed.v1
- variables.stock.computed.v1

Produces:
- signals.opportunity.scored.v1

Contract notes (v1 strict): output payload must be exactly:
{symbol, ts, opportunity_score, confidence, regime, components}
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from src.contracts import streams
from src.core.ids import new_event_id
from src.core.models import EventEnvelope

from .regime_detector import detect_regime


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    try:
        xf = float(x)
    except Exception:
        return lo
    if xf < lo:
        return lo
    if xf > hi:
        return hi
    return xf


def _num(m: Mapping[str, Any], k: str) -> float | None:
    v = m.get(k)
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _scale_minus1_1_to_0_100(x: float) -> float:
    return _clamp((float(x) + 1.0) * 50.0)


def _coerce_score_0_100(v: Any) -> float | None:
    """Best-effort coercion to [0, 100].

    L2 variables are expected to be normalized, but during early integration we
    keep the composer tolerant.
    """
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        if 0.0 <= x <= 100.0:
            return x
        # Common case: [-1, 1] normalized signals
        if -1.0 <= x <= 1.0:
            return _scale_minus1_1_to_0_100(x)
        # Otherwise treat as already a score but clamp.
        return _clamp(x)
    return None


@dataclass
class _MarketSnapshot:
    ts: str
    variables: dict[str, Any]
    quality: dict[str, Any]


class SignalComposer:
    """Stateful composer that keeps the latest market snapshot for scoring stocks."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest_market: _MarketSnapshot | None = None

    def update_market(self, ev: EventEnvelope) -> None:
        if ev.schema != streams.VARIABLES_MARKET_COMPUTED_V1:
            return
        variables = ev.payload.get("variables")
        quality = ev.payload.get("quality")
        if not isinstance(variables, dict) or not isinstance(quality, dict):
            return
        ts = str(ev.payload.get("ts", ""))
        with self._lock:
            self._latest_market = _MarketSnapshot(ts=ts, variables=dict(variables), quality=dict(quality))

    def compose_from_stock(self, ev: EventEnvelope) -> EventEnvelope | None:
        """Compose an opportunity signal from a stock variables event."""
        if ev.schema != streams.VARIABLES_STOCK_COMPUTED_V1:
            return None

        payload = ev.payload
        symbol = str(payload.get("symbol", ""))
        ts = str(payload.get("ts", ""))
        variables = payload.get("variables")
        quality = payload.get("quality")
        if not isinstance(variables, dict) or not isinstance(quality, dict):
            return None

        with self._lock:
            market = self._latest_market

        market_vars = market.variables if market else {}
        market_quality = market.quality if market else {}

        regime = self._compute_regime(stock_vars=variables, market_vars=market_vars)

        market_signal, market_components = self._compute_market_signal(market_vars)
        stock_signal, stock_components = self._compute_stock_signal(variables)
        timing_signal, timing_components = self._compute_timing_signal(market_vars)
        risk_signal, risk_components = self._compute_risk_signal(stock_vars=variables, market_vars=market_vars, regime=regime)

        # Weighted sum per docs/ARCHITECTURE.md.
        opportunity = (
            0.3 * market_signal
            + 0.4 * stock_signal
            + 0.2 * timing_signal
            - 0.1 * risk_signal
        )
        opportunity = _clamp(opportunity)

        confidence = self._compute_confidence(stock_quality=quality, market_quality=market_quality, used_components={
            "market": market_signal,
            "stock": stock_signal,
            "timing": timing_signal,
            "risk": risk_signal,
        })

        components = {
            "market": {"score": market_signal, **market_components},
            "stock": {"score": stock_signal, **stock_components},
            "timing": {"score": timing_signal, **timing_components},
            "risk": {"score": risk_signal, **risk_components},
        }

        out_payload = {
            "symbol": symbol,
            "ts": ts,
            "opportunity_score": float(opportunity),
            "confidence": float(confidence),
            "regime": str(regime),
            "components": components,
        }

        return EventEnvelope(
            event_id=new_event_id(),
            trace_id=ev.trace_id,
            produced_at=datetime.now(timezone.utc),
            schema=streams.SIGNALS_OPPORTUNITY_SCORED_V1,
            schema_version=1,
            payload=out_payload,
            source_service="signals-service",
        )

    def _compute_regime(self, *, stock_vars: Mapping[str, Any], market_vars: Mapping[str, Any]) -> str:
        # L2 may already emit regime_state as an environment variable.
        rs = stock_vars.get("regime_state")
        if isinstance(rs, str) and rs.strip():
            return rs.strip()
        rm = market_vars.get("regime_state")
        if isinstance(rm, str) and rm.strip():
            return rm.strip()
        return detect_regime(market_vars)

    def _compute_market_signal(self, market_vars: Mapping[str, Any]) -> tuple[float, dict[str, Any]]:
        val_pct = _num(market_vars, "market_valuation_percentile")
        money_heat = _num(market_vars, "money_flow_heat")
        foreign_flow = _num(market_vars, "foreign_capital_flow")

        parts: dict[str, Any] = {}

        # Convert known ranges to 0..100 scores.
        flow_score = None
        if money_heat is not None:
            parts["money_flow_heat"] = money_heat
            parts["money_flow_score"] = _scale_minus1_1_to_0_100(money_heat)
        if foreign_flow is not None:
            parts["foreign_capital_flow"] = foreign_flow
            parts["foreign_flow_score"] = _scale_minus1_1_to_0_100(foreign_flow)

        flow_scores = [parts[k] for k in ("money_flow_score", "foreign_flow_score") if k in parts]
        if flow_scores:
            flow_score = sum(flow_scores) / len(flow_scores)

        valuation_score = None
        if val_pct is not None:
            parts["market_valuation_percentile"] = val_pct
            # Prefer reasonable valuation (mid-range) for robustness.
            valuation_score = _clamp(100.0 - abs(val_pct - 50.0) * 2.0)
            parts["valuation_score"] = valuation_score

        scores = [s for s in (flow_score, valuation_score) if s is not None]
        if not scores:
            return 50.0, parts

        # Weighted preference: flows matter more than valuation in early MVP.
        if flow_score is not None and valuation_score is not None:
            return _clamp(0.7 * flow_score + 0.3 * valuation_score), parts
        return _clamp(sum(scores) / len(scores)), parts

    def _compute_stock_signal(self, stock_vars: Mapping[str, Any]) -> tuple[float, dict[str, Any]]:
        parts: dict[str, Any] = {}

        vp = _coerce_score_0_100(stock_vars.get("volume_price_signal"))
        rs = _coerce_score_0_100(stock_vars.get("relative_strength"))
        fs = _coerce_score_0_100(stock_vars.get("fundamental_score"))
        mfb = stock_vars.get("main_force_behavior")

        if vp is not None:
            parts["volume_price_signal"] = vp
        if rs is not None:
            parts["relative_strength"] = rs
        if fs is not None:
            parts["fundamental_score"] = fs
        if isinstance(mfb, str) and mfb.strip():
            parts["main_force_behavior"] = mfb.strip()

        base = 50.0
        w_sum = 0.0

        def add(score: float | None, w: float) -> None:
            nonlocal base, w_sum
            if score is None:
                return
            base += w * (float(score) - 50.0)
            w_sum += w

        add(vp, 0.50)
        add(rs, 0.30)
        add(fs, 0.20)

        # Small behavioral adjustment.
        if isinstance(mfb, str):
            if mfb in ("MAIN_FORCE_PUMP", "ACCUMULATION"):
                base += 5.0
            elif mfb in ("MAIN_FORCE_DUMP",):
                base -= 5.0

        return _clamp(base), parts

    def _compute_timing_signal(self, market_vars: Mapping[str, Any]) -> tuple[float, dict[str, Any]]:
        parts: dict[str, Any] = {}
        vol_comp = _num(market_vars, "volatility_compression")
        if vol_comp is None:
            return 50.0, parts
        parts["volatility_compression"] = vol_comp
        # High compression indicates an approaching move; this is timing, not direction.
        return _clamp(vol_comp * 100.0), parts

    def _compute_risk_signal(
        self,
        *,
        stock_vars: Mapping[str, Any],
        market_vars: Mapping[str, Any],
        regime: str,
    ) -> tuple[float, dict[str, Any]]:
        parts: dict[str, Any] = {"regime": regime}
        risk = 0.0

        pip = _num(stock_vars, "policy_intervention_prob")
        if pip is None:
            pip = _num(market_vars, "policy_intervention_prob")
        if pip is not None:
            parts["policy_intervention_prob"] = pip
            risk += _clamp(pip * 100.0)

        rca = stock_vars.get("rule_change_alert")
        if rca is None:
            rca = market_vars.get("rule_change_alert")
        if isinstance(rca, bool):
            parts["rule_change_alert"] = rca
            if rca:
                risk += 20.0

        vol_comp = _num(market_vars, "volatility_compression")
        if vol_comp is not None and vol_comp >= 0.90:
            parts["extreme_volatility_compression"] = True
            risk += 10.0

        if str(regime).upper() == "TRANSITION":
            risk += 40.0

        return _clamp(risk), parts

    def _compute_confidence(
        self,
        *,
        stock_quality: Mapping[str, Any],
        market_quality: Mapping[str, Any],
        used_components: Mapping[str, float],
    ) -> float:
        # Prefer an explicit upstream confidence if L2 provides it.
        qs = _coerce_score_0_100(stock_quality.get("confidence"))
        qm = _coerce_score_0_100(market_quality.get("confidence"))
        explicit = [q for q in (qs, qm) if q is not None]
        quality_conf = sum(explicit) / len(explicit) if explicit else 60.0

        # Components completeness: if everything is default 50, likely low information.
        informative = sum(1 for v in used_components.values() if abs(v - 50.0) >= 1.0)
        completeness = (informative / max(1, len(used_components))) * 100.0

        return _clamp(0.7 * quality_conf + 0.3 * completeness)

