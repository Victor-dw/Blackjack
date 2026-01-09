from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class EventEnvelope:
    event_id: str
    trace_id: str
    produced_at: datetime
    schema: str
    schema_version: int
    payload: Dict[str, Any]
    source_service: Optional[str] = None
