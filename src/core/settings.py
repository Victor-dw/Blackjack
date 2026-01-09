from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import os


@dataclass(frozen=True)
class Settings:
    env: str
    redis_url: str
    redis_trade_url: str | None
    redis_consumer_group: str
    postgres_dsn: str
    clickhouse_url: str
    execution_dry_run: bool = True


def load_settings(path: str | Path = "config/settings.yaml") -> Settings:
    p = Path(path)

    # Keep imports optional at module import time (tests/tools may not need YAML).
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError as e:  # pragma: no cover
        raise ModuleNotFoundError(
            "PyYAML is required to load config/settings.yaml. Install with: pip install pyyaml"
        ) from e

    data: Dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8"))

    # Env overrides (used for compose profile isolation).
    env_redis_url = os.getenv("BLACKJACK_REDIS_URL")
    env_redis_trade_url = os.getenv("BLACKJACK_REDIS_TRADE_URL")

    redis_section = data.get("redis", {})
    redis_url = env_redis_url or redis_section.get("compute_url") or redis_section["url"]
    redis_trade_url = env_redis_trade_url or redis_section.get("trade_url")
    return Settings(
        env=data.get("env", "dev"),
        redis_url=redis_url,
        redis_trade_url=redis_trade_url,
        redis_consumer_group=redis_section.get("stream", {}).get("consumer_group", "blackjack"),
        postgres_dsn=data["postgres"]["dsn"],
        clickhouse_url=data["clickhouse"]["url"],
        execution_dry_run=bool(data.get("execution", {}).get("dry_run", True)),
    )
