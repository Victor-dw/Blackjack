"""Integration test harness for end-to-end pipeline validation.

This module provides the integration testing framework for P6 旁路质量:
- End-to-end pipeline tests
- Data flow validation
- Record persistence verification
- Event contract compliance

Key test scenarios:
1. Full pipeline: perception -> variables -> signals -> strategy -> risk -> execution -> postmortem
2. Trade recording: execution events -> trade_recorder -> PostgreSQL
3. Decision evaluation: trade_record -> decision_evaluator -> quality scores
4. Backtest isolation: verify backtest cannot access trade-network
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Callable
from pathlib import Path


@dataclass
class TestEvent:
    """A test event for pipeline validation."""
    stream: str
    envelope: dict[str, Any]
    expected_outputs: list[str] = field(default_factory=list)
    should_fail: bool = False


@dataclass
class TestResult:
    """Result of a test case."""
    name: str
    passed: bool
    duration_ms: float
    error: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "details": self.details,
        }


@dataclass
class TestSuiteResult:
    """Result of a test suite run."""
    suite_name: str
    total: int
    passed: int
    failed: int
    duration_ms: float
    results: list[TestResult]

    @property
    def success_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "success_rate": self.success_rate,
            "duration_ms": self.duration_ms,
            "results": [r.to_dict() for r in self.results],
        }


class MockMessageBus:
    """Mock message bus for integration testing."""

    def __init__(self) -> None:
        self._published: list[tuple[str, dict[str, Any]]] = []
        self._handlers: dict[str, list[Callable]] = {}

    def publish(self, stream: str, event) -> None:
        """Record published events."""
        from dataclasses import asdict
        if hasattr(event, '__dataclass_fields__'):
            envelope_dict = asdict(event)
            if 'produced_at' in envelope_dict and hasattr(envelope_dict['produced_at'], 'isoformat'):
                envelope_dict['produced_at'] = envelope_dict['produced_at'].isoformat()
        else:
            envelope_dict = event
        self._published.append((stream, envelope_dict))

    def get_published(self, stream: Optional[str] = None) -> list[tuple[str, dict]]:
        """Get published events, optionally filtered by stream."""
        if stream is None:
            return self._published
        return [(s, e) for s, e in self._published if s == stream]

    def clear(self) -> None:
        """Clear published events."""
        self._published.clear()


class IntegrationTestHarness:
    """Harness for running integration tests.
    
    This harness validates:
    1. Event contracts (schema validation)
    2. Data flow through the pipeline
    3. Record persistence to database
    4. Network isolation (backtest cannot access trade-network)
    """

    def __init__(
        self,
        mock_bus: Optional[MockMessageBus] = None,
    ) -> None:
        self._bus = mock_bus or MockMessageBus()
        self._results: list[TestResult] = []

    def run_contract_tests(self) -> TestSuiteResult:
        """Run contract validation tests using golden events."""
        import time
        from src.contracts.validation import validate_envelope_dict

        start = time.time()
        results: list[TestResult] = []
        golden_dir = Path("contracts/golden_events/v1")

        for path in sorted(golden_dir.glob("*.json")):
            test_start = time.time()
            try:
                ev = json.loads(path.read_text(encoding="utf-8"))
                is_invalid = "invalid" in path.name

                if is_invalid:
                    try:
                        validate_envelope_dict(ev)
                        results.append(TestResult(
                            name=f"contract:{path.name}",
                            passed=False,
                            duration_ms=(time.time() - test_start) * 1000,
                            error="Expected validation to fail but it passed",
                        ))
                    except ValueError:
                        results.append(TestResult(
                            name=f"contract:{path.name}",
                            passed=True,
                            duration_ms=(time.time() - test_start) * 1000,
                        ))
                else:
                    validate_envelope_dict(ev)
                    results.append(TestResult(
                        name=f"contract:{path.name}",
                        passed=True,
                        duration_ms=(time.time() - test_start) * 1000,
                    ))

            except Exception as e:
                results.append(TestResult(
                    name=f"contract:{path.name}",
                    passed=False,
                    duration_ms=(time.time() - test_start) * 1000,
                    error=str(e),
                ))

        total_time = (time.time() - start) * 1000
        passed = sum(1 for r in results if r.passed)

        return TestSuiteResult(
            suite_name="contract_validation",
            total=len(results),
            passed=passed,
            failed=len(results) - passed,
            duration_ms=total_time,
            results=results,
        )

    def run_trade_recorder_tests(self) -> TestSuiteResult:
        """Run trade recorder integration tests."""
        import time
        from src.postmortem.trade_recorder import (
            TradeRecorder, InMemoryTradeRecordRepository,
            TradeStatus, DecisionSnapshot,
        )

        start = time.time()
        results: list[TestResult] = []

        # Test 1: Record executed order
        test_start = time.time()
        try:
            repo = InMemoryTradeRecordRepository()
            recorder = TradeRecorder(repo, self._bus)

            payload = {
                "order_id": "ord-test-001",
                "symbol": "600000.SH",
                "ts": "2026-01-01T10:00:00+08:00",
                "status": "FILLED",
                "filled_qty": 100,
                "avg_price": 10.50,
                "broker": "qmt-sandbox",
                "side": "BUY",
                "qty": 100,
            }

            snapshot = DecisionSnapshot(
                market_vars={"valuation_percentile": 45.0},
                stock_vars={"relative_strength": 65.0},
                signal_snapshot={"opportunity_score": 72.0},
                regime_state="BULL",
                strategy_triggered="trend_following",
            )

            record = recorder.record_execution(
                event_id="evt-exec-001",
                trace_id="trace-001",
                payload=payload,
                is_success=True,
                decision_snapshot=snapshot,
            )

            # Verify record
            assert record.status == TradeStatus.EXECUTED
            assert record.symbol == "600000.SH"
            assert record.order.filled_qty == 100

            # Verify persistence
            retrieved = repo.get_by_id(record.trade_id)
            assert retrieved is not None
            assert retrieved.trade_id == record.trade_id

            results.append(TestResult(
                name="trade_recorder:record_executed_order",
                passed=True,
                duration_ms=(time.time() - test_start) * 1000,
            ))

        except Exception as e:
            results.append(TestResult(
                name="trade_recorder:record_executed_order",
                passed=False,
                duration_ms=(time.time() - test_start) * 1000,
                error=str(e),
            ))

        # Test 2: Record failed order
        test_start = time.time()
        try:
            repo = InMemoryTradeRecordRepository()
            recorder = TradeRecorder(repo, self._bus)

            payload = {
                "order_id": "ord-test-002",
                "symbol": "000001.SZ",
                "ts": "2026-01-01T10:05:00+08:00",
                "status": "REJECTED",
                "filled_qty": 0,
                "avg_price": 0,
                "broker": "qmt-sandbox",
            }

            record = recorder.record_execution(
                event_id="evt-exec-002",
                trace_id="trace-002",
                payload=payload,
                is_success=False,
            )

            assert record.status == TradeStatus.FAILED
            assert record.order.filled_qty == 0

            results.append(TestResult(
                name="trade_recorder:record_failed_order",
                passed=True,
                duration_ms=(time.time() - test_start) * 1000,
            ))

        except Exception as e:
            results.append(TestResult(
                name="trade_recorder:record_failed_order",
                passed=False,
                duration_ms=(time.time() - test_start) * 1000,
                error=str(e),
            ))

        total_time = (time.time() - start) * 1000
        passed = sum(1 for r in results if r.passed)

        return TestSuiteResult(
            suite_name="trade_recorder",
            total=len(results),
            passed=passed,
            failed=len(results) - passed,
            duration_ms=total_time,
            results=results,
        )

    def run_decision_evaluator_tests(self) -> TestSuiteResult:
        """Run decision evaluator integration tests."""
        import time
        from src.postmortem.trade_recorder import (
            TradeRecord, TradeStatus, OrderDetails, DecisionSnapshot,
        )
        from src.postmortem.decision_evaluator import (
            DecisionQualityEvaluator, OutcomeClassification,
        )

        start = time.time()
        results: list[TestResult] = []

        # Test 1: Good decision classification
        test_start = time.time()
        try:
            evaluator = DecisionQualityEvaluator()

            # Good decision with all required data
            record = TradeRecord(
                trade_id="trd-test-001",
                trace_id="trace-001",
                symbol="600000.SH",
                timestamp=datetime.now(timezone.utc),
                status=TradeStatus.EXECUTED,
                order=OrderDetails(
                    order_id="ord-001",
                    side="BUY",
                    qty=100,
                    filled_qty=100,
                    avg_price=10.50,
                    broker="qmt-sandbox",
                ),
                decision_snapshot=DecisionSnapshot(
                    market_vars={"valuation_percentile": 45, "sentiment": 0.6, "volatility": 0.15},
                    stock_vars={"relative_strength": 65, "volume_signal": 1.2, "trend": "UP"},
                    signal_snapshot={"opportunity_score": 72, "confidence": 80},
                    regime_state="BULL",
                    strategy_triggered="trend_following",
                    kelly_calculation={"f_star": 0.12, "conservative_factor": 0.5},
                    risk_check_result={"can_trade": True, "reason": "within_limits"},
                ),
                pnl=150.0,
            )

            report = evaluator.evaluate(record, hide_result=False)

            assert report.scores.overall >= 0.7, f"Expected good decision score, got {report.scores.overall}"
            assert report.classification == OutcomeClassification.DESERVED_WIN

            results.append(TestResult(
                name="decision_evaluator:good_decision_profit",
                passed=True,
                duration_ms=(time.time() - test_start) * 1000,
                details={"overall_score": report.scores.overall},
            ))

        except Exception as e:
            results.append(TestResult(
                name="decision_evaluator:good_decision_profit",
                passed=False,
                duration_ms=(time.time() - test_start) * 1000,
                error=str(e),
            ))

        # Test 2: Bad decision (missing data)
        test_start = time.time()
        try:
            evaluator = DecisionQualityEvaluator()

            # Bad decision - missing critical data
            record = TradeRecord(
                trade_id="trd-test-002",
                trace_id="trace-002",
                symbol="000001.SZ",
                timestamp=datetime.now(timezone.utc),
                status=TradeStatus.EXECUTED,
                order=OrderDetails(
                    order_id="ord-002",
                    side="BUY",
                    qty=100,
                    filled_qty=100,
                    avg_price=15.00,
                    broker="qmt-sandbox",
                ),
                decision_snapshot=DecisionSnapshot(),  # Empty snapshot
                pnl=50.0,  # Profit despite bad decision
            )

            report = evaluator.evaluate(record, hide_result=False)

            assert report.scores.overall < 0.7, f"Expected poor decision score, got {report.scores.overall}"
            assert report.classification == OutcomeClassification.DANGEROUS_WIN
            assert len(report.issues) > 0

            results.append(TestResult(
                name="decision_evaluator:bad_decision_profit",
                passed=True,
                duration_ms=(time.time() - test_start) * 1000,
                details={"issues_count": len(report.issues)},
            ))

        except Exception as e:
            results.append(TestResult(
                name="decision_evaluator:bad_decision_profit",
                passed=False,
                duration_ms=(time.time() - test_start) * 1000,
                error=str(e),
            ))

        total_time = (time.time() - start) * 1000
        passed = sum(1 for r in results if r.passed)

        return TestSuiteResult(
            suite_name="decision_evaluator",
            total=len(results),
            passed=passed,
            failed=len(results) - passed,
            duration_ms=total_time,
            results=results,
        )

    def run_backtest_isolation_tests(self) -> TestSuiteResult:
        """Run tests to verify backtest is isolated from trade-network."""
        import time

        start = time.time()
        results: list[TestResult] = []

        # Test: Verify backtest only accesses compute-network
        test_start = time.time()
        try:
            from src.evolution.backtest_engine import BacktestEngine, InMemoryDataProvider

            # Create backtest engine with mock data
            provider = InMemoryDataProvider()
            engine = BacktestEngine(provider, message_bus=self._bus)

            # Verify engine has no access to trade-related modules
            # (This is a structural check - in production, Docker network isolation enforces this)
            
            # The engine should only use data_provider and message_bus
            assert hasattr(engine, '_data_provider')
            assert hasattr(engine, '_bus')
            
            # Verify no trade-network related attributes
            assert not hasattr(engine, '_broker')
            assert not hasattr(engine, '_qmt_client')
            assert not hasattr(engine, '_trade_redis')

            results.append(TestResult(
                name="backtest_isolation:no_trade_network_access",
                passed=True,
                duration_ms=(time.time() - test_start) * 1000,
            ))

        except Exception as e:
            results.append(TestResult(
                name="backtest_isolation:no_trade_network_access",
                passed=False,
                duration_ms=(time.time() - test_start) * 1000,
                error=str(e),
            ))

        total_time = (time.time() - start) * 1000
        passed = sum(1 for r in results if r.passed)

        return TestSuiteResult(
            suite_name="backtest_isolation",
            total=len(results),
            passed=passed,
            failed=len(results) - passed,
            duration_ms=total_time,
            results=results,
        )

    def run_health_monitor_tests(self) -> TestSuiteResult:
        """Run health monitor integration tests."""
        import time
        from src.evolution.health_monitor import HealthMonitor, AlertLevel

        start = time.time()
        results: list[TestResult] = []

        # Test 1: Normal operation
        test_start = time.time()
        try:
            monitor = HealthMonitor()

            # Record some winning trades
            for i in range(10):
                day = f"{i+1:02d}"  # Zero-padded day
                monitor.record_trade("trend_following", {
                    "pnl": 100.0,
                    "timestamp": f"2026-01-{day}T10:00:00+08:00",
                    "symbol": "600000.SH",
                })

            report = monitor.check_health("trend_following")

            assert report.overall_level == AlertLevel.GREEN
            assert report.metrics.recent_win_rate == 1.0

            results.append(TestResult(
                name="health_monitor:normal_operation",
                passed=True,
                duration_ms=(time.time() - test_start) * 1000,
            ))

        except Exception as e:
            results.append(TestResult(
                name="health_monitor:normal_operation",
                passed=False,
                duration_ms=(time.time() - test_start) * 1000,
                error=str(e),
            ))

        # Test 2: Loss streak alert
        test_start = time.time()
        try:
            monitor = HealthMonitor()

            # Record losing streak
            for i in range(6):
                monitor.record_trade("mean_reversion", {
                    "pnl": -50.0,
                    "timestamp": f"2026-01-0{i+1}T10:00:00+08:00",
                    "symbol": "000001.SZ",
                })

            report = monitor.check_health("mean_reversion")

            assert report.overall_level == AlertLevel.RED
            assert report.metrics.current_loss_streak >= 5
            assert any(a.metric_name == "loss_streak" for a in report.alerts)

            results.append(TestResult(
                name="health_monitor:loss_streak_alert",
                passed=True,
                duration_ms=(time.time() - test_start) * 1000,
            ))

        except Exception as e:
            results.append(TestResult(
                name="health_monitor:loss_streak_alert",
                passed=False,
                duration_ms=(time.time() - test_start) * 1000,
                error=str(e),
            ))

        total_time = (time.time() - start) * 1000
        passed = sum(1 for r in results if r.passed)

        return TestSuiteResult(
            suite_name="health_monitor",
            total=len(results),
            passed=passed,
            failed=len(results) - passed,
            duration_ms=total_time,
            results=results,
        )

    def run_all(self) -> dict[str, TestSuiteResult]:
        """Run all integration test suites."""
        suites = {
            "contract_validation": self.run_contract_tests,
            "trade_recorder": self.run_trade_recorder_tests,
            "decision_evaluator": self.run_decision_evaluator_tests,
            "backtest_isolation": self.run_backtest_isolation_tests,
            "health_monitor": self.run_health_monitor_tests,
        }

        results = {}
        for name, runner in suites.items():
            try:
                results[name] = runner()
            except Exception as e:
                results[name] = TestSuiteResult(
                    suite_name=name,
                    total=1,
                    passed=0,
                    failed=1,
                    duration_ms=0,
                    results=[TestResult(
                        name=f"{name}:suite_error",
                        passed=False,
                        duration_ms=0,
                        error=str(e),
                    )],
                )

        return results

    def print_summary(self, results: dict[str, TestSuiteResult]) -> None:
        """Print a summary of test results."""
        print("\n" + "=" * 60)
        print("INTEGRATION TEST SUMMARY")
        print("=" * 60)

        total_tests = 0
        total_passed = 0
        total_failed = 0

        for name, suite in results.items():
            status = "✅" if suite.failed == 0 else "❌"
            print(f"\n{status} {suite.suite_name}")
            print(f"   Passed: {suite.passed}/{suite.total} ({suite.success_rate*100:.0f}%)")
            print(f"   Duration: {suite.duration_ms:.1f}ms")

            if suite.failed > 0:
                for r in suite.results:
                    if not r.passed:
                        print(f"   ❌ {r.name}: {r.error}")

            total_tests += suite.total
            total_passed += suite.passed
            total_failed += suite.failed

        print("\n" + "-" * 60)
        overall_status = "✅ ALL PASSED" if total_failed == 0 else "❌ SOME FAILED"
        print(f"{overall_status}: {total_passed}/{total_tests} tests passed")
        print("=" * 60 + "\n")


def run_integration_tests() -> int:
    """Run integration tests and return exit code."""
    harness = IntegrationTestHarness()
    results = harness.run_all()
    harness.print_summary(results)

    total_failed = sum(s.failed for s in results.values())
    return 1 if total_failed > 0 else 0


if __name__ == "__main__":
    import sys
    from pathlib import Path
    # Add repository root to path for imports
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    sys.exit(run_integration_tests())

