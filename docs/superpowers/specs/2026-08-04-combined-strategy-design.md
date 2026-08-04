# 组合策略设计：比值位置 + 双动量

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将比值百分位（位置信号）作为辅助维度叠加到双动量策略上，利用位置过滤噪音、增强信号置信度，并在 UI 上同时展示两个维度。

**Architecture:** 比值百分位作为"估值过滤器"，动量作为"触发器"。比值处于历史低位时放宽动量门槛（更容易买入创业板），比值处于历史高位时收紧门槛（更难买入创业板、更容易切红利）。回测引擎增加组合策略分支，支持 A/B 对比。

**Tech Stack:** Streamlit, Pandas, AKShare, Plotly

---

## 1. 背景与动机

### 当前问题

纯双动量策略回测表现：
- 年化收益 ~21%，最大回撤 ~26%，夏普 0.88
- 问题：趋势反转时容易追高，有时在比值已极高时仍追入创业板

### 两个维度的互补性

| 维度 | 优势 | 劣势 |
|------|------|------|
| **比值位置**（百分位） | 能识别极端估值区域 | 滞后，到达极值时行情可能已走完 |
| **动量方向**（ROC） | 反应快，跟随趋势 | 容易追高，趋势反转时来不及 |

### 组合思路

- **比值位置** → 回答"这个资产便宜吗？"（值不值得买）
- **动量方向** → 回答"趋势向哪走？"（什么时候买）

极端低位 + 动量转正 = 最强买入信号
极端高位 + 动量转负 = 最强卖出信号
中间区域 = 按纯动量操作

---

## 2. 策略逻辑

### 2.1 比值百分位计算

使用 750 天（3年）滚动窗口，计算当前比值在过去 3 年的分位数：

```python
ratio_series = close_cy / close_hl
rolling_rank = ratio_series.rolling(window=750).rank()
percentile = rolling_rank / 750  # 0~1
```

### 2.2 动量百分位计算（解决门槛区分度问题）

**问题**：使用固定 rf 倍数作为门槛区分度太低。20 天动量的 rf_period ≈ 0.12%，而正常波动是 ±5%~±15%，0.06% 和 0.18% 几乎都贴在 0 上，"收紧/放宽"形同虚设。

**解决方案**：改用动量自身的滚动百分位作为门槛。

```python
# 计算创业板动量的 250 天滚动百分位
cy_mom_percentile = cy_momentum.rolling(window=250).rank() / 250
```

这样门槛是自适应的：当动量处于自身历史的低位时，即使绝对值为正也可能被认为是"弱势"；当动量处于自身历史的高位时，被认为是"强势"。

### 2.3 信号矩阵

将比值百分位分为三个区域，结合动量百分位过滤：

| 比值位置 \ 动量状态 | 创业板动量领先且强势 | 红利动量领先且强势 | 两者均弱势 |
|---|---|---|---|
| **低位（≤20%）** | 🔵 **强信号**买创业板 | 🔵 买创业板（放宽：动量百分位>30%即可） | ⚪ 空仓 |
| **中间（20%~80%）** | 🔵 买创业板（动量百分位>50%） | 🟠 买红利（动量百分位>50%） | ⚪ 空仓 |
| **高位（≥80%）** | 🔵 买创业板（收紧：动量百分位>70%） | 🟠 **强信号**买红利 | ⚪ 空仓 |

具体规则：

**低位区域（percentile ≤ 20%）：**
- 创业板动量 > 红利动量 且 创业板动量百分位 > 30% → 🔵 买创业板（门槛降低）
- 红利动量 > 创业板动量 且 红利动量百分位 > 50% → 🟠 买红利
- 否则 → ⚪ 空仓

**中间区域（20% < percentile < 80%）：**
- 创业板动量 > 红利动量 且 创业板动量百分位 > 50% → 🔵 买创业板
- 红利动量 > 创业板动量 且 红利动量百分位 > 50% → 🟠 买红利
- 否则 → ⚪ 空仓

**高位区域（percentile ≥ 80%）：**
- 创业板动量 > 红利动量 且 创业板动量百分位 > 70% → 🔵 买创业板（门槛提高）
- 红利动量 > 创业板动量 且 红利动量百分位 > 30% → 🟠 买红利（门槛降低）
- 否则 → ⚪ 空仓

### 2.4 信号输出

与纯动量策略一致：
- `1` = 买入创业板
- `-1` = 买入红利
- `0` = 空仓

T+1 执行。

---

## 3. 代码设计

### 3.1 config.py 新增参数

```python
STRATEGY_CONFIG = {
    # ... 现有参数保持不变 ...
    "percentile_window": 750,       # 比值百分位滚动窗口
    "momentum_percentile_window": 250,  # 动量百分位滚动窗口（1年）
    "low_percentile": 0.20,         # 低位阈值
    "high_percentile": 0.80,        # 高位阈值
    # 动量百分位门槛（按比值区域）
    "low_cy_mom_pct_threshold": 0.30,   # 低位时创业板动量百分位门槛
    "mid_mom_pct_threshold": 0.50,      # 中间时动量百分位门槛
    "high_cy_mom_pct_threshold": 0.70,  # 高位时创业板动量百分位门槛
    "low_hl_mom_pct_threshold": 0.50,   # 低位时红利动量百分位门槛
    "high_hl_mom_pct_threshold": 0.30,  # 高位时红利动量百分位门槛
}
```

### 3.2 strategy.py 新增函数

```python
def calculate_ratio_percentile(ratio_series: pd.Series, window: int = 750) -> pd.Series:
    """计算比值的滚动百分位"""
    rolling_rank = ratio_series.rolling(window=window).rank()
    return rolling_rank / window

def calculate_momentum_percentile(momentum_series: pd.Series, window: int = 250) -> pd.Series:
    """计算动量的滚动百分位（自适应门槛）"""
    rolling_rank = momentum_series.rolling(window=window).rank()
    return rolling_rank / window

def generate_combined_signals(df: pd.DataFrame, window: int = None) -> pd.Series:
    """
    组合策略：比值位置 + 双动量（使用动量百分位作为自适应门槛）
    Args:
        df: 包含 close_cy, close_hl, ratio 的 DataFrame
        window: 动量窗口
    Returns:
        信号序列：1=创业板, -1=红利, 0=空仓
    """
    if window is None:
        window = STRATEGY_CONFIG['momentum_window']

    # 计算动量
    cy_mom = calculate_momentum(df['close_cy'], window)
    hl_mom = calculate_momentum(df['close_hl'], window)

    # 计算比值百分位
    ratio_pct = calculate_ratio_percentile(df['ratio'])

    # 计算动量百分位（自适应门槛）
    mom_pct_window = STRATEGY_CONFIG['momentum_percentile_window']
    cy_mom_pct = calculate_momentum_percentile(cy_mom, mom_pct_window)
    hl_mom_pct = calculate_momentum_percentile(hl_mom, mom_pct_window)

    # 阈值参数
    low_pct = STRATEGY_CONFIG['low_percentile']
    high_pct = STRATEGY_CONFIG['high_percentile']
    low_cy_threshold = STRATEGY_CONFIG['low_cy_mom_pct_threshold']
    mid_threshold = STRATEGY_CONFIG['mid_mom_pct_threshold']
    high_cy_threshold = STRATEGY_CONFIG['high_cy_mom_pct_threshold']
    low_hl_threshold = STRATEGY_CONFIG['low_hl_mom_pct_threshold']
    high_hl_threshold = STRATEGY_CONFIG['high_hl_mom_pct_threshold']

    # 向量化条件
    cy_stronger = cy_mom > hl_mom  # 平局归红利
    hl_stronger = ~cy_stronger

    # 低位区域
    low_mask = ratio_pct <= low_pct
    low_cy_buy = low_mask & cy_stronger & (cy_mom_pct > low_cy_threshold)
    low_hl_buy = low_mask & hl_stronger & (hl_mom_pct > low_hl_threshold)

    # 中间区域
    mid_mask = (ratio_pct > low_pct) & (ratio_pct < high_pct)
    mid_cy_buy = mid_mask & cy_stronger & (cy_mom_pct > mid_threshold)
    mid_hl_buy = mid_mask & hl_stronger & (hl_mom_pct > mid_threshold)

    # 高位区域
    high_mask = ratio_pct >= high_pct
    high_cy_buy = high_mask & cy_stronger & (cy_mom_pct > high_cy_threshold)
    high_hl_buy = high_mask & hl_stronger & (hl_mom_pct > high_hl_threshold)

    # 合并信号
    signals = pd.Series(0, index=df.index, dtype=float)
    signals[low_cy_buy | mid_cy_buy | high_cy_buy] = 1.0
    signals[low_hl_buy | mid_hl_buy | high_hl_buy] = -1.0

    # 数据不足时设为 NaN
    signals[cy_mom.isna() | ratio_pct.isna() | cy_mom_pct.isna()] = np.nan

    return signals
```

### 3.3 保留纯动量策略

`generate_signals()` 保留不变，作为"纯动量"基线。新增 `generate_combined_signals()` 作为组合策略。

### 3.4 backtester.py 改动

- `run_backtest()` 增加 `strategy_type` 参数：`'momentum'` 或 `'combined'`
- 根据 `strategy_type` 选择不同的信号生成函数
- 回测结果增加 `ratio_percentile` 和 `cy_momentum_percentile` 列

### 3.5 app.py 改动

**实时卡片：**
- 新增比值百分位显示
- 新增动量百分位显示
- 信号区域增加"信号强度"标签（强信号 / 普通 / 空仓）

**比值图：**
- 增加百分位区域着色（绿色=低位，灰色=中间，红色=高位）
- 增加第三面板：百分位走势线（比值百分位 + 动量百分位）

**回测 Tab：**
- 增加策略选择下拉框（纯动量 / 组合策略）
- 增加对比模式：两条净值曲线叠加显示

---

## 4. 测试计划

### 4.1 单元测试

- `test_calculate_ratio_percentile`: 验证百分位计算正确性
- `test_combined_signals_low_percentile`: 低位时放宽门槛
- `test_combined_signals_high_percentile`: 高位时收紧门槛
- `test_combined_signals_mid_percentile`: 中间等同纯动量
- `test_backtest_combined`: 组合策略回测流程

### 4.2 回测验证

- 组合策略 vs 纯动量对比
- 关注：年化收益是否提升、最大回撤是否降低、夏普是否改善
- 参数敏感性：low/high 阈值从 10%/90% 到 30%/70% 扫描

---

## 5. 文件修改清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `config.py` | 修改 | 新增 `percentile_window`, `low_percentile`, `high_percentile` |
| `strategy.py` | 修改 | 新增 `calculate_ratio_percentile()`, `generate_combined_signals()` |
| `backtester.py` | 修改 | `run_backtest()` 增加 `strategy_type` 参数 |
| `app.py` | 修改 | 实时卡片增加百分位显示，回测增加策略选择和对比 |
| `tests/test_strategy.py` | 修改 | 新增组合策略测试用例 |
| `tests/test_backtester.py` | 修改 | 新增组合策略回测测试 |

---

## 6. 风险与局限

1. **参数增加**：组合策略多了 3 个参数（窗口、低阈值、高阈值），过拟合风险增大
2. **循环性能**：初始实现用 for 循环，需要后续向量化优化
3. **百分位滞后**：750 天窗口本身是滞后指标，极端行情时可能误判
4. **回测期有限**：2015 年至今数据量约 2500 天，750 天窗口意味着前 3 年无百分位数据
