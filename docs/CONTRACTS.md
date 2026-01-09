## Message Contracts (v1)

This document is the **contract-first** interface between services.

### 0. Rules (read before coding)

1) **Schema v1 “freeze” ≠ “never change”**
- Freeze means: **field semantics of v1 are immutable**.
- If you need new fields / different meaning: **publish a new v2 stream**.
- Forbidden: silently adding fields to v1, changing meaning, or removing fields.

2) **Golden events must include dirty data**
Golden events are part of contracts (not optional). They must include:
- Missing fields (schema invalid)
- Timestamp out-of-order sequences
- Duplicate events (same `event_id`) to verify idempotency
- Extreme values: e.g. `price=0`, `volume < 0`

3) **Execution dry_run requires physical isolation**
- Not just `if dry_run: return`.
- Must be **different compose profile** and/or **different network plane**.
- Before QMT/broker integration, Execution must not be able to reach broker network.

---

### 1) Envelope (all streams)

All events are JSON objects stored in Redis Streams field `event`.

Required fields:
- `event_id`: string (unique idempotency key)
- `trace_id`: string
- `produced_at`: ISO8601 with timezone
- `schema`: string, e.g. `risk.order.approved.v1`
- `schema_version`: int (v1 = 1)
- `payload`: object

Optional fields:
- `source_service`: string

**v1 strictness:** no extra fields are allowed.

---

### 2) Stream Map (v1)

Core pipeline:
- `perception.market_data.collected.v1`
- `variables.market.computed.v1`
- `signals.opportunity.scored.v1`
- `strategy.candidate_action.generated.v1`
- `risk.order.approved.v1` / `risk.order.rejected.v1`
- `execution.order.executed.v1` / `execution.order.failed.v1`

Side streams:
- `perception.heartbeat.v1`
- `signals.regime.detected.v1`

DLQ:
- `dlq.<base_stream>.v1` (internal)

---

### 3) Payload semantics (v1 summary)

The authoritative runtime validator is implemented in `src/contracts/validation.py`.
Golden events live under `contracts/golden_events/v1/`.
