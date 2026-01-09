from __future__ import annotations

import pytest

from src.risk.defense import (
    DEFAULT_DEFENSE_CONFIG,
    DefenseInputs,
    calculate_defense_weight,
    is_frozen_by_defense,
)


def test_defense_default_is_one() -> None:
    assert calculate_defense_weight(DefenseInputs()) == 1.0


def test_defense_policy_intervention_reduces_weight() -> None:
    w = calculate_defense_weight(DefenseInputs(policy_intervention_prob=0.6))
    assert w == pytest.approx(0.5)


def test_defense_rule_change_alert_reduces_weight() -> None:
    w = calculate_defense_weight(DefenseInputs(rule_change_alert=True))
    assert w == pytest.approx(0.3)


def test_defense_bankruptcy_probability_reduces_weight() -> None:
    w = calculate_defense_weight(DefenseInputs(bankruptcy_prob=0.5))
    assert w == pytest.approx(0.5)


def test_defense_freeze_threshold() -> None:
    # Multiply to < 0.3 => frozen
    w = calculate_defense_weight(DefenseInputs(rule_change_alert=True, regime_state="TRANSITION"))
    assert w < DEFAULT_DEFENSE_CONFIG.freeze_threshold
    assert is_frozen_by_defense(w) is True
