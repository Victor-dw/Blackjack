"""Bankruptcy / risk-of-ruin helpers.

The v1 contracts do not carry enough portfolio context to enforce a full
risk-of-ruin policy end-to-end, but L5 risk needs the primitive so defense
weight can incorporate it when upstream supplies the metric.
"""

from __future__ import annotations


def approximate_risk_of_ruin(
    *,
    win_prob: float,
    payout_odds: float,
    stake_frac: float,
    max_consecutive_losses: int = 10,
) -> float:
    """Approximate probability of hitting a ruin threshold via loss streak.

    This is a conservative proxy: probability of observing at least one streak
    of `max_consecutive_losses` losses in an IID Bernoulli sequence.

    It is not a full portfolio ruin model, but works as a simple guard.
    """

    if not (0.0 <= win_prob <= 1.0):
        raise ValueError("win_prob must be within [0, 1]")
    if payout_odds <= 0:
        raise ValueError("payout_odds must be > 0")
    if stake_frac < 0:
        raise ValueError("stake_frac must be >= 0")
    if max_consecutive_losses <= 0:
        raise ValueError("max_consecutive_losses must be > 0")

    # With no stake, no ruin via bet sizing.
    if stake_frac == 0:
        return 0.0

    # Loss probability.
    q = 1.0 - float(win_prob)

    # Probability of N consecutive losses at any point in a long horizon is hard;
    # use an upper bound via geometric trials: P(streak) <= q^N / (1 - q^N).
    p_streak = q ** int(max_consecutive_losses)
    if p_streak >= 1.0:
        return 1.0
    approx = p_streak / max(1e-12, (1.0 - p_streak))
    return max(0.0, min(1.0, approx))


def max_loss_streak_survival_prob(*, loss_prob: float, n: int) -> float:
    """Probability of surviving a streak of n losses (i.e., not seeing n losses).

    Uses a simple complement bound; intended for quick defense heuristics.
    """

    if not (0.0 <= loss_prob <= 1.0):
        raise ValueError("loss_prob must be within [0, 1]")
    if n <= 0:
        raise ValueError("n must be > 0")

    p_streak = float(loss_prob) ** int(n)
    return max(0.0, min(1.0, 1.0 - p_streak))

