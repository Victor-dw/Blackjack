from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

from .models import EventEnvelope
from .idempotency import RedisIdempotencyStore

from src.contracts.streams import dlq_stream
from src.contracts.validation import validate_envelope_dict


class MessageBus:
    """Abstraction for layer-to-layer communication."""

    def publish(self, stream: str, event: EventEnvelope) -> None:  # pragma: no cover
        raise NotImplementedError

    def consume(self, stream: str, group: str, consumer: str) -> Iterable[EventEnvelope]:  # pragma: no cover
        raise NotImplementedError


@dataclass(frozen=True)
class ReceivedMessage:
    stream: str
    message_id: str
    envelope: EventEnvelope
    fields: dict[str, str]


class RedisStreamBus(MessageBus):
    """Redis Streams implementation (skeleton).

    NOTE: This file defines the interface and the basic serialization format.
    Wire-up (redis client, groups, ack) is intentionally minimal at skeleton stage.
    """

    def __init__(
        self,
        redis_url: str,
        *,
        block_ms: int = 5000,
        read_count: int = 10,
        max_attempts: int = 5,
        dedupe_ttl_seconds: int = 7 * 24 * 3600,
        retry_backoff_seconds: float = 0.5,
    ):
        self.redis_url = redis_url
        self._client = None
        self.block_ms = block_ms
        self.read_count = read_count
        self.max_attempts = max_attempts
        self.dedupe_ttl_seconds = dedupe_ttl_seconds
        self.retry_backoff_seconds = retry_backoff_seconds

    def _get_client(self):
        if self._client is None:
            import redis  # type: ignore

            self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    def _ensure_group(self, stream: str, group: str) -> None:
        client = self._get_client()
        try:
            client.xgroup_create(name=stream, groupname=group, id="$", mkstream=True)
        except Exception as e:
            # BUSYGROUP means it already exists.
            if "BUSYGROUP" not in str(e):
                raise

    def _envelope_to_wire_dict(self, event: EventEnvelope) -> dict:
        d = asdict(event)
        produced_at = event.produced_at
        if isinstance(produced_at, datetime):
            if produced_at.tzinfo is None:
                produced_at = produced_at.replace(tzinfo=timezone.utc)
            d["produced_at"] = produced_at.isoformat()
        validate_envelope_dict(d)
        return d

    def _wire_dict_to_envelope(self, d: dict) -> EventEnvelope:
        # validate first (strict)
        validate_envelope_dict(d)
        produced_at = datetime.fromisoformat(str(d["produced_at"]).replace("Z", "+00:00"))
        return EventEnvelope(
            event_id=d["event_id"],
            trace_id=d["trace_id"],
            produced_at=produced_at,
            schema=d["schema"],
            schema_version=int(d["schema_version"]),
            payload=d["payload"],
            source_service=d.get("source_service"),
        )

    def publish(self, stream: str, event: EventEnvelope) -> None:
        client = self._get_client()
        wire = self._envelope_to_wire_dict(event)
        body = json.dumps(wire, ensure_ascii=False)
        client.xadd(stream, {"event": body})

    def consume(self, stream: str, group: str, consumer: str) -> Iterable[EventEnvelope]:
        # Backwards-compatible helper: yields envelopes (no ack/retry semantics).
        for msg in self.poll(stream=stream, group=group, consumer=consumer):
            yield msg.envelope

    def poll(self, *, stream: str, group: str, consumer: str) -> list[ReceivedMessage]:
        self._ensure_group(stream, group)
        client = self._get_client()
        resp = client.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={stream: ">"},
            count=self.read_count,
            block=self.block_ms,
        )
        out: list[ReceivedMessage] = []
        for (sname, items) in resp:
            for (msg_id, fields) in items:
                raw = dict(fields)
                body = raw.get("event")
                if not body:
                    # malformed message
                    out.append(
                        ReceivedMessage(
                            stream=sname,
                            message_id=msg_id,
                            envelope=EventEnvelope(
                                event_id="",
                                trace_id="",
                                produced_at=datetime.now(timezone.utc),
                                schema="invalid.v1",
                                schema_version=1,
                                payload={},
                                source_service=None,
                            ),
                            fields=raw,
                        )
                    )
                    continue
                d = json.loads(body)
                env = self._wire_dict_to_envelope(d)
                out.append(ReceivedMessage(stream=sname, message_id=msg_id, envelope=env, fields=raw))
        return out

    def ack(self, *, stream: str, group: str, message_id: str) -> None:
        client = self._get_client()
        client.xack(stream, group, message_id)

    def _attempt_key(self, *, group: str, stream: str, event_id: str) -> str:
        return f"attempt:{group}:{stream}:{event_id}"

    def _dlq(self, *, base_stream: str, event_json: str, error: str, original_message_id: str) -> None:
        client = self._get_client()
        client.xadd(
            dlq_stream(base_stream),
            {
                "event": event_json,
                "error": error,
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "original_stream": base_stream,
                "original_message_id": original_message_id,
            },
        )

    def run_worker(
        self,
        *,
        stream: str,
        group: str,
        consumer: str,
        handler: Callable[[EventEnvelope], None],
        stop_after_messages: int | None = None,
    ) -> None:
        """Run an at-least-once worker with idempotency + retry + DLQ.

        - Strict contract validation (v1: no extra fields)
        - Duplicate event_id is skipped (idempotent)
        - On handler exception: retry up to max_attempts, then DLQ
        """

        client = self._get_client()
        idem = RedisIdempotencyStore(client, key_prefix=f"processed:{group}:{stream}")
        processed = 0

        while True:
            batch = self.poll(stream=stream, group=group, consumer=consumer)
            if not batch:
                continue

            for msg in batch:
                env = msg.envelope
                # Re-parse and validate the wire payload to enforce strict v1.
                body = msg.fields.get("event") or "{}"
                try:
                    wire = json.loads(body)
                    validate_envelope_dict(wire)
                except Exception as e:
                    self._dlq(base_stream=stream, event_json=body, error=f"contract_invalid: {e}", original_message_id=msg.message_id)
                    self.ack(stream=stream, group=group, message_id=msg.message_id)
                    continue

                if idem.seen(env.event_id):
                    self.ack(stream=stream, group=group, message_id=msg.message_id)
                    continue

                try:
                    handler(env)
                except Exception as e:
                    attempt_key = self._attempt_key(group=group, stream=stream, event_id=env.event_id)
                    attempt = int(client.incr(attempt_key))
                    # Avoid unbounded growth of retry counters.
                    client.expire(attempt_key, self.dedupe_ttl_seconds)
                    if attempt >= self.max_attempts:
                        self._dlq(
                            base_stream=stream,
                            event_json=body,
                            error=f"handler_failed_after_{attempt}: {e}",
                            original_message_id=msg.message_id,
                        )
                        self.ack(stream=stream, group=group, message_id=msg.message_id)
                        continue

                    # Ack and requeue the same event (same event_id). Idempotency will stop double-processing.
                    self.ack(stream=stream, group=group, message_id=msg.message_id)
                    time.sleep(self.retry_backoff_seconds)
                    client.xadd(stream, {"event": body})
                    continue

                idem.mark(env.event_id, ttl_seconds=self.dedupe_ttl_seconds)
                self.ack(stream=stream, group=group, message_id=msg.message_id)

                processed += 1
                if stop_after_messages is not None and processed >= stop_after_messages:
                    return
