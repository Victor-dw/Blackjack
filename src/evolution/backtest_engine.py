"""Backtest engine for strategy validation.

IMPORTANT: This layer must be PHYSICALLY ISOLATED from live execution.
- Only allowed to access compute-network
- NEVER allowed to access trade-network
- AI/backtest services MUST NOT have access to trading interfaces

The backtest engine is used for:
1. Strategy validation before deployment
2. Parameter optimization (grid/random/bayesian)
3. Overfitting detection (in-sample vs out-of-sample)
4. Historical performance analysis
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Protocol, Callable
from enum import Enum
import math


class BacktestStatus(str, Enum):
    """Status of a backtest run."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class BacktestMetrics:
    """Standard backtest performance metrics."""
    # Returns
    total_return: float = 0.0
    annualized_return: float = 0.0

    # Risk metrics
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0

    # Trade statistics
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_holding_period_days: float = 0.0

    # Risk-adjusted
    risk_adjusted_return: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BacktestMetrics":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class BacktestTrade:
    """A single trade in a backtest."""
    trade_id: str
    symbol: str
    entry_date: datetime
    exit_date: Optional[datetime]
    side: str  # BUY / SELL
    entry_price: float
    exit_price: Optional[float]
    qty: float
    pnl: Optional[float] = None
    holding_period_days: Optional[float] = None
    strategy: str = ""

    def calculate_pnl(self) -> Optional[float]:
        if self.exit_price is None:
            return None
        if self.side == "BUY":
            return (self.exit_price - self.entry_price) * self.qty
        else:
            return (self.entry_price - self.exit_price) * self.qty


@dataclass
class BacktestResult:
    """Complete backtest result."""
    backtest_id: str
    strategy: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    metrics: BacktestMetrics
    parameters: dict[str, Any]
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[tuple[str, float]] = field(default_factory=list)
    status: BacktestStatus = BacktestStatus.COMPLETED
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "backtest_id": self.backtest_id,
            "strategy": self.strategy,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "initial_capital": self.initial_capital,
            "final_capital": self.final_capital,
            "metrics": self.metrics.to_dict(),
            "parameters": self.parameters,
            "trade_count": len(self.trades),
            "status": self.status.value,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
        }


class HistoricalDataProvider(Protocol):
    """Interface for historical data access."""

    def get_ohlcv(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        timeframe: str = "1d",
    ) -> list[dict[str, Any]]:
        """Get OHLCV data for a symbol."""
        ...

    def get_market_data(
        self,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """Get market-wide data (index, breadth, etc.)."""
        ...


class Strategy(Protocol):
    """Interface for backtestable strategies."""

    @property
    def name(self) -> str:
        """Strategy name."""
        ...

    def generate_signals(
        self,
        market_data: dict[str, Any],
        stock_data: dict[str, Any],
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Generate trading signals.

        Returns list of signals with:
        - symbol
        - action (BUY/SELL/HOLD)
        - target_position_frac
        - confidence
        """
        ...


class InMemoryDataProvider:
    """In-memory data provider for testing."""

    def __init__(self) -> None:
        self._data: dict[str, list[dict[str, Any]]] = {}

    def add_data(self, symbol: str, data: list[dict[str, Any]]) -> None:
        self._data[symbol] = data

    def get_ohlcv(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        timeframe: str = "1d",
    ) -> list[dict[str, Any]]:
        data = self._data.get(symbol, [])
        return [
            d for d in data
            if start_date <= d.get("date", d.get("ts", "")) <= end_date
        ]

    def get_market_data(
        self,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        # Return index data if available
        return self.get_ohlcv("INDEX", start_date, end_date)


class BacktestEngine:
    """Backtest engine for strategy validation.

    IMPORTANT: This engine must be PHYSICALLY ISOLATED from live execution.
    It only has access to compute-network and historical data.

    Usage:
        engine = BacktestEngine(data_provider)
        result = engine.run(
            strategy=my_strategy,
            symbols=["600000.SH", "000001.SZ"],
            start_date="2025-01-01",
            end_date="2025-12-31",
            parameters={"entry_threshold": 70},
            initial_capital=1_000_000,
        )
    """

    def __init__(
        self,
        data_provider: HistoricalDataProvider,
        message_bus=None,
        risk_free_rate: float = 0.03,
    ) -> None:
        self._data_provider = data_provider
        self._bus = message_bus
        self._risk_free_rate = risk_free_rate

    def run(
        self,
        strategy: Strategy,
        symbols: list[str],
        start_date: str,
        end_date: str,
        parameters: dict[str, Any],
        initial_capital: float = 1_000_000,
    ) -> BacktestResult:
        """Run a backtest for a strategy.

        Args:
            strategy: Strategy to backtest
            symbols: List of symbols to trade
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            parameters: Strategy parameters
            initial_capital: Starting capital

        Returns:
            BacktestResult with metrics and trades
        """
        from src.core.ids import new_event_id

        backtest_id = f"bt-{strategy.name}-{new_event_id()[:8]}"

        try:
            # Load historical data
            market_data = self._data_provider.get_market_data(start_date, end_date)
            stock_data = {
                sym: self._data_provider.get_ohlcv(sym, start_date, end_date)
                for sym in symbols
            }

            # Run simulation
            trades, equity_curve = self._simulate(
                strategy=strategy,
                market_data=market_data,
                stock_data=stock_data,
                parameters=parameters,
                initial_capital=initial_capital,
            )

            # Calculate metrics
            final_capital = equity_curve[-1][1] if equity_curve else initial_capital
            metrics = self._calculate_metrics(
                trades=trades,
                equity_curve=equity_curve,
                initial_capital=initial_capital,
                start_date=start_date,
                end_date=end_date,
            )

            result = BacktestResult(
                backtest_id=backtest_id,
                strategy=strategy.name,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                final_capital=final_capital,
                metrics=metrics,
                parameters=parameters,
                trades=trades,
                equity_curve=equity_curve,
                status=BacktestStatus.COMPLETED,
            )

        except Exception as e:
            result = BacktestResult(
                backtest_id=backtest_id,
                strategy=strategy.name,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                final_capital=initial_capital,
                metrics=BacktestMetrics(),
                parameters=parameters,
                status=BacktestStatus.FAILED,
                error_message=str(e),
            )

        # Publish completion event
        self._publish_completion_event(result)

        return result

    def _simulate(
        self,
        strategy: Strategy,
        market_data: list[dict[str, Any]],
        stock_data: dict[str, list[dict[str, Any]]],
        parameters: dict[str, Any],
        initial_capital: float,
    ) -> tuple[list[BacktestTrade], list[tuple[str, float]]]:
        """Run the trading simulation."""
        trades: list[BacktestTrade] = []
        equity_curve: list[tuple[str, float]] = []

        capital = initial_capital
        positions: dict[str, BacktestTrade] = {}  # Open positions
        trade_counter = 0

        # Build date index from market data
        dates = sorted(set(d.get("date", d.get("ts", ""))[:10] for d in market_data))

        for date in dates:
            # Get data for this date
            daily_market = [d for d in market_data if d.get("date", d.get("ts", ""))[:10] == date]
            daily_stock = {
                sym: [d for d in data if d.get("date", d.get("ts", ""))[:10] == date]
                for sym, data in stock_data.items()
            }

            if not daily_market:
                continue

            # Generate signals
            signals = strategy.generate_signals(
                market_data={"date": date, "bars": daily_market},
                stock_data=daily_stock,
                parameters=parameters,
            )

            # Process signals
            for signal in signals:
                symbol = signal.get("symbol", "")
                action = signal.get("action", "HOLD")

                if action == "BUY" and symbol not in positions:
                    # Open position
                    stock_bars = daily_stock.get(symbol, [])
                    if stock_bars:
                        bar = stock_bars[0]
                        price = bar.get("close", bar.get("price", 0))
                        if price > 0:
                            trade_counter += 1
                            qty = (capital * 0.1) / price  # 10% position
                            trade = BacktestTrade(
                                trade_id=f"bt-trade-{trade_counter}",
                                symbol=symbol,
                                entry_date=datetime.fromisoformat(date),
                                exit_date=None,
                                side="BUY",
                                entry_price=price,
                                exit_price=None,
                                qty=qty,
                                strategy=strategy.name,
                            )
                            positions[symbol] = trade
                            capital -= price * qty

                elif action == "SELL" and symbol in positions:
                    # Close position
                    stock_bars = daily_stock.get(symbol, [])
                    if stock_bars:
                        bar = stock_bars[0]
                        price = bar.get("close", bar.get("price", 0))
                        if price > 0:
                            trade = positions.pop(symbol)
                            trade.exit_date = datetime.fromisoformat(date)
                            trade.exit_price = price
                            trade.pnl = trade.calculate_pnl()
                            if trade.exit_date and trade.entry_date:
                                trade.holding_period_days = (trade.exit_date - trade.entry_date).days
                            trades.append(trade)
                            capital += price * trade.qty

            # Calculate portfolio value
            portfolio_value = capital
            for sym, pos in positions.items():
                stock_bars = daily_stock.get(sym, [])
                if stock_bars:
                    bar = stock_bars[0]
                    price = bar.get("close", bar.get("price", pos.entry_price))
                    portfolio_value += price * pos.qty

            equity_curve.append((date, portfolio_value))

        return trades, equity_curve

    def _calculate_metrics(
        self,
        trades: list[BacktestTrade],
        equity_curve: list[tuple[str, float]],
        initial_capital: float,
        start_date: str,
        end_date: str,
    ) -> BacktestMetrics:
        """Calculate backtest performance metrics."""
        if not equity_curve:
            return BacktestMetrics()

        final_value = equity_curve[-1][1]
        total_return = (final_value - initial_capital) / initial_capital

        # Calculate drawdown
        peak = initial_capital
        max_dd = 0.0
        for _, value in equity_curve:
            if value > peak:
                peak = value
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd

        # Calculate returns for Sharpe ratio
        returns = []
        for i in range(1, len(equity_curve)):
            prev_val = equity_curve[i - 1][1]
            curr_val = equity_curve[i][1]
            if prev_val > 0:
                returns.append((curr_val - prev_val) / prev_val)

        # Sharpe ratio (annualized)
        sharpe = 0.0
        if returns:
            avg_return = sum(returns) / len(returns)
            std_return = math.sqrt(sum((r - avg_return) ** 2 for r in returns) / len(returns)) if len(returns) > 1 else 0
            if std_return > 0:
                daily_rf = self._risk_free_rate / 252
                sharpe = (avg_return - daily_rf) / std_return * math.sqrt(252)

        # Trade statistics
        completed_trades = [t for t in trades if t.pnl is not None]
        total_trades = len(completed_trades)

        wins = [t for t in completed_trades if t.pnl and t.pnl > 0]
        losses = [t for t in completed_trades if t.pnl and t.pnl < 0]

        win_rate = len(wins) / total_trades if total_trades > 0 else 0

        total_profit = sum(t.pnl for t in wins if t.pnl) if wins else 0
        total_loss = abs(sum(t.pnl for t in losses if t.pnl)) if losses else 0
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf') if total_profit > 0 else 0

        avg_win = total_profit / len(wins) if wins else 0
        avg_loss = total_loss / len(losses) if losses else 0

        avg_holding = 0.0
        if completed_trades:
            holding_days = [t.holding_period_days for t in completed_trades if t.holding_period_days]
            avg_holding = sum(holding_days) / len(holding_days) if holding_days else 0

        # Annualized return
        try:
            start = datetime.fromisoformat(start_date)
            end = datetime.fromisoformat(end_date)
            days = (end - start).days
            years = days / 365.25
            annualized = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
        except Exception:
            annualized = 0

        return BacktestMetrics(
            total_return=total_return,
            annualized_return=annualized,
            max_drawdown=max_dd,
            sharpe_ratio=sharpe,
            total_trades=total_trades,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_holding_period_days=avg_holding,
        )

    def _publish_completion_event(self, result: BacktestResult) -> None:
        """Publish evolution.backtest.completed.v1 event."""
        if self._bus is None:
            return

        from src.core.ids import new_event_id
        from src.core.models import EventEnvelope
        from src.contracts.streams import EVOLUTION_BACKTEST_COMPLETED_V1

        envelope = EventEnvelope(
            event_id=new_event_id(),
            trace_id=new_event_id(),
            produced_at=datetime.now(timezone.utc),
            schema=EVOLUTION_BACKTEST_COMPLETED_V1,
            schema_version=1,
            payload={
                "backtest_id": result.backtest_id,
                "strategy": result.strategy,
                "start_date": result.start_date,
                "end_date": result.end_date,
                "metrics": result.metrics.to_dict(),
                "parameters": result.parameters,
            },
            source_service="evolution-service",
        )

        self._bus.publish(EVOLUTION_BACKTEST_COMPLETED_V1, envelope)


class ParameterOptimizer:
    """Optimizer for strategy parameters.

    Supports:
    - Grid search
    - Random search
    - (Future: Bayesian optimization)
    """

    def __init__(self, engine: BacktestEngine) -> None:
        self._engine = engine

    def grid_search(
        self,
        strategy: Strategy,
        symbols: list[str],
        start_date: str,
        end_date: str,
        param_grid: dict[str, list[Any]],
        initial_capital: float = 1_000_000,
        metric: str = "sharpe_ratio",
    ) -> list[BacktestResult]:
        """Run grid search over parameter combinations.

        Args:
            strategy: Strategy to optimize
            symbols: Symbols to trade
            start_date: Start date
            end_date: End date
            param_grid: Dict of param_name -> list of values
            initial_capital: Starting capital
            metric: Metric to optimize (sharpe_ratio, total_return, etc.)

        Returns:
            List of BacktestResults sorted by metric
        """
        from itertools import product

        # Generate all combinations
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(product(*param_values))

        results: list[BacktestResult] = []

        for combo in combinations:
            params = dict(zip(param_names, combo))
            result = self._engine.run(
                strategy=strategy,
                symbols=symbols,
                start_date=start_date,
                end_date=end_date,
                parameters=params,
                initial_capital=initial_capital,
            )
            results.append(result)

        # Sort by metric
        results.sort(
            key=lambda r: getattr(r.metrics, metric, 0),
            reverse=True,
        )

        return results
