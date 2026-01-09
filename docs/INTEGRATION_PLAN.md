# 联调计划

## 时间节奏（2 周冲刺）

```
Week 1: 并行开发
├── Day 1-2: P1 补齐 CI + replay 工具
├── Day 1-5: P2-P6 各自实现 + 单元测试
└── Day 5: 首次集成（冒烟测试）

Week 2: 联调收敛
├── Day 6-7: 修复集成问题
├── Day 8-9: 端到端测试（dry-run）
├── Day 10: QMT 接入（双人审阅 + 隔离环境）
└── Day 10: 上线验收
```

---

## 每日规范

### 代码合入规则

| 时间点 | 动作 |
|--------|------|
| 每天 18:00 前 | 提交 PR 到 `develop` 分支 |
| 每天 18:00 | P1 跑 CI（pytest + contract test + compileall） |
| CI 通过后 | 合入 `develop` |

### 自测要求

每个 PR 必须包含：
1. **单元测试**：覆盖核心逻辑
2. **契约测试**：用 golden_events 验证输入输出
3. **compileall 通过**：无语法错误

---

## 集成测试检查点

### Day 5 首次集成

| 检查项 | 负责人 | 通过标准 |
|--------|--------|----------|
| L1→L2 数据流通 | P2 | `variables.*.computed.v1` 能收到事件 |
| L2→L3 数据流通 | P3 | `signals.opportunity.scored.v1` 能收到事件 |
| L3→L4 数据流通 | P4 | `strategy.candidate_action.generated.v1` 能收到事件 |
| L4→L5 数据流通 | P5 | `risk.order.approved.v1` 能收到事件 |
| L5→L6 dry-run | P5 | executor-dry 能处理审批事件 |
| L7 记录落库 | P6 | PostgreSQL 有 trade_record |

### Day 8 端到端测试

| 场景 | 输入 | 期望输出 |
|------|------|----------|
| Happy Path | 1 条 market_data | execution.order.executed.v1 |
| 风控拒绝 | 超限仓位请求 | risk.order.rejected.v1 |
| 重复事件 | 相同 event_id × 2 | 只处理 1 次（幂等） |
| 脏数据 | 缺字段的事件 | 进入 DLQ |

### Day 10 QMT 接入

| 前置条件 | 检查人 |
|----------|--------|
| ✅ dry-run 全部通过 | P5 + P6 |
| ✅ trade-bridge 白名单正确 | P1 |
| ✅ executor-live 只在 trade-network | P1 |
| ✅ 双人 Code Review | P5 + P1 |
| ✅ 小资金测试账户 | 团队负责人 |

---

## 沟通机制

| 频率 | 形式 | 内容 |
|------|------|------|
| 每天 10:00 | 站会 15min | 昨日进展 / 今日计划 / 阻塞 |
| Day 5, Day 8 | 集成会 1h | 联调问题 + 修复分配 |
| 随时 | 群消息 | 契约变更必须 @全员 |

---

## 风险预案

| 风险 | 预案 |
|------|------|
| 某层进度落后 | P6 支援（旁路系统可后移） |
| 契约需要调整 | P1 发 v1.1 或 v2，禁止偷改 v1 |
| QMT 接入问题 | Day 10 之前不接真钱，用 stub |
| 联调发现架构问题 | 立即拉会，P1 + 相关人决策 |

