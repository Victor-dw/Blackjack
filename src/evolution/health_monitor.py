"""Strategy health monitoring - monitors strategy performance and health.

This module implements continuous monitoring of strategy health,
following the architecture document's specifications:

监控指标:
  - 近期胜率 vs 历史胜率 (偏离度)
  - 近期夏普比 vs 历史夏普比
  - 最大回撤监控
  - 连续亏损次数
  - 策略信号频率变化

预警阈值:
  - 胜率下降 > 10%: 黄色预警
  - 夏普比下降 > 30%: 橙色预警
  - 最大回撤突破历史: 红色预警
  - 连续亏损 > 5次: 暂停策略
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Optional
import statistics


class AlertLevel(str, Enum):
    """Alert severity levels."""
    GREEN = "GREEN"      # Normal operation
    YELLOW = "YELLOW"    # Warning - record and observe
    ORANGE = "ORANGE"    # Caution - reduce position weight
    RED = "RED"          # Critical - pause strategy, human review


class AlertAction(str, Enum):
    """Recommended actions for alerts."""
    CONTINUE = "CONTINUE"         # Keep operating normally
    LOG_OBSERVE = "LOG_OBSERVE"   # Log and continue to observe
    REDUCE_WEIGHT = "REDUCE_WEIGHT"  # Reduce strategy position weight
    PAUSE = "PAUSE"               # Pause the strategy
    HUMAN_REVIEW = "HUMAN_REVIEW"  # Require human intervention


@dataclass
class HealthMetrics:
    """Current health metrics for a strategy."""
    strategy_name: str

    # Win rate metrics
    recent_win_rate: float = 0.0    # Last N trades
    historical_win_rate: float = 0.0  # All-time
    win_rate_deviation: float = 0.0   # (recent - historical) / historical

    # Sharpe ratio metrics
    recent_sharpe: float = 0.0
    historical_sharpe: float = 0.0
    sharpe_deviation: float = 0.0

    # Drawdown metrics
    current_drawdown: float = 0.0
    max_historical_drawdown: float = 0.0
    is_new_max_drawdown: bool = False

    # Streak metrics
    current_loss_streak: int = 0
    max_loss_streak: int = 0
    current_win_streak: int = 0

    # Activity metrics
    recent_signal_frequency: float = 0.0  # Signals per day (recent)
    historical_signal_frequency: float = 0.0
    frequency_deviation: float = 0.0

    # Time metrics
    last_trade_time: Optional[datetime] = None
    last_update_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "recent_win_rate": self.recent_win_rate,
            "historical_win_rate": self.historical_win_rate,
            "win_rate_deviation": self.win_rate_deviation,
            "recent_sharpe": self.recent_sharpe,
            "historical_sharpe": self.historical_sharpe,
            "sharpe_deviation": self.sharpe_deviation,
            "current_drawdown": self.current_drawdown,
            "max_historical_drawdown": self.max_historical_drawdown,
            "is_new_max_drawdown": self.is_new_max_drawdown,
            "current_loss_streak": self.current_loss_streak,
            "max_loss_streak": self.max_loss_streak,
            "current_win_streak": self.current_win_streak,
            "recent_signal_frequency": self.recent_signal_frequency,
            "historical_signal_frequency": self.historical_signal_frequency,
            "frequency_deviation": self.frequency_deviation,
            "last_trade_time": self.last_trade_time.isoformat() if self.last_trade_time else None,
            "last_update_time": self.last_update_time.isoformat(),
        }


@dataclass
class HealthAlert:
    """A health alert for a strategy."""
    strategy_name: str
    level: AlertLevel
    action: AlertAction
    metric_name: str
    message: str
    current_value: float
    threshold_value: float
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "level": self.level.value,
            "action": self.action.value,
            "metric_name": self.metric_name,
            "message": self.message,
            "current_value": self.current_value,
            "threshold_value": self.threshold_value,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class HealthReport:
    """Complete health report for a strategy."""
    metrics: HealthMetrics
    alerts: list[HealthAlert]
    overall_level: AlertLevel
    recommended_action: AlertAction

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics.to_dict(),
            "alerts": [a.to_dict() for a in self.alerts],
            "overall_level": self.overall_level.value,
            "recommended_action": self.recommended_action.value,
        }


@dataclass
class StrategyHealthConfig:
    """Configuration for health monitoring thresholds."""
    # Win rate thresholds
    win_rate_yellow_threshold: float = 0.10  # 10% decline

    # Sharpe ratio thresholds
    sharpe_orange_threshold: float = 0.30  # 30% decline

    # Drawdown thresholds (relative to historical max)
    drawdown_red_threshold: float = 1.0  # 100% of historical max = new record

    # Streak thresholds
    loss_streak_pause_threshold: int = 5

    # Frequency thresholds
    frequency_deviation_threshold: float = 0.50  # 50% change

    # Recent window size (number of trades)
    recent_window_size: int = 20


class HealthMonitor:
    """Monitor for strategy health and performance.

    This monitor tracks strategy performance metrics and generates
    alerts when performance degrades beyond configured thresholds.
    """

    def __init__(self, config: Optional[StrategyHealthConfig] = None) -> None:
        self._config = config or StrategyHealthConfig()
        self._trade_history: dict[str, list[dict[str, Any]]] = {}
        self._metrics_cache: dict[str, HealthMetrics] = {}
        self._peak_values: dict[str, float] = {}  # For drawdown calculation

    def record_trade(
        self,
        strategy_name: str,
        trade: dict[str, Any],
    ) -> None:
        """Record a completed trade for health tracking.

        Args:
            strategy_name: Name of the strategy
            trade: Trade details with at least:
                - pnl: Profit/loss
                - timestamp: Trade completion time
                - symbol: Traded symbol
        """
        if strategy_name not in self._trade_history:
            self._trade_history[strategy_name] = []

        self._trade_history[strategy_name].append(trade)

        # Update peak value for drawdown
        if strategy_name not in self._peak_values:
            self._peak_values[strategy_name] = 0.0

        cumulative_pnl = sum(t.get("pnl", 0) for t in self._trade_history[strategy_name])
        if cumulative_pnl > self._peak_values[strategy_name]:
            self._peak_values[strategy_name] = cumulative_pnl

    def check_health(self, strategy_name: str) -> HealthReport:
        """Check health status of a strategy.

        Args:
            strategy_name: Name of the strategy to check

        Returns:
            HealthReport with metrics, alerts, and recommended action
        """
        metrics = self._calculate_metrics(strategy_name)
        alerts = self._generate_alerts(metrics)

        # Determine overall level and action
        overall_level, recommended_action = self._determine_overall_status(alerts)

        # Cache metrics
        self._metrics_cache[strategy_name] = metrics

        return HealthReport(
            metrics=metrics,
            alerts=alerts,
            overall_level=overall_level,
            recommended_action=recommended_action,
        )

    def _calculate_metrics(self, strategy_name: str) -> HealthMetrics:
        """Calculate health metrics for a strategy."""
        trades = self._trade_history.get(strategy_name, [])

        if not trades:
            return HealthMetrics(strategy_name=strategy_name)

        # Split into recent and historical
        window_size = self._config.recent_window_size
        recent_trades = trades[-window_size:] if len(trades) >= window_size else trades

        # Win rates
        historical_wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
        historical_win_rate = historical_wins / len(trades)

        recent_wins = sum(1 for t in recent_trades if t.get("pnl", 0) > 0)
        recent_win_rate = recent_wins / len(recent_trades)

        win_rate_deviation = 0.0
        if historical_win_rate > 0:
            win_rate_deviation = (recent_win_rate - historical_win_rate) / historical_win_rate

        # Sharpe ratios (simplified daily returns approximation)
        historical_sharpe = self._calculate_sharpe(trades)
        recent_sharpe = self._calculate_sharpe(recent_trades)

        sharpe_deviation = 0.0
        if historical_sharpe > 0:
            sharpe_deviation = (recent_sharpe - historical_sharpe) / historical_sharpe

        # Drawdown
        cumulative_pnl = sum(t.get("pnl", 0) for t in trades)
        peak = self._peak_values.get(strategy_name, cumulative_pnl)
        current_drawdown = (peak - cumulative_pnl) / peak if peak > 0 else 0

        # Historical max drawdown (simplified)
        max_dd = self._calculate_max_drawdown(trades)
        is_new_max = current_drawdown > max_dd if max_dd > 0 else False

        # Loss streak
        current_loss_streak = 0
        current_win_streak = 0
        max_loss_streak = 0
        temp_loss_streak = 0

        for t in trades:
            if t.get("pnl", 0) < 0:
                temp_loss_streak += 1
                max_loss_streak = max(max_loss_streak, temp_loss_streak)
            else:
                temp_loss_streak = 0

        # Current streaks (from end)
        for t in reversed(trades):
            if t.get("pnl", 0) < 0:
                if current_win_streak == 0:
                    current_loss_streak += 1
                else:
                    break
            else:
                if current_loss_streak == 0:
                    current_win_streak += 1
                else:
                    break

        # Signal frequency
        if len(trades) >= 2:
            timestamps = [t.get("timestamp") for t in trades if t.get("timestamp")]
            if len(timestamps) >= 2:
                try:
                    if isinstance(timestamps[0], str):
                        timestamps = [datetime.fromisoformat(ts.replace("Z", "+00:00")) for ts in timestamps]

                    total_days = (timestamps[-1] - timestamps[0]).days or 1
                    historical_freq = len(trades) / total_days

                    recent_timestamps = [t.get("timestamp") for t in recent_trades if t.get("timestamp")]
                    if len(recent_timestamps) >= 2:
                        if isinstance(recent_timestamps[0], str):
                            recent_timestamps = [datetime.fromisoformat(ts.replace("Z", "+00:00")) for ts in recent_timestamps]
                        recent_days = (recent_timestamps[-1] - recent_timestamps[0]).days or 1
                        recent_freq = len(recent_trades) / recent_days
                    else:
                        recent_freq = historical_freq

                    freq_deviation = (recent_freq - historical_freq) / historical_freq if historical_freq > 0 else 0
                except Exception:
                    historical_freq = 0
                    recent_freq = 0
                    freq_deviation = 0
            else:
                historical_freq = 0
                recent_freq = 0
                freq_deviation = 0
        else:
            historical_freq = 0
            recent_freq = 0
            freq_deviation = 0

        last_trade = trades[-1] if trades else None
        last_trade_time = None
        if last_trade and last_trade.get("timestamp"):
            ts = last_trade["timestamp"]
            if isinstance(ts, str):
                last_trade_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            else:
                last_trade_time = ts

        return HealthMetrics(
            strategy_name=strategy_name,
            recent_win_rate=recent_win_rate,
            historical_win_rate=historical_win_rate,
            win_rate_deviation=win_rate_deviation,
            recent_sharpe=recent_sharpe,
            historical_sharpe=historical_sharpe,
            sharpe_deviation=sharpe_deviation,
            current_drawdown=current_drawdown,
            max_historical_drawdown=max_dd,
            is_new_max_drawdown=is_new_max,
            current_loss_streak=current_loss_streak,
            max_loss_streak=max_loss_streak,
            current_win_streak=current_win_streak,
            recent_signal_frequency=recent_freq,
            historical_signal_frequency=historical_freq,
            frequency_deviation=freq_deviation,
            last_trade_time=last_trade_time,
        )

    def _calculate_sharpe(self, trades: list[dict[str, Any]], risk_free_rate: float = 0.03) -> float:
        """Calculate Sharpe ratio from trades."""
        if len(trades) < 2:
            return 0.0

        returns = [t.get("pnl", 0) for t in trades]
        if not returns:
            return 0.0

        avg_return = statistics.mean(returns)
        try:
            std_return = statistics.stdev(returns)
        except statistics.StatisticsError:
            std_return = 0

        if std_return == 0:
            return 0.0

        # Annualize (assume daily)
        daily_rf = risk_free_rate / 252
        sharpe = (avg_return - daily_rf) / std_return
        return sharpe

    def _calculate_max_drawdown(self, trades: list[dict[str, Any]]) -> float:
        """Calculate maximum drawdown from trade history."""
        if not trades:
            return 0.0

        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0

        for t in trades:
            cumulative += t.get("pnl", 0)
            if cumulative > peak:
                peak = cumulative
            elif peak > 0:
                dd = (peak - cumulative) / peak
                if dd > max_dd:
                    max_dd = dd

        return max_dd

    def _generate_alerts(self, metrics: HealthMetrics) -> list[HealthAlert]:
        """Generate alerts based on metrics and thresholds."""
        alerts: list[HealthAlert] = []
        config = self._config

        # Win rate alert (YELLOW)
        if metrics.win_rate_deviation < -config.win_rate_yellow_threshold:
            alerts.append(HealthAlert(
                strategy_name=metrics.strategy_name,
                level=AlertLevel.YELLOW,
                action=AlertAction.LOG_OBSERVE,
                metric_name="win_rate",
                message=f"Win rate declined by {abs(metrics.win_rate_deviation)*100:.1f}%",
                current_value=metrics.recent_win_rate,
                threshold_value=metrics.historical_win_rate * (1 - config.win_rate_yellow_threshold),
            ))

        # Sharpe ratio alert (ORANGE)
        if metrics.sharpe_deviation < -config.sharpe_orange_threshold:
            alerts.append(HealthAlert(
                strategy_name=metrics.strategy_name,
                level=AlertLevel.ORANGE,
                action=AlertAction.REDUCE_WEIGHT,
                metric_name="sharpe_ratio",
                message=f"Sharpe ratio declined by {abs(metrics.sharpe_deviation)*100:.1f}%",
                current_value=metrics.recent_sharpe,
                threshold_value=metrics.historical_sharpe * (1 - config.sharpe_orange_threshold),
            ))

        # Max drawdown alert (RED)
        if metrics.is_new_max_drawdown:
            alerts.append(HealthAlert(
                strategy_name=metrics.strategy_name,
                level=AlertLevel.RED,
                action=AlertAction.HUMAN_REVIEW,
                metric_name="max_drawdown",
                message=f"New maximum drawdown: {metrics.current_drawdown*100:.1f}%",
                current_value=metrics.current_drawdown,
                threshold_value=metrics.max_historical_drawdown,
            ))

        # Loss streak alert (PAUSE)
        if metrics.current_loss_streak >= config.loss_streak_pause_threshold:
            alerts.append(HealthAlert(
                strategy_name=metrics.strategy_name,
                level=AlertLevel.RED,
                action=AlertAction.PAUSE,
                metric_name="loss_streak",
                message=f"Consecutive losses: {metrics.current_loss_streak}",
                current_value=float(metrics.current_loss_streak),
                threshold_value=float(config.loss_streak_pause_threshold),
            ))

        return alerts

    def _determine_overall_status(
        self,
        alerts: list[HealthAlert]
    ) -> tuple[AlertLevel, AlertAction]:
        """Determine overall status from alerts."""
        if not alerts:
            return AlertLevel.GREEN, AlertAction.CONTINUE

        # Find highest severity alert
        severity_order = [AlertLevel.RED, AlertLevel.ORANGE, AlertLevel.YELLOW]

        for level in severity_order:
            level_alerts = [a for a in alerts if a.level == level]
            if level_alerts:
                # Return the most severe action among alerts at this level
                action_order = [
                    AlertAction.HUMAN_REVIEW,
                    AlertAction.PAUSE,
                    AlertAction.REDUCE_WEIGHT,
                    AlertAction.LOG_OBSERVE,
                ]
                for action in action_order:
                    if any(a.action == action for a in level_alerts):
                        return level, action
                return level, level_alerts[0].action

        return AlertLevel.GREEN, AlertAction.CONTINUE

    def get_all_metrics(self) -> dict[str, HealthMetrics]:
        """Get cached metrics for all monitored strategies."""
        return self._metrics_cache.copy()

    def clear_history(self, strategy_name: str) -> None:
        """Clear trade history for a strategy."""
        if strategy_name in self._trade_history:
            del self._trade_history[strategy_name]
        if strategy_name in self._metrics_cache:
            del self._metrics_cache[strategy_name]
        if strategy_name in self._peak_values:
            del self._peak_values[strategy_name]
