"""Compatibility wrapper for the QMT broker adapter.

The task assignment specifies this file path. The implementation lives in
src/execution/brokers/qmt_broker.py.
"""

from __future__ import annotations

from .brokers.qmt_broker import BrokerExecutionResult, QMTBroker

__all__ = ["QMTBroker", "BrokerExecutionResult"]
