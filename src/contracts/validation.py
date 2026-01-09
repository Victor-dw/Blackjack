from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from . import streams


ENVELOPE_REQUIRED_KEYS = {
    "event_id",
    "trace_id",
    "produced_at",
    "schema",
    "schema_version",
    "payload",
}
ENVELOPE_OPTIONAL_KEYS = {"source_service"}


def _require_exact_keys(obj: dict[str, Any], *, required: set[str], optional: set[str] | None = None) -> None:
    optional = optional or set()
    keys = set(obj.keys())
    missing = required - keys
    extra = keys - required - optional
    if missing:
        raise ValueError(f"missing keys: {sorted(missing)}")
    if extra:
        raise ValueError(f"extra keys not allowed in v1: {sorted(extra)}")


def _require_str(d: dict[str, Any], k: str) -> str:
    v = d.get(k)
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{k} must be non-empty string")
    return v


def _require_int(d: dict[str, Any], k: str) -> int:
    v = d.get(k)
    if not isinstance(v, int):
        raise ValueError(f"{k} must be int")
    return v


def _require_number(d: dict[str, Any], k: str) -> float:
    v = d.get(k)
    if not isinstance(v, (int, float)):
        raise ValueError(f"{k} must be number")
    return float(v)


def _parse_iso8601(s: str) -> datetime:
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception as e:  # pragma: no cover
        raise ValueError(f"invalid ISO8601 timestamp: {s}") from e
    if dt.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return dt


def validate_envelope_dict(event: dict[str, Any]) -> None:
    """Strict v1 validation.

    - v1 does not allow extra fields (schema evolution uses v2 streams)
    - payload must match schema-specific rules
    """

    _require_exact_keys(event, required=ENVELOPE_REQUIRED_KEYS, optional=ENVELOPE_OPTIONAL_KEYS)
    _require_str(event, "event_id")
    _require_str(event, "trace_id")
    produced_at = _require_str(event, "produced_at")
    _parse_iso8601(produced_at)

    schema = _require_str(event, "schema")
    schema_version = _require_int(event, "schema_version")
    if schema_version != 1 or not schema.endswith(".v1"):
        raise ValueError("schema_version must be 1 and schema must end with .v1")

    payload = event.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("payload must be object")
    validate_payload(schema, payload)


def validate_payload(schema: str, payload: dict[str, Any]) -> None:
    if schema == streams.PERCEPTION_HEARTBEAT_V1:
        _require_exact_keys(payload, required={"status"})
        _require_str(payload, "status")
        return

    if schema == streams.PERCEPTION_MARKET_DATA_COLLECTED_V1:
        _require_exact_keys(
            payload,
            required={"symbol", "ts", "timeframe", "open", "high", "low", "close", "volume", "source"},
        )
        _require_str(payload, "symbol")
        _parse_iso8601(_require_str(payload, "ts"))
        _require_str(payload, "timeframe")
        for k in ["open", "high", "low", "close"]:
            if _require_number(payload, k) <= 0:
                raise ValueError(f"{k} must be > 0")
        if _require_number(payload, "volume") < 0:
            raise ValueError("volume must be >= 0")
        _require_str(payload, "source")
        return

    if schema in (streams.VARIABLES_MARKET_COMPUTED_V1, streams.VARIABLES_STOCK_COMPUTED_V1):
        _require_exact_keys(payload, required={"symbol", "ts", "variables", "quality"})
        _require_str(payload, "symbol")
        _parse_iso8601(_require_str(payload, "ts"))
        if not isinstance(payload.get("variables"), dict):
            raise ValueError("variables must be object")
        if not isinstance(payload.get("quality"), dict):
            raise ValueError("quality must be object")
        return

    if schema == streams.SIGNALS_REGIME_DETECTED_V1:
        _require_exact_keys(payload, required={"symbol", "ts", "regime"})
        _require_str(payload, "symbol")
        _parse_iso8601(_require_str(payload, "ts"))
        _require_str(payload, "regime")
        return

    if schema == streams.SIGNALS_OPPORTUNITY_SCORED_V1:
        _require_exact_keys(payload, required={"symbol", "ts", "opportunity_score", "confidence", "regime", "components"})
        _require_str(payload, "symbol")
        _parse_iso8601(_require_str(payload, "ts"))
        score = _require_number(payload, "opportunity_score")
        conf = _require_number(payload, "confidence")
        if not (0 <= score <= 100):
            raise ValueError("opportunity_score must be 0..100")
        if not (0 <= conf <= 100):
            raise ValueError("confidence must be 0..100")
        _require_str(payload, "regime")
        if not isinstance(payload.get("components"), dict):
            raise ValueError("components must be object")
        return

    if schema == streams.STRATEGY_CANDIDATE_ACTION_GENERATED_V1:
        _require_exact_keys(payload, required={"symbol", "ts", "action", "strategy", "target_position_frac", "rationale"})
        _require_str(payload, "symbol")
        _parse_iso8601(_require_str(payload, "ts"))
        action = _require_str(payload, "action")
        if action not in {"BUY", "SELL", "HOLD"}:
            raise ValueError("action must be BUY/SELL/HOLD")
        _require_str(payload, "strategy")
        frac = _require_number(payload, "target_position_frac")
        if not (-1.0 <= frac <= 1.0):
            raise ValueError("target_position_frac must be -1..1")
        _require_str(payload, "rationale")
        return

    if schema in (streams.RISK_ORDER_APPROVED_V1, streams.RISK_ORDER_REJECTED_V1):
        _require_exact_keys(
            payload,
            required={
                "symbol",
                "ts",
                "can_trade",
                "final_position_frac",
                "risk_per_trade",
                "reason",
                "order",
            },
        )
        _require_str(payload, "symbol")
        _parse_iso8601(_require_str(payload, "ts"))
        if not isinstance(payload.get("can_trade"), bool):
            raise ValueError("can_trade must be bool")
        pos = _require_number(payload, "final_position_frac")
        if not (-1.0 <= pos <= 1.0):
            raise ValueError("final_position_frac must be -1..1")
        rpt = _require_number(payload, "risk_per_trade")
        if rpt < 0:
            raise ValueError("risk_per_trade must be >= 0")
        _require_str(payload, "reason")
        if not isinstance(payload.get("order"), dict):
            raise ValueError("order must be object")
        return

    if schema in (streams.EXECUTION_ORDER_EXECUTED_V1, streams.EXECUTION_ORDER_FAILED_V1):
        _require_exact_keys(payload, required={"order_id", "symbol", "ts", "status", "filled_qty", "avg_price", "broker"})
        _require_str(payload, "order_id")
        _require_str(payload, "symbol")
        _parse_iso8601(_require_str(payload, "ts"))
        _require_str(payload, "status")
        if _require_number(payload, "filled_qty") < 0:
            raise ValueError("filled_qty must be >= 0")
        if _require_number(payload, "avg_price") < 0:
            raise ValueError("avg_price must be >= 0")
        _require_str(payload, "broker")
        return

    if schema == streams.POSTMORTEM_TRADE_RECORD_CREATED_V1:
        _require_exact_keys(
            payload,
            required={"trade_id", "symbol", "ts", "status", "order", "decision_snapshot"},
        )
        _require_str(payload, "trade_id")
        _require_str(payload, "symbol")
        _parse_iso8601(_require_str(payload, "ts"))
        status = _require_str(payload, "status")
        if status not in {"EXECUTED", "FAILED", "PARTIAL"}:
            raise ValueError("status must be EXECUTED/FAILED/PARTIAL")
        if not isinstance(payload.get("order"), dict):
            raise ValueError("order must be object")
        if not isinstance(payload.get("decision_snapshot"), dict):
            raise ValueError("decision_snapshot must be object")
        return

    if schema == streams.EVOLUTION_BACKTEST_COMPLETED_V1:
        _require_exact_keys(
            payload,
            required={"backtest_id", "strategy", "start_date", "end_date", "metrics", "parameters"},
        )
        _require_str(payload, "backtest_id")
        _require_str(payload, "strategy")
        _require_str(payload, "start_date")
        _require_str(payload, "end_date")
        if not isinstance(payload.get("metrics"), dict):
            raise ValueError("metrics must be object")
        if not isinstance(payload.get("parameters"), dict):
            raise ValueError("parameters must be object")
        return

    if schema == streams.EVOLUTION_PARAMETER_PROPOSED_V1:
        _require_exact_keys(
            payload,
            required={"proposal_id", "strategy", "current_parameters", "proposed_parameters", "rationale"},
        )
        _require_str(payload, "proposal_id")
        _require_str(payload, "strategy")
        if not isinstance(payload.get("current_parameters"), dict):
            raise ValueError("current_parameters must be object")
        if not isinstance(payload.get("proposed_parameters"), dict):
            raise ValueError("proposed_parameters must be object")
        _require_str(payload, "rationale")
        return

    # For new schemas: add v2 stream, then update this mapping.
    raise ValueError(f"unknown schema: {schema}")


def validate_many(events: Iterable[dict[str, Any]]) -> None:
    for ev in events:
        validate_envelope_dict(ev)
