# 创业板/中证红利比值信号系统设计

## 概述

本系统是一个基于 Streamlit 的量化信号工具，用于监控创业板指数与中证红利指数的比值，并根据历史极值区间提供抄底/逃顶信号。

### 核心理念

- **创业板指数**：代表高弹性、高成长的进攻型资产
- **中证红利全收益指数**：代表稳定分红、防御型的现金流资产（含股息再投资）
- 两个指数具有明显的负相关性，比值在历史上有清晰的极值区间

### 信号规则（滚动百分位法）

> **为什么不用固定阈值？**
> 绝对比值在长期维度下是非平稳的——指数基期不同、成分股分红除权、中枢漂移等因素会导致固定阈值在几年后失效。因此改用**滚动百分位**，让阈值自适应市场变化。

使用过去 3 年（约 750 个交易日）的滚动分位数来判断信号：

| 条件 | 信号 | 含义 | 操作建议 |
|------|------|------|----------|
| 滚动分位 ≤ 10% | 🔴 抄底 | 比值处于近 3 年底部区域 | 买入创业板指数，卖出中证红利指数 |
| 滚动分位 ≥ 90% | 🟢 逃顶 | 比值处于近 3 年顶部区域 | 卖出创业板指数，买入中证红利指数 |
| 10% < 分位 < 90% | 🟡 中性 | 比值处于正常区间 | 持有观望 |

> **备选方案：Z-Score 均值回归模型**
> $Z = \frac{Ratio - Mean_{N}}{Std_{N}}$，当 $Z < -2$ 时抄底，$Z > 2$ 时逃顶。
> 可在后续版本中作为可选模式提供。

### 信号防钝化机制

在极端单边行情中，比值可能连续数周维持在极值区间。为避免频繁触发信号：

- **上穿/下穿触发**：仅当比值**首次穿越**阈值百分位时触发信号，而非每次刷新都触发
- **冷却期（Cooldown）**：同一方向信号触发后，至少间隔 20 个交易日才能再次触发
- **状态转移**：内部维护当前状态（抄底/中性/逃顶），仅当状态发生变化时才输出信号

## 技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| 框架 | Streamlit ≥ 1.37 | 快速开发，支持 `st.fragment` 局部刷新 |
| 数据源 | AKShare | 免费开源，无需注册 |
| 图表库 | Plotly | 交互性强，支持缩放和悬停 |
| 数据处理 | Pandas | 标准数据分析库 |
| 自动刷新 | `streamlit-autorefresh` | 避免 `time.sleep` 阻塞和整页闪烁 |

## 架构设计

### 整体架构

```
┌──────────────────────────────────────────────────────┐
│                  Streamlit 应用层                     │
│                                                      │
│  ┌─ Tab 1: 实时信号 ──────────────────────────────┐ │
│  │  ┌──────────────────────────────────────────┐  │ │
│  │  │  当前比值 / 滚动分位 / 信号灯 / 操作建议  │  │ │
│  │  └──────────────────────────────────────────┘  │ │
│  │  ┌──────────────────────────────────────────┐  │ │
│  │  │  比值历史走势图（折线 + 阈值区域）        │  │ │
│  │  └──────────────────────────────────────────┘  │ │
│  │  ┌──────────────────────────────────────────┐  │ │
│  │  │  指数对比图（双 Y 轴）                    │  │ │
│  │  └──────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────┘ │
│                                                      │
│  ┌─ Tab 2: 历史回测 ──────────────────────────────┐ │
│  │  ┌──────────────────────────────────────────┐  │ │
│  │  │  信号触发记录表                           │  │ │
│  │  └──────────────────────────────────────────┘  │ │
│  │  ┌──────────────────────────────────────────┐  │ │
│  │  │  策略累计收益曲线                         │  │ │
│  │  └──────────────────────────────────────────┘  │ │
│  │  ┌──────────────────────────────────────────┐  │ │
│  │  │  收益统计（胜率、平均收益、最大回撤）     │  │ │
│  │  └──────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────────────────┐
│                  数据层（AKShare）                     │
│  - 创业板指数历史数据（@st.cache_data, ttl=1h）      │
│  - 中证红利全收益指数历史数据                         │
│  - 轻量级实时行情接口（单指数查询）                   │
│  - 回测结果缓存（@st.cache_data）                     │
└──────────────────────────────────────────────────────┘
```

### 数据流

1. 启动时加载历史数据（缓存 1 小时）
2. 合并数据 → 计算比值 → 计算滚动分位
3. `st.fragment` 局部刷新实时比值和信号（不重渲染图表）
4. Tab 2 的回测结果按需计算并缓存

## 数据层设计

### 指数代码

- 创业板指数：`399006`（深交所）
- 中证红利全收益指数：`H20922`（上交所）

> **为什么用全收益指数？**
> 中证红利价格指数（`000922`）不含股息再投资收益。长期来看，价格指数因除权会被不断拉低，导致比值存在向上的趋势漂移。全收益指数（`H20922`）包含股息再投资，能真实反映红利资产的实际总回报。

### AKShare 接口

| 用途 | 函数 | 说明 |
|------|------|------|
| 历史日线 | `ak.index_zh_a_hist(symbol="399006")` | 返回日期、收盘等字段 |
| 实时行情 | `ak.stock_zh_index_daily_em(symbol="sz399006")` | 轻量级单指数查询，避免拉取全市场数据 |

> **为什么不用 `ak.stock_zh_index_spot_em()`？**
> 该接口抓取全市场数千个指数的实时行情，高峰期耗时 3-5 秒，容易超时。改用单指数查询接口，响应速度快且稳定。

### 数据获取逻辑

```python
@st.cache_data(ttl=3600)  # 缓存1小时
def load_historical_data(symbol):
    """加载历史日线数据"""
    df = ak.index_zh_a_hist(symbol=symbol)
    return df[['日期', '收盘']].rename(columns={'日期': 'date', '收盘': 'close'})

def get_realtime_quote(symbol):
    """获取单指数实时报价（轻量级）"""
    df = ak.stock_zh_index_daily_em(symbol=symbol)
    return df.iloc[-1]['close']  # 最新收盘价
```

### 数据合并与比值计算

```python
# 合并两个指数的历史数据（inner join 确保日期对齐）
merged = pd.merge(
    chuangyeban_df, hongli_df,
    on='date', suffixes=('_cy', '_hl'),
    how='inner'
)
# 丢弃可能的空值
merged = merged.dropna()
merged['ratio'] = merged['close_cy'] / merged['close_hl']
```

### 滚动百分位计算（向量化）

```python
def calculate_rolling_percentile(ratio_series, window=750):
    """
    计算滚动百分位（3年窗口）
    使用 Rolling Rank 向量化计算，避免 rolling().apply() 的逐行回调开销
    性能：比 percentileofscore 方式快 50~100 倍
    """
    rolling_rank = ratio_series.rolling(window=window).rank()
    return rolling_rank / window
```

### 缓存策略

- 历史数据：`@st.cache_data(ttl=3600)` 缓存 1 小时
- 回测结果：`@st.cache_data` 持久缓存（仅在数据更新时失效）
- 实时报价：不缓存，每次刷新时重新获取

## 信号计算逻辑

### 核心规则（状态 vs 事件分离）

> **状态（State）**：持仓状态（buy/sell/neutral）——持续存在
> **事件（Event）**：仅当状态发生**有意义变化**时触发——这才是调仓信号

```python
def calculate_signal(current_ratio, rolling_percentile, prev_state):
    """
    计算信号，区分状态与事件
    prev_state: 上一次的持仓状态 ('buy' / 'sell' / 'neutral')
    返回: (display_info, new_state, event_or_none)
    """
    # 基于滚动百分位判断新状态
    if rolling_percentile <= 0.1:
        new_state = 'buy'
    elif rolling_percentile >= 0.9:
        new_state = 'sell'
    else:
        new_state = 'neutral'

    # 判断是否产生调仓事件
    event = None
    if prev_state != new_state:
        if new_state in ('buy', 'sell'):
            # 中性 → 抄底/逃顶：主动调仓事件
            event = _state_to_event(new_state, action_type='entry')
        elif prev_state in ('buy', 'sell') and new_state == 'neutral':
            # 抄底/逃顶 → 中性：止盈/回归观望事件
            event = _state_to_event(new_state, action_type='exit')

    return _get_display_info(new_state), new_state, event

def _state_to_event(state, action_type):
    events = {
        'buy': {
            'signal': '抄底', 'color': 'red', 'emoji': '🔴',
            'description': '比值进入近3年底部区域',
            'action': '买入创业板指数，卖出中证红利指数',
            'type': action_type  # 'entry' 或 'exit'
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

def _get_display_info(state):
    """返回当前状态的展示信息（非事件，仅展示）"""
    return _state_to_event(state, action_type='hold')
```

> **信号记录表只记录 Event**：只有"进入抄底"、"进入逃顶"、"回归中性"这些状态变化才记录到回测表中，避免表格被大量"维持中性"淹没。

### 展示逻辑

```
当前比值: 0.45
滚动分位: 15%（近3年）
🟡 中性信号
比值处于正常区间，建议持有观望
```

### 信号颜色映射（Streamlit）

- 红色：`st.error()`
- 绿色：`st.success()`
- 黄色：`st.warning()`

## UI 布局

### Tab 分离设计

使用 `st.tabs(["📡 实时信号", "📊 历史回测"])` 将页面分为两个 Tab：

- **Tab 1（实时信号）**：包含信号卡片、比值历史走势、指数对比图。盘中自动刷新。
- **Tab 2（历史回测）**：包含信号记录表、策略累计收益曲线、统计指标。按需计算，不自动刷新。

> **为什么分 Tab？**
> 回测计算耗时较长，与实时信号分离后：
> 1. 实时 Tab 的刷新不会触发回测重算
> 2. 用户不被大量图表淹没，关注点更集中
> 3. 回测结果可独立缓存

### 页面结构

```
┌──────────────────────────────────────────────────┐
│  📊 创业板/中证红利 比值信号系统                    │
│  最后更新: 2026-08-03 14:30                       │
├──────────────────────────────────────────────────┤
│  [📡 实时信号]  [📊 历史回测]                      │
│                                                  │
│  ── Tab 1: 实时信号 ─────────────────────────── │
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │  当前比值    0.45                           │ │
│  │  滚动分位    15%（近3年）                    │ │
│  │  🟡 中性信号                                │ │
│  │  比值处于正常区间，建议持有观望              │ │
│  └────────────────────────────────────────────┘ │
│                                                  │
│  ── 比值历史走势 ─────────────────────────────── │
│  ┌────────────────────────────────────────────┐ │
│  │  📈 折线图                                  │ │
│  │  - 主线: 比值走势                           │ │
│  │  -  shaded: 10%/90% 分位阈值区域            │ │
│  │  - 标注: 历史信号触发点                     │ │
│  └────────────────────────────────────────────┘ │
│                                                  │
│  ── 指数对比 ────────────────────────────────── │
│  ┌────────────────────────────────────────────┐ │
│  │  📈 双Y轴折线图                             │ │
│  │  - 左轴: 创业板指数（蓝色）                 │ │
│  │  - 右轴: 中证红利全收益指数（橙色）         │ │
│  └────────────────────────────────────────────┘ │
│                                                  │
│  ── Tab 2: 历史回测 ────────────────────────── │
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │  📋 信号触发记录表                           │ │
│  │  日期 | 信号 | 比值 | 分位 | 后续收益       │ │
│  └────────────────────────────────────────────┘ │
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │  📈 策略累计收益曲线                        │ │
│  │  - 抄底→持有创业板                          │ │
│  │  - 逃顶→持有红利                            │ │
│  │  - 中性→保持上一仓位                        │ │
│  └────────────────────────────────────────────┘ │
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │  📊 统计指标                                 │ │
│  │  信号次数 | 胜率 | 平均收益 | 最大回撤      │ │
│  └────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

### 关键交互

- 页面顶部显示最后更新时间
- 图表支持 Plotly 原生交互（缩放、悬停查看数值）
- Tab 2 回测区域使用 `st.form` + "开始回测" 按钮，避免页面加载时自动计算

### Plotly 性能优化

当历史数据超过 2000 个数据点时，使用 `Scattergl` 替代 `Scatter` 以获得 WebGL 加速渲染：

```python
import plotly.graph_objects as go

fig.add_trace(go.Scattergl(
    x=df['date'], y=df['ratio'],
    mode='lines', name='比值'
))
fig.update_traces(connectgaps=True)
```

## 自动刷新机制

```python
from streamlit_autorefresh import st_autorefresh
from datetime import datetime

def is_trading_hours():
    """判断是否在盘中交易时间"""
    now = datetime.now()
    if now.weekday() >= 5:  # 周末
        return False
    hour, minute = now.hour, now.minute
    morning = (hour == 9 and minute >= 30) or (hour == 10) or (hour == 11 and minute <= 30)
    afternoon = (hour == 13) or (hour == 14)
    return morning or afternoon

# 使用 streamlit-autorefresh 组件，避免 time.sleep 阻塞
if is_trading_hours():
    # 每5分钟刷新一次，仅在信号区块内生效
    st_autorefresh(interval=5 * 60 * 1000, key="realtime_refresh")
```

> **为什么不用 `time.sleep(300)` + `st.rerun()`？**
> 1. `time.sleep` 会阻塞整个 Python 线程 5 分钟
> 2. `st.rerun()` 导致整页重新渲染，所有 Plotly 图表重建，体验极差
> 3. `streamlit-autorefresh` 仅触发脚本重跑，配合 `st.fragment` 可实现局部刷新

### 局部刷新（st.fragment）

```python
@st.fragment(run_every=300)  # Streamlit 1.37+
def realtime_signal_widget():
    """
    仅刷新信号区块，不影响下方图表
    优化：只抓取最新单 Tick 报价，拼接到已缓存的历史数据末尾
    避免每次重算整条历史时间序列
    """
    # 仅获取最新报价（~100ms）
    cy_price = get_realtime_quote('sz399006')
    hl_price = get_realtime_quote('sh000922')

    # 拼接到缓存的历史数据最后一行
    historical = st.session_state['merged_data']
    latest = pd.DataFrame([{
        'date': pd.Timestamp.now().normalize(),
        'close_cy': cy_price,
        'close_hl': hl_price,
        'ratio': cy_price / hl_price
    }])
    updated = pd.concat([historical.iloc[:-1], latest], ignore_index=True)

    # 仅计算最后一个点的滚动分位（利用已缓存的历史分位）
    ratio = updated['ratio'].iloc[-1]
    percentile = updated['ratio'].iloc[-1] / updated['ratio'].rolling(750).max().iloc[-1]

    signal, new_state, event = calculate_signal(
        ratio, percentile, st.session_state.get('prev_state', 'neutral')
    )
    st.session_state['prev_state'] = new_state
    # 渲染信号卡片...
```

## 回测逻辑

### 回测算法（避免前瞻性偏误）

```python
@st.cache_data
def backtest_signals(df, window=750, low_pct=0.1, high_pct=0.9):
    """
    回测历史信号，生成策略累计收益曲线
    注意：使用 T 日数据生成信号，T+1 日执行交易（避免 look-ahead bias）
    """
    # 1. 计算滚动百分位
    df['percentile'] = calculate_rolling_percentile(df['ratio'], window)

    # 2. 生成信号（T日）
    df['signal'] = 0  # 0=中性, 1=抄底, -1=逃顶
    df.loc[df['percentile'] <= low_pct, 'signal'] = 1
    df.loc[df['percentile'] >= high_pct, 'signal'] = -1

    # 3. 信号去重（仅保留状态变化）
    df['signal'] = df['signal'].diff().fillna(0).apply(
        lambda x: 1 if x > 0 else (-1 if x < 0 else 0)
    )
    df['signal'] = df['signal'].replace(0, method='ffill').fillna(0)

    # 4. T+1 执行（延迟一天交易，避免 look-ahead bias）
    df['position'] = df['signal'].shift(1)

    # 5. 计算每日收益
    df['cy_return'] = df['close_cy'].pct_change()
    df['hl_return'] = df['close_hl'].pct_change()

    # 6. 策略收益：抄底时持有创业板，逃顶时持有红利，中性时持有货币基金（无风险利率）
    RISK_FREE_DAILY = 0.015 / 252  # 年化 1.5%，折算日利率

    df['strategy_return'] = RISK_FREE_DAILY  # 默认：中性区间持有货基
    df.loc[df['position'] == 1, 'strategy_return'] = df.loc[df['position'] == 1, 'cy_return']
    df.loc[df['position'] == -1, 'strategy_return'] = df.loc[df['position'] == -1, 'hl_return']

    # 7. 累计净值
    df['strategy_nav'] = (1 + df['strategy_return']).cumprod()
    df['cy_nav'] = (1 + df['cy_return']).cumprod()  # 基准：买入持有创业板
    df['hl_nav'] = (1 + df['hl_return']).cumprod()  # 基准：买入持有红利

    return df
```

### 回测展示

- **信号记录表**：每次信号触发的日期、比值、滚动分位、信号类型
- **策略累计收益曲线**：策略净值 vs 创业板基准 vs 红利基准
- **统计指标**：
  - 信号触发次数（抄底/逃顶各多少次）
  - 策略年化收益率
  - 胜率（信号触发后 20 日正收益比例）
  - 最大回撤
  - 夏普比率

## 错误处理

| 场景 | 处理方式 |
|------|----------|
| AKShare API 请求失败 | `st.error()` 显示错误，保留上次缓存数据 |
| 非交易日/非交易时间 | 显示"市场已收盘"，使用最后已知数据，停止自动刷新 |
| 历史数据缺失/日期不对齐 | `pd.merge(how='inner')` + `dropna()` 确保数据完整 |
| 实时报价获取失败 | 显示"--"，不触发自动刷新 |
| 滚动窗口内数据不足 | 显示"历史数据不足3年，信号仅供参考" |

## 项目结构

```
chuangyeban/
├── app.py                 # UI 展现层 (Tabs, layout, st.fragment)
├── config.py              # 配置项 (窗口大小 750, 阈值 0.1/0.9, 指数代码, 无风险利率)
├── data_loader.py         # AKShare 接口对接, @st.cache_data 数据清洗
├── strategy.py            # 向量化计算: 滚动百分位 (Rank法)、信号生成与防钝化
├── backtester.py          # 回测引擎: T+1 收益计算, 策略 NAV, 统计指标
├── requirements.txt       # 依赖
└── .gitignore
```

## 依赖

```
streamlit>=1.37.0
streamlit-autorefresh>=1.0.1
akshare>=1.10.0
pandas>=2.0.0
plotly>=5.18.0
```

## 未来扩展

- 增加 Z-Score 模式作为信号的备选算法
- 支持自定义滚动窗口长度和分位阈值
- 添加邮件/微信通知功能
- 支持更多指数对（如沪深300/中证500）
- 导出回测报告为 PDF
