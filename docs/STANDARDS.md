## Blackjack OS Backend Standards (v1)

This standard is derived from `docs/ARCHITECTURE.md` and applies to all future development.

### 1. Non-negotiables

1. **AI vs Execution isolation**
   - Backtest/evolution logic must never call broker/QMT adapters.
2. **Execution is mechanical**
   - Execution service reads approved parameters and executes. No extra judgement.
3. **Decision vs outcome separation**
   - Post-mortem stores full decision snapshots.

### 2. Layer boundaries

- Perception → Variables → Signals → Strategies → Risk → Execution → Postmortem → Evolution
- Cross-layer imports are allowed only via `src.core` and `src.contracts`.

### 3. Message contracts (Redis Streams)

- Stream name pattern: `<layer>.<entity>.<event>.v<version>`
- Each message must include: `event_id`, `trace_id`, `produced_at`, `schema`, `schema_version`, `payload`
- Breaking changes publish a new `v2` stream.

### 4. Config rules

- Strategy & risk thresholds must live in `config/` (no magic numbers in code).
- Any parameter change must be reviewable (PR + approval).

### 5. Testing baseline

- Unit tests for `src.risk.*` and `src.signals.*` are top priority.
- Integration tests validate the pipeline with mocked broker.
