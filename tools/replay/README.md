## Replay / Golden Events

Purpose:
- Allow every developer to locally replay the same **golden events** into Redis Streams
- Validate contracts and quickly smoke-test a subset of the pipeline

### Publish golden events

```bash
python tools/replay/publish_golden_events.py --redis-url redis://localhost:6379/0
```

By default it publishes `contracts/golden_events/v1/*.json` into their `schema` stream.

Notes:
- The golden set includes **dirty/invalid events** for contract testing.
- The publisher will **skip invalid events by default**.
- Use `--fail-on-invalid` if you want the replay command to fail fast instead.
