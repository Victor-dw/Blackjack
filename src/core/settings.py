from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml


@dataclass(frozen=True)
class Settings:
    env: str
    redis_url: str
    redis_consumer_group: str
    postgres_dsn: str
    clickhouse_url: str
    execution_dry_run: bool = True


def load_settings(path: str | Path = "config/settings.yaml") -> Settings:
    p = Path(path)
    data: Dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8"))
    return Settings(
        env=data.get("env", "dev"),
        redis_url=data["redis"]["url"],
        redis_consumer_group=data["redis"]["stream"].get("consumer_group", "blackjack"),
        postgres_dsn=data["postgres"]["dsn"],
        clickhouse_url=data["clickhouse"]["url"],
        execution_dry_run=bool(data.get("execution", {}).get("dry_run", True)),
    )
