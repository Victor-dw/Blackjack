from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol


class IdempotencyStore(Protocol):
    """Tracks whether an event_id has been processed.

    Contract: if `seen(event_id)` is True then the event must be treated as already processed.
    """

    def seen(self, event_id: str) -> bool:
        ...

    def mark(self, event_id: str, *, ttl_seconds: int) -> None:
        ...


@dataclass
class InMemoryIdempotencyStore:
    _seen: dict[str, float]

    def __init__(self) -> None:
        self._seen = {}

    def seen(self, event_id: str) -> bool:
        now = time.time()
        expired = [k for k, exp in self._seen.items() if exp <= now]
        for k in expired:
            self._seen.pop(k, None)
        return event_id in self._seen

    def mark(self, event_id: str, *, ttl_seconds: int) -> None:
        self._seen[event_id] = time.time() + ttl_seconds


class RedisIdempotencyStore:
    def __init__(self, redis_client, *, key_prefix: str):
        self._client = redis_client
        self._prefix = key_prefix.rstrip(":")

    def _key(self, event_id: str) -> str:
        return f"{self._prefix}:{event_id}"

    def seen(self, event_id: str) -> bool:
        return bool(self._client.exists(self._key(event_id)))

    def mark(self, event_id: str, *, ttl_seconds: int) -> None:
        # SET NX prevents concurrent duplicates from double-processing.
        self._client.set(self._key(event_id), "1", ex=ttl_seconds, nx=True)
