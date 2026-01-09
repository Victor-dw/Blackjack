# Stream Map (v1)

全链路事件流清单。**这是并行开发的核心契约。**

---

## 1. 核心流水线

```
L1 Perception ─→ L2 Variables ─→ L3 Signals ─→ L4 Strategies ─→ L5 Risk ─→ L6 Execution
```

| 层 | 输入 Stream | 输出 Stream | 生产者 | 消费者 |
|----|-------------|-------------|--------|--------|
| L1 | 外部数据源 | `perception.market_data.collected.v1` | perception | variables |
| L1 | - | `perception.heartbeat.v1` | perception | monitor |
| L2 | `perception.market_data.collected.v1` | `variables.market.computed.v1` | variables | signals |
| L2 | `perception.market_data.collected.v1` | `variables.stock.computed.v1` | variables | signals |
| L3 | `variables.*.computed.v1` | `signals.opportunity.scored.v1` | signals | strategies |
| L3 | `variables.*.computed.v1` | `signals.regime.detected.v1` | signals | strategies |
| L4 | `signals.opportunity.scored.v1` | `strategy.candidate_action.generated.v1` | strategies | risk |
| L5 | `strategy.candidate_action.generated.v1` | `risk.order.approved.v1` | risk | execution |
| L5 | `strategy.candidate_action.generated.v1` | `risk.order.rejected.v1` | risk | postmortem |
| L6 | `risk.order.approved.v1` | `execution.order.executed.v1` | execution | postmortem |
| L6 | `risk.order.approved.v1` | `execution.order.failed.v1` | execution | postmortem |

---

## 2. 旁路系统

| 层 | 输入 Stream | 输出 Stream | 生产者 | 消费者 |
|----|-------------|-------------|--------|--------|
| L7 | `risk.order.*`, `execution.order.*` | `postmortem.trade_record.created.v1` | postmortem | evolution, API |
| L8 | 历史数据 (DB) | `evolution.backtest.completed.v1` | evolution | API |
| L8 | 历史数据 (DB) | `evolution.parameter.proposed.v1` | evolution | **人工审批** |

---

## 3. 死信队列 (DLQ)

每个 stream 自动生成对应的 DLQ：

```
dlq.<base_stream>.v1
```

例如：`dlq.perception.market_data.collected.v1`

---

## 4. Consumer Group 命名规范

```
<consuming_service>-group
```

| Service | Group Name |
|---------|------------|
| variables | `variables-group` |
| signals | `signals-group` |
| strategies | `strategies-group` |
| risk | `risk-group` |
| execution | `execution-group` |
| postmortem | `postmortem-group` |
| trade-bridge | `trade-bridge` |

---

## 5. 网络隔离

```
┌─────────────────────────────────────────────────────────────┐
│  compute-network (redis-compute)                            │
│  L1 → L2 → L3 → L4 → L5 → postmortem → evolution → API     │
└─────────────────────────────────────────────────────────────┘
                          │
                   [trade-bridge]  ← 唯一网关，白名单转发
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  trade-network (redis-trade)                                │
│  executor-live → QMT/券商                                   │
└─────────────────────────────────────────────────────────────┘
```

