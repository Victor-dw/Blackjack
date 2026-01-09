from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

# Allow running from repo root without installing as a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import redis  # type: ignore

from src.contracts.validation import validate_envelope_dict


def _iter_event_files(root: Path) -> list[Path]:
    return [Path(p) for p in sorted(glob.glob(str(root / "*.json")))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--redis-url", required=True)
    ap.add_argument("--events-dir", default=str(Path("contracts") / "golden_events" / "v1"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--fail-on-invalid",
        action="store_true",
        help="By default invalid (dirty) golden events are skipped. Use this flag to fail fast instead.",
    )
    args = ap.parse_args()

    root = Path(args.events_dir)
    files = _iter_event_files(root)
    if not files:
        raise SystemExit(f"no golden events found under {root}")

    r = redis.Redis.from_url(args.redis_url, decode_responses=True)
    for fp in files:
        ev = json.loads(fp.read_text(encoding="utf-8"))
        try:
            validate_envelope_dict(ev)
        except Exception as e:
            if args.fail_on_invalid:
                raise
            print(f"[skip-invalid] {fp.name}: {e}")
            continue
        stream = ev["schema"]
        body = json.dumps(ev, ensure_ascii=False)
        if args.dry_run:
            print(f"[dry-run] xadd {stream} <- {fp.name}")
        else:
            r.xadd(stream, {"event": body})
            print(f"xadd {stream} <- {fp.name}")


if __name__ == "__main__":
    main()
