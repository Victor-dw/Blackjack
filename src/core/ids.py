from __future__ import annotations

import uuid


def new_event_id() -> str:
    return str(uuid.uuid4())


def new_trace_id() -> str:
    return str(uuid.uuid4())
