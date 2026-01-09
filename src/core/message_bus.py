from __future__ import annotations

import json
from dataclasses import asdict
from typing import Iterable, Optional

from .models import EventEnvelope


class MessageBus:
    """Abstraction for layer-to-layer communication."""

    def publish(self, stream: str, event: EventEnvelope) -> None:  # pragma: no cover
        raise NotImplementedError

    def consume(self, stream: str, group: str, consumer: str) -> Iterable[EventEnvelope]:  # pragma: no cover
        raise NotImplementedError


class RedisStreamBus(MessageBus):
    """Redis Streams implementation (skeleton).

    NOTE: This file defines the interface and the basic serialization format.
    Wire-up (redis client, groups, ack) is intentionally minimal at skeleton stage.
    """

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            import redis  # type: ignore

            self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    def publish(self, stream: str, event: EventEnvelope) -> None:
        client = self._get_client()
        body = json.dumps(asdict(event), ensure_ascii=False, default=str)
        client.xadd(stream, {"event": body})

    def consume(self, stream: str, group: str, consumer: str) -> Iterable[EventEnvelope]:
        # Skeleton placeholder. Real implementation should:
        # - create group if absent
        # - use XREADGROUP + block
        # - ack on success, DLQ on failure
        return []
