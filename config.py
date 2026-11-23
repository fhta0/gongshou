"""
全局配置：指数代码、动量参数、无风险利率等
修改此文件即可适配其他指数对（如沪深300/中证500）
"""

STRATEGY_CONFIG = {
    "symbol_a": {
        "code": "399006",
        "name": "创业板指",
        "spot_code": "sz399006"
    },
    "symbol_b": {
        "code": "000922",
        "name": "中证红利",
        "spot_code": "sh000922"
    },
    "momentum_window": 20,           # 主窗口（用于无风险门槛计算）
    "momentum_windows": [10, 20, 40],  # 多窗口平滑（取均值，减少基准跳变）
    "trend_filter_windows": [60, 120, 200],  # 长周期趋势过滤窗口（多窗口平滑）
    "risk_free_rate": 0.015,         # 年化无风险利率 1.5%
    "dividend_yield": 0.035,         # 中证红利历史股息率（ETF 510880 实测分红 2016-2026 均值 ~3.5%，原 4.5% 偏高）
    "cooldown_days": 12,             # 信号冷却期（防频繁切换；敏感性测试：5→12 天 sharpe 0.41→0.71，DD 23.71%→17.48%）

    # 动量百分位参数（用于信号强度展示和动量衰竭退出）
    "percentile_window": 750,            # 比值百分位滚动窗口（3年交易日）
    "momentum_percentile_window": 250,   # 动量百分位滚动窗口（1年）
    "low_percentile": 0.20,              # 低位阈值（比值≤20%分位，用于信号强度标签）
    "high_percentile": 0.80,             # 高位阈值（比值≥80%分位，用于信号强度标签）
    "decay_exit_threshold": 0.20,        # 动量衰竭退出阈值（动量百分位低于此值退出）

    # 波动率目标仓位
    "target_vol": 0.14,                  # 目标年化波动率 14%（DD=23.71%，留 1.29pp 余量）
    "vol_lookback": 60,                  # 实现波动率回看窗口（交易日，60d 比 20d 更平滑）
}
