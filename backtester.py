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

    # 3. 信号去重（兼容 Pandas 2.1+）
    result['signal'] = result['signal'].replace(0, None).ffill().fillna(0)

    # 4. T+1 执行
    result['position'] = result['signal'].shift(1)

    # 5. 计算每日收益
    result['cy_return'] = result['close_cy'].pct_change()
    result['hl_return'] = result['close_hl'].pct_change()

    # 6. 策略收益
    risk_free_daily = STRATEGY_CONFIG['risk_free_rate'] / 252
    result['strategy_return'] = risk_free_daily
    result.loc[result['position'] == 1, 'strategy_return'] = result.loc[result['position'] == 1, 'cy_return']
    result.loc[result['position'] == -1, 'strategy_return'] = result.loc[result['position'] == -1, 'hl_return']

    # 7. 累计净值
    result['strategy_nav'] = (1 + result['strategy_return'].fillna(0)).cumprod()
    result['cy_nav'] = (1 + result['cy_return'].fillna(0)).cumprod()
    result['hl_nav'] = (1 + result['hl_return'].fillna(0)).cumprod()

    return result
