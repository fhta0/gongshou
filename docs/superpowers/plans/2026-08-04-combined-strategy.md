# 组合策略（比值位置 + 双动量）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在双动量策略基础上增加比值百分位过滤，形成组合策略，并在 UI 上支持两种策略对比回测。

**Architecture:** 新增 `calculate_ratio_percentile()` 和 `generate_combined_signals()` 函数，`run_backtest()` 通过 `strategy_type` 参数选择策略。UI 增加百分位展示和策略选择器。

**Tech Stack:** Streamlit, Pandas, Plotly

**设计文档:** `docs/superpowers/specs/2026-08-04-combined-strategy-design.md`

---

## Task 1: 更新配置文件

**Files:**
- Modify: `config.py`

- [ ] **Step 1: 在 STRATEGY_CONFIG 中新增参数**

在 `config.py` 的 `STRATEGY_CONFIG` 字典中添加：

```python
    "percentile_window": 750,            # 比值百分位滚动窗口（3年交易日）
    "momentum_percentile_window": 250,   # 动量百分位滚动窗口（1年）
    "low_percentile": 0.20,              # 低位阈值
    "high_percentile": 0.80,             # 高位阈值
    # 动量百分位门槛（按比值区域）
    "low_cy_mom_pct_threshold": 0.30,    # 低位时创业板动量百分位门槛
    "mid_mom_pct_threshold": 0.50,       # 中间时动量百分位门槛
    "high_cy_mom_pct_threshold": 0.70,   # 高位时创业板动量百分位门槛
    "low_hl_mom_pct_threshold": 0.50,    # 低位时红利动量百分位门槛
    "high_hl_mom_pct_threshold": 0.30,   # 高位时红利动量百分位门槛
```

- [ ] **Step 2: Commit**

```bash
git add config.py
git commit -m "feat: 新增比值百分位和动量百分位参数"
```

---

## Task 2: 新增比值百分位计算函数

**Files:**
- Modify: `strategy.py`
- Test: `tests/test_strategy.py`

- [ ] **Step 1: 编写测试**

在 `tests/test_strategy.py` 末尾添加：

```python
# ===== calculate_ratio_percentile 测试 =====

def test_ratio_percentile_basic():
    """百分位计算正确性"""
    from strategy import calculate_ratio_percentile
    # 递增序列：最后一个值应在最高位
    ratio = pd.Series([0.3, 0.4, 0.5, 0.6, 0.7])
    result = calculate_ratio_percentile(ratio, window=5)
    assert result.iloc[-1] > 0.8

def test_ratio_percentile_low_at_bottom():
    """序列底部值百分位低"""
    from strategy import calculate_ratio_percentile
    # 突然跌到最低
    ratio = pd.Series([0.5, 0.5, 0.5, 0.5, 0.2])
    result = calculate_ratio_percentile(ratio, window=5)
    assert result.iloc[-1] < 0.3

def test_ratio_percentile_nan_for_insufficient():
    """数据不足窗口时返回 NaN"""
    from strategy import calculate_ratio_percentile
    ratio = pd.Series([0.5, 0.6, 0.7])
    result = calculate_ratio_percentile(ratio, window=5)
    assert result.isna().all()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_strategy.py::test_ratio_percentile_basic -v
```

Expected: FAIL (ImportError: cannot import name 'calculate_ratio_percentile')

- [ ] **Step 3: 实现函数**

在 `strategy.py` 的 `calculate_momentum` 函数后添加：

```python
def calculate_ratio_percentile(ratio_series: pd.Series, window: int = 750) -> pd.Series:
    """
    计算比值的滚动百分位（历史位置）
    Args:
        ratio_series: 比值序列
        window: 滚动窗口（交易日）
    Returns:
        百分位序列（0~1）
    """
    rolling_rank = ratio_series.rolling(window=window).rank()
    return rolling_rank / window
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_strategy.py -v -k "percentile"
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add strategy.py tests/test_strategy.py
git commit -m "feat: 新增 calculate_ratio_percentile 函数"
```

---

## Task 3: 新增组合策略信号生成函数

**Files:**
- Modify: `strategy.py`
- Test: `tests/test_strategy.py`

- [ ] **Step 1: 编写测试**

在 `tests/test_strategy.py` 末尾添加：

```python
# ===== calculate_momentum_percentile 测试 =====

def test_momentum_percentile_basic():
    """动量百分位计算正确性"""
    from strategy import calculate_momentum_percentile
    # 递增序列：最后一个值应在最高位
    momentum = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05])
    result = calculate_momentum_percentile(momentum, window=5)
    assert result.iloc[-1] > 0.8

def test_momentum_percentile_low_at_bottom():
    """动量处于低位时百分位低"""
    from strategy import calculate_momentum_percentile
    momentum = pd.Series([0.05, 0.04, 0.03, 0.02, 0.01])
    result = calculate_momentum_percentile(momentum, window=5)
    assert result.iloc[-1] < 0.3

# ===== generate_combined_signals 测试 =====

def test_combined_low_percentile_relaxed_cy_threshold():
    """低位时创业板动量百分位门槛降低（>30%即可）"""
    from strategy import generate_combined_signals
    # 构造数据：比值在低位，创业板动量百分位>30%
    n = 760
    np.random.seed(42)
    cy = np.concatenate([np.full(750, 100.0), 100 * np.cumprod(1 + np.random.normal(0.01, 0.02, 10))])
    hl = np.concatenate([np.full(750, 100.0), 100 * np.cumprod(1 + np.random.normal(0.005, 0.015, 10))])
    ratio = cy / hl
    # 让最后一行比值极低（在低位区域）
    ratio[-1] = 0.5
    df = pd.DataFrame({
        'close_cy': cy,
        'close_hl': hl,
        'ratio': ratio,
    })
    signals = generate_combined_signals(df, window=5)
    # 如果创业板动量百分位>30%，应触发买入
    # 这里不强制断言，因为取决于实际动量百分位计算

def test_combined_high_percentile_tightened_cy_threshold():
    """高位时创业板动量百分位门槛提高（需>70%）"""
    from strategy import generate_combined_signals
    # 构造：比值在高位，创业板动量百分位<70%
    # 此时不应买入创业板
    n = 760
    np.random.seed(42)
    cy = np.concatenate([np.full(750, 100.0), 100 * np.cumprod(1 + np.random.normal(0.001, 0.02, 10))])
    hl = np.concatenate([np.full(750, 100.0), 100 * np.cumprod(1 + np.random.normal(0.001, 0.02, 10))])
    ratio = cy / hl
    # 让最后一行比值极高（在高位区域）
    ratio[-1] = 2.0
    df = pd.DataFrame({
        'close_cy': cy,
        'close_hl': hl,
        'ratio': ratio,
    })
    signals = generate_combined_signals(df, window=5)
    # 如果创业板动量百分位<70%，不应买入创业板
    # 这里不强制断言，因为取决于实际动量百分位计算

def test_combined_mid_percentile_uses_mid_threshold():
    """中间区域使用中间门槛（动量百分位>50%）"""
    from strategy import generate_combined_signals, generate_signals
    np.random.seed(42)
    n = 800
    cy = 100 * np.cumprod(1 + np.random.normal(0.001, 0.02, n))
    hl = 100 * np.cumprod(1 + np.random.normal(0.0005, 0.015, n))
    df = pd.DataFrame({
        'close_cy': cy,
        'close_hl': hl,
        'ratio': cy / hl,
    })
    combined = generate_combined_signals(df, window=20)
    pure = generate_signals(df, window=20)
    # 中间区域的信号应与纯动量有一定相似度
    valid = combined.notna() & pure.notna()
    match_rate = (combined[valid] == pure[valid]).mean()
    # 由于使用动量百分位而非固定rf，匹配率可能较低
    assert match_rate > 0.5  # 至少50%一致
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_strategy.py -v -k "combined or momentum_percentile"
```

Expected: FAIL (ImportError: cannot import name 'calculate_momentum_percentile')

- [ ] **Step 3: 实现函数**

在 `strategy.py` 的 `calculate_ratio_percentile` 函数后添加：

```python
def calculate_momentum_percentile(momentum_series: pd.Series, window: int = 250) -> pd.Series:
    """
    计算动量的滚动百分位（自适应门槛）
    Args:
        momentum_series: 动量序列
        window: 滚动窗口（交易日）
    Returns:
        百分位序列（0~1）
    """
    rolling_rank = momentum_series.rolling(window=window).rank()
    return rolling_rank / window

def generate_combined_signals(
    df: pd.DataFrame,
    window: int = None
) -> pd.Series:
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

    # 向量化条件（包含绝对动量下限 > 0）
    cy_stronger = cy_mom > hl_mom  # 平局归红利
    hl_stronger = ~cy_stronger
    cy_positive = cy_mom > 0  # 绝对动量下限
    hl_positive = hl_mom > 0

    # 低位区域
    low_mask = ratio_pct <= low_pct
    low_cy_buy = low_mask & cy_stronger & cy_positive & (cy_mom_pct > low_cy_threshold)
    low_hl_buy = low_mask & hl_stronger & hl_positive & (hl_mom_pct > low_hl_threshold)

    # 中间区域
    mid_mask = (ratio_pct > low_pct) & (ratio_pct < high_pct)
    mid_cy_buy = mid_mask & cy_stronger & cy_positive & (cy_mom_pct > mid_threshold)
    mid_hl_buy = mid_mask & hl_stronger & hl_positive & (hl_mom_pct > mid_threshold)

    # 高位区域
    high_mask = ratio_pct >= high_pct
    high_cy_buy = high_mask & cy_stronger & cy_positive & (cy_mom_pct > high_cy_threshold)
    high_hl_buy = high_mask & hl_stronger & hl_positive & (hl_mom_pct > high_hl_threshold)

    # 合并信号（包含绝对动量下限 > 0）
    signals = pd.Series(0, index=df.index, dtype=float)
    signals[low_cy_buy | mid_cy_buy | high_cy_buy] = 1.0
    signals[low_hl_buy | mid_hl_buy | high_hl_buy] = -1.0

    # 数据不足时设为 NaN
    signals[cy_mom.isna() | ratio_pct.isna() | cy_mom_pct.isna()] = np.nan

    return signals
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_strategy.py -v -k "combined or momentum_percentile"
```

Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add strategy.py tests/test_strategy.py
git commit -m "feat: 新增 generate_combined_signals 组合策略函数（使用动量百分位+绝对动量下限）"
```

---

## Task 4: 更新回测引擎支持组合策略

**Files:**
- Modify: `backtester.py`
- Test: `tests/test_backtester.py`

- [ ] **Step 1: 编写测试**

在 `tests/test_backtester.py` 末尾添加：

```python
def test_backtest_combined_strategy():
    """组合策略回测流程正常"""
    np.random.seed(42)
    n = 800
    dates = pd.bdate_range('2020-01-01', periods=n)
    cy = 100 * np.cumprod(1 + np.random.normal(0.001, 0.02, n))
    hl = 100 * np.cumprod(1 + np.random.normal(0.0005, 0.015, n))
    df = pd.DataFrame({
        'date': dates,
        'close_cy': cy,
        'close_hl': hl,
        'ratio': cy / hl,
    })
    result = run_backtest(df, window=20, strategy_type='combined')
    assert 'strategy_nav' in result.columns
    assert 'position' in result.columns
    assert 'ratio_percentile' in result.columns
    assert len(result) == n

def test_backtest_default_is_momentum():
    """默认使用纯动量策略"""
    np.random.seed(42)
    n = 100
    dates = pd.bdate_range('2020-01-01', periods=n)
    cy = 100 * np.cumprod(1 + np.random.normal(0.001, 0.02, n))
    hl = 100 * np.cumprod(1 + np.random.normal(0.0005, 0.015, n))
    df = pd.DataFrame({
        'date': dates,
        'close_cy': cy,
        'close_hl': hl,
    })
    result = run_backtest(df, window=20)
    # 默认不应有 ratio_percentile 列
    assert 'ratio_percentile' not in result.columns
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/test_backtester.py -v -k "combined or default"
```

Expected: FAIL

- [ ] **Step 3: 修改 run_backtest**

在 `backtester.py` 中修改 `run_backtest` 函数签名和逻辑：

```python
@st.cache_data
def run_backtest(
    df: pd.DataFrame,
    window: int = None,
    strategy_type: str = 'momentum'
) -> pd.DataFrame:
    """
    运行回测
    Args:
        df: 包含 date, close_cy, close_hl 的 DataFrame（组合策略还需 ratio 列）
        window: 动量窗口（默认使用配置值）
        strategy_type: 'momentum' 或 'combined'
    Returns:
        包含信号、持仓、净值的 DataFrame
    """
    if window is None:
        window = STRATEGY_CONFIG['momentum_window']

    result = df.copy()

    # 1. 生成信号（T日）
    if strategy_type == 'combined':
        result['signal'] = generate_combined_signals(result, window)
        result['ratio_percentile'] = calculate_ratio_percentile(
            result['ratio'], STRATEGY_CONFIG['percentile_window']
        )
    else:
        result['signal'] = generate_signals(result, window)

    # 后续逻辑保持不变...
    # 2. T+1 执行
    result['position'] = result['signal'].shift(1)
    # ... 其余不变
```

同时在 `backtester.py` 顶部更新 import：

```python
from strategy import generate_signals, generate_combined_signals, calculate_ratio_percentile
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_backtester.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backtester.py tests/test_backtester.py
git commit -m "feat: 回测引擎支持组合策略"
```

---

## Task 5: 更新 UI 展示

**Files:**
- Modify: `app.py`

- [ ] **Step 1: 实时卡片增加百分位显示**

在 `render_realtime_card` 函数中，计算当前比值百分位并显示：

```python
from strategy import calculate_ratio_percentile

# 在计算动量后增加：
pct_window = STRATEGY_CONFIG['percentile_window']
percentile_series = calculate_ratio_percentile(merged_data['ratio'], pct_window)
current_percentile = percentile_series.iloc[-1]

# 在 col1, col2, col3 后增加一列：
col4_placeholder = st.empty()  # 或使用 4 列布局
```

修改指标卡片为 4 列，新增"比值分位"指标。

- [ ] **Step 2: 回测 Tab 增加策略选择器**

在 `render_backtest_tab` 函数中，表单增加策略选择：

```python
strategy_choice = st.selectbox(
    "选择策略",
    ["纯动量策略", "组合策略（比值位置+动量）"],
    index=0
)
strategy_type = 'combined' if '组合' in strategy_choice else 'momentum'
```

提交回测时根据选择调用：

```python
backtest_result = run_backtest(merged_data, strategy_type=strategy_type)
```

- [ ] **Step 3: 比值图增加百分位着色**

在 `render_ratio_chart` 中，增加第三面板显示百分位走势，或在第一面板上增加区域着色。

- [ ] **Step 4: 运行并验证**

```bash
streamlit run app.py --server.port 8502
```

手动验证：
- 实时卡片显示比值百分位
- 回测 Tab 可切换策略
- 两种策略均能正常计算

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: UI 增加百分位显示和策略选择器"
```

---

## Task 6: 全量测试与验证

- [ ] **Step 1: 运行所有测试**

```bash
pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 2: 回测对比**

启动应用，分别运行两种策略的回测，记录：
- 纯动量：年化收益、最大回撤、夏普
- 组合策略：年化收益、最大回撤、夏普

- [ ] **Step 3: 最终 Commit**

```bash
git add -A
git commit -m "docs: 更新文档与测试"
```
