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
    "risk_free_rate": 0.015,         # 年化无风险利率 1.5%
    "dividend_yield": 0.045,         # 中证红利历史股息率常数近似（年化，价格指数→全收益折算）
    "cooldown_days": 5,              # 信号冷却期（防频繁切换）

    # 组合策略参数（比值位置 + 动量百分位）
    "percentile_window": 750,            # 比值百分位滚动窗口（3年交易日）
    "momentum_percentile_window": 250,   # 动量百分位滚动窗口（1年）
    "low_percentile": 0.20,              # 低位阈值（比值≤20%分位）
    "high_percentile": 0.80,             # 高位阈值（比值≥80%分位）
    # 动量百分位门槛（按比值区域）
    "low_cy_mom_pct_threshold": 0.30,    # 低位时创业板动量百分位门槛
    "mid_mom_pct_threshold": 0.50,       # 中间时动量百分位门槛
    "high_cy_mom_pct_threshold": 0.70,   # 高位时创业板动量百分位门槛
    "low_hl_mom_pct_threshold": 0.50,    # 低位时红利动量百分位门槛
    "high_hl_mom_pct_threshold": 0.30,   # 高位时红利动量百分位门槛
}
