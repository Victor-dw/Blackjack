from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.contracts.validation import validate_envelope_dict
from src.core.idempotency import InMemoryIdempotencyStore


GOLDEN_DIR = Path("contracts") / "golden_events" / "v1"


@pytest.mark.parametrize("path", sorted(GOLDEN_DIR.glob("*.json")))
def test_golden_events_contract_validation(path: Path) -> None:
    ev = json.loads(path.read_text(encoding="utf-8"))
    if "invalid" in path.name:
        with pytest.raises(ValueError):
            validate_envelope_dict(ev)
    else:
        validate_envelope_dict(ev)


def test_idempotency_duplicate_event_ids_are_detected() -> None:
    a = json.loads((GOLDEN_DIR / "07_duplicate_valid_a.json").read_text(encoding="utf-8"))
    b = json.loads((GOLDEN_DIR / "08_duplicate_valid_b.json").read_text(encoding="utf-8"))
    validate_envelope_dict(a)
    validate_envelope_dict(b)

    store = InMemoryIdempotencyStore()
    assert store.seen(a["event_id"]) is False
    store.mark(a["event_id"], ttl_seconds=60)
    assert store.seen(b["event_id"]) is True
