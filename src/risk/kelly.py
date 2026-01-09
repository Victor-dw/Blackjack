"""Kelly position sizing.

This module is a pure function library used by the L5 risk layer.

Contract note:
- v1 message schemas do not currently carry win_prob/odds, but the Kelly
  calculator is still implemented as a reusable primitive for future v2.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KellyBreakdown:
    """Detailed Kelly computation for audit/debug."""

    win_prob: float
    odds: float
    q: float
    f_star: float
    fraction_used: float
    f_used: float


def kelly_fraction(
    win_prob: float,
    odds: float,
    *,
    fraction: float = 0.5,
    min_frac: float = 0.0,
    max_frac: float = 1.0,
) -> float:
    """Return the (conservative) Kelly position fraction.

    Formula (Jeff Ma style):
        f* = (b*p - q) / b
    where:
        p = win probability
        q = 1 - p
        b = odds (profit/loss ratio)

    The returned value is clipped into [min_frac, max_frac].
    """

    if not (0.0 <= win_prob <= 1.0):
        raise ValueError("win_prob must be within [0, 1]")
    if odds <= 0:
        raise ValueError("odds must be > 0")
    if fraction < 0:
        raise ValueError("fraction must be >= 0")
    if min_frac > max_frac:
        raise ValueError("min_frac must be <= max_frac")

    p = float(win_prob)
    q = 1.0 - p
    b = float(odds)
    f_star = (b * p - q) / b
    f_used = f_star * float(fraction)

    # Kelly can be negative when EV <= 0. In practice we do not short by default
    # in this system layer, so clip at 0.
    f_used = max(0.0, f_used)
    f_used = min(max_frac, max(min_frac, f_used))
    return f_used


def kelly_breakdown(
    win_prob: float,
    odds: float,
    *,
    fraction: float = 0.5,
    min_frac: float = 0.0,
    max_frac: float = 1.0,
) -> KellyBreakdown:
    """Return a detailed, auditable Kelly calculation."""

    if not (0.0 <= win_prob <= 1.0):
        raise ValueError("win_prob must be within [0, 1]")
    if odds <= 0:
        raise ValueError("odds must be > 0")

    p = float(win_prob)
    q = 1.0 - p
    b = float(odds)
    f_star = (b * p - q) / b
    f_used = kelly_fraction(win_prob, odds, fraction=fraction, min_frac=min_frac, max_frac=max_frac)
    return KellyBreakdown(
        win_prob=p,
        odds=b,
        q=q,
        f_star=f_star,
        fraction_used=float(fraction),
        f_used=f_used,
    )

