# 双动量策略估值过滤设计

**日期**: 2026-11-24  
**状态**: 设计中

## 概述

在现有纯动量策略基础上，增加估值硬约束，避免在高估值区域追涨。

## 问题背景

当前策略是纯动量逻辑：
- 比较创业板和红利 20 天动量
- 选择动量更强的一方
- 胜者动量需超过无风险利率

**痛点**：即使某指数已经明显高估（如红利 PE 处于历史高位），只要动量还在上升，策略仍会推荐买入。

## 设计方案

### 核心逻辑

```
原信号生成：
1. cy_mom > hl_mom 且 cy_mom > rf_rate → 买入创业板
2. hl_mom > cy_mom 且 hl_mom > rf_rate → 买入红利
3. 否则 → 空仓

新增估值约束：
1. 计算各指数 PE 历史百分位（近 N 年）
2. 如果推荐买入的指数 PE 百分位 > 阈值 → 改为空仓
3. 否则保持原信号
```

### 数据源

**akshare 指数估值接口**：
- `index_value_hist_funddb(symbol, indicator="市盈率")` — 从韭圈儿获取历史 PE 数据
- 返回字段：`date`, `pe`, `pe_percentile`（百分位）

**备用方案**：
- 如果 funddb 接口不可用，从中证指数官网直接获取
- 或者手动维护 PE 数据文件（作为 fallback）

### 过滤规则

```python
# 伪代码
cy_pe_percentile = calculate_pe_percentile('cy', window=1000)  # 近 4 年
hl_pe_percentile = calculate_pe_percentile('hl', window=1000)

signal = generate_momentum_signal(df)

# 估值约束
if signal == 1 and cy_pe_percentile > threshold:
    signal = 0  # 创业板高估，改为空仓
elif signal == -1 and hl_pe_percentile > threshold:
    signal = 0  # 红利高估，改为空仓
```

### 阈值优化

**方法**：网格搜索 + 回测

```python
thresholds = [0.70, 0.75, 0.80, 0.85, 0.90]
pe_windows = [500, 750, 1000, 1500]

best_sharpe = 0
best_params = None

for threshold in thresholds:
    for window in pe_windows:
        result = run_backtest(df, pe_threshold=threshold, pe_window=window)
        if result.sharpe > best_sharpe:
            best_sharpe = result.sharpe
            best_params = (threshold, window)
```

**优化目标**：
- 主目标：夏普比率最大化
- 约束：最大回撤 ≤ 20%

### 参数配置

新增 `config.py` 参数：

```python
STRATEGY_CONFIG = {
    # ... 现有参数 ...
    
    # 估值过滤参数
    "apply_pe_filter": True,
    "pe_percentile_threshold": 0.80,  # 高估阈值（80% 分位）
    "pe_window": 1000,                # PE 百分位计算窗口（约 4 年）
}
```

### UI 展示

在信号卡片中增加估值信息：

```
当前信号：买入红利
信号强度：普通
估值状态：红利 PE 3200，处于近 4 年 65% 分位（适中）
         创业板 PE 45，处于近 4 年 25% 分位（低估）
```

**估值状态标签**：
- < 30% 分位：🟢 低估
- 30%-70% 分位：🟡 适中
- \> 70% 分位：🔴 高估

### 回测对比

新增对比图表：

```
策略 A：纯动量（现有）
策略 B：动量 + 估值过滤（新）

对比指标：
- 年化收益
- 最大回撤
- 夏普比率
- 估值过滤触发次数
```

## 实现步骤

### Phase 1：数据层

1. 在 `data_loader.py` 中新增函数：
   - `load_pe_history(symbol)` — 获取指数历史 PE 数据
   - `calculate_pe_percentile(pe_series, window)` — 计算 PE 百分位

2. 错误处理：
   - 如果 akshare 接口失败，返回空 DataFrame
   - 回退到 Demo 模式（模拟 PE 数据）

### Phase 2：策略层

1. 在 `strategy.py` 中新增函数：
   - `apply_pe_filter(signals, cy_pe_pct, hl_pe_pct, threshold)` — 应用估值过滤

2. 修改 `generate_signals()`：
   - 新增参数 `apply_pe_filter=False`（向后兼容）
   - 如果启用，调用估值过滤函数

3. 修改 `calculate_signal()`：
   - 新增参数 `cy_pe_pct`, `hl_pe_pct`
   - 在信号生成后应用估值约束

### Phase 3：回测层

1. 修改 `backtester.py`：
   - `run_backtest()` 新增参数 `apply_pe_filter`, `pe_threshold`, `pe_window`
   - 加载 PE 数据并计算百分位
   - 应用估值过滤

2. 新增统计指标：
   - `pe_filter_count` — 估值过滤触发次数
   - `pe_filter_impact` — 估值过滤对收益的贡献

### Phase 4：阈值优化

1. 新增 `optimize_pe_threshold.py`：
   - 网格搜索最优阈值组合
   - 输出最优参数到 `config.py`

2. 运行回测对比：
   - 纯动量 vs 动量 + 估值过滤
   - 记录在 `docs/superpowers/specs/pe-filter-backtest-result.md`

### Phase 5：UI 层

1. 修改 `app.py`：
   - 信号卡片增加估值状态展示
   - 新增"估值过滤"开关（默认开启）
   - 新增参数调节滑块（阈值、窗口）

2. 新增对比图表：
   - 纯动量 vs 估值过滤的回测净值曲线
   - 估值百分位时间序列图

## 测试计划

### 单元测试

1. `test_data_loader.py`：
   - 测试 `load_pe_history()` 数据加载
   - 测试 `calculate_pe_percentile()` 计算逻辑

2. `test_strategy.py`：
   - 测试 `apply_pe_filter()` 过滤逻辑
   - 测试边界情况（PE 数据缺失、全 NaN 等）

3. `test_backtester.py`：
   - 测试估值过滤后的回测结果
   - 验证统计指标正确性

### 集成测试

1. 启动 Streamlit 应用，检查：
   - 估值数据是否正常加载
   - 信号是否正确应用估值过滤
   - UI 展示是否完整

2. 运行完整回测：
   - 对比纯动量 vs 估值过滤
   - 检查统计指标是否合理

## 风险与缓解

### 风险 1：PE 数据不可用

**场景**：akshare 接口失效或数据缺失

**缓解**：
- 添加错误日志和 fallback 机制
- 如果 PE 数据缺失，自动关闭估值过滤，回退到纯动量
- 在 UI 上显示警告

### 风险 2：阈值过拟合

**场景**：历史回测优化的阈值在未来失效

**缓解**：
- 使用较宽松的阈值（如 80% 而非 90%）
- 定期重新优化（每半年或一年）
- 在 UI 上提示"历史表现不代表未来"

### 风险 3：估值陷阱

**场景**：低估值但基本面恶化（如红利成分股盈利大幅下滑）

**缓解**：
- 估值过滤只是辅助，不改变动量核心逻辑
- 在 UI 上说明"估值低 ≠ 一定涨"

## 成功标准

1. **功能完整**：估值过滤可开关，参数可调
2. **性能提升**：夏普比率 ≥ 纯动量策略
3. **回撤控制**：最大回撤 ≤ 18%（原 17.48%）
4. **用户体验**：UI 清晰展示估值状态和过滤逻辑

## 参考资料

- [akshare 指数估值文档](https://akshare.akfamily.xyz/data/index/index.html)
- [simonlin1212/a-stock-data](https://github.com/simonlin1212/a-stock-data) — 数据源参考
- [韭圈儿 funddb.cn](https://funddb.cn) — PE 数据来源
