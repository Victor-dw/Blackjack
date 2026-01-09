from __future__ import annotations


from src.signals.volume_price import (
    ACCUMULATION,
    MAIN_FORCE_DUMP,
    MAIN_FORCE_PUMP,
    WEAK_RISE,
    VolumePriceModel,
)


def test_volume_price_model_main_force_pump() -> None:
    m = VolumePriceModel(normalization_scale=2.0)
    r = m.compute(
        current_turnover_rate=0.02,
        avg_turnover_rate=0.01,
        current_pct_change=0.03,
        avg_abs_pct_change=0.01,
    )
    assert r.effort_ratio > 1.5
    assert r.result_ratio > 0.5
    assert r.interpretation == MAIN_FORCE_PUMP
    assert 0 <= r.score_0_100 <= 100
    assert r.score_0_100 > 90


def test_volume_price_model_main_force_dump() -> None:
    m = VolumePriceModel()
    r = m.compute(
        current_turnover_rate=0.02,
        avg_turnover_rate=0.01,
        current_pct_change=-0.02,
        avg_abs_pct_change=0.01,
    )
    assert r.interpretation == MAIN_FORCE_DUMP
    assert r.score_0_100 < 50


def test_volume_price_model_accumulation() -> None:
    m = VolumePriceModel()
    r = m.compute(
        current_turnover_rate=0.02,
        avg_turnover_rate=0.01,
        current_pct_change=0.001,
        avg_abs_pct_change=0.01,
    )
    assert r.interpretation == ACCUMULATION


def test_volume_price_model_weak_rise() -> None:
    m = VolumePriceModel()
    r = m.compute(
        current_turnover_rate=0.006,
        avg_turnover_rate=0.01,
        current_pct_change=0.01,
        avg_abs_pct_change=0.02,
    )
    assert r.interpretation == WEAK_RISE
