"""Mean reversion strategy.

This strategy is most active in CONSOLIDATION, and conservative elsewhere.
If the upstream opportunity components contain mean-reversion hints, we use
them to determine BUY/SELL direction.
"""

from __future__ import annotations

from typing import Any

from src.strategies.base_strategy import BaseStrategy, CandidateAction, StrategyConfig


class MeanReversionStrategy(BaseStrategy):
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

        if reg != "CONSOLIDATION":
            return self.make_candidate(
                symbol=symbol,
                ts=ts,
                action="HOLD",
                target_position_frac=0.0,
                rationale=f"{self.name}: regime {reg} not suitable for mean reversion",
            )

        if score < self.opportunity_threshold:
            return self.make_candidate(
                symbol=symbol,
                ts=ts,
                action="HOLD",
                target_position_frac=0.0,
                rationale=f"{self.name}: score {score:.1f} < threshold {self.opportunity_threshold:.1f}",
            )

        # Determine direction
        direction = str(components.get("mean_reversion_direction", components.get("mr_direction", ""))).upper()
        if direction not in {"BUY", "SELL"}:
            # Numeric signal convention: negative -> BUY (oversold), positive -> SELL (overbought)
            mr_signal = components.get("mean_reversion_signal", components.get("mr_signal"))
            try:
                if mr_signal is not None:
                    s = float(mr_signal)
                    if s < 0:
                        direction = "BUY"
                    elif s > 0:
                        direction = "SELL"
            except Exception:
                direction = ""

        if direction not in {"BUY", "SELL"}:
            oversold = bool(components.get("oversold", False))
            overbought = bool(components.get("overbought", False))
            if oversold and not overbought:
                direction = "BUY"
            elif overbought and not oversold:
                direction = "SELL"

        if direction not in {"BUY", "SELL"}:
            return self.make_candidate(
                symbol=symbol,
                ts=ts,
                action="HOLD",
                target_position_frac=0.0,
                rationale=f"{self.name}: no MR direction info in components",
            )

        size = self.size_from_score(opportunity_score=score, confidence=confidence)
        frac = +size if direction == "BUY" else -size
        return self.make_candidate(
            symbol=symbol,
            ts=ts,
            action=direction,
            target_position_frac=frac,
            rationale=f"{self.name}: CONSOLIDATION MR {direction} score {score:.1f}, conf {confidence:.1f}",
        )
