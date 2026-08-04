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
    "momentum_window": 20,           # 动量回看窗口（交易日）
    "risk_free_rate": 0.015,         # 年化无风险利率 1.5%
    "cooldown_days": 5               # 信号冷却期（防频繁切换）
}
