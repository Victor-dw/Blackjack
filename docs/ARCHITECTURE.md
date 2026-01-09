# Blackjack Operating System - 架构设计文档

> "在混沌中提取可控优势的操作系统"

## 一、核心理念

### 1.1 项目定位

这不是一个炒股软件，而是一套**概率优势操作系统**。

核心思想来自马恺文（Jeff Ma）的决策哲学：
- **算牌思维**：不预测涨跌，只识别统计优势
- **凯利准则**：活着比赢更重要
- **观察员-大玩家分离**：AI算牌，策略执行
- **决策vs结果分离**：不因结果否定决策

### 1.2 核心公式

```
赢 = (识别正预期价值) × (严格的头寸管理) × (排除情绪的重复执行)
```

### 1.3 设计原则

| 原则 | 说明 |
|-----|------|
| AI与执行隔离 | AI只输出参数，不参与实盘决策 |
| 一切皆变量 | 将混沌信息转化为可计算的数字 |
| 禁止个人发挥 | 执行层只读参数，机械执行 |
| 结果与决策分离 | 复盘只看决策质量，不看盈亏 |
| 活着优先 | 破产概率是最高优先级约束 |

---

## 二、系统架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                    BLACKJACK OPERATING SYSTEM                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ 感知层   │→│ 变量层   │→│ 信号层   │→│ 策略层   │       │
│  │Perception│  │Variables │  │ Signals  │  │Strategies│       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
│       ↑                                          ↓             │
│  ┌──────────┐                            ┌──────────┐         │
│  │ 迭代层   │←─────── 复盘层 ←───────────│ 风控层   │         │
│  │Evolution │        Post-Mortem         │Risk Ctrl │         │
│  └──────────┘                            └────┬─────┘         │
│                                               ↓               │
│                                         ┌──────────┐         │
│                                         │ 执行层   │         │
│                                         │Execution │         │
│                                         └──────────┘         │
│                                               ↓               │
│                                         ┌──────────┐         │
│                                         │Trade Node │         │
│                                         │(Win/QMT)  │         │
│                                         └──────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、八层架构详解

### L1: 感知层 (Perception Layer)

**职责**：收集牌桌上的一切信息，并将其变成**可追溯、可重放、可校验**的原始数据流。

**数据源**：

| 类别 | 数据源（示例） | 频率 | 关键约束 |
|-----|---------------|------|----------|
| 行情数据 | Tushare/通达信/聚宽 | 实时/日线 | 交易日历一致性、复权口径、停牌/临停标记 |
| 财报数据 | 东方财富/同花顺 | 季度 | 披露日与“报告期”区分、口径变更追踪 |
| 资金流向 | Level-2/北向资金 | 实时 | 延迟/缺口可接受但必须可观测（SLA） |
| 舆情事件 | 新闻爬虫/公告监控 | 实时 | 去重、来源可信度、事件时间戳准确性 |
| 政策动态 | 证监会/交易所公告 | 事件驱动 | 强一致：宁可慢，不可错（误报成本极高） |

**感知层的“底线”**（必须写进工程约束）：
- **原始区不可变（immutable raw）**：先落盘再清洗，任何修正以新版本/补丁形式追加。
- **幂等采集**：每条数据都有 `source_event_id`/`ingest_id`，重复拉取不会产生重复事件。
- **水位线（watermark）与新鲜度（freshness）**：明确每类数据“应到时间”和“允许迟到”。
- **可观测性**：延迟、缺失率、异常率、源站错误码必须可监控告警。

**输出（契约）**：清洗后的原始数据流（仍保持“最少推断”原则）。

- `RawMarketEvent`：{`event_id`, `source`, `ts`, `symbol`, `payload`, `checksum`, `ingested_at`}
- `Bar/OHLCV`：统一字段 + 明确时区/交易日历 + 复权标记
- `CorporateAction/Event`：公告/事件的结构化记录（可回放）

---

### L2: 变量层 (Variables Layer)

**职责**：把信息转化为可计算的数字

**核心变量组**：

```yaml
市场变量 (Market Variables):
  - market_valuation_percentile   # 全市场估值分位 [0-100]
  - volatility_compression        # 波动率压缩程度 [0-1]
  - market_sentiment_cycle        # 情绪周期阶段 [恐慌/犹豫/乐观/疯狂]
  - money_flow_heat               # 资金热度 [-1, 1]
  - foreign_capital_flow          # 外资流向 [-1, 1]

个股变量 (Stock Variables):
  - volume_price_signal           # 量价信号（你的核心模型）
  - relative_strength             # 相对强弱 [0-100]
  - fundamental_score             # 基本面评分 [0-100]
  - main_force_behavior           # 主力行为 [吸筹/洗盘/拉升/出货/无]
  - l2_active_buy_sell_ratio      # L2主动买卖比

环境变量 (Environment Variables):
  - policy_intervention_prob      # 政策干预概率 [0-1]
  - rule_change_alert             # 规则变化预警 [bool]
  - regime_state                  # 市场状态 [牛市/熊市/震荡/转折]
```

**变量归一化**：所有变量标准化到统一区间，便于跨变量比较

---

### L3: 信号层 (Signals Layer)

**职责**：这副牌现在有多热？

**信号合成**：

```python
# 核心信号计算（你的量价模型）
def calculate_volume_price_signal(stock):
    effort = current_turnover_rate / historical_avg_turnover
    result = current_change_pct / historical_avg_volatility
    signal = effort * result
    return normalize(signal)

# 机会评分
opportunity_score = weighted_sum([
    (market_signal, 0.3),
    (stock_signal, 0.4),
    (timing_signal, 0.2),
    (risk_signal, -0.1)  # 负权重，风险越高分越低
])
```

**Regime Detection（市场状态识别）**：

| 状态 | 识别条件 | 策略响应 |
|-----|---------|---------|
| 牛市 | 估值分位>70 + 外资持续流入 | 趋势策略激活 |
| 熊市 | 估值分位<30 + 资金持续流出 | 防守为主 |
| 震荡 | 波动率压缩 + 无明显趋势 | 均值回归策略 |
| 结构跳变 | 单日异动>3σ | 暂停交易，重新评估 |

**输出**：
- `opportunity_score` (0-100)
- `confidence_level` (0-100)
- `regime_state` (枚举)
- `warning_flags` (列表)

---

### L4: 策略层 (Strategies Layer)

**职责**：什么条件下出手？出手多少？

**多策略引擎**：

```yaml
趋势跟踪策略:
  适用Regime: [牛市, 上涨趋势]
  入场条件:
    - 量价信号 > 阈值A
    - 相对强弱 > 60
    - 外资连续N日流入
  出场条件:
    - 止损: -X%
    - 止盈: 移动止盈
    - 信号反转

均值回归策略:
  适用Regime: [震荡]
  入场条件:
    - 估值分位 < 20
    - RSI < 30
    - 波动率压缩后放大
  出场条件:
    - 回归均值
    - 时间止损

事件驱动策略:
  适用Regime: [任意]
  入场条件:
    - 舆情事件检测
    - 历史相似事件胜率 > 60%
  出场条件:
    - 事件窗口结束
```

#### 4.1 多周期（日线 + 分钟）管辖权：Daily Gate + Minute Execution

> 目标：同时支持日线与分钟级别，但避免“互相打架/破坏统计优势”。

**推荐默认模式（强约束）**：
- **日线策略 = 准入与预算**：决定“是否允许交易、允许交易的股票池、该标的最大风险预算/仓位预算”。
- **分钟策略 = 择时与执行**：只能在日线授予的预算范围内做入场/出场优化；不得突破日线预算。

**冲突处理（写死为规则，不允许人为临时解释）**：
- 日线 `HOLD` 且未触发风控 → 分钟策略只能做“更优入场/更优出场”，不能反向开仓。
- 日线触发“禁入/冻结” → 分钟策略全部停止。
- 同一标的同一时刻出现 BUY 与 SELL → 视为不确定，取消操作。

**实现形态**：
- `StrategySignal.time_frame` 明确来源（DAILY/MINUTE）。
- 风控层对每个标的维护 `position_budget_daily` 与 `risk_budget_daily`。

**策略输出**：
```python
@dataclass
class StrategySignal:
    action: str           # BUY / SELL / HOLD
    stock_code: str       # 标的代码
    entry_price: float    # 入场价
    stop_loss: float      # 止损价
    take_profit: float    # 止盈价
    win_prob: float       # 历史胜率 p
    odds: float           # 盈亏比 b
    time_frame: str       # DAILY / MINUTE
    strategy_name: str    # 策略名称
```


---

### L5: 风控层 (Risk Control Layer)

**职责**：活着比赢更重要

#### 5.1 凯利准则计算器

```python
def kelly_criterion(win_prob: float, odds: float) -> float:
    """
    计算最优仓位比例

    f* = (b*p - q) / b

    其中:
    - p = 胜率
    - q = 1 - p = 败率
    - b = 赔率（盈亏比）
    """
    p = win_prob
    q = 1 - p
    b = odds

    f_star = (b * p - q) / b

    # 实际使用半凯利或更保守
    conservative_factor = 0.5

    return max(0, f_star * conservative_factor)
```

#### 5.2 硬风控（Circuit Breakers，强制生效）

> 硬风控优先级高于任何策略信号。触发即降档/冻结，直到人工解除或满足恢复条件。

**建议内置硬约束**：
- `daily_loss_limit`：单日最大亏损（达到即停止新开仓）
- `weekly_drawdown_limit` / `monthly_drawdown_limit`：周/月最大回撤
- `max_single_name_position`：单标的最大仓位
- `max_sector_exposure`：单行业/题材最大敞口
- `liquidity_guard`：流动性不足禁止交易（成交额/换手率/盘口深度阈值）
- `limit_up_down_guard`：涨跌停/一字板/停牌/临停 → 禁止下单或自动撤单
- `regime_transition_freeze`：Regime=TRANSITION 或 结构跳变 → 禁止开新仓

#### 5.3 软风控（Kelly + 波动率目标 + 相关性去重）

**软风控用于“仓位缩放”，不用于“强行预测”**：
- **半凯利/四分之一凯利**：将理论凯利仓位乘以保守系数
- **波动率目标（Vol Targeting）**：波动率上升 → 自动降仓
- **相关性去重**：高度相关标的合并看待，限制叠加暴露

#### 5.4 风险-of-ruin（破产风险）评估（建议用 Monte Carlo）

> 说明：A股的滑点、涨跌停不可成交、隔夜跳空会让“简单公式”严重失真。
> 本项作为**风险评估指标**，不作为唯一决策依据；最终以硬风控为准。

（简化示例，仅用于直觉参考）

```python
def bankruptcy_probability(win_prob: float, num_bets: int) -> float:
    """
		简化破产概率（仅直觉参考，实盘应改为 Monte Carlo）

    P(破产) = ((1-p)/p)^n
    """
    p = win_prob
    if p >= 0.5:
        return ((1 - p) / p) ** num_bets
    else:
        return 1.0  # 胜率<50%时，长期必然破产
```

#### 5.5 A股防御权重（规则干扰/老千权重）

```python
def calculate_defense_weight(env_vars: dict) -> float:
    """
    根据环境变量计算防御权重
    权重越低，仓位越保守
    """
    weight = 1.0

    # 政策干预风险
    if env_vars['policy_intervention_prob'] > 0.5:
        weight *= 0.5

    # 规则变化预警
    if env_vars['rule_change_alert']:
        weight *= 0.3

    # 信号置信度不足
    if env_vars['confidence_level'] < 60:
        weight *= 0.7

    # 连续亏损保护（防止情绪报复交易）
    if env_vars['consecutive_losses'] > 3:
        weight *= 0.5

    # 市场结构跳变
    if env_vars['regime_state'] == 'TRANSITION':
        weight *= 0.3

    return weight
```

#### 5.6 最终仓位计算（必须经过：硬风控审批 → 软风控缩放）

```python
def calculate_final_position(
    signal: StrategySignal,
    portfolio: Portfolio,
    env_vars: dict
) -> float:
    """
    综合所有因素计算最终仓位
    """
    # 1. 凯利最优仓位
    kelly_position = kelly_criterion(signal.win_prob, signal.odds)

    # 2. 防御权重
    defense_weight = calculate_defense_weight(env_vars)

    # 3. 组合约束
    max_single_position = 0.1  # 单只最大10%
    remaining_capacity = 1.0 - portfolio.current_heat

    # 4. 最终仓位
    final = min(
        kelly_position * defense_weight,
        max_single_position,
        remaining_capacity
    )

    return final
```

**风控层输出**：
- `final_position_size` - 最终仓位大小
- `risk_per_trade` - 单笔风险敞口
- `portfolio_heat` - 组合热度
- `can_trade` - 是否允许交易（布尔）

#### 5.7 风控审批产物（可追溯 / 可签名 / 可落库）

为保证“执行层冷血不自作主张”，风控层应输出**结构化审批结果**（建议命名为 `RiskApproval`），并包含：

- `intent_id`：TradeIntent 唯一标识（用于执行域幂等）
- `approved`：是否通过
- `reasons[]`：拒绝/降档原因（人可读 + 机器可读 code）
- `limits_snapshot`：本次决策采用的风控配置快照（含版本号）
- `position_plan`：目标仓位/拆单计划/价格类型约束（如适用）
- `audit`：策略名、运行批次、输入变量摘要（用于复盘与审计）

> 原则：同一份输入（策略信号 + 组合状态 + 风控配置快照）必须产出同一份审批结果（可重复计算、可验证）。

#### 5.8 风控配置文件（`config/risk/limits.yaml`）建议结构

目标：让硬风控/软风控/降档策略**可配置、可审计、可回放**，并且能被 `RiskApproval.limits_snapshot` 完整引用。

**设计原则**：
- **版本化**：每次修改必须更新 `version`，并生成 `checksum`（内容哈希）。
- **可灰度**：支持 `effective_from`（生效时间）与 `environment`（dev/paper/prod）。
- **不可绕过**：执行域只信任 `RiskApproval` 的快照；不在执行域读取 yaml 以免“现场改配置”。

（示例，仅展示关键字段，你可以按需扩展）

```yaml
version: 1
meta:
  environment: prod
  effective_from: "2026-01-01T00:00:00+08:00"
  owner: "risk-committee"

hard:
  daily_loss_limit_pct: 0.02
  weekly_drawdown_limit_pct: 0.06
  monthly_drawdown_limit_pct: 0.10
  max_single_name_position_pct: 0.10
  max_sector_exposure_pct: 0.25

  liquidity_guard:
    min_turnover_cny: 50000000
    min_turnover_rate_pct: 1.0

  limit_up_down_guard:
    forbid_when_limit_up: true
    forbid_when_limit_down: true
    forbid_when_suspended: true

  regime_transition_freeze:
    enabled: true
    regime_values: ["TRANSITION"]

soft:
  kelly_fraction: 0.50
  vol_target:
    target_annualized: 0.15
    lookback_days: 20
    max_position_scale: 1.0
  correlation_dedup:
    window_days: 60
    max_cluster_exposure_pct: 0.20

defense_weight:
  policy_intervention_prob:
    threshold: 0.50
    multiplier: 0.50
  rule_change_alert:
    multiplier: 0.30

overrides:
  manual_freeze: false
  allowlist_symbols: []

audit:
  checksum: "sha256:..."
  comment: "tighten limits around policy window"
```

**与审批产物的绑定**：
- `RiskApproval.limits_snapshot` 建议至少包含：`version`、`checksum`、`hard/soft` 的完整配置片段。
- 复盘层对任意一笔交易都应能回答：**当时用的哪份风控配置？**（避免“规则漂移”导致复盘不可比）。

---

### L6: 执行层 (Execution Layer)

**职责**：冷血机器，禁止个人发挥

#### 6.1 核心原则

```
⚠️ 执行层的唯一准则：

1. 只读取参数，不做任何"智能判断"
2. 参数说买 → 买
3. 参数说卖 → 卖
4. 没有"我觉得现在不太对"
5. 没有"再等等看"
6. 没有"加点仓/减点仓"
7. 任何偏离都是系统bug，必须修复
```

#### 6.1.1 执行域隔离（Compute vs Trade Node）

> 现实约束：QMT/miniQMT（xtquant）通常需要 Windows 券商客户端环境。
> 因此推荐将系统分为两个域：

- **Compute Domain（Docker/服务器）**：采集/变量/信号/策略/风控/回测/复盘
- **Trade Domain（Windows 节点）**：仅执行 `RiskApproved TradeIntent` → 下单 → 回传成交

**安全边界（写死）**：
- Trade Domain 只接受来自 Compute Domain 的 **TradeIntent（已签名、可校验、可追溯）**。
- Trade Domain 只允许访问券商/QMT网络与必要的回传通道，其它出网默认拒绝。
- AI/回测服务禁止直接访问交易接口。

#### 6.2 执行时间框架

| 时间框架 | 流程 | 特点 |
|---------|------|-----|
| 日线级别 | 收盘计算 → 次日开盘确认 → 执行 | T+1确认机制 |
| 分钟级别 | 实时计算 → 条件触发 → 立即执行 | 需要Level-2数据 |

#### 6.3 交易状态机与幂等性（全自动化的生命线）

> 目标：**可重试、可恢复、可对账**；在“网络抖动/进程崩溃/重复投递”下依旧做到**有效的“只下单一次”**。

核心认知：分布式系统里“严格 exactly-once”很难成立；我们追求的是 **effectively-once**（靠幂等键 + 落库状态 + 对账修复）。

**对象分层**：
- `StrategySignal`：策略输出（可多次产生）
- `TradeIntent`：交易意图（唯一ID，签名，包含预算与风控参数）
- `RiskApproval`：风控审批结果（不可篡改记录）
- `Order`：具体下单指令（可拆分/可撤单/可部分成交）
- `Fill`：成交回报（可能多笔）
- `Position`：持仓状态（最终真相）

**落库原则（建议）**：
- `TradeIntent` / `RiskApproval` / `Order` / `Fill` 必须持久化；不要只靠内存。
- Trade Domain 使用“**inbox（入站幂等）** + **outbox（可靠发布）**”模式：
  - inbox：按 `intent_id` 记录“已处理/处理中/处理结果摘要”。
  - outbox：把“下单结果/成交回报/状态变更事件”可靠投递回 Compute Domain。

**基本状态机**（最小可用）：

`NEW -> RISK_APPROVED -> SUBMITTING -> SUBMITTED -> PARTIALLY_FILLED -> FILLED | CANCELLED | REJECTED`。

建议补充的“工程态”状态：
- `SUBMIT_UNKNOWN`：下单请求已发出但回包丢失（必须先对账再重试）
- `CANCEL_PENDING`：已发撤单但未确认

**幂等键**：
- TradeIntent 必须包含 `intent_id`（全局唯一）
- Order 必须包含 `order_id`（全局唯一）
- Trade Domain 对同一个 `intent_id` 重复请求必须返回同一结果（幂等）

**重试策略（建议）**：
- Compute → Trade 的投递按“至少一次（at-least-once）”设计。
- Trade Domain 在接到重复 `intent_id` 时：
  - 若已完成：直接返回已落库的结果/当前状态
  - 若处理中：返回 `202/PROCESSING` + 当前状态（不要重复下单）
  - 若处于 `SUBMIT_UNKNOWN`：先做 broker 对账（query）再决定是否补偿

**对账/修复（必备后台任务）**：
- 周期性拉取券商“未完成订单/当日成交/当前持仓”，与本地状态做 reconcile。
- 允许“状态自愈”：例如发现 broker 已成交但本地缺 fill，则补写 fill 并推进状态。

##### 6.3.1 状态迁移表（触发条件 / 落库动作 / 回传事件）

说明：下表是“intent 级别”的推荐主状态机；若有拆单（1 intent → N 子订单），可将 intent 状态视为子订单状态的聚合（例如：任一子订单部分成交则 intent=PARTIALLY_FILLED）。

| 当前状态 | 触发条件（输入） | 落库动作（必须原子化/可重放） | 回传事件（outbox） | 下一状态 | 备注 |
|---------|------------------|------------------------------|-------------------|---------|------|
| NEW | 收到 `TradeIntent` + `RiskApproval(approved=true)` | upsert intent + approval；记录签名/快照；创建订单计划（可为空） | `trade.intent_approved` | RISK_APPROVED | 若 intent 已存在则返回已存状态（幂等） |
| NEW | 收到 `RiskApproval(approved=false)` | upsert intent + approval；冻结原因入库 | `trade.intent_rejected` | REJECTED | 拒绝也要可追溯 |
| RISK_APPROVED | worker 领取 intent（开始提交） | 写入 `SUBMITTING`；生成 `submit_attempt_id`；记录开始时间 | `trade.submit_started` | SUBMITTING | 领取应加锁/租约，避免并发提交 |
| SUBMITTING | broker ACK（返回 broker_order_id） | 写入本地映射（intent/order ↔ broker_order_id）；落 raw req/resp；记录提交时间 | `trade.order_submitted` | SUBMITTED | broker_order_id 建议唯一约束 |
| SUBMITTING | 已发出但超时/断连（是否提交未知） | 记录异常 + request_hash + sent_at；标记未知 | `trade.submit_unknown` | SUBMIT_UNKNOWN | 不允许“盲重试” |
| SUBMIT_UNKNOWN | 对账发现已存在订单/已成交 | 补齐 broker_order_id 映射；补写缺失 fills；推进状态 | `trade.reconciled` | SUBMITTED/PARTIALLY_FILLED/FILLED | 以券商为准（source of truth） |
| SUBMIT_UNKNOWN | 对账确认不存在且允许补偿 | 增加 attempt；再次置为 SUBMITTING | `trade.submit_retry` | SUBMITTING | 必须满足“确知未成交/未挂单” |
| SUBMITTED | 收到成交回报（cum_qty < qty） | append fill；更新订单累计；更新持仓快照（可选） | `trade.fill_recorded` | PARTIALLY_FILLED | 同一 fill 需去重（fill_id/自然键） |
| PARTIALLY_FILLED | 收到成交回报（cum_qty == qty） | append fill；完成订单；更新持仓最终状态 | `trade.order_filled` | FILLED | FILLED 后不再提交/撤单 |
| SUBMITTED/PARTIALLY_FILLED | 发起撤单 | 写入 `CANCEL_PENDING`；记录 cancel_request_id | `trade.cancel_requested` | CANCEL_PENDING | 撤单也是一条可重放指令 |
| CANCEL_PENDING | 撤单成功 | 更新状态；记录 ack；若部分成交则保留 fills | `trade.order_cancelled` | CANCELLED | CANCELLED 可能伴随已成交部分 |
| SUBMITTED/SUBMITTING | 券商明确拒单 | 记录拒单原因（原始码+归一化码） | `trade.order_rejected` | REJECTED | 与风控拒绝区分 |

##### 6.3.2 回传事件清单（建议）

建议所有事件统一包含：`event_id`、`intent_id`、`order_id`（如有）、`occurred_at`、`payload`、`schema_version`。

- `trade.intent_approved` / `trade.intent_rejected`
- `trade.submit_started` / `trade.submit_unknown` / `trade.submit_retry`
- `trade.order_submitted` / `trade.order_rejected`
- `trade.fill_recorded` / `trade.order_filled` / `trade.order_cancelled`
- `trade.reconciled`（对账修复后的状态统一广播）

##### 6.3.3 幂等与并发控制（必须写进工程约束）

- **唯一约束**：`intent_id`（intent 表）、`order_id`（order 表）、`broker_order_id`（映射表）至少三处唯一。
- **inbox 去重**：对“收到同一个 intent”的请求，先查 inbox 状态再决定返回历史结果或继续处理。
- **提交租约**：对处于 `SUBMITTING` 的 intent 加“租约/锁”（带过期），防止两个进程同时向券商提交。
- **fill 去重**：以券商回报自带 id 为优先；若无，则用（broker_order_id + 成交时间 + 价格 + 数量）等自然键去重。

#### 6.4 QMT/miniQMT 接口（Trade Domain 内部实现）

**实现方式建议：Port/Adapter（交易接口适配层）**

- `ExecutionLayer` 只认识你的领域对象：`TradeIntent/Order/Fill`。
- `QmtAdapter`（或 `XtQuantAdapter`）负责把领域对象映射到 QMT/miniQMT 的具体调用。
- 不在适配层做“策略判断”；适配层只做：参数映射、调用、结果归一化、回调/轮询对接、日志与对账。

**适配器最小接口（建议）**：

```python
class BrokerAdapter(Protocol):
    def place_order(self, order: Order) -> BrokerOrderAck: ...
    def cancel_order(self, broker_order_id: str) -> CancelAck: ...
    def query_open_orders(self) -> list[BrokerOrder]: ...
    def query_fills(self, trading_day: str) -> list[BrokerFill]: ...
    def query_positions(self) -> list[BrokerPosition]: ...
```

**A股实盘细节（适配层必须处理/显式拒绝）**：
- 100股一手、最小变动价位、涨跌停/一字板可成交性
- 停牌/临停/集合竞价阶段的下单规则
- 手续费/印花税/过户费口径（至少要在复盘记录中可追溯）

**强制绑定链路标识（建议）**：
- 尽可能把 `intent_id/order_id` 写入券商侧“备注/自定义字段”（若接口支持）；否则至少保证本地映射表可追溯。

##### 6.4.1 领域对象 ↔ 券商对象映射（建议先固化成表）

- `symbol`：统一代码规范（如 `600000.SH`/`000001.SZ`）→ QMT 所需格式（写死一套转换函数）
- `direction`：BUY/SELL（A股：卖出要考虑可用持仓、T+1 等约束）
- `order_type`：LIMIT/MARKET/特殊价（若策略层不产生，则在风控审批中明确）
- `price`：按最小价位 tick 进行 round/clip，并记录原始值供审计
- `volume`：100 股一手，必须在适配层进行规格化并记录“调整前/调整后”

##### 6.4.2 下单前校验（适配层负责，但不做策略判断）

- **交易时段与集合竞价**：不满足时段则返回“可重试/不可重试”的明确错误码
- **涨跌停/停牌/临停**：策略上即便允许，也要在适配层显式拒绝或降级为“挂单不可成交风险”
- **账户/资金/可用仓位**：只做“是否满足券商约束”的校验；真正的仓位预算来自 `RiskApproval`

##### 6.4.3 回报获取：回调优先，轮询兜底

无论 QMT 使用回调还是轮询，统一原则：
- 回报进入后先落库（fill/order 状态），再写 outbox 事件
- 允许乱序/重复回报（靠去重与可重放更新解决）

##### 6.4.4 错误分级与补偿（建议标准化）

把所有异常归一化为以下几类（便于重试策略一致）：
- `VALIDATION_ERROR`：本地校验失败（不重试）
- `BROKER_REJECT`：券商拒单（不重试，需记录原始拒单码）
- `TRANSIENT_ERROR`：网络/超时/临时不可用（可重试，但要受租约与频率限制）
- `UNKNOWN_AFTER_SEND`：请求已发出但结果未知（进入 `SUBMIT_UNKNOWN`，只能对账后处理）

##### 6.4.5 映射表与对账字段（建议落库最小集合）

- `intent_id` / `order_id`
- `broker_order_id`
- `submit_attempt_id`
- `request_hash`（便于定位重复提交/参数差异）
- `remark/tag`（若券商支持，把 intent_id 写进去以提升对账可靠性）

##### 6.4.6 可测试性：先做 Stub，再接真 QMT

- 先实现 `StubAdapter`（内存撮合/固定回报），把 6.3 状态机跑通
- 再接 `XtQuantAdapter`，并保留“录制/回放”能力（记录 raw req/resp + 回报流）

---

### L7: 复盘层 (Post-Mortem Layer)

**职责**：屏蔽结果，只看决策

#### 7.1 交易记录结构

```python
@dataclass
class TradeRecord:
    """交易记录 - 保存决策时刻的完整快照"""

    # 元信息
    trade_id: str
    timestamp: datetime

    # 决策时刻快照
    market_vars_snapshot: dict      # 当时的市场变量
    stock_vars_snapshot: dict       # 当时的个股变量
    signal_snapshot: dict           # 当时的信号评分
    regime_state: str               # 当时的Regime状态
    strategy_triggered: str         # 触发的策略
    kelly_calculation: dict         # 凯利计算过程
    risk_check_result: dict         # 风控审批结果

    # 执行信息
    order_details: Order
    execution_result: ExecutionResult

    # 结果（复盘时可隐藏）
    pnl: float                      # 盈亏
    holding_period: int             # 持仓时间
    max_drawdown: float             # 最大回撤
```

#### 7.2 决策质量评估

```python
class DecisionQualityEvaluator:
    """决策质量评估器 - 不看结果，只看过程"""

    def evaluate(self, record: TradeRecord, hide_result: bool = True) -> dict:
        scores = {
            # 信息充分度：当时掌握的信息是否足够？
            'information_completeness': self._eval_info_completeness(record),

            # 逻辑严密度：推理过程是否有漏洞？
            'logic_rigor': self._eval_logic_rigor(record),

            # 系统符合度：是否严格按策略执行？
            'system_compliance': self._eval_system_compliance(record),

            # 仓位合理度：凯利计算是否正确？
            'position_rationality': self._eval_position(record)
        }

        # 综合决策质量分
        scores['overall'] = sum(scores.values()) / len(scores)

        return scores

    def classify_outcome(self, record: TradeRecord) -> str:
        """
        结果分类

        🟢 决策正确 + 盈利 = DESERVED_WIN (应得的成功)
        🟡 决策正确 + 亏损 = BAD_LUCK (坏运气，不改策略)
        🔴 决策错误 + 盈利 = DANGEROUS_WIN (危险的成功，必须警惕)
        ⚫ 决策错误 + 亏损 = DESERVED_LOSS (该亏的，找出漏洞)
        """
        decision_quality = self.evaluate(record)['overall']
        is_profit = record.pnl > 0

        if decision_quality >= 0.7:
            return 'DESERVED_WIN' if is_profit else 'BAD_LUCK'
        else:
            return 'DANGEROUS_WIN' if is_profit else 'DESERVED_LOSS'
```



---

### L8: 迭代层 (Evolution Layer)

**职责**：市场在变，系统也要变

#### 8.1 AI回测引擎

```python
class BacktestEngine:
    """
    AI回测引擎

    ⚠️ 核心原则：AI只做回测验证，不参与实盘决策
    """

    def backtest_strategy(
        self,
        strategy: Strategy,
        start_date: str,
        end_date: str,
        initial_capital: float = 1_000_000
    ) -> BacktestResult:
        """运行策略回测"""
        pass

    def optimize_parameters(
        self,
        strategy: Strategy,
        param_grid: dict,
        method: str = 'bayesian'  # grid / random / bayesian
    ) -> OptimizationResult:
        """参数优化"""
        pass

    def detect_overfitting(
        self,
        in_sample_result: BacktestResult,
        out_sample_result: BacktestResult
    ) -> OverfittingReport:
        """过拟合检测"""
        pass
```

#### 8.2 策略健康度监控

```yaml
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

响应动作:
  - 黄色预警: 记录日志，继续观察
  - 橙色预警: 降低该策略仓位权重
  - 红色预警: 暂停策略，触发人工审核
```

#### 8.3 参数更新流程

```
┌─────────────────────────────────────────────────────────────┐
│                    参数更新流程                              │
│                                                             │
│  0. 生成新参数版本号（StrategyConfigVersion）                │
│     ↓                                                       │
│  1. AI提出参数修改建议（仅建议，不可直达实盘）              │
│     ↓                                                       │
│  2. 回测验证（样本外测试）                                  │
│     ↓                                                       │
│  3. 人工审核确认 ← ⚠️ 必须有人参与                          │
│     ↓                                                       │
│  4. 灰度/小仓位试运行（纸上交易或1%仓位，N天）              │
│     ↓                                                       │
│  5. 观察期通过后，全量切换                                  │
│                                                             │
│  ⚠️ 禁止实时自动修改策略参数                                │
│  ⚠️ 禁止AI直接影响实盘交易                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 四、数据流全景图

```
                           BLACKJACK 数据流

    ┌─────────────────────────────────────────────────────────┐
    │                      外部数据源                         │
    │  行情API  财报API  资金流API  L2数据  舆情爬虫  政策监控 │
    └───────────────────────────┬─────────────────────────────┘
                                ↓
    ┌───────────────────────────┴─────────────────────────────┐
    │                    数据湖 (Data Lake)                   │
    │                    PostgreSQL / ClickHouse              │
    └───────────────────────────┬─────────────────────────────┘
                                ↓
    ┌───────────────────────────┴─────────────────────────────┐
    │                    变量计算引擎                          │
    │              原始数据 → 标准化变量                       │
    └───────────────────────────┬─────────────────────────────┘
                                ↓
    ┌───────────────────────────┴─────────────────────────────┐
    │                    信号合成引擎                          │
    │              变量 → 信号评分 + Regime                    │
    └───────────────────────────┬─────────────────────────────┘
                                ↓
    ┌───────────────────────────┴─────────────────────────────┐
    │                    策略引擎                              │
    │              信号 → 交易指令                             │
    └───────────────────────────┬─────────────────────────────┘
                                ↓
    ┌───────────────────────────┴─────────────────────────────┐
    │                    风控引擎                              │
    │              交易指令 → 仓位计算 → 审批                  │
    └───────────────────────────┬─────────────────────────────┘
                                ↓
    ┌───────────────────────────┴─────────────────────────────┐
    │                    执行引擎                              │
    │              审批通过 → QMT订单                          │
    └───────────────────────────┬─────────────────────────────┘
                                ↓
    ┌───────────────────────────┴─────────────────────────────┐
    │                    QMT / miniQMT                        │
    │                    券商交易接口                          │
    └───────────────────────────┬─────────────────────────────┘
                                ↓
    ┌───────────────────────────┴─────────────────────────────┐
    │                    交易记录存储                          │
    │              完整决策快照 + 执行结果                     │
    └───────────────────────────┬─────────────────────────────┘
                                ↓
    ┌───────────────────────────┴─────────────────────────────┐
    │                    复盘系统                              │
    │              决策质量评估 + 结果分类                     │
    └───────────────────────────┬─────────────────────────────┘
                                ↓
    ┌───────────────────────────┴─────────────────────────────┐
    │                    迭代引擎                              │
    │              回测 → 优化 → 人工审核 → 更新               │
    └─────────────────────────────────────────────────────────┘
```


---

## 五、技术选型

### 5.1 技术栈

| 层级 | 技术选型 | 说明 |
|-----|---------|------|
| 语言 | Python 3.11+ | 量化生态最完善 |
| 数据存储 | PostgreSQL + Redis | 关系型 + 缓存 |
| 时序数据 | ClickHouse / TimescaleDB | 高性能时序查询 |
| 消息队列 | Redis Stream / RabbitMQ | 层间通信 |
| 任务调度 | Celery / APScheduler | 定时任务 |
| 容器化 | Docker + Docker Compose | 部署和隔离 |
| 监控 | Prometheus + Grafana | 系统监控 |
| 日志 | ELK Stack / Loki | 日志收集分析 |

### 5.2 核心依赖

```yaml
数据获取:
  - akshare        # A股数据（免费）
  - tushare        # A股数据（需要积分）
  - baostock       # A股历史数据（免费）
  - efinance       # 实时行情

量化框架:
  - pandas         # 数据处理
  - numpy          # 数值计算
  - ta-lib         # 技术指标
  - backtrader     # 回测框架
  - zipline        # 回测框架备选

机器学习:
  - scikit-learn   # 传统ML
  - xgboost        # 梯度提升
  - optuna         # 超参优化

交易接口:
  - xtquant        # QMT Python接口
  - easytrader     # 备用（同花顺/通达信）

Web服务:
  - fastapi        # API服务
  - uvicorn        # ASGI服务器
```

---

## 六、Docker 部署架构

### 6.1 容器编排

```yaml
# docker-compose.yml 概览
services:
  # 数据服务
  postgres:        # 主数据库
  redis:           # 缓存 + 消息队列
  clickhouse:      # 时序数据

  # 核心服务
  data-collector:  # 数据采集器
  variable-engine: # 变量计算引擎
  signal-engine:   # 信号合成引擎
  strategy-engine: # 策略引擎
  risk-engine:     # 风控引擎
  executor:        # 执行引擎

  # 辅助服务
  backtest:        # 回测服务
  postmortem:      # 复盘服务

  # 监控
  prometheus:      # 指标收集
  grafana:         # 可视化
```

### 6.2 服务隔离原则

```
┌─────────────────────────────────────────────────────────────┐
│                      服务隔离设计                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  【网络隔离】                                               │
│  ├─ data-network:     数据采集相关服务                     │
│  ├─ compute-network:  计算相关服务                         │
│  ├─ trade-network:    交易相关服务（严格隔离）             │
│  └─ monitor-network:  监控相关服务                         │
│                                                             │
│  【权限隔离】                                               │
│  ├─ 数据服务: 只读外部API                                  │
│  ├─ 计算服务: 无网络外联权限                               │
│  ├─ 交易服务: 只能连QMT，其他全部禁止                     │
│  └─ 回测服务: 与实盘完全隔离                               │
│                                                             │
│  【关键原则】                                               │
│  ⚠️ 回测服务与执行服务必须物理隔离                         │
│  ⚠️ AI服务不能直接访问交易接口                             │
│  ⚠️ 策略参数修改必须经过人工审批                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 七、核心变量设计详解

### 7.1 你的量价信号模型（核心）

```python
class VolumePriceSignal:
    """
    量价信号模型 - 系统的核心

    核心思想：
    同样的结果（涨跌），不同的力度（成交量），意味着不同的资金行为
    """

    def calculate(self, stock_code: str, date: str) -> float:
        """
        信号 = (当前力度 / 历史均力度) × (当前结果 / 历史均结果)
        """
        # 获取数据
        current = self.get_current_data(stock_code, date)
        history = self.get_history_data(stock_code, lookback=20)

        # 力度：使用换手率（自动适应股本变化）
        current_effort = current['turnover_rate']
        avg_effort = history['turnover_rate'].mean()

        # 结果：涨跌幅
        current_result = current['pct_change']
        avg_result = history['pct_change'].abs().mean()

        # 信号计算
        effort_ratio = current_effort / avg_effort if avg_effort > 0 else 1
        result_ratio = current_result / avg_result if avg_result > 0 else 0

        signal = effort_ratio * result_ratio

        return signal

    def interpret(self, signal: float, effort_ratio: float, result: float) -> str:
        """
        信号解读 - 识别主力行为
        """
        if effort_ratio > 1.5:  # 放量
            if result > 0.5:
                return "MAIN_FORCE_PUMP"   # 主力拉升
            elif result < -0.5:
                return "MAIN_FORCE_DUMP"   # 主力出货
            elif abs(result) < 0.3:
                return "ACCUMULATION"       # 吸筹
        elif effort_ratio < 0.7:  # 缩量
            if result > 0:
                return "WEAK_RISE"          # 弱涨（无量空涨）
            else:
                return "WEAK_DROP"          # 弱跌（惜售）
        else:
            return "NORMAL"                 # 正常波动
```


### 7.2 市场状态变量

```python
class MarketStateVariables:
    """市场状态变量 - 判断牌堆冷热"""

    def calculate_valuation_percentile(self) -> float:
        """
        全市场估值分位

        返回：当前PE/PB在历史中的分位数 [0-100]
        - < 20: 极度低估（牌堆冷）
        - 20-40: 低估
        - 40-60: 合理
        - 60-80: 高估
        - > 80: 极度高估（牌堆热）
        """
        current_pe = self.get_market_pe()
        history_pe = self.get_history_pe(years=10)
        percentile = (history_pe < current_pe).sum() / len(history_pe) * 100
        return percentile

    def calculate_volatility_compression(self) -> float:
        """
        波动率压缩程度

        返回：[0-1]，越接近1表示波动率越压缩（大动作前的宁静）
        """
        current_vol = self.get_current_volatility(window=5)
        avg_vol = self.get_avg_volatility(window=60)

        compression = 1 - (current_vol / avg_vol) if avg_vol > 0 else 0
        return max(0, min(1, compression))

    def detect_regime(self) -> str:
        """
        市场状态识别

        返回：BULL / BEAR / CONSOLIDATION / TRANSITION
        """
        ma20 = self.get_index_ma(20)
        ma60 = self.get_index_ma(60)
        current = self.get_index_current()
        vol_compression = self.calculate_volatility_compression()

        # 趋势判断
        if current > ma20 > ma60:
            return "BULL"
        elif current < ma20 < ma60:
            return "BEAR"
        elif vol_compression > 0.7:
            return "TRANSITION"  # 波动率极度压缩，可能变盘
        else:
            return "CONSOLIDATION"
```

### 7.3 政策干预变量

```python
class PolicyInterventionDetector:
    """
    政策干预检测器 - A股的"老千"防护

    马恺文会加入的变量：规则干扰（Regulator & Market Manipulation）
    """

    def calculate_intervention_probability(self) -> float:
        """
        计算政策干预概率

        考虑因素：
        - 近期是否有重大会议
        - 监管层近期发言倾向
        - 市场是否处于敏感位置
        - 历史同期是否有维稳倾向
        """
        factors = {
            'major_meeting_nearby': self._check_major_meetings(),
            'regulator_sentiment': self._analyze_regulator_speech(),
            'market_at_key_level': self._check_key_price_levels(),
            'historical_pattern': self._check_historical_intervention()
        }

        # 加权计算
        weights = {
            'major_meeting_nearby': 0.3,
            'regulator_sentiment': 0.3,
            'market_at_key_level': 0.2,
            'historical_pattern': 0.2
        }

        probability = sum(
            factors[k] * weights[k] for k in factors
        )

        return probability

    def detect_rule_change(self) -> bool:
        """
        检测规则变化

        监控：
        - 交易所公告
        - 证监会新规
        - 印花税/交易费用调整
        - 涨跌停规则变化
        """
        alerts = []
        alerts.extend(self._scan_exchange_announcements())
        alerts.extend(self._scan_csrc_announcements())

        # 如果有重大规则变化，返回True
        return len([a for a in alerts if a['severity'] == 'HIGH']) > 0
```

### 7.4 主力行为变量

```python
class MainForceBehaviorDetector:
    """
    主力行为检测器

    核心：通过Level-2数据判断"对手在做什么"
    """

    def analyze_order_flow(self, stock_code: str) -> dict:
        """
        分析订单流

        返回：
        - active_buy_ratio: 主动买入占比
        - active_sell_ratio: 主动卖出占比
        - large_order_direction: 大单方向
        - order_imbalance: 订单不平衡度
        """
        l2_data = self.get_l2_data(stock_code)

        # 主动买卖统计
        active_buy = l2_data[l2_data['direction'] == 'BUY']['amount'].sum()
        active_sell = l2_data[l2_data['direction'] == 'SELL']['amount'].sum()
        total = active_buy + active_sell

        # 大单统计（成交额 > 50万）
        large_orders = l2_data[l2_data['amount'] > 500000]
        large_buy = large_orders[large_orders['direction'] == 'BUY']['amount'].sum()
        large_sell = large_orders[large_orders['direction'] == 'SELL']['amount'].sum()

        return {
            'active_buy_ratio': active_buy / total if total > 0 else 0.5,
            'active_sell_ratio': active_sell / total if total > 0 else 0.5,
            'large_order_direction': 'BUY' if large_buy > large_sell else 'SELL',
            'order_imbalance': (active_buy - active_sell) / total if total > 0 else 0
        }

    def classify_behavior(self, stock_code: str, vp_signal: float) -> str:
        """
        综合判断主力行为

        结合量价信号和订单流
        """
        order_flow = self.analyze_order_flow(stock_code)

        # 放量 + 主动买入多 + 涨幅小 → 吸筹
        # 放量 + 主动卖出多 + 涨幅大 → 出货
        # 缩量 + 下跌 → 洗盘或无人接盘

        if order_flow['active_buy_ratio'] > 0.6 and abs(vp_signal) < 0.5:
            return "ACCUMULATING"  # 吸筹
        elif order_flow['active_sell_ratio'] > 0.6 and vp_signal > 1:
            return "DISTRIBUTING"  # 出货
        elif order_flow['order_imbalance'] > 0.3:
            return "PUMPING"       # 拉升
        elif order_flow['order_imbalance'] < -0.3:
            return "DUMPING"       # 砸盘
        else:
            return "NEUTRAL"       # 中性
```

---

## 八、多策略协调机制

### 8.1 策略优先级与冲突解决

```python
class StrategyCoordinator:
    """
    多策略协调器

    解决问题：当多个策略同时给出信号时，如何决策？
    """

    def __init__(self):
        self.strategies = {
            'trend_following': TrendFollowingStrategy(),
            'mean_reversion': MeanReversionStrategy(),
            'event_driven': EventDrivenStrategy(),
            'value_investing': ValueInvestingStrategy()
        }

        # 策略优先级（根据当前Regime动态调整）
        self.priority_matrix = {
            'BULL': ['trend_following', 'event_driven', 'value_investing'],
            'BEAR': ['value_investing', 'mean_reversion'],
            'CONSOLIDATION': ['mean_reversion', 'event_driven'],
            'TRANSITION': []  # 转折期不主动开仓
        }

    def resolve_conflicts(
        self,
        signals: List[StrategySignal],
        regime: str
    ) -> Optional[StrategySignal]:
        """
        解决策略冲突

        规则：
        1. 按Regime优先级排序
        2. 同方向信号可以叠加置信度
        3. 反方向信号互相抵消
        4. 最终信号强度不足则不操作
        """
        if regime == 'TRANSITION':
            return None  # 转折期不开新仓

        priority_order = self.priority_matrix.get(regime, [])

        # 按优先级筛选
        valid_signals = [
            s for s in signals
            if s.strategy_name in priority_order
        ]

        if not valid_signals:
            return None

        # 检查方向一致性
        buy_signals = [s for s in valid_signals if s.action == 'BUY']
        sell_signals = [s for s in valid_signals if s.action == 'SELL']

        if buy_signals and sell_signals:
            # 方向冲突，取消操作
            return None

        # 返回优先级最高的信号
        for strategy_name in priority_order:
            for signal in valid_signals:
                if signal.strategy_name == strategy_name:
                    return signal

        return None
```

### 8.2 仓位分配

```python
class PositionAllocator:
    """
    仓位分配器

    基于凯利准则 + 组合约束
    """

    def __init__(self, max_total_position: float = 0.8):
        self.max_total_position = max_total_position  # 最大总仓位80%
        self.max_single_position = 0.1                # 单只最大10%
        self.max_sector_position = 0.3                # 单行业最大30%
        self.max_correlation_overlap = 0.5            # 高相关性股票总仓位

    def allocate(
        self,
        signals: List[StrategySignal],
        portfolio: Portfolio,
        risk_params: dict
    ) -> List[PositionOrder]:
        """
        分配仓位

        步骤：
        1. 计算每个信号的凯利仓位
        2. 应用防御权重
        3. 检查组合约束
        4. 按优先级分配剩余额度
        """
        orders = []
        remaining_capacity = self.max_total_position - portfolio.current_position

        for signal in sorted(signals, key=lambda x: x.win_prob * x.odds, reverse=True):
            # 凯利仓位
            kelly_pos = self._kelly_position(signal.win_prob, signal.odds)

            # 防御权重
            defense_weight = risk_params.get('defense_weight', 1.0)
            adjusted_pos = kelly_pos * defense_weight

            # 组合约束
            final_pos = min(
                adjusted_pos,
                self.max_single_position,
                remaining_capacity,
                self._sector_remaining(signal.stock_code, portfolio)
            )

            if final_pos > 0.01:  # 最小仓位1%
                orders.append(PositionOrder(
                    stock_code=signal.stock_code,
                    position_size=final_pos,
                    signal=signal
                ))
                remaining_capacity -= final_pos

            if remaining_capacity <= 0.01:
                break

        return orders
```


---

## 九、项目目录结构

```
blackjack/
├── docker-compose.yml          # Docker编排
├── Dockerfile                  # 主镜像
├── requirements.txt            # Python依赖
├── config/
│   ├── settings.yaml           # 主配置
│   ├── strategies/             # 策略配置
│   │   ├── trend_following.yaml
│   │   ├── mean_reversion.yaml
│   │   └── event_driven.yaml
│   └── risk/                   # 风控配置
│       └── limits.yaml
│
├── src/
│   ├── __init__.py
│   │
│   ├── perception/             # Layer 1: 感知层
│   │   ├── __init__.py
│   │   ├── data_collector.py   # 数据采集器
│   │   ├── sources/
│   │   │   ├── akshare_source.py
│   │   │   ├── tushare_source.py
│   │   │   └── l2_source.py
│   │   └── cleaners/
│   │       └── data_cleaner.py
│   │
│   ├── variables/              # Layer 2: 变量层
│   │   ├── __init__.py
│   │   ├── market_vars.py      # 市场变量
│   │   ├── stock_vars.py       # 个股变量
│   │   ├── env_vars.py         # 环境变量
│   │   └── normalizer.py       # 归一化
│   │
│   ├── signals/                # Layer 3: 信号层
│   │   ├── __init__.py
│   │   ├── volume_price.py     # 量价信号（核心）
│   │   ├── signal_composer.py  # 信号合成
│   │   └── regime_detector.py  # Regime检测
│   │
│   ├── strategies/             # Layer 4: 策略层
│   │   ├── __init__.py
│   │   ├── base_strategy.py    # 策略基类
│   │   ├── trend_following.py
│   │   ├── mean_reversion.py
│   │   ├── event_driven.py
│   │   └── coordinator.py      # 策略协调器
│   │
│   ├── risk/                   # Layer 5: 风控层
│   │   ├── __init__.py
│   │   ├── kelly.py            # 凯利计算
│   │   ├── bankruptcy.py       # 破产概率
│   │   ├── defense.py          # 防御权重
│   │   └── position_allocator.py
│   │
│   ├── execution/              # Layer 6: 执行层
│   │   ├── __init__.py
│   │   ├── executor.py         # 执行引擎
│   │   ├── brokers/
│   │   │   ├── qmt_broker.py   # QMT接口
│   │   │   └── mini_qmt.py     # miniQMT接口
│   │   └── order_manager.py
│   │
│   ├── postmortem/             # Layer 7: 复盘层
│   │   ├── __init__.py
│   │   ├── trade_recorder.py   # 交易记录
│   │   ├── decision_evaluator.py
│   │   └── outcome_classifier.py
│   │
│   ├── evolution/              # Layer 8: 迭代层
│   │   ├── __init__.py
│   │   ├── backtest_engine.py  # 回测引擎
│   │   ├── optimizer.py        # 参数优化
│   │   ├── overfitting_detector.py
│   │   └── health_monitor.py   # 策略健康度
│   │
│   ├── core/                   # 核心模块
│   │   ├── __init__.py
│   │   ├── models.py           # 数据模型
│   │   ├── database.py         # 数据库
│   │   ├── cache.py            # 缓存
│   │   └── message_bus.py      # 消息总线
│   │
│   └── api/                    # API服务
│       ├── __init__.py
│       ├── main.py             # FastAPI入口
│       └── routes/
│           ├── signals.py
│           ├── strategies.py
│           └── portfolio.py
│
├── tests/                      # 测试
│   ├── unit/
│   ├── integration/
│   └── backtest/
│
├── scripts/                    # 脚本
│   ├── init_db.py
│   ├── download_history.py
│   └── run_backtest.py
│
└── docs/                       # 文档
    ├── ARCHITECTURE.md         # 本文档
    ├── VARIABLES.md            # 变量详解
    ├── STRATEGIES.md           # 策略详解
    └── DEPLOYMENT.md           # 部署指南
```

---

## 十、开发路线图

### Phase 1: 基础设施（2周）

```
目标：搭建数据管道和基础框架

任务：
├── 搭建Docker环境
├── 配置PostgreSQL + Redis + ClickHouse
├── 实现数据采集器（akshare/tushare）
├── 实现变量计算框架
└── 单元测试覆盖

交付物：
├── 能够采集A股日线/分钟数据
├── 能够计算基础变量
└── Docker一键启动
```

### Phase 2: 核心引擎（3周）

```
目标：实现信号层和策略层

任务：
├── 实现量价信号模型（你的核心）
├── 实现市场状态变量
├── 实现Regime Detection
├── 实现第一个策略（趋势跟踪）
├── 实现凯利计算器
└── 回测框架

交付物：
├── 能够计算量价信号
├── 能够识别市场状态
├── 能够运行回测
└── 第一个策略回测报告
```

### Phase 3: 风控与执行（2周）

```
目标：实现风控层和执行层

任务：
├── 实现完整风控链
├── 实现防御权重计算
├── 实现仓位分配器
├── 对接QMT/miniQMT（模拟）
└── 实现订单管理

交付物：
├── 完整的风控审批流程
├── 模拟交易测试通过
└── QMT接口联调成功
```

### Phase 4: 复盘与迭代（2周）

```
目标：实现复盘层和迭代层

任务：
├── 实现交易记录系统
├── 实现决策质量评估
├── 实现结果分类
├── 实现策略健康度监控
└── 实现参数优化流程

交付物：
├── 完整的交易日志
├── 决策质量报告
├── 策略健康度仪表盘
```

### Phase 5: 多策略扩展（持续）

```
目标：扩展策略库

任务：
├── 均值回归策略
├── 事件驱动策略
├── 价值投资策略
├── 策略协调器
└── 多策略回测

交付物：
├── 4+个可用策略
├── 策略协调机制
└── 多策略组合回测
```

---

## 十一、关键设计决策记录

### 决策1：AI与执行严格隔离

**问题**：AI是否应该直接控制交易？

**决策**：否。AI只输出变量参数，不参与实盘决策。

**理由**：
- 防止AI的"直觉"污染执行纪律
- 确保所有交易都能追溯到明确的规则
- 马恺文原则：禁止个人发挥

### 决策2：使用换手率而非绝对成交量

**问题**：如何处理股本变化导致的误判？

**决策**：所有量的指标都使用相对化指标（换手率、资金参与度）

**理由**：
- 自动适应增发、解禁等股本变化
- 历史数据可比性
- 你的GPT对话中已验证这个思路

### 决策3：结构跳变时暂停交易

**问题**：市场突变时如何应对？

**决策**：检测到Regime=TRANSITION时，禁止新开仓

**理由**：
- 马恺文会在"牌堆被换"时离场
- 宁可错过机会，不可承担未知风险
- 先保住本金，再考虑盈利

### 决策4：策略参数修改必须人工审批

**问题**：AI能否自动优化并更新策略参数？

**决策**：否。AI只能提建议，必须人工审批后才能生效。

**理由**：
- 防止过拟合
- 确保人类对系统有最终控制权
- 马恺文原则：系统的稳定性高于单次收益

---

## 十二、附录

### A. 马恺文核心原则速查

| 原则 | 在系统中的体现 |
|-----|---------------|
| 只在EV>0时下注 | 信号层的opportunity_score必须>阈值 |
| 凯利准则 | 风控层的仓位计算 |
| 禁止个人发挥 | 执行层只读参数，不做判断 |
| 决策vs结果分离 | 复盘层的四象限分类 |
| 活着比赢更重要 | 破产概率作为最高优先级约束 |
| 应对规则干扰 | 政策干预概率 + 防御权重 |
| 系统稳定性 | 参数修改必须人工审批 |

### B. 变量清单

```yaml
市场变量:
  - market_valuation_percentile    # 估值分位
  - volatility_compression         # 波动率压缩
  - market_sentiment_cycle         # 情绪周期
  - money_flow_heat                # 资金热度
  - foreign_capital_flow           # 外资流向
  - margin_balance_change          # 融资余额变化

个股变量:
  - volume_price_signal            # 量价信号
  - relative_strength              # 相对强弱
  - fundamental_score              # 基本面评分
  - main_force_behavior            # 主力行为
  - l2_active_buy_sell_ratio       # L2买卖比
  - earnings_surprise              # 业绩超预期

环境变量:
  - policy_intervention_prob       # 政策干预概率
  - rule_change_alert              # 规则变化预警
  - regime_state                   # 市场状态
  - event_calendar                 # 事件日历
```

### C. 信号阈值参考

```yaml
opportunity_score:
  - < 30: 不操作
  - 30-50: 可关注
  - 50-70: 可小仓位
  - 70-90: 可标准仓位
  - > 90: 可重仓（但仍受凯利约束）

confidence_level:
  - < 40: 降低仓位50%
  - 40-60: 正常仓位
  - > 60: 可提高仓位（但不超过凯利上限）

defense_weight:
  - 1.0: 正常
  - 0.5-1.0: 谨慎
  - < 0.5: 防守
  - < 0.3: 暂停开仓
```

---

**文档版本**: v1.0
**最后更新**: 2026-01-09
**作者**: Blackjack System Design