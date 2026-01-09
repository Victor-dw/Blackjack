"""Trend following strategy.

High-level behavior:
- In BULL regime: prefer BUY above threshold.
- In BEAR regime: prefer SELL above threshold.
- In CONSOLIDATION: HOLD (trend not reliable).
- In TRANSITION: HOLD (freeze).
"""

from __future__ import annotations

from typing import Any

from src.strategies.base_strategy import BaseStrategy, CandidateAction, StrategyConfig


class TrendFollowingStrategy(BaseStrategy):
    def __init__(self, *, config: StrategyConfig):
        super().__init__(config=config)

    def generate(self, *, opportunity: dict[str, Any], regime: dict[str, Any]) -> CandidateAction:
        symbol = str(opportunity.get("symbol"))
        ts = str(opportunity.get("ts"))
        score = float(opportunity.get("opportunity_score", 0.0))
        confidence = float(opportunity.get("confidence", 0.0))
        reg = str(regime.get("regime", opportunity.get("regime", ""))).upper()

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

        size = self.size_from_score(opportunity_score=score, confidence=confidence)
        if reg == "BULL":
            return self.make_candidate(
                symbol=symbol,
                ts=ts,
                action="BUY",
                target_position_frac=+size,
                rationale=f"{self.name}: BULL + high score {score:.1f}, conf {confidence:.1f}",
            )
        if reg == "BEAR":
            return self.make_candidate(
                symbol=symbol,
                ts=ts,
                action="SELL",
                target_position_frac=-size,
                rationale=f"{self.name}: BEAR + high score {score:.1f}, conf {confidence:.1f}",
            )

        # CONSOLIDATION/unknown -> no trend bet
        return self.make_candidate(
            symbol=symbol,
            ts=ts,
            action="HOLD",
            target_position_frac=0.0,
            rationale=f"{self.name}: regime {reg} not suitable for trend-following",
        )
