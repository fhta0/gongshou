# 创业板/中证红利比值信号系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Streamlit dashboard that monitors the ratio of ChiNext Index to CSI Dividend Total Return Index, generating buy/sell signals based on rolling percentile thresholds with real-time updates during trading hours.

**Architecture:** Five-module Streamlit app: `config.py` (centralized parameters), `data_loader.py` (AKShare data fetching with caching), `strategy.py` (vectorized rolling percentile + state/event signal logic), `backtester.py` (T+1 execution engine with cumulative NAV), `app.py` (Tab-based UI with st.fragment for partial refresh).

**Tech Stack:** Streamlit ≥ 1.37, AKShare, Pandas, Plotly (Scattergl), streamlit-autorefresh, pytest

---

## File Structure

| File | Responsibility |
|------|---------------|
| `config.py` | Global config: index codes, thresholds, window size, risk-free rate |
| `data_loader.py` | AKShare interface, historical data loading, real-time change %, data merging |
| `strategy.py` | Rolling percentile (vectorized rank), signal calculation (state vs event) |
| `backtester.py` | Backtest engine: T+1 execution, strategy NAV, statistics (win rate, Sharpe, max drawdown) |
| `app.py` | Streamlit UI: tabs, signal card, Plotly charts, auto-refresh, st.fragment |
| `tests/test_strategy.py` | Unit tests for rolling percentile and signal logic |
| `tests/test_backtester.py` | Unit tests for backtest engine and statistics |
| `requirements.txt` | Dependencies |

---

### Task 1: Project Setup & Configuration

**Files:**
- Create: `requirements.txt`
- Create: `config.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```txt
streamlit>=1.37.0
streamlit-autorefresh>=1.0.1
akshare>=1.10.0
pandas>=2.0.0
plotly>=5.18.0
pytest>=7.0.0
```

- [ ] **Step 2: Create config.py**

```python
"""
全局配置：指数代码、阈值、窗口大小、无风险利率等
修改此文件即可适配其他指数对（如沪深300/中证500）
"""

STRATEGY_CONFIG = {
    "symbol_a": {
        "code": "399006",
        "name": "创业板指",
        "spot_code": "sz399006"
    },
    "symbol_b": {
        "code": "H20922",
        "name": "中证红利全收益",
        "spot_code": "sh000922"
    },
    "rolling_window": 750,       # 3年交易日
    "low_percentile": 0.10,      # 抄底阈值
    "high_percentile": 0.90,     # 逃顶阈值
    "risk_free_rate": 0.015,     # 年化无风险利率 1.5%
    "cooldown_days": 20          # 信号冷却期（交易日）
}
```

- [ ] **Step 3: Create tests directory**

```bash
mkdir -p tests
touch tests/__init__.py
```

- [ ] **Step 4: Install dependencies**

```bash
pip install -r requirements.txt
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt config.py tests/__init__.py
git commit -m "feat: project setup with config and dependencies"
```

---

### Task 2: Data Loader — Historical Data

**Files:**
- Create: `data_loader.py`

- [ ] **Step 1: Create data_loader.py with historical data loading**

```python
"""
数据层：AKShare 接口对接，数据清洗与缓存
"""
import akshare as ak
import pandas as pd
import streamlit as st
from config import STRATEGY_CONFIG


@st.cache_data(ttl=3600)
def load_historical_data(symbol: str) -> pd.DataFrame:
    """
    加载单指数历史日线数据
    Args:
        symbol: 指数代码，如 '399006'
    Returns:
        DataFrame with columns: ['date', 'close']
    """
    try:
        df = ak.index_zh_a_hist(symbol=symbol)
        result = df[['日期', '收盘']].copy()
        result.columns = ['date', 'close']
        result['date'] = pd.to_datetime(result['date'])
        return result
    except Exception as e:
        st.error(f"获取历史数据失败 ({symbol}): {e}")
        return pd.DataFrame(columns=['date', 'close'])


def load_merged_data() -> pd.DataFrame:
    """
    加载并合并两个指数的历史数据，计算比值
    Returns:
        DataFrame with columns: ['date', 'close_cy', 'close_hl', 'ratio']
    """
    symbol_a = STRATEGY_CONFIG['symbol_a']['code']
    symbol_b = STRATEGY_CONFIG['symbol_b']['code']

    df_a = load_historical_data(symbol_a)
    df_b = load_historical_data(symbol_b)

    if df_a.empty or df_b.empty:
        st.error("历史数据加载失败，请检查网络连接")
        return pd.DataFrame()

    # Inner join 确保日期对齐
    merged = pd.merge(df_a, df_b, on='date', suffixes=('_cy', '_hl'), how='inner')
    merged = merged.dropna()
    merged['ratio'] = merged['close_cy'] / merged['close_hl']
    return merged.reset_index(drop=True)
```

- [ ] **Step 2: Quick smoke test**

```bash
python -c "from data_loader import load_historical_data; df = load_historical_data('399006'); print(df.head())"
```

Expected: DataFrame with 'date' and 'close' columns, ~3000+ rows

- [ ] **Step 3: Commit**

```bash
git add data_loader.py
git commit -m "feat: data loader with historical data loading and merging"
```

---

### Task 3: Data Loader — Real-time Change

**Files:**
- Modify: `data_loader.py`

- [ ] **Step 1: Add get_realtime_change function**

Append to `data_loader.py`:

```python
def get_realtime_change(spot_code: str) -> float:
    """
    获取单指数盘中实时涨跌幅（轻量级）
    Args:
        spot_code: 如 'sz399006'
    Returns:
        float, 如 0.015 表示涨 1.5%
    """
    try:
        df = ak.stock_zh_index_daily_em(symbol=spot_code)
        if len(df) < 2:
            return 0.0
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        return (latest['close'] - prev['close']) / prev['close']
    except Exception as e:
        st.error(f"获取实时行情失败 ({spot_code}): {e}")
        return 0.0
```

- [ ] **Step 2: Quick smoke test**

```bash
python -c "from data_loader import get_realtime_change; print(get_realtime_change('sz399006'))"
```

Expected: A float like `0.0123` (or similar)

- [ ] **Step 3: Commit**

```bash
git add data_loader.py
git commit -m "feat: add real-time change percentage fetching"
```

---

### Task 4: Strategy — Rolling Percentile (TDD)

**Files:**
- Create: `strategy.py`
- Create: `tests/test_strategy.py`

- [ ] **Step 1: Write the failing test**

```python
"""tests/test_strategy.py"""
import pandas as pd
import pytest
from strategy import calculate_rolling_percentile


def test_rolling_percentile_basic():
    """滚动百分位：已知序列的百分位计算"""
    # 构造一个简单递增序列 [1, 2, 3, 4, 5]
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = calculate_rolling_percentile(series, window=5)

    # 最后一个值 5 应该是窗口内最大值，百分位接近 1.0
    assert result.iloc[-1] == pytest.approx(1.0, abs=0.01)

    # 第一个有效值（index=4, window=5）
    assert result.iloc[4] == pytest.approx(1.0, abs=0.01)


def test_rolling_percentile_with_window():
    """滚动百分位：窗口外的值不影响"""
    series = pd.Series([10.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
    result = calculate_rolling_percentile(series, window=5)

    # 最后一个窗口 [5,6,7,8,9]，9 是最大值
    assert result.iloc[-1] == pytest.approx(1.0, abs=0.01)


def test_rolling_percentile_nan_for_insufficient_data():
    """数据不足窗口时返回 NaN"""
    series = pd.Series([1.0, 2.0, 3.0])
    result = calculate_rolling_percentile(series, window=5)

    # 前4个值都应该是 NaN（窗口不够）
    assert result.iloc[:4].isna().all()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_strategy.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'strategy'`

- [ ] **Step 3: Write minimal implementation**

```python
"""strategy.py"""
import pandas as pd


def calculate_rolling_percentile(ratio_series: pd.Series, window: int = 750) -> pd.Series:
    """
    计算滚动百分位（向量化 Rank 法）
    使用 Rolling Rank 代替 apply(percentileofscore)，性能提升 50-100 倍
    Args:
        ratio_series: 比值序列
        window: 滚动窗口大小（默认 750 = 3 年交易日）
    Returns:
        滚动百分位序列，值域 [0, 1]
    """
    rolling_rank = ratio_series.rolling(window=window).rank()
    return rolling_rank / window
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_strategy.py -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add strategy.py tests/test_strategy.py
git commit -m "feat: vectorized rolling percentile with tests"
```

---

### Task 5: Strategy — Signal Calculation (TDD)

**Files:**
- Modify: `strategy.py`
- Modify: `tests/test_strategy.py`

- [ ] **Step 1: Write failing tests for signal calculation**

Append to `tests/test_strategy.py`:

```python
from strategy import calculate_signal


def test_signal_buy_when_percentile_low():
    """分位 ≤ 0.1 时触发抄底信号"""
    display, new_state, event = calculate_signal(
        current_ratio=0.25,
        rolling_percentile=0.05,
        prev_state='neutral'
    )
    assert new_state == 'buy'
    assert event is not None
    assert event['signal'] == '抄底'
    assert event['type'] == 'entry'


def test_signal_sell_when_percentile_high():
    """分位 ≥ 0.9 时触发逃顶信号"""
    display, new_state, event = calculate_signal(
        current_ratio=0.85,
        rolling_percentile=0.95,
        prev_state='neutral'
    )
    assert new_state == 'sell'
    assert event is not None
    assert event['signal'] == '逃顶'
    assert event['type'] == 'entry'


def test_signal_neutral_in_middle():
    """分位在 0.1~0.9 之间为中性"""
    display, new_state, event = calculate_signal(
        current_ratio=0.5,
        rolling_percentile=0.5,
        prev_state='neutral'
    )
    assert new_state == 'neutral'
    assert event is None  # 中性到中性，无事件


def test_signal_no_event_when_state_unchanged():
    """状态不变时不触发事件"""
    display, new_state, event = calculate_signal(
        current_ratio=0.25,
        rolling_percentile=0.05,
        prev_state='buy'  # 已经是 buy
    )
    assert new_state == 'buy'
    assert event is None  # buy → buy，无事件


def test_signal_exit_event_when_returning_to_neutral():
    """从抄底/逃顶回归中性时触发 exit 事件"""
    display, new_state, event = calculate_signal(
        current_ratio=0.5,
        rolling_percentile=0.5,
        prev_state='buy'  # 从 buy 变到 neutral
    )
    assert new_state == 'neutral'
    assert event is not None
    assert event['signal'] == '中性'
    assert event['type'] == 'exit'


def test_display_info_always_returned():
    """始终返回展示信息"""
    display, _, _ = calculate_signal(0.5, 0.5, 'neutral')
    assert 'signal' in display
    assert 'emoji' in display
    assert 'description' in display
    assert 'action' in display
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_strategy.py::test_signal_buy_when_percentile_low -v
```

Expected: FAIL — `ImportError: cannot import name 'calculate_signal'`

- [ ] **Step 3: Implement signal calculation**

Append to `strategy.py`:

```python
from typing import Tuple, Optional
from config import STRATEGY_CONFIG


def calculate_signal(
    current_ratio: float,
    rolling_percentile: float,
    prev_state: str
) -> Tuple[dict, str, Optional[dict]]:
    """
    计算信号，区分状态与事件
    Args:
        current_ratio: 当前比值
        rolling_percentile: 当前滚动百分位
        prev_state: 上一次的持仓状态 ('buy' / 'sell' / 'neutral')
    Returns:
        (display_info, new_state, event_or_none)
        - display_info: 当前状态展示信息
        - new_state: 新的持仓状态
        - event_or_none: 调仓事件（仅状态变化时非 None）
    """
    low_pct = STRATEGY_CONFIG['low_percentile']
    high_pct = STRATEGY_CONFIG['high_percentile']

    # 基于滚动百分位判断新状态
    if rolling_percentile <= low_pct:
        new_state = 'buy'
    elif rolling_percentile >= high_pct:
        new_state = 'sell'
    else:
        new_state = 'neutral'

    # 判断是否产生调仓事件
    event = None
    if prev_state != new_state:
        if new_state in ('buy', 'sell'):
            event = _state_to_event(new_state, action_type='entry')
        elif prev_state in ('buy', 'sell') and new_state == 'neutral':
            event = _state_to_event(new_state, action_type='exit')

    return _get_display_info(new_state), new_state, event


def _state_to_event(state: str, action_type: str) -> dict:
    """将状态转为事件字典"""
    events = {
        'buy': {
            'signal': '抄底', 'color': 'red', 'emoji': '🔴',
            'description': '比值进入近3年底部区域',
            'action': '买入创业板指数，卖出中证红利指数',
            'type': action_type
        },
        'sell': {
            'signal': '逃顶', 'color': 'green', 'emoji': '🟢',
            'description': '比值进入近3年顶部区域',
            'action': '卖出创业板指数，买入中证红利指数',
            'type': action_type
        },
        'neutral': {
            'signal': '中性', 'color': 'orange', 'emoji': '🟡',
            'description': '比值回归正常区间',
            'action': '止盈观望',
            'type': action_type
        }
    }
    return events[state]


def _get_display_info(state: str) -> dict:
    """返回当前状态的展示信息（非事件，仅展示）"""
    return _state_to_event(state, action_type='hold')
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/test_strategy.py -v
```

Expected: 9 PASSED (3 from rolling percentile + 6 from signal)

- [ ] **Step 5: Commit**

```bash
git add strategy.py tests/test_strategy.py
git commit -m "feat: signal calculation with state/event separation and tests"
```

---

### Task 6: Backtester — Core Engine (TDD)

**Files:**
- Create: `backtester.py`
- Create: `tests/test_backtester.py`

- [ ] **Step 1: Write failing tests for backtest engine**

```python
"""tests/test_backtester.py"""
import pandas as pd
import pytest
from backtester import run_backtest
from config import STRATEGY_CONFIG


@pytest.fixture
def sample_data():
    """构造测试数据：100天，前50天比值低（抄底区），后50天比值高（逃顶区）"""
    dates = pd.date_range('2020-01-01', periods=100, freq='B')
    # 前50天比值低 → 百分位低 → 抄底信号
    # 后50天比值高 → 百分位高 → 逃顶信号
    ratio_low = [0.3] * 50
    ratio_high = [0.8] * 50

    df = pd.DataFrame({
        'date': dates,
        'close_cy': [100 + i * 0.5 for i in range(100)],  # 创业板缓慢上涨
        'close_hl': [200 - i * 0.2 for i in range(100)],  # 红利缓慢下跌
        'ratio': ratio_low + ratio_high
    })
    return df


def test_backtest_returns_dataframe_with_nav(sample_data):
    """回测应返回包含净值列的 DataFrame"""
    result = run_backtest(sample_data, window=20)  # 小窗口用于测试

    assert 'strategy_nav' in result.columns
    assert 'cy_nav' in result.columns
    assert 'hl_nav' in result.columns
    assert 'position' in result.columns
    assert len(result) == len(sample_data)


def test_backtest_t1_execution(sample_data):
    """T+1 执行：信号日不交易，次日才建仓"""
    result = run_backtest(sample_data, window=20)

    # 第一天 position 应该是 NaN（没有前一天信号）
    assert pd.isna(result['position'].iloc[0])


def test_backtest_position_values(sample_data):
    """仓位值应为 1（抄底）、-1（逃顶）或 0（中性）"""
    result = run_backtest(sample_data, window=20)

    valid_positions = {1.0, -1.0, 0.0, float('nan')}
    actual_positions = set(result['position'].dropna().unique())
    assert actual_positions.issubset({1.0, -1.0, 0.0})


def test_backtest_nav_starts_at_1(sample_data):
    """净值曲线应从 1 开始"""
    result = run_backtest(sample_data, window=20)

    # 第一个有效净值应该接近 1
    first_valid = result['strategy_nav'].dropna().iloc[0]
    assert first_valid == pytest.approx(1.0, abs=0.01)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_backtester.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'backtester'`

- [ ] **Step 3: Implement backtest engine**

```python
"""backtester.py"""
import pandas as pd
import streamlit as st
from config import STRATEGY_CONFIG
from strategy import calculate_rolling_percentile


@st.cache_data
def run_backtest(
    df: pd.DataFrame,
    window: int = None,
    low_pct: float = None,
    high_pct: float = None
) -> pd.DataFrame:
    """
    回测历史信号，生成策略累计收益曲线
    T 日数据生成信号，T+1 日执行交易（避免 look-ahead bias）

    Args:
        df: 包含 date, close_cy, close_hl, ratio 的 DataFrame
        window: 滚动窗口大小
        low_pct: 抄底阈值
        high_pct: 逃顶阈值
    Returns:
        DataFrame with position, strategy_return, strategy_nav, cy_nav, hl_nav
    """
    if window is None:
        window = STRATEGY_CONFIG['rolling_window']
    if low_pct is None:
        low_pct = STRATEGY_CONFIG['low_percentile']
    if high_pct is None:
        high_pct = STRATEGY_CONFIG['high_percentile']

    result = df.copy()

    # 1. 计算滚动百分位
    result['percentile'] = calculate_rolling_percentile(result['ratio'], window)

    # 2. 生成信号（T日）
    result['signal'] = 0  # 0=中性, 1=抄底, -1=逃顶
    result.loc[result['percentile'] <= low_pct, 'signal'] = 1
    result.loc[result['percentile'] >= high_pct, 'signal'] = -1

    # 3. 信号去重（仅保留状态变化，前向填充持仓）
    result['signal'] = result['signal'].replace(0, method='ffill').fillna(0)

    # 4. T+1 执行（延迟一天交易）
    result['position'] = result['signal'].shift(1)

    # 5. 计算每日收益
    result['cy_return'] = result['close_cy'].pct_change()
    result['hl_return'] = result['close_hl'].pct_change()

    # 6. 策略收益：抄底→创业板，逃顶→红利，中性→无风险利率
    risk_free_daily = STRATEGY_CONFIG['risk_free_rate'] / 252
    result['strategy_return'] = risk_free_daily  # 默认：中性持有货基
    result.loc[result['position'] == 1, 'strategy_return'] = result.loc[result['position'] == 1, 'cy_return']
    result.loc[result['position'] == -1, 'strategy_return'] = result.loc[result['position'] == -1, 'hl_return']

    # 7. 累计净值
    result['strategy_nav'] = (1 + result['strategy_return'].fillna(0)).cumprod()
    result['cy_nav'] = (1 + result['cy_return'].fillna(0)).cumprod()
    result['hl_nav'] = (1 + result['hl_return'].fillna(0)).cumprod()

    return result
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_backtester.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add backtester.py tests/test_backtester.py
git commit -m "feat: backtest engine with T+1 execution and tests"
```

---

### Task 7: Backtester — Statistics

**Files:**
- Modify: `backtester.py`
- Modify: `tests/test_backtester.py`

- [ ] **Step 1: Write failing tests for statistics**

Append to `tests/test_backtester.py`:

```python
from backtester import calculate_statistics


def test_statistics_structure():
    """统计结果应包含关键指标"""
    df = pd.DataFrame({
        'strategy_nav': [1.0, 1.05, 1.10, 1.08, 1.15],
        'cy_nav': [1.0, 1.02, 1.04, 1.03, 1.06],
        'hl_nav': [1.0, 1.01, 1.015, 1.02, 1.025],
        'position': [0, 1, 1, 0, -1],
        'strategy_return': [0.0, 0.05, 0.0476, -0.0182, 0.0648]
    })
    stats = calculate_statistics(df)

    assert 'total_return' in stats
    assert 'annualized_return' in stats
    assert 'max_drawdown' in stats
    assert 'sharpe_ratio' in stats
    assert 'win_rate' in stats


def test_max_drawdown_calculation():
    """最大回撤计算正确"""
    df = pd.DataFrame({
        'strategy_nav': [1.0, 1.2, 1.1, 1.0, 1.3],
        'strategy_return': [0.0, 0.2, -0.0833, -0.0909, 0.3]
    })
    stats = calculate_statistics(df)

    # 从 1.2 跌到 1.0，回撤 = (1.2 - 1.0) / 1.2 = 16.67%
    assert stats['max_drawdown'] == pytest.approx(0.1667, abs=0.01)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_backtester.py::test_statistics_structure -v
```

Expected: FAIL — `ImportError: cannot import name 'calculate_statistics'`

- [ ] **Step 3: Implement statistics function**

Append to `backtester.py`:

```python
def calculate_statistics(df: pd.DataFrame) -> dict:
    """
    计算回测统计指标
    Args:
        df: 包含 strategy_nav, strategy_return 的 DataFrame
    Returns:
        dict with keys: total_return, annualized_return, max_drawdown, sharpe_ratio, win_rate
    """
    nav = df['strategy_nav'].dropna()
    returns = df['strategy_return'].dropna()

    if len(nav) < 2:
        return {
            'total_return': 0.0,
            'annualized_return': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0,
            'win_rate': 0.0
        }

    # 总收益率
    total_return = (nav.iloc[-1] / nav.iloc[0]) - 1

    # 年化收益率（假设 252 交易日）
    n_days = len(nav)
    annualized_return = (1 + total_return) ** (252 / n_days) - 1

    # 最大回撤
    cummax = nav.cummax()
    drawdown = (cummax - nav) / cummax
    max_drawdown = drawdown.max()

    # 夏普比率（假设无风险利率 1.5%）
    risk_free_daily = STRATEGY_CONFIG['risk_free_rate'] / 252
    excess_returns = returns - risk_free_daily
    sharpe_ratio = (excess_returns.mean() / excess_returns.std()) * (252 ** 0.5) if excess_returns.std() > 0 else 0.0

    # 胜率（正收益天数占比）
    win_rate = (returns > 0).sum() / len(returns) if len(returns) > 0 else 0.0

    return {
        'total_return': total_return,
        'annualized_return': annualized_return,
        'max_drawdown': max_drawdown,
        'sharpe_ratio': sharpe_ratio,
        'win_rate': win_rate
    }
```

- [ ] **Step 4: Run all backtester tests**

```bash
pytest tests/test_backtester.py -v
```

Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add backtester.py tests/test_backtester.py
git commit -m "feat: backtest statistics (return, drawdown, Sharpe, win rate)"
```

---

### Task 8: App — Main Layout & Tab Structure

**Files:**
- Create: `app.py`

- [ ] **Step 1: Create app.py with basic layout**

```python
"""
创业板/中证红利比值信号系统 - Streamlit 主入口
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

from config import STRATEGY_CONFIG
from data_loader import load_merged_data, get_realtime_change
from strategy import calculate_rolling_percentile, calculate_signal
from backtester import run_backtest, calculate_statistics


# 页面配置
st.set_page_config(
    page_title="比值信号系统",
    page_icon="📊",
    layout="wide"
)


def is_trading_hours() -> bool:
    """判断是否在盘中交易时间"""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    hour, minute = now.hour, now.minute
    morning = (hour == 9 and minute >= 30) or (hour == 10) or (hour == 11 and minute <= 30)
    afternoon = (hour == 13) or (hour == 14)
    return morning or afternoon


def main():
    # 标题
    st.title("📊 创业板/中证红利 比值信号系统")

    # 加载历史数据
    with st.spinner("加载历史数据..."):
        merged_data = load_merged_data()

    if merged_data.empty:
        st.error("数据加载失败，请刷新页面重试")
        st.stop()

    # 存入 session state
    st.session_state['merged_data'] = merged_data

    # 最后更新时间
    last_update = merged_data['date'].iloc[-1].strftime('%Y-%m-%d')
    st.caption(f"历史数据截至: {last_update}")

    # 盘中自动刷新
    if is_trading_hours():
        st_autorefresh(interval=5 * 60 * 1000, key="realtime_refresh")
        st.info("🔴 盘中模式：每 5 分钟自动刷新")

    # Tab 布局
    tab1, tab2 = st.tabs(["📡 实时信号", "📊 历史回测"])

    with tab1:
        render_signal_tab(merged_data)

    with tab2:
        render_backtest_tab(merged_data)


def render_signal_tab(merged_data: pd.DataFrame):
    """Tab 1: 实时信号"""
    st.subheader("当前信号")

    # 计算当前比值和分位
    ratio = merged_data['ratio'].iloc[-1]
    percentiles = calculate_rolling_percentile(merged_data['ratio'], STRATEGY_CONFIG['rolling_window'])
    percentile = percentiles.iloc[-1]

    # 获取信号
    prev_state = st.session_state.get('prev_state', 'neutral')
    display, new_state, event = calculate_signal(ratio, percentile, prev_state)
    st.session_state['prev_state'] = new_state

    # 信号卡片
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("当前比值", f"{ratio:.4f}")
    with col2:
        st.metric("滚动分位", f"{percentile:.1%}")
    with col3:
        st.metric("状态", f"{display['emoji']} {display['signal']}")

    # 信号描述
    if display['color'] == 'red':
        st.error(f"**{display['description']}**\n\n操作建议：{display['action']}")
    elif display['color'] == 'green':
        st.success(f"**{display['description']}**\n\n操作建议：{display['action']}")
    else:
        st.warning(f"**{display['description']}**\n\n操作建议：{display['action']}")

    # 新事件提醒
    if event and event['type'] == 'entry':
        st.balloons()
        st.toast(f"🔔 新信号：{event['signal']}！", icon="🚨")

    # 比值历史走势图
    st.subheader("比值历史走势")
    render_ratio_chart(merged_data, percentiles)

    # 指数对比图
    st.subheader("指数对比")
    render_index_comparison(merged_data)


def render_ratio_chart(merged_data: pd.DataFrame, percentiles: pd.Series):
    """绘制比值历史走势图"""
    import plotly.graph_objects as go

    fig = go.Figure()

    # 使用 Scattergl 提升大数据集性能
    fig.add_trace(go.Scattergl(
        x=merged_data['date'],
        y=merged_data['ratio'],
        mode='lines',
        name='比值',
        line=dict(color='royalblue', width=2)
    ))

    # 阈值区域
    fig.add_hline(y=STRATEGY_CONFIG['low_percentile'], line_dash="dash", line_color="red",
                  annotation_text="抄底线 10%")
    fig.add_hline(y=STRATEGY_CONFIG['high_percentile'], line_dash="dash", line_color="green",
                  annotation_text="逃顶线 90%")

    fig.update_layout(
        xaxis_title="日期",
        yaxis_title="比值（创业板/中证红利）",
        hovermode='x unified',
        height=400
    )
    fig.update_traces(connectgaps=True)

    st.plotly_chart(fig, use_container_width=True)


def render_index_comparison(merged_data: pd.DataFrame):
    """绘制双Y轴指数对比图"""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scattergl(x=merged_data['date'], y=merged_data['close_cy'],
                     name=STRATEGY_CONFIG['symbol_a']['name'],
                     line=dict(color='blue')),
        secondary_y=False
    )

    fig.add_trace(
        go.Scattergl(x=merged_data['date'], y=merged_data['close_hl'],
                     name=STRATEGY_CONFIG['symbol_b']['name'],
                     line=dict(color='orange')),
        secondary_y=True
    )

    fig.update_xaxes(title_text="日期")
    fig.update_yaxes(title_text=STRATEGY_CONFIG['symbol_a']['name'], secondary_y=False)
    fig.update_yaxes(title_text=STRATEGY_CONFIG['symbol_b']['name'], secondary_y=True)
    fig.update_layout(height=400, hovermode='x unified')

    st.plotly_chart(fig, use_container_width=True)


def render_backtest_tab(merged_data: pd.DataFrame):
    """Tab 2: 历史回测"""
    st.subheader("历史回测")

    # 使用 form + button 避免自动计算
    with st.form("backtest_form"):
        st.markdown("点击按钮开始回测（可能需要几秒钟）")
        submitted = st.form_submit_button("🚀 开始回测")

    if submitted:
        with st.spinner("正在计算回测..."):
            backtest_result = run_backtest(merged_data)
            stats = calculate_statistics(backtest_result)

        # 统计指标
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("总收益率", f"{stats['total_return']:.2%}")
        with col2:
            st.metric("年化收益率", f"{stats['annualized_return']:.2%}")
        with col3:
            st.metric("最大回撤", f"{stats['max_drawdown']:.2%}")
        with col4:
            st.metric("夏普比率", f"{stats['sharpe_ratio']:.2f}")
        with col5:
            st.metric("胜率", f"{stats['win_rate']:.2%}")

        # 策略累计收益曲线
        st.subheader("策略累计收益曲线")
        render_nav_chart(backtest_result)

        # 信号记录表
        st.subheader("信号触发记录")
        render_signal_table(backtest_result)


def render_nav_chart(backtest_result: pd.DataFrame):
    """绘制策略净值曲线"""
    import plotly.graph_objects as go

    fig = go.Figure()

    fig.add_trace(go.Scattergl(
        x=backtest_result['date'], y=backtest_result['strategy_nav'],
        mode='lines', name='策略净值', line=dict(color='purple', width=2)
    ))
    fig.add_trace(go.Scattergl(
        x=backtest_result['date'], y=backtest_result['cy_nav'],
        mode='lines', name='创业板基准', line=dict(color='blue', dash='dash')
    ))
    fig.add_trace(go.Scattergl(
        x=backtest_result['date'], y=backtest_result['hl_nav'],
        mode='lines', name='红利基准', line=dict(color='orange', dash='dash')
    ))

    fig.update_layout(
        xaxis_title="日期",
        yaxis_title="净值",
        hovermode='x unified',
        height=400
    )
    fig.update_traces(connectgaps=True)

    st.plotly_chart(fig, use_container_width=True)


def render_signal_table(backtest_result: pd.DataFrame):
    """绘制信号触发记录表"""
    # 提取状态变化点
    signals = backtest_result[backtest_result['signal'].diff() != 0].copy()

    if signals.empty:
        st.info("回测期间无信号触发")
        return

    # 格式化显示
    display_df = signals[['date', 'signal', 'ratio', 'percentile']].copy()
    display_df['date'] = display_df['date'].dt.strftime('%Y-%m-%d')
    display_df['ratio'] = display_df['ratio'].apply(lambda x: f"{x:.4f}")
    display_df['percentile'] = display_df['percentile'].apply(lambda x: f"{x:.1%}")
    display_df['signal'] = display_df['signal'].map({1: '🔴 抄底', -1: '🟢 逃顶', 0: '🟡 中性'})
    display_df.columns = ['日期', '信号', '比值', '分位']

    st.dataframe(display_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the app**

```bash
streamlit run app.py
```

Expected: Browser opens at http://localhost:8501 with the dashboard

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: Streamlit app with tabs, charts, and backtest UI"
```

---

### Task 9: Final Integration & Polish

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Update .gitignore**

Ensure `.gitignore` includes:

```
.superpowers/
__pycache__/
*.pyc
.env
.venv/
```

- [ ] **Step 2: Run all tests**

```bash
pytest tests/ -v
```

Expected: 15 PASSED (3 rolling percentile + 6 signal + 4 backtest engine + 2 statistics)

- [ ] **Step 3: Final commit**

```bash
git add .gitignore
git commit -m "chore: finalize project, all tests passing"
```

- [ ] **Step 4: Launch and verify**

```bash
streamlit run app.py
```

Verify:
1. Tab 1 shows current ratio, percentile, signal
2. Ratio chart displays with threshold lines
3. Index comparison chart shows dual Y-axis
4. Tab 2 backtest button works
5. Statistics display correctly
6. Signal table shows state transitions

---

## Summary

| Task | Module | Description | Est. Time |
|------|--------|-------------|-----------|
| 1 | Setup | requirements.txt, config.py | 5 min |
| 2 | data_loader | Historical data loading | 10 min |
| 3 | data_loader | Real-time change fetching | 5 min |
| 4 | strategy | Rolling percentile (TDD) | 15 min |
| 5 | strategy | Signal calculation (TDD) | 20 min |
| 6 | backtester | Backtest engine (TDD) | 20 min |
| 7 | backtester | Statistics (TDD) | 15 min |
| 8 | app | Streamlit UI | 30 min |
| 9 | Integration | Final polish & verify | 10 min |
| **Total** | | | **~2 hours** |
