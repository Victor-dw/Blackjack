"""Multi-strategy coordinator.

The coordinator is responsible for selecting a single candidate action per
symbol/timestamp, avoiding conflicting BUY/SELL signals.

It follows the priority matrix described in docs/ARCHITECTURE.md (Section 8).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Optional

from src.strategies.base_strategy import CandidateAction


DEFAULT_PRIORITY_MATRIX: dict[str, list[str]] = {
    "BULL": ["trend_following", "event_driven", "value_investing"],
    "BEAR": ["value_investing", "mean_reversion"],
    "CONSOLIDATION": ["mean_reversion", "event_driven"],
    "TRANSITION": [],
}


class StrategyCoordinator:
    """Resolve multiple strategy candidates into a single action."""

    def __init__(
        self,
        *,
        priority_matrix: Optional[dict[str, list[str]]] = None,
        coordinator_name: str = "coordinator",
    ) -> None:
        self.priority_matrix = dict(priority_matrix or DEFAULT_PRIORITY_MATRIX)
        self.coordinator_name = coordinator_name

    def resolve(
        self,
        *,
        candidates: Iterable[CandidateAction],
        regime: str,
        symbol: Optional[str] = None,
        ts: Optional[str] = None,
    ) -> CandidateAction:
        """Resolve a final candidate.

        Returns a HOLD candidate (target_position_frac=0) when:
        - TRANSITION regime
        - no actionable candidates after filtering
        - conflicting BUY vs SELL signals
        """

        cand_list = list(candidates)
        sym = symbol or (cand_list[0].symbol if cand_list else "")
        t = ts or (cand_list[0].ts if cand_list else "")

        reg = str(regime).upper()
        if reg == "TRANSITION":
            return CandidateAction(
                symbol=sym,
                ts=t,
                action="HOLD",
                strategy=self.coordinator_name,
                target_position_frac=0.0,
                rationale=f"{self.coordinator_name}: TRANSITION regime freeze",
            )

        priority_order = self.priority_matrix.get(reg, [])
        if not priority_order:
            return CandidateAction(
                symbol=sym,
                ts=t,
                action="HOLD",
                strategy=self.coordinator_name,
                target_position_frac=0.0,
                rationale=f"{self.coordinator_name}: no priority order for regime {reg}",
            )

        # Filter to actionable candidates in the priority set.
        valid = [
            c
            for c in cand_list
            if c.strategy in priority_order and c.action in {"BUY", "SELL"}
        ]
        if not valid:
            return CandidateAction(
                symbol=sym,
                ts=t,
                action="HOLD",
                strategy=self.coordinator_name,
                target_position_frac=0.0,
                rationale=f"{self.coordinator_name}: no actionable candidates",
            )

        buys = [c for c in valid if c.action == "BUY"]
        sells = [c for c in valid if c.action == "SELL"]
        if buys and sells:
            return CandidateAction(
                symbol=sym,
                ts=t,
                action="HOLD",
                strategy=self.coordinator_name,
                target_position_frac=0.0,
                rationale=(
                    f"{self.coordinator_name}: conflict BUY vs SELL; "
                    f"buy={sorted({c.strategy for c in buys})} sell={sorted({c.strategy for c in sells})}"
                ),
            )

        same_dir = buys if buys else sells
        # Choose by priority order; additionally allow same-direction "support" by taking
        # the largest absolute suggested position among the same-direction candidates.
        max_abs = max(abs(c.target_position_frac) for c in same_dir)
        sign = 1.0 if same_dir[0].action == "BUY" else -1.0
        combined_frac = min(1.0, max_abs) * sign

        chosen: Optional[CandidateAction] = None
        for name in priority_order:
            for c in same_dir:
                if c.strategy == name:
                    chosen = c
                    break
            if chosen is not None:
                break

        if chosen is None:
            # Defensive fallback: pick the first.
            chosen = same_dir[0]

        supporters = [c.strategy for c in same_dir if c.strategy != chosen.strategy]
        rationale = chosen.rationale
        if supporters:
            rationale = f"{rationale} | supported_by={supporters}"

        return replace(chosen, target_position_frac=combined_frac, rationale=rationale)
