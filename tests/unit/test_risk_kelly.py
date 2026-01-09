from __future__ import annotations

import pytest

from src.risk.kelly import kelly_fraction


def test_kelly_fraction_basic_half_kelly() -> None:
    # p=0.6, b=1.0 => f*=(1*0.6-0.4)/1=0.2 ; half-kelly => 0.1
    assert kelly_fraction(0.6, 1.0, fraction=0.5) == pytest.approx(0.1)


def test_kelly_fraction_negative_ev_clipped_to_zero() -> None:
    # p=0.4, b=1.0 => f*=-0.2 => clipped to 0
    assert kelly_fraction(0.4, 1.0, fraction=1.0) == 0.0


@pytest.mark.parametrize(
    "win_prob,odds",
    [(-0.1, 1.0), (1.1, 1.0), (0.5, 0.0), (0.5, -1.0)],
)
def test_kelly_fraction_invalid_inputs_raise(win_prob: float, odds: float) -> None:
    with pytest.raises(ValueError):
        kelly_fraction(win_prob, odds)
