from __future__ import annotations

# v1 stream names (frozen semantics for v1).

PERCEPTION_HEARTBEAT_V1 = "perception.heartbeat.v1"
PERCEPTION_MARKET_DATA_COLLECTED_V1 = "perception.market_data.collected.v1"

VARIABLES_MARKET_COMPUTED_V1 = "variables.market.computed.v1"
VARIABLES_STOCK_COMPUTED_V1 = "variables.stock.computed.v1"

SIGNALS_REGIME_DETECTED_V1 = "signals.regime.detected.v1"
SIGNALS_OPPORTUNITY_SCORED_V1 = "signals.opportunity.scored.v1"

STRATEGY_CANDIDATE_ACTION_GENERATED_V1 = "strategy.candidate_action.generated.v1"

RISK_ORDER_APPROVED_V1 = "risk.order.approved.v1"
RISK_ORDER_REJECTED_V1 = "risk.order.rejected.v1"

EXECUTION_ORDER_EXECUTED_V1 = "execution.order.executed.v1"
EXECUTION_ORDER_FAILED_V1 = "execution.order.failed.v1"

POSTMORTEM_TRADE_RECORD_CREATED_V1 = "postmortem.trade_record.created.v1"

EVOLUTION_BACKTEST_COMPLETED_V1 = "evolution.backtest.completed.v1"
EVOLUTION_PARAMETER_PROPOSED_V1 = "evolution.parameter.proposed.v1"


def dlq_stream(base_stream: str) -> str:
    return f"dlq.{base_stream}.v1"
