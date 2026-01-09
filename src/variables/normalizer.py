"""Factor normalization utilities.

L2 variables are consumed by L3 signals. We keep normalization dependency-free
and conservative:
- clamp to known ranges
- provide simple stable transforms (tanh/sigmoid) when needed

This file intentionally does *not* depend on pandas/numpy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping


def clamp(x: float, lo: float, hi: float) -> float:
    xf = float(x)
    if xf < lo:
        return lo
    if xf > hi:
        return hi
    return xf


def tanh_to_minus1_1(x: float, *, scale: float = 1.0) -> float:
    if not isinstance(x, (int, float)):
        return 0.0
    s = float(scale) if scale and scale > 0 else 1.0
    return float(math.tanh(float(x) / s))


def tanh_to_0_100(x: float, *, scale: float = 1.0) -> float:
    y = tanh_to_minus1_1(x, scale=scale)
    return clamp((y + 1.0) * 50.0, 0.0, 100.0)


@dataclass(frozen=True)
class FactorNormalizer:
    """Simple range enforcement for known variable keys.

    The contracts do not constrain inner `variables`/`quality` keys, but
    downstream heuristics expect some ranges to be consistent.
    """

    def normalize_market(self, variables: Mapping[str, Any]) -> dict[str, Any]:
        out = dict(variables)
        if "market_valuation_percentile" in out and isinstance(out["market_valuation_percentile"], (int, float)):
            out["market_valuation_percentile"] = clamp(float(out["market_valuation_percentile"]), 0.0, 100.0)
        if "volatility_compression" in out and isinstance(out["volatility_compression"], (int, float)):
            out["volatility_compression"] = clamp(float(out["volatility_compression"]), 0.0, 1.0)
        for k in ("money_flow_heat", "foreign_capital_flow"):
            if k in out and isinstance(out[k], (int, float)):
                out[k] = clamp(float(out[k]), -1.0, 1.0)
        # Optional risk-related keys.
        if "policy_intervention_prob" in out and isinstance(out["policy_intervention_prob"], (int, float)):
            out["policy_intervention_prob"] = clamp(float(out["policy_intervention_prob"]), 0.0, 1.0)
        if "rule_change_alert" in out and not isinstance(out["rule_change_alert"], bool):
            out.pop("rule_change_alert", None)
        return out

    def normalize_stock(self, variables: Mapping[str, Any]) -> dict[str, Any]:
        out = dict(variables)
        for k in ("volume_price_signal", "relative_strength", "fundamental_score"):
            if k in out and isinstance(out[k], (int, float)):
                out[k] = clamp(float(out[k]), 0.0, 100.0)
        if "policy_intervention_prob" in out and isinstance(out["policy_intervention_prob"], (int, float)):
            out["policy_intervention_prob"] = clamp(float(out["policy_intervention_prob"]), 0.0, 1.0)
        if "rule_change_alert" in out and not isinstance(out["rule_change_alert"], bool):
            out.pop("rule_change_alert", None)
        if "main_force_behavior" in out and not isinstance(out["main_force_behavior"], str):
            out.pop("main_force_behavior", None)
        return out

