from __future__ import annotations


from dataclasses import asdict
from datetime import datetime, timezone

from src.contracts import streams
from src.contracts.validation import validate_envelope_dict
from src.core.models import EventEnvelope
from src.strategies.base_strategy import CandidateAction, StrategyConfig
from src.strategies.coordinator import StrategyCoordinator
from src.strategies.event_driven import EventDrivenStrategy
from src.strategies.mean_reversion import MeanReversionStrategy
from src.strategies.trend_following import TrendFollowingStrategy


def _wire(ev: EventEnvelope) -> dict:
    d = asdict(ev)
    d["produced_at"] = ev.produced_at.isoformat()
    return d


def test_candidate_action_envelope_is_contract_valid() -> None:
    c = CandidateAction(
        symbol="AAPL",
        ts="2026-01-01T00:00:00+00:00",
        action="BUY",
        strategy="trend_following",
        target_position_frac=0.5,
        rationale="unit-test",
    )
    env = c.to_envelope(trace_id="trace-1", produced_at=datetime.now(timezone.utc), event_id="evt-1")
    validate_envelope_dict(_wire(env))
    assert env.schema == streams.STRATEGY_CANDIDATE_ACTION_GENERATED_V1


def test_strategy_config_load_supports_nested_params(tmp_path) -> None:
    p = tmp_path / "s.yaml"
    p.write_text(
        """
        # comment
        name: trend_following
        enabled: true
        params:
          opportunity_threshold: 60
          max_positions: 10
        """.strip(),
        encoding="utf-8",
    )

    cfg = StrategyConfig.load(p)
    assert cfg.name == "trend_following"
    assert cfg.enabled is True
    assert cfg.params["opportunity_threshold"] == 60
    assert cfg.params["max_positions"] == 10


def test_trend_following_generate_buy_in_bull() -> None:
    s = TrendFollowingStrategy(
        config=StrategyConfig(name="trend_following", enabled=True, params={"opportunity_threshold": 60})
    )
    out = s.generate(
        opportunity={
            "symbol": "AAPL",
            "ts": "2026-01-01T00:00:00+00:00",
            "opportunity_score": 80,
            "confidence": 70,
            "regime": "BULL",
            "components": {},
        },
        regime={"symbol": "AAPL", "ts": "2026-01-01T00:00:00+00:00", "regime": "BULL"},
    )
    assert out.action == "BUY"
    assert out.target_position_frac > 0


def test_mean_reversion_generate_sell_in_consolidation_overbought() -> None:
    s = MeanReversionStrategy(
        config=StrategyConfig(name="mean_reversion", enabled=True, params={"opportunity_threshold": 70})
    )
    out = s.generate(
        opportunity={
            "symbol": "AAPL",
            "ts": "2026-01-01T00:00:00+00:00",
            "opportunity_score": 90,
            "confidence": 80,
            "regime": "CONSOLIDATION",
            "components": {"overbought": True},
        },
        regime={"symbol": "AAPL", "ts": "2026-01-01T00:00:00+00:00", "regime": "CONSOLIDATION"},
    )
    assert out.action == "SELL"
    assert out.target_position_frac < 0


def test_event_driven_hold_without_event_condition() -> None:
    s = EventDrivenStrategy(
        config=StrategyConfig(name="event_driven", enabled=True, params={"opportunity_threshold": 75})
    )
    out = s.generate(
        opportunity={
            "symbol": "AAPL",
            "ts": "2026-01-01T00:00:00+00:00",
            "opportunity_score": 90,
            "confidence": 80,
            "regime": "BULL",
            "components": {},
        },
        regime={"symbol": "AAPL", "ts": "2026-01-01T00:00:00+00:00", "regime": "BULL"},
    )
    assert out.action == "HOLD"
    assert out.target_position_frac == 0.0


def test_base_strategy_on_signal_dedupes_by_symbol_ts() -> None:
    s = TrendFollowingStrategy(
        config=StrategyConfig(name="trend_following", enabled=True, params={"opportunity_threshold": 60})
    )
    opp = EventEnvelope(
        event_id="evt-opp-1",
        trace_id="trace-1",
        produced_at=datetime.now(timezone.utc),
        schema=streams.SIGNALS_OPPORTUNITY_SCORED_V1,
        schema_version=1,
        payload={
            "symbol": "AAPL",
            "ts": "2026-01-01T00:00:00+00:00",
            "opportunity_score": 80,
            "confidence": 70,
            "regime": "BULL",
            "components": {},
        },
        source_service="signals",
    )

    out1 = s.on_signal(opp)
    assert out1 is not None
    out2 = s.on_signal(opp)
    assert out2 is None


def test_coordinator_conflict_returns_hold() -> None:
    coord = StrategyCoordinator()
    out = coord.resolve(
        candidates=[
            CandidateAction(
                symbol="AAPL",
                ts="2026-01-01T00:00:00+00:00",
                action="BUY",
                strategy="trend_following",
                target_position_frac=0.3,
                rationale="tf",
            ),
            CandidateAction(
                symbol="AAPL",
                ts="2026-01-01T00:00:00+00:00",
                action="SELL",
                strategy="event_driven",
                target_position_frac=-0.4,
                rationale="ed",
            ),
        ],
        regime="BULL",
        symbol="AAPL",
        ts="2026-01-01T00:00:00+00:00",
    )
    assert out.action == "HOLD"
    assert out.target_position_frac == 0.0
    assert out.strategy == "coordinator"


def test_coordinator_picks_highest_priority_in_bull() -> None:
    coord = StrategyCoordinator()
    out = coord.resolve(
        candidates=[
            CandidateAction(
                symbol="AAPL",
                ts="2026-01-01T00:00:00+00:00",
                action="BUY",
                strategy="event_driven",
                target_position_frac=0.2,
                rationale="ed",
            ),
            CandidateAction(
                symbol="AAPL",
                ts="2026-01-01T00:00:00+00:00",
                action="BUY",
                strategy="trend_following",
                target_position_frac=0.4,
                rationale="tf",
            ),
        ],
        regime="BULL",
    )
    assert out.action == "BUY"
    assert out.strategy == "trend_following"
    assert out.target_position_frac == 0.4


def test_coordinator_transition_freeze_returns_hold_contract_valid() -> None:
    coord = StrategyCoordinator()
    c = coord.resolve(
        candidates=[],
        regime="TRANSITION",
        symbol="AAPL",
        ts="2026-01-01T00:00:00+00:00",
    )
    assert c.action == "HOLD"

    env = c.to_envelope(trace_id="trace-1", produced_at=datetime.now(timezone.utc), event_id="evt-ca-1")
    validate_envelope_dict(_wire(env))
