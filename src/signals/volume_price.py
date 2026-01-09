"""Volume-price signal model (effort × result).

This module is intentionally dependency-free (no pandas/numpy) so it can run
inside the streaming services and be unit-tested easily.

Core idea (see docs/ARCHITECTURE.md):

- effort  := current_turnover_rate / historical_avg_turnover_rate
- result  := current_pct_change / historical_avg_abs_pct_change
- raw     := effort * result

We additionally provide a stable normalization to [0, 100] for downstream
opportunity scoring.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


MAIN_FORCE_PUMP = "MAIN_FORCE_PUMP"
MAIN_FORCE_DUMP = "MAIN_FORCE_DUMP"
ACCUMULATION = "ACCUMULATION"
WEAK_RISE = "WEAK_RISE"
WEAK_DROP = "WEAK_DROP"
NORMAL = "NORMAL"


@dataclass(frozen=True)
class VolumePriceFeatures:
    """Computed effort-vs-result features for a single bar/window."""

    current_turnover_rate: float
    avg_turnover_rate: float
    effort_ratio: float

    current_pct_change: float
    avg_abs_pct_change: float
    result_ratio: float

    raw_signal: float
    score_0_100: float
    interpretation: str


def _safe_div(n: float, d: float, *, default: float) -> float:
    if not isinstance(n, (int, float)) or not isinstance(d, (int, float)):
        return default
    if d == 0:
        return default
    return float(n) / float(d)


def effort_ratio(current_turnover_rate: float, avg_turnover_rate: float) -> float:
    """Effort ratio; returns 1.0 if average is not usable."""
    if avg_turnover_rate <= 0:
        return 1.0
    return _safe_div(current_turnover_rate, avg_turnover_rate, default=1.0)


def result_ratio(current_pct_change: float, avg_abs_pct_change: float) -> float:
    """Result ratio; returns 0.0 if average is not usable."""
    if avg_abs_pct_change <= 0:
        return 0.0
    return _safe_div(current_pct_change, avg_abs_pct_change, default=0.0)


def normalize_raw_to_0_100(raw_signal: float, *, scale: float = 2.0) -> float:
    """Map an unbounded raw signal to [0, 100] in a smooth, stable way.

    We use tanh for robustness against outliers.
    - raw=0 -> 50
    - raw>>0 -> 100
    - raw<<0 -> 0
    """
    if not isinstance(raw_signal, (int, float)):
        return 50.0
    if scale <= 0:
        scale = 1.0
    x = float(raw_signal) / float(scale)
    y = math.tanh(x)
    score = (y + 1.0) * 50.0
    return max(0.0, min(100.0, score))


def interpret_effort_vs_result(*, effort_ratio_value: float, result_ratio_value: float) -> str:
    """Interpret the effort-vs-result relationship into a coarse behavior label."""
    er = float(effort_ratio_value)
    rr = float(result_ratio_value)

    # Thresholds are heuristic and intentionally conservative.
    if er > 1.5:  # 放量
        if rr > 0.5:
            return MAIN_FORCE_PUMP
        if rr < -0.5:
            return MAIN_FORCE_DUMP
        if abs(rr) < 0.3:
            return ACCUMULATION

    if er < 0.7:  # 缩量
        if rr > 0:
            return WEAK_RISE
        return WEAK_DROP

    return NORMAL


class VolumePriceModel:
    """Core volume-price (effort×result) signal model."""

    def __init__(self, *, normalization_scale: float = 2.0):
        self.normalization_scale = normalization_scale

    def compute(
        self,
        *,
        current_turnover_rate: float,
        avg_turnover_rate: float,
        current_pct_change: float,
        avg_abs_pct_change: float,
    ) -> VolumePriceFeatures:
        er = effort_ratio(current_turnover_rate, avg_turnover_rate)
        rr = result_ratio(current_pct_change, avg_abs_pct_change)
        raw = er * rr
        score = normalize_raw_to_0_100(raw, scale=self.normalization_scale)
        interp = interpret_effort_vs_result(effort_ratio_value=er, result_ratio_value=rr)
        return VolumePriceFeatures(
            current_turnover_rate=float(current_turnover_rate),
            avg_turnover_rate=float(avg_turnover_rate),
            effort_ratio=float(er),
            current_pct_change=float(current_pct_change),
            avg_abs_pct_change=float(avg_abs_pct_change),
            result_ratio=float(rr),
            raw_signal=float(raw),
            score_0_100=float(score),
            interpretation=str(interp),
        )

