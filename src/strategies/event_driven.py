"""Event-driven strategy.

MVP behavior (contract-safe):
- Only consider trading when opportunity_score >= threshold
- Require some "event" indication in opportunity.components
- Respect TRANSITION freeze (always HOLD)

This is intentionally conservative until upstream event signals are richer.
"""

from __future__ import annotations

from typing import Any

from src.strategies.base_strategy import BaseStrategy, CandidateAction, StrategyConfig


class EventDrivenStrategy(BaseStrategy):
    def __init__(self, *, config: StrategyConfig):
        super().__init__(config=config)

    def generate(self, *, opportunity: dict[str, Any], regime: dict[str, Any]) -> CandidateAction:
        symbol = str(opportunity.get("symbol"))
        ts = str(opportunity.get("ts"))
        score = float(opportunity.get("opportunity_score", 0.0))
        confidence = float(opportunity.get("confidence", 0.0))
        reg = str(regime.get("regime", opportunity.get("regime", ""))).upper()

        components = opportunity.get("components")
        if not isinstance(components, dict):
            components = {}

        if reg == "TRANSITION":
            return self.make_candidate(
                symbol=symbol,
                ts=ts,
                action="HOLD",
                target_position_frac=0.0,
                rationale=f"{self.name}: TRANSITION regime freeze",
            )

        if score < self.opportunity_threshold:
            return self.make_candidate(
                symbol=symbol,
                ts=ts,
                action="HOLD",
                target_position_frac=0.0,
                rationale=f"{self.name}: score {score:.1f} < threshold {self.opportunity_threshold:.1f}",
            )

        event_detected = bool(components.get("event_detected", False))
        # Best-effort numeric signals
        try:
            event_score = float(components.get("event_score", 0.0))
        except Exception:
            event_score = 0.0
        try:
            news_impact = float(components.get("news_impact", 0.0))
        except Exception:
            news_impact = 0.0

        if not (event_detected or event_score > 0.0 or news_impact > 0.0):
            return self.make_candidate(
                symbol=symbol,
                ts=ts,
                action="HOLD",
                target_position_frac=0.0,
                rationale=f"{self.name}: no event condition in components",
            )

        direction = str(components.get("event_direction", "BUY")).upper()
        if direction not in {"BUY", "SELL"}:
            direction = "BUY"

        size = self.size_from_score(opportunity_score=score, confidence=confidence)
        frac = +size if direction == "BUY" else -size
        return self.make_candidate(
            symbol=symbol,
            ts=ts,
            action=direction,
            target_position_frac=frac,
            rationale=f"{self.name}: event {direction} score {score:.1f}, conf {confidence:.1f}, regime {reg}",
        )
