# 6 人分工表

## 角色分配

| 角色 | 负责模块 | 核心职责 | 交付物 |
|------|----------|----------|--------|
| **P1 底座** | core, contracts, infra | 消息总线、契约验证、Docker、CI | message_bus, validation, compose |
| **P2 数据** | L1 perception, L2 variables | 行情采集、因子计算 | data_collector, market_vars, stock_vars |
| **P3 信号** | L3 signals | 信号合成、市场状态识别 | signal_composer, regime_detector |
| **P4 策略** | L4 strategies | 策略逻辑、动作生成 | base_strategy, trend/mean/event |
| **P5 风控执行** | L5 risk, L6 execution | 风控审批、订单执行 | kelly, defense, executor, QMT适配 |
| **P6 旁路质量** | L7 postmortem, L8 evolution, 联调 | 复盘、回测、集成测试 | trade_recorder, backtest_engine, harness |

---

## 详细任务清单

### P1 底座（已完成 80%）

| 任务 | 状态 | 说明 |
|------|------|------|
| ✅ message_bus.py | 完成 | ACK/重试/DLQ/幂等 |
| ✅ contracts/validation.py | 完成 | v1 严格校验 |
| ✅ golden_events/ | 完成 | 10 个测试向量 |
| ✅ docker-compose.yml | 完成 | 网络隔离 |
| ⬜ CI pipeline | 待做 | GitHub Actions: pytest + compileall |
| ⬜ replay 工具 | 待做 | 用于联调的事件回放脚本 |

### P2 数据

| 任务 | 输入 | 输出 | 说明 |
|------|------|------|------|
| ⬜ data_collector.py | 外部API/QMT | `perception.market_data.collected.v1` | 行情采集 |
| ⬜ market_vars.py | market_data | `variables.market.computed.v1` | 大盘因子 |
| ⬜ stock_vars.py | market_data | `variables.stock.computed.v1` | 个股因子 |
| ⬜ normalizer.py | - | - | 因子归一化 |

### P3 信号

| 任务 | 输入 | 输出 | 说明 |
|------|------|------|------|
| ⬜ signal_composer.py | variables.*.computed | `signals.opportunity.scored.v1` | 机会评分 |
| ⬜ regime_detector.py | variables.market.computed | `signals.regime.detected.v1` | 牛熊识别 |
| ⬜ volume_price.py | - | - | 量价特征 |

### P4 策略

| 任务 | 输入 | 输出 | 说明 |
|------|------|------|------|
| ⬜ base_strategy.py | - | - | 策略抽象基类 |
| ⬜ trend_following.py | opportunity + regime | `strategy.candidate_action.generated.v1` | 趋势跟踪 |
| ⬜ mean_reversion.py | opportunity + regime | `strategy.candidate_action.generated.v1` | 均值回归 |
| ⬜ event_driven.py | opportunity + regime | `strategy.candidate_action.generated.v1` | 事件驱动 |
| ⬜ coordinator.py | - | - | 多策略协调 |

### P5 风控执行

| 任务 | 输入 | 输出 | 说明 |
|------|------|------|------|
| ⬜ kelly.py | 胜率/赔率 | - | Kelly 仓位计算 |
| ⬜ defense.py | 账户状态 | - | 破产概率/连亏保护 |
| ⬜ position_allocator.py | candidate_action | `risk.order.approved/rejected.v1` | 最终审批 |
| ⬜ executor.py | order.approved | `execution.order.executed/failed.v1` | 订单执行 |
| ⬜ qmt_broker.py | - | - | QMT 适配器（最后接入） |

### P6 旁路质量

| 任务 | 输入 | 输出 | 说明 |
|------|------|------|------|
| ⬜ trade_recorder.py | order.executed | `postmortem.trade_record.created.v1` | 交易记录落库 |
| ⬜ decision_evaluator.py | trade_record | - | 决策质量评估 |
| ⬜ backtest_engine.py | 历史数据 | `evolution.backtest.completed.v1` | 回测引擎 |
| ⬜ health_monitor.py | - | - | 策略健康监控 |
| ⬜ integration harness | - | - | 集成测试框架 |

---

## 依赖关系（开发顺序）

```
P1 底座 ────────────────────────────────────────────────────┐
    │                                                       │
    ├── P2 数据 ─┐                                         │
    │            ├── P3 信号 ─── P4 策略 ─── P5 风控执行    │
    │            │                                         │
    └── P6 旁路质量 ←──────────────────────────────────────┘
```

**关键点：P1 已完成 80%，其他 5 人可立即并行开发。**

