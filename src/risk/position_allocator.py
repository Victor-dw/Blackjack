"""L5 Risk: final position allocator / approver.

Consumes: strategy.candidate_action.generated.v1
Produces: risk.order.approved.v1 or risk.order.rejected.v1

Notes:
- v1 contracts are enforced by src/contracts/validation.py.
- The allocator must be deterministic for a given input + config.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from src.contracts.streams import RISK_ORDER_APPROVED_V1, RISK_ORDER_REJECTED_V1
from src.core.ids import new_event_id
from src.core.models import EventEnvelope

from .defense import DEFAULT_DEFENSE_CONFIG, DefenseInputs, calculate_defense_weight, is_frozen_by_defense


@dataclass(frozen=True)
class RiskLimits:
    max_single_position_frac: float = 0.10
    min_trade_position_frac: float = 0.01
    default_risk_per_trade: float = 0.01


DEFAULT_RISK_LIMITS = RiskLimits()


def _sign_from_action(action: str) -> int:
    if action == "BUY":
        return 1
    if action == "SELL":
        return -1
    return 0


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class PositionAllocator:
    def __init__(
        self,
        *,
        limits: RiskLimits = DEFAULT_RISK_LIMITS,
    ) -> None:
        self._limits = limits

    def allocate(
        self,
        *,
        symbol: str,
        ts: str,
        action: str,
        strategy: str,
        target_position_frac: float,
        rationale: str,
        defense_inputs: DefenseInputs | None = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """Return (schema, payload) for risk order approved/rejected."""

        defense_inputs = defense_inputs or DefenseInputs()
        defense_weight = calculate_defense_weight(defense_inputs)

        if action == "HOLD":
            return (
                RISK_ORDER_REJECTED_V1,
                {
                    "symbol": symbol,
                    "ts": ts,
                    "can_trade": False,
                    "final_position_frac": 0.0,
                    "risk_per_trade": 0.0,
                    "reason": "hold_no_order",
                    "order": {
                        "order_id": f"noop-{new_event_id()}",
                        "side": "HOLD",
                        "qty": 0,
                        "strategy": strategy,
                        "rationale": rationale,
                        "target_position_frac": target_position_frac,
                        "defense_weight": defense_weight,
                    },
                },
            )

        if action not in {"BUY", "SELL"}:
            return (
                RISK_ORDER_REJECTED_V1,
                {
                    "symbol": symbol,
                    "ts": ts,
                    "can_trade": False,
                    "final_position_frac": 0.0,
                    "risk_per_trade": 0.0,
                    "reason": "invalid_action",
                    "order": {
                        "order_id": f"noop-{new_event_id()}",
                        "side": action,
                        "qty": 0,
                        "strategy": strategy,
                        "rationale": rationale,
                        "target_position_frac": target_position_frac,
                        "defense_weight": defense_weight,
                    },
                },
            )

        # Defense freeze gate.
        if is_frozen_by_defense(defense_weight, config=DEFAULT_DEFENSE_CONFIG):
            return (
                RISK_ORDER_REJECTED_V1,
                {
                    "symbol": symbol,
                    "ts": ts,
                    "can_trade": False,
                    "final_position_frac": 0.0,
                    "risk_per_trade": 0.0,
                    "reason": "defense_freeze",
                    "order": {
                        "order_id": f"noop-{new_event_id()}",
                        "side": action,
                        "qty": 0,
                        "strategy": strategy,
                        "rationale": rationale,
                        "target_position_frac": target_position_frac,
                        "defense_weight": defense_weight,
                    },
                },
            )

        sign = _sign_from_action(action)
        desired = abs(float(target_position_frac)) * sign

        # Apply defense scaling and hard caps.
        final = desired * defense_weight
        if final > 0:
            final = min(final, self._limits.max_single_position_frac)
        if final < 0:
            final = max(final, -self._limits.max_single_position_frac)

        if abs(final) < self._limits.min_trade_position_frac:
            return (
                RISK_ORDER_REJECTED_V1,
                {
                    "symbol": symbol,
                    "ts": ts,
                    "can_trade": False,
                    "final_position_frac": 0.0,
                    "risk_per_trade": 0.0,
                    "reason": "below_min_position",
                    "order": {
                        "order_id": f"noop-{new_event_id()}",
                        "side": action,
                        "qty": 0,
                        "strategy": strategy,
                        "rationale": rationale,
                        "target_position_frac": target_position_frac,
                        "defense_weight": defense_weight,
                    },
                },
            )

        order_id = f"ord-{new_event_id()}"
        # Placeholder sizing: express qty in "units" so L6 can remain mechanical.
        qty = max(1, int(round(abs(final) * 100)))

        return (
            RISK_ORDER_APPROVED_V1,
            {
                "symbol": symbol,
                "ts": ts,
                "can_trade": True,
                "final_position_frac": float(final),
                "risk_per_trade": float(self._limits.default_risk_per_trade),
                "reason": "within_limits",
                "order": {
                    "order_id": order_id,
                    "side": action,
                    "qty": qty,
                    "symbol": symbol,
                    "strategy": strategy,
                    "rationale": rationale,
                    "target_position_frac": target_position_frac,
                    "final_position_frac": float(final),
                    "defense_weight": defense_weight,
                },
            },
        )

    def handle_candidate_action(self, ev: EventEnvelope) -> EventEnvelope:
        """Build and return the risk decision envelope for a candidate action."""

        p = ev.payload
        schema, payload = self.allocate(
            symbol=str(p["symbol"]),
            ts=str(p["ts"]),
            action=str(p["action"]),
            strategy=str(p["strategy"]),
            target_position_frac=float(p["target_position_frac"]),
            rationale=str(p["rationale"]),
        )
        return EventEnvelope(
            event_id=new_event_id(),
            trace_id=ev.trace_id,
            produced_at=_now_utc(),
            schema=schema,
            schema_version=1,
            payload=payload,
            source_service="risk-service",
        )

