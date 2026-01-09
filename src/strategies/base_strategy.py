"""L4 Strategies: base abstractions.

This layer consumes signal events and produces candidate actions.

Contract references:
- inputs: signals.opportunity.scored.v1, signals.regime.detected.v1
- output: strategy.candidate_action.generated.v1
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from src.contracts import streams
from src.core.ids import new_event_id
from src.core.models import EventEnvelope


ALLOWED_ACTIONS_V1 = {"BUY", "SELL", "HOLD"}


@dataclass(frozen=True)
class CandidateAction:
    """Internal representation of `strategy.candidate_action.generated.v1` payload."""

    symbol: str
    ts: str
    action: str
    strategy: str
    target_position_frac: float
    rationale: str

    def to_payload(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "ts": self.ts,
            "action": self.action,
            "strategy": self.strategy,
            "target_position_frac": float(self.target_position_frac),
            "rationale": self.rationale,
        }

    def to_envelope(
        self,
        *,
        trace_id: str,
        source_service: str = "strategies",
        produced_at: Optional[datetime] = None,
        event_id: Optional[str] = None,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_id=event_id or new_event_id(),
            trace_id=trace_id,
            produced_at=produced_at or datetime.now(timezone.utc),
            schema=streams.STRATEGY_CANDIDATE_ACTION_GENERATED_V1,
            schema_version=1,
            payload=self.to_payload(),
            source_service=source_service,
        )


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    enabled: bool
    params: Dict[str, Any]

    @staticmethod
    def load(path: str | Path) -> "StrategyConfig":
        data = load_simple_yaml_mapping(path)
        name = str(data.get("name", ""))
        enabled = bool(data.get("enabled", True))
        params = data.get("params")
        if not isinstance(params, dict):
            params = {}
        return StrategyConfig(name=name, enabled=enabled, params=dict(params))


def load_simple_yaml_mapping(path: str | Path) -> Dict[str, Any]:
    """Parse a *very small* subset of YAML (mappings only) to avoid adding deps.

    Supports:
    - nested mappings via 2-space indentation
    - scalars: bool, int, float, str (quoted/unquoted)
    - `#` comments
    """

    text = Path(path).read_text(encoding="utf-8")
    root: Dict[str, Any] = {}
    stack: list[tuple[int, Dict[str, Any]]] = [(0, root)]

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip("\n\r")
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip(" "))
        key_part, sep, value_part = line.lstrip(" ").partition(":")
        if sep != ":":
            raise ValueError(f"Invalid YAML line (missing ':'): {raw_line}")
        key = key_part.strip()
        value_raw = value_part.strip()

        while stack and indent < stack[-1][0]:
            stack.pop()
        if not stack:
            raise ValueError(f"Invalid indentation in YAML: {raw_line}")

        current = stack[-1][1]

        if value_raw == "":
            new_map: Dict[str, Any] = {}
            current[key] = new_map
            stack.append((indent + 2, new_map))
            continue

        current[key] = _parse_yaml_scalar(value_raw)

    return root


def _parse_yaml_scalar(v: str) -> Any:
    s = v.strip()
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        return s[1:-1]
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    # int
    try:
        if all(c in "-0123456789" for c in s) and any(c.isdigit() for c in s):
            return int(s)
    except Exception:
        pass
    # float
    try:
        if any(c in s for c in ".eE"):
            return float(s)
    except Exception:
        pass
    return s


class BaseStrategy(ABC):
    """Base strategy with signal buffering and common sizing helpers."""

    def __init__(self, *, config: StrategyConfig):
        if not config.name:
            raise ValueError("StrategyConfig.name must be non-empty")
        self.config = config
        self.name = config.name
        self.enabled = bool(config.enabled)
        self.params: Dict[str, Any] = dict(config.params)

        self._opportunity_by_symbol: dict[str, dict[str, Any]] = {}
        self._regime_by_symbol: dict[str, dict[str, Any]] = {}
        self._last_emitted_ts_by_symbol: dict[str, str] = {}

    @property
    def opportunity_threshold(self) -> float:
        return float(self.params.get("opportunity_threshold", 60))

    def on_signal(self, env: EventEnvelope) -> Optional[CandidateAction]:
        """Ingest one upstream signal event; emit a candidate action when ready."""

        if not self.enabled:
            return None

        if env.schema not in {
            streams.SIGNALS_OPPORTUNITY_SCORED_V1,
            streams.SIGNALS_REGIME_DETECTED_V1,
        }:
            return None

        payload = env.payload or {}
        symbol = payload.get("symbol")
        if not isinstance(symbol, str) or not symbol.strip():
            return None

        if env.schema == streams.SIGNALS_OPPORTUNITY_SCORED_V1:
            self._opportunity_by_symbol[symbol] = payload
            # Fallback regime from opportunity payload (it includes a `regime` field in v1).
            reg = payload.get("regime")
            ts = payload.get("ts")
            if isinstance(reg, str) and isinstance(ts, str) and symbol not in self._regime_by_symbol:
                self._regime_by_symbol[symbol] = {"symbol": symbol, "ts": ts, "regime": reg}
        else:
            self._regime_by_symbol[symbol] = payload

        opp = self._opportunity_by_symbol.get(symbol)
        reg = self._regime_by_symbol.get(symbol)
        if not opp or not reg:
            return None

        ts = opp.get("ts")
        if not isinstance(ts, str) or not ts.strip():
            return None

        if self._last_emitted_ts_by_symbol.get(symbol) == ts:
            return None

        candidate = self.generate(opportunity=opp, regime=reg)
        candidate = self._sanitize_candidate(candidate)
        self._last_emitted_ts_by_symbol[symbol] = ts
        return candidate

    @abstractmethod
    def generate(self, *, opportunity: dict[str, Any], regime: dict[str, Any]) -> CandidateAction:
        """Generate a candidate action given the latest signals for the symbol."""

    def make_candidate(
        self,
        *,
        symbol: str,
        ts: str,
        action: str,
        target_position_frac: float,
        rationale: str,
        strategy: Optional[str] = None,
    ) -> CandidateAction:
        return CandidateAction(
            symbol=symbol,
            ts=ts,
            action=str(action).upper(),
            strategy=strategy or self.name,
            target_position_frac=float(target_position_frac),
            rationale=str(rationale),
        )

    def size_from_score(self, *, opportunity_score: float, confidence: float) -> float:
        """Map score/confidence (0..100) to a target position fraction (0..1)."""

        score = max(0.0, min(100.0, float(opportunity_score)))
        conf = max(0.0, min(100.0, float(confidence)))
        frac = score / 100.0

        # Default scaling based on docs/ARCHITECTURE.md '阈值参考'
        low = float(self.params.get("confidence_low", 40))
        high = float(self.params.get("confidence_high", 60))
        low_mul = float(self.params.get("confidence_low_multiplier", 0.5))
        high_mul = float(self.params.get("confidence_high_multiplier", 1.2))

        if conf < low:
            frac *= low_mul
        elif conf > high:
            frac *= high_mul

        return max(0.0, min(1.0, frac))

    def _sanitize_candidate(self, c: CandidateAction) -> CandidateAction:
        action = str(c.action).upper()
        if action not in ALLOWED_ACTIONS_V1:
            action = "HOLD"
        frac = float(c.target_position_frac)
        if frac > 1.0:
            frac = 1.0
        if frac < -1.0:
            frac = -1.0
        rationale = str(c.rationale)
        if not rationale.strip():
            rationale = f"{self.name}: empty rationale"
        return CandidateAction(
            symbol=str(c.symbol),
            ts=str(c.ts),
            action=action,
            strategy=str(c.strategy),
            target_position_frac=frac,
            rationale=rationale,
        )
