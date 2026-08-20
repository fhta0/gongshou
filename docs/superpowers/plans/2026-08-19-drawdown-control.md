# 实施计划：数据口径修正 + 回撤控制层

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修正红利数据口径（000922 价格指数 + 股息率估算，近似全收益；H20922 数据源经实测不可用），并实现回撤控制机制——按 **B（趋势过滤）→ C（动量衰竭，测增量）→ D（波动率目标）→ A（回撤止损，可选）** 顺序分阶段叠加，每阶段独立 A/B 验证。验收：保底线 回撤 ≤25% / 年化 ≥+8% / Calmar ≥0.4 / 夏普 ≥0.6；理想目标 回撤 ≤20% / Calmar ≥0.5 / 夏普 ≥0.7。

**Architecture:** 数据层先行（S0）。风控机制与信号生成解耦，纯动量与组合策略统一受益。机制 A 默认关闭、仅当 B/C/D 后回撤仍 >25% 才评估；机制 C 测增量、无改善则弃用。机制 B 用多窗口平滑动量（[60,120,200]）保持与短周期一致的平滑口径。

**Tech Stack:** Streamlit, Pandas, AKShare

**设计文档:** `docs/superpowers/specs/2026-08-19-drawdown-control-design.md`

---

> ⚠️ **前置说明**：当前工作区有未提交的"多窗口平滑动量"改动（app.py / config.py / strategy.py / tests/test_strategy.py）。实施本计划前，先提交或暂存这些改动，保证每个 commit 单一逻辑。

## Task 0: 提交/暂存当前未提交改动

- [ ] **Step 1: 提交平滑动量改动**

```bash
git add app.py config.py strategy.py tests/test_strategy.py
git commit -m "feat: 多窗口平滑动量（10/20/40天均值）替代单一20天窗口"
```

- [ ] **Step 2: 确认基线测试通过**

```bash
pytest tests/ -q
```

Expected: 43 passed（当前基线）

---

## Task 1 (S0): 数据口径修正 — 红利价格指数 + 股息率估算（退路方案）

> **数据可得性核查结论（2026-08-19 实测，已定案）**：H20922（akshare csindex / 官网 API）、ETF 累计净值（eastmoney）均不可用，走退路方案：000922 价格指数 + 常数股息率 4.5%。核查明细与误差分析见 spec §2.1。

**Files:**
- Modify: `config.py`, `data_loader.py`
- Test: `tests/test_data_loader.py`（新增）

- [ ] **Step 1: 新增配置参数（config.py）**

```python
"dividend_yield": 0.045,   # 中证红利历史股息率常数近似（年化，价格指数→全收益折算）
```

- [ ] **Step 2: 实现股息再投资折算（data_loader.py）**

新增纯函数（便于单元测试），并在 `load_historical_hl()` 返回前调用：

```python
def _apply_dividend_adjustment(close: pd.Series, dividend_yield: float = None) -> pd.Series:
    """
    对价格指数序列叠加股息再投资，近似全收益指数
    公式：adjusted[t] = adjusted[t-1] × (1 + 日价格收益 + 年化股息率/252)
    """
    if close.empty:
        return close
    if dividend_yield is None:
        dividend_yield = STRATEGY_CONFIG.get('dividend_yield', 0.045)
    div_daily = dividend_yield / 252
    total_return = close.pct_change() + div_daily
    return close.iloc[0] * (1 + total_return.fillna(0)).cumprod()
```

```python
# load_historical_hl() 内，astype(float) 之后：
result['close'] = _apply_dividend_adjustment(result['close'])
```

- [ ] **Step 3: 编写单元测试（tests/test_data_loader.py，新增）**

覆盖：首值不变、股息再投资增长快于价格、横盘仍增长、公式精确性、股息率=0 等价原序列、空序列。

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_data_loader.py -v
pytest tests/ -q
```

- [ ] **Step 5: A/B 基线对比（原始 000922 口径 vs 折算后口径）**

跑两种策略回测，记录：年化、最大回撤、夏普、持仓分布。预期：红利持仓占比上升、创业板下降、最大回撤下降。结果记录到 spec §3.1 或独立文档。

- [ ] **Step 6: Commit**

```bash
git add config.py data_loader.py tests/test_data_loader.py
git commit -m "fix: 红利价格指数叠加股息再投资(4.5%年化)近似全收益口径"
```

---

## Task 2 (S1): 机制 B — 长期趋势过滤（平滑动量）

**Files:**
- Modify: `strategy.py`
- Test: `tests/test_strategy.py`

- [ ] **Step 1: 新增配置参数（config.py）**

```python
"trend_filter_windows": [60, 120, 200],  # 长周期趋势过滤窗口（多窗口平滑，与短周期口径一致）
```

- [ ] **Step 2: 编写测试（先红）**

在 `tests/test_strategy.py` 添加：

```python
def test_trend_filter_blocks_when_long_momentum_negative():
    """长周期平滑动量为负时信号强制为 0"""
    # 构造：价格 200 天前高于现在（长期下行）但短期动量为正
    # 预期：generate_signals 输出 0

def test_trend_filter_preserves_signal_when_positive():
    """长周期平滑动量为正时不改变原信号"""

def test_trend_filter_nan_during_warmup():
    """趋势窗口数据不足时信号保持 NaN（不把无数据当看空）"""
```

- [ ] **Step 3: 实现 `_apply_trend_filter`**

在 `strategy.py` 新增，向量化，应用于 `generate_signals` 与 `generate_combined_signals` 的 raw 信号（冷却期之前）：

```python
def _apply_trend_filter(raw_signals: pd.Series,
                        close_cy: pd.Series,
                        close_hl: pd.Series,
                        windows: list = None) -> pd.Series:
    """
    长周期趋势过滤：持有标的长周期平滑动量 > 0 才允许持仓，否则空仓。
    与短周期一致的平滑口径（calculate_smoothed_momentum）。
    """
    if windows is None:
        windows = STRATEGY_CONFIG.get('trend_filter_windows', [60, 120, 200])
    cy_trend = calculate_smoothed_momentum(close_cy, windows)
    hl_trend = calculate_smoothed_momentum(close_hl, windows)
    cy_trend_ok = cy_trend > 0
    hl_trend_ok = hl_trend > 0
    result = raw_signals.copy()
    result[((result == 1) & ~cy_trend_ok) | ((result == -1) & ~hl_trend_ok)] = 0
    # 趋势数据不足（暖机期）→ 保持 NaN，与现有"数据不足设 NaN"口径一致
    result[cy_trend.isna() | hl_trend.isna()] = np.nan
    return result
```

> 注意：`~cy_trend_ok` 对 NaN 会得到 True（NaN > 0 为 False），必须用后续的 `isna()` 赋值覆盖，顺序不能反。

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_strategy.py -v -k "trend_filter"
pytest tests/ -q
```

- [ ] **Step 5: A/B 验证（S1）**

S0 基线 ± 趋势过滤对比。重点看 2022-2024 阴跌段的持仓与回撤；确认暖机期延长（200 天）的收益代价可接受。

- [ ] **Step 6: Commit**

```bash
git add strategy.py tests/test_strategy.py config.py
git commit -m "feat: 长期趋势过滤（多窗口平滑动量[60/120/200]>0）"
```

---

## Task 3 (S2): 机制 C — 动量衰竭退出（测增量）

**Files:**
- Modify: `strategy.py`
- Test: `tests/test_strategy.py`

- [ ] **Step 1: 新增配置参数（config.py）**

```python
"decay_exit_threshold": 0.20,  # 动量衰竭退出阈值（动量百分位低于此值退出）
```

- [ ] **Step 2: 编写测试（先红）**

```python
def test_decay_exit_blocks_hold_when_percentile_low():
    """持有标的方向信号但动量百分位低于阈值 → 信号改为 0"""
    # 构造：raw 信号为 1（买创业板）但 cy_mom_pct < 0.20

def test_decay_exit_preserves_strong_momentum():
    """动量百分位高于阈值时信号不变"""
```

- [ ] **Step 3: 实现 `_apply_momentum_decay_exit`**

在 `strategy.py` 新增，逐日向量化（无状态依赖），在冷却期之前应用：

```python
def _apply_momentum_decay_exit(raw_signals: pd.Series,
                               cy_mom_pct: pd.Series,
                               hl_mom_pct: pd.Series,
                               threshold: float = None) -> pd.Series:
    """
    动量衰竭退出：信号为买入某标的但该标的动量百分位 < threshold 时改为空仓。
    阈值(0.20) < 所有入场门槛(0.30~0.70)，只影响"曾经满足入场后衰减"的持仓。
    """
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_strategy.py -v -k "decay_exit"
pytest tests/ -q
```

- [ ] **Step 5: A/B 验证（S2）—— 增量判定**

S1 基线 ± 动量衰竭退出对比。按 spec §2.4 判定标准：
- 回撤改善 ≥ 2pp 且年化损失 ≤ 1pp → 保留
- **回撤改善 < 2pp 且年化损失 > 1pp → 弃用 C**（保留代码与测试，默认关闭，commit 时在消息中记录结论）
- 重点看 2021 年底筑顶期是否比 B 更早退出

- [ ] **Step 6: Commit**

```bash
# 保留时
git add strategy.py tests/test_strategy.py config.py
git commit -m "feat: 动量衰竭退出（动量百分位<20%时退出，增量验证通过）"

# 弃用时（实现与测试保留，默认关闭）
git add strategy.py tests/test_strategy.py config.py
git commit -m "feat: 动量衰竭退出（实现完成，增量验证无改善，默认关闭）"
```

---

## Task 4 (S3): 机制 D — 波动率目标仓位

**Files:**
- Modify: `backtester.py`
- Test: `tests/test_backtester.py`

- [ ] **Step 1: 新增配置参数（config.py）**

```python
"target_vol": 0.12,       # 目标年化波动率
"vol_lookback": 20,       # 实现波动率回看窗口（交易日）
```

- [ ] **Step 2: 编写测试（先红）**

```python
def test_vol_target_scales_down_in_high_vol():
    """高波动期 scale < 1（降仓）"""

def test_vol_target_caps_at_one():
    """低波动期 scale 封顶 1.0（不加杠杆）"""

def test_vol_target_return_formula():
    """收益 = scale×标的收益 + (1-scale)×无风险日收益"""
```

- [ ] **Step 3: 实现波动率目标收益计算**

在 `backtester.py` 的收益计算段：

```python
# 滚动年化波动率（cy / hl）
cy_vol = result['cy_return'].rolling(vol_lookback).std() * (252 ** 0.5)
hl_vol = result['hl_return'].rolling(vol_lookback).std() * (252 ** 0.5)

# 按持仓取对应波动率，计算 scale（封顶 1.0）
vol = np.where(result['position'] == 1.0, cy_vol,
       np.where(result['position'] == -1.0, hl_vol, np.nan))
scale = (target_vol / vol).clip(upper=1.0).fillna(1.0)  # 波动率≈0/空仓时满仓

# 策略收益 = scale×标的收益 + (1-scale)×无风险收益
result['strategy_return'] = (scale * result['strategy_return']
                             + (1 - scale) * risk_free_daily)
```

> 注意：`vol` 为 NaN（空仓日）时 scale 取 1.0，此时 strategy_return 本来就是 risk_free_daily，公式自洽。

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/test_backtester.py -v -k "vol_target"
pytest tests/ -q
```

- [ ] **Step 5: A/B 验证（S3）**

S2 基线 ± 波动率目标对比。重点看净值曲线平滑度（月度亏损分布、回撤）与夏普。

- [ ] **Step 6: Commit**

```bash
git add backtester.py tests/test_backtester.py config.py
git commit -m "feat: 波动率目标仓位（目标年化12%，降仓不平仓）"
```

---

## Task 5 (S4): 机制 A — 净值回撤止损（可选，go/no-go）

**Files:**
- Modify: `backtester.py`（若启用）
- Test: `tests/test_backtester.py`（若启用）

- [ ] **Step 1: go/no-go 判定（先于实现）**

跑 S3 完整基线（B+C+D 全开），看最大回撤：
- **回撤 ≤ 25% → 不实现 A**，直接执行 Step 5（记录结论）并跳过 Step 2-4
- **回撤 > 25% → 继续 Step 2**（启用 A）

- [ ] **Step 2: 新增配置参数（config.py）**

```python
"dd_stop_threshold": 0.15,   # 净值回撤止损阈值（扣费后净值，相对峰值）
"dd_stop_cooldown": 20,      # 止损后强制空仓天数
```

- [ ] **Step 3: 编写测试（先红）**

```python
def test_drawdown_stop_forces_cash():
    """净值回撤超过阈值后强制空仓"""
    # 构造：先涨后深跌的价格序列，使策略净值回撤超过 15%

def test_drawdown_stop_cooldown_then_resume():
    """止损后冷却期内保持空仓，冷却结束后恢复正常信号"""

def test_drawdown_stop_counts_as_switch():
    """止损触发的空仓应计为一次切换（收交易成本）"""
```

- [ ] **Step 4: 实现 `apply_drawdown_stop`**

在 `backtester.py` 新增，按日循环模拟（参考 `_apply_cooldown` 风格）：

```python
def apply_drawdown_stop(result: pd.DataFrame,
                        threshold: float = None,
                        cooldown: int = None) -> pd.DataFrame:
    """
    净值回撤止损：strategy_nav_net 相对峰值回撤 ≥ threshold 时强制空仓，
    空仓持续 cooldown 天后恢复按信号执行。
    返回带止损后 position / is_switch 的 DataFrame。
    """
    # 1. 按日循环：维护 running nav（扣费后）、峰值、空仓剩余天数
    # 2. 空仓剩余天数 > 0 → position=0；否则恢复 result['position']
    # 3. 记录 is_switch（止损触发与恢复各计一次）
```

在 `run_backtest` 中于 T+1 持仓计算之后调用（收益/成本计算之前）。注意：止损后需**重算**收益、成本、净值列（止损改变了持仓序列）。

- [ ] **Step 5: 记录 go/no-go 结论 + A/B 验证（S4，若启用）**

无论是否启用，都把判定与验证结果记录到 spec §4（验收结论）。若启用：S3 基线 ± 回撤止损对比，重点验证尾部风险与"卖在低点"代价。

- [ ] **Step 6: Commit**

```bash
# 启用时
git add backtester.py tests/test_backtester.py config.py
git commit -m "feat: 净值回撤止损（阈值15%+冷却20天，B/C/D后回撤仍>25%触发）"

# 不启用时（仅记录结论）
git add docs/
git commit -m "docs: 回撤止损 go/no-go 判定——B/C/D 已把回撤压至≤25%，A 不启用"
```

---

## Task 6: 组合验证与参数敏感性

- [ ] **Step 1: 全机制组合回测**

最终方案（B+C/D 保留项 + A 若启用）跑两种策略完整 A/B，输出：年化、最大回撤、夏普、Calmar、分年收益表、持仓分布、切换次数、累计成本。

- [ ] **Step 2: 样本外验证**

- 样本内 2018-03 ~ 2022-12 调参；样本外 2023-01 ~ 最新只验证
- **定位**：样本外检验"收益不回退"而非"风控有效"（OOS 区间无深跌，见 spec §3.2）
- 风控有效性以样本内压力段（2018 / 2020 / 2021-2024）的分段与分年表为证据
- 可选：滚动窗口多次切片（walk-forward）

- [ ] **Step 3: 参数敏感性网格**

- B：窗口组 {[120], [60,120,200], [120,200,250]}
- C（若保留）：threshold ∈ {0.10, 0.20, 0.30}
- D：target_vol ∈ {10%, 12%, 15%}，vol_lookback ∈ {20, 60}
- A（若启用）：threshold ∈ {10%, 15%, 20%}，cooldown ∈ {10, 20, 40}
- 确认指标呈平台状而非尖峰状，网格结果表格记录到 spec

- [ ] **Step 4: 成本敏感性**

单边成本 {0.1%, 0.2%, 0.3%} × 最终方案，确认结论不翻转。

- [ ] **Step 5: 更新 spec 验收结论**

按 spec §4 两档标准逐项核对（保底：回撤 ≤25% / 年化 ≥+8% / Calmar ≥0.4 / 夏普 ≥0.6；理想：回撤 ≤20% / Calmar ≥0.5 / 夏普 ≥0.7），如实记录达标情况与未达标原因。

- [ ] **Step 6: Commit**

```bash
git add docs/
git commit -m "docs: 记录回撤控制层回测结果与参数敏感性结论"
```

---

## Task 7: UI 开关（可选）

**Files:**
- Modify: `app.py`

- [ ] **Step 1: 回测表单增加机制开关**

`render_backtest_tab` 的 form 增加多选框：启用趋势过滤 / 动量衰竭退出（若保留）/ 波动率目标（默认开）；回撤止损（若启用，默认关），传参给 `run_backtest`。

- [ ] **Step 2: 手动验证**

```bash
streamlit run app.py
```

回测 Tab 各开关组合均可正常出结果；实时 Tab 不受影响（本期实时端不应用回撤控制，见 spec §6-6）。

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: 回测表单暴露回撤控制机制开关"
```

---

## 完成标准（DoD）

- [ ] 全部测试通过（`pytest tests/ -q`）
- [ ] 红利口径修正落地（000922 + 股息率 4.5% 估算）并有新旧口径 A/B 记录
- [ ] 机制 B 实现并验证；机制 C 完成增量判定（保留或弃用均有结论记录）；机制 D 实现并验证；机制 A 完成 go/no-go 判定（启用或不启用均有结论记录）
- [ ] 样本外验证（收益不回退定位）与参数敏感性网格完成，结论记录到 spec
- [ ] 验收指标按两档标准逐项核对（保底：回撤 ≤25% / 年化 ≥+8% / Calmar ≥0.4 / 夏普 ≥0.6），达标或如实记录偏差

---

## Phase B：实盘化准备

> **前置条件**：Task 1-7 全部完成，Phase A 验证通过（6 项验收全过 + OOS 无回退）。
> **go/no-go 结论（2026-08-20）**：**GO**，带两个条件：① 实时端信号与验证配置对齐 ② ETF 验证 + 小资金试运行后再放大仓位。

## Task 8: 实时端 = 回测端逻辑对齐（已完成 ✅）

**状态**：已完成（commit 4a05109）

**改动**：
- `app.py` `render_realtime_card`：新增衰减退出（动量百分位 < 20% 强制空仓）+ 波动率仓位显示
- `app.py` `render_backtest_tab`：回测表单新增衰减退出/波动率目标开关（默认启用）
- `config.py`：target_vol 15% → 14%（DD 余量 1.39pp vs 0.28pp）

**验证**：60 tests passed，app 导入正常

---

## Task 9: ETF 可交易性验证（159915 / 510880）

**Files:**
- Create: `etf_backtest.py`（或新增模块）
- Modify: `data_loader.py`（ETF 数据加载）

- [ ] **Step 1: 获取 ETF 历史数据**

用 `ak.fund_etf_hist_sina`（新浪 ETF 历史）或备选源获取：
- 159915（创业板 ETF）
- 510880（红利 ETF）

数据范围：2015 年起（与指数回测对齐）

- [ ] **Step 2: ETF 口径回测**

用 ETF 收盘价替代指数价格跑一次完整回测（含衰减退出 + 波动率目标 14%/60d），对比指数口径结果：
- 跟踪误差（年化收益差、DD 差）
- 溢价折价影响

**额外价值**：510880 的市场价+分红 ≈ 真实全收益。用它回测可自然检验 4.5% 常数股息率近似的误差——如果 ETF 口径与当前近似口径接近，常数假设就坐实了。

- [ ] **Step 3: 实际交易成本验证**

159915/510880 均免印花税、佣金可低至万 1-3。记录实际成本假设，与回测的 0.1% 对比。

- [ ] **Step 4: 更新 spec 记录结论**

- [ ] **Step 5: Commit**

```bash
git add etf_backtest.py data_loader.py docs/
git commit -m "feat: ETF 可交易性验证（159915/510880）"
```

---

## Task 10: 小资金/纸面试运行（2-3 个月）

> **前置条件**：Task 9 完成（ETF 数据验证通过）

**目标**：验证实时数据链路、信号推送稳定性、执行可行性。不追求收益，追求流程可靠。

- [ ] **Step 1: 定义试运行协议**

记录以下流程：
- 每日何时查看信号（收盘前 vs 收盘后）
- 信号触发时的执行步骤（ETF 代码、限价单 vs 市价单）
- 仓位记录方式（ spreadsheet / 简单数据库）
- 异常处理（数据缺失、信号异常时的默认行为）

- [ ] **Step 2: 用小资金或纸面记录执行 2-3 个月**

- [ ] **Step 3: 评估试运行结果**

- 信号频率是否与回测一致（~17 次/年）
- 数据链路是否稳定（sina 实时行情可用性）
- 执行可行性（ETF 流动性、滑点）
- 任何预期外的问题

- [ ] **Step 4: 记录结论，更新 spec**

---

## Task 11: 信号推送 + 执行清单

> 可与 Task 10 并行

- [ ] **Step 1: Webhook 推送**

信号变化时推送通知到微信/钉钉。包含：
- 信号类型（买入创业板/买入红利/空仓）
- 动量数据（创业板/红利各自动量、百分位）
- 建议仓位（波动率缩放比例）
- 衰减退出状态

- [ ] **Step 2: 执行清单模板**

低频系统（~17 次/年）配人工执行清单：
- 操作方向（买/卖）
- ETF 代码（159915 或 510880）
- 目标仓位（百分比 × 波动率缩放）
- 执行时间建议（收盘前后）
- 限价单参考价位

---

## Task 12: 仓位落地

> **前置条件**：Task 10 试运行完成，Task 11 信号推送就绪

- [ ] **Step 1: 确定仓位比例**

feedback 建议 20-40%，按 30% 配置算：
- 策略自身 23.61% 回撤对组合的贡献 ≈ 7.1%
- 组合层面完全可控

- [ ] **Step 2: 实盘执行**

按试运行验证过的流程执行，定期检查信号与执行的一致性。

- [ ] **Step 3: 季度回顾**

每季度对比实盘与回测的差异，分析原因（滑点、执行延迟、数据问题）。

---

## Phase B 完成标准

- [ ] ETF 口径回测完成，与指数口径对比记录在 spec
- [ ] 试运行 2-3 个月，信号频率/数据链路/执行可行性评估完成
- [ ] 信号推送可用（Webhook → 微信/钉钉）
- [ ] 实盘仓位落地，季度回顾机制建立
- [ ] 每 Task 独立 commit（Conventional Commits）
