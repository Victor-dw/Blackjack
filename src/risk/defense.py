"""Defense weight computation.

This is the "go defensive" multiplier described in docs/ARCHITECTURE.md.
Weight is in (0, 1]. Smaller means more conservative sizing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DefenseInputs:
    policy_intervention_prob: float = 0.0
    rule_change_alert: bool = False
    confidence_level: float = 100.0
    consecutive_losses: int = 0
    # Optional external metric (e.g. from Monte Carlo). If provided and high,
    # we reduce risk aggressively.
    bankruptcy_prob: float | None = None
    regime_state: str = ""


@dataclass(frozen=True)
class DefenseConfig:
    # thresholds / multipliers align with docs/ARCHITECTURE.md defaults.
    policy_threshold: float = 0.5
    policy_multiplier: float = 0.5

    rule_change_multiplier: float = 0.3

    confidence_threshold: float = 60.0
    confidence_multiplier: float = 0.7

    consecutive_losses_threshold: int = 3
    consecutive_losses_multiplier: float = 0.5

    transition_regime_value: str = "TRANSITION"
    transition_multiplier: float = 0.3

    bankruptcy_threshold: float = 0.10
    bankruptcy_multiplier: float = 0.5

    # Hard freeze gate (used by allocator): weight below this means do not open.
    freeze_threshold: float = 0.3


DEFAULT_DEFENSE_CONFIG = DefenseConfig()


def calculate_defense_weight(
    inputs: DefenseInputs,
    *,
    config: DefenseConfig = DEFAULT_DEFENSE_CONFIG,
) -> float:
    """Compute defense weight in [0, 1].

    This function is deterministic and side-effect free.
    """

    w = 1.0

    if not (0.0 <= inputs.policy_intervention_prob <= 1.0):
        raise ValueError("policy_intervention_prob must be within [0, 1]")

    if inputs.policy_intervention_prob > config.policy_threshold:
        w *= config.policy_multiplier

    if inputs.rule_change_alert:
        w *= config.rule_change_multiplier

    if inputs.confidence_level < config.confidence_threshold:
        w *= config.confidence_multiplier

    if inputs.consecutive_losses > config.consecutive_losses_threshold:
        w *= config.consecutive_losses_multiplier

    if inputs.regime_state == config.transition_regime_value:
        w *= config.transition_multiplier

    if inputs.bankruptcy_prob is not None:
        if not (0.0 <= inputs.bankruptcy_prob <= 1.0):
            raise ValueError("bankruptcy_prob must be within [0, 1]")
        if inputs.bankruptcy_prob >= config.bankruptcy_threshold:
            w *= config.bankruptcy_multiplier

    # Clip into [0, 1]
    if w < 0:
        w = 0.0
    if w > 1:
        w = 1.0
    return w


def is_frozen_by_defense(weight: float, *, config: DefenseConfig = DEFAULT_DEFENSE_CONFIG) -> bool:
    return weight < config.freeze_threshold

