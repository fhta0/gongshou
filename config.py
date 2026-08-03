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
