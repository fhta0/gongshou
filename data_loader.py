"""
数据层：多数据源接口对接（新浪 + 中证指数官网），数据清洗与缓存
"""
import akshare as ak
import pandas as pd
import numpy as np
import streamlit as st
from config import STRATEGY_CONFIG


def _generate_demo_data() -> pd.DataFrame:
    """生成模拟数据用于 Demo 模式"""
    np.random.seed(42)
    n_days = 1000
    dates = pd.bdate_range(end=pd.Timestamp.now(), periods=n_days)

    # 模拟创业板：基期 3000，带趋势和波动
    cy_base = 3000
    cy_returns = np.random.normal(0.0003, 0.02, n_days)
    cy_prices = cy_base * np.cumprod(1 + cy_returns)

    # 模拟红利：基期 4000，波动较小
    hl_base = 4000
    hl_returns = np.random.normal(0.0002, 0.01, n_days)
    hl_prices = hl_base * np.cumprod(1 + hl_returns)

    return pd.DataFrame({
        'date': dates,
        'close_cy': cy_prices,
        'close_hl': hl_prices,
        'ratio': cy_prices / hl_prices
    })


@st.cache_data(ttl=3600)
def load_historical_cy() -> pd.DataFrame:
    """
    加载创业板指历史日线（新浪数据源）
    Returns:
        DataFrame with columns: ['date', 'close']
    """
    try:
        df = ak.stock_zh_index_daily(symbol='sz399006')
        result = df[['date', 'close']].copy()
        result['date'] = pd.to_datetime(result['date'])
        return result
    except Exception:
        return pd.DataFrame(columns=['date', 'close'])


@st.cache_data(ttl=3600)
def load_historical_hl() -> pd.DataFrame:
    """
    加载中证红利指数历史日线（中证指数官网数据源）
    Returns:
        DataFrame with columns: ['date', 'close']
    """
    try:
        symbol = STRATEGY_CONFIG['symbol_b']['code']
        # CSIndex 接口需要较长的日期范围
        df = ak.stock_zh_index_hist_csindex(
            symbol=symbol,
            start_date='20150101',
            end_date=pd.Timestamp.now().strftime('%Y%m%d')
        )
        result = df[['日期', '收盘']].copy()
        result.columns = ['date', 'close']
        result['date'] = pd.to_datetime(result['date'])
        result['close'] = result['close'].astype(float)
        return result
    except Exception:
        return pd.DataFrame(columns=['date', 'close'])


def load_merged_data(demo: bool = False) -> pd.DataFrame:
    """
    加载并合并两个指数的历史数据，计算比值
    如果 API 失败且 demo=True，返回模拟数据
    """
    if demo:
        return _generate_demo_data()

    df_a = load_historical_cy()
    df_b = load_historical_hl()

    if df_a.empty or df_b.empty:
        st.warning("⚠️ 无法连接数据源，已切换到 **Demo 模式**（模拟数据）")
        return _generate_demo_data()

    # Inner join 确保日期对齐
    merged = pd.merge(df_a, df_b, on='date', suffixes=('_cy', '_hl'), how='inner')
    merged = merged.dropna()
    merged['ratio'] = merged['close_cy'] / merged['close_hl']
    return merged.reset_index(drop=True)


def get_realtime_change(spot_code: str) -> float:
    """
    获取单指数盘中实时涨跌幅（新浪数据源）
    API 失败时返回 0（Demo 模式）
    """
    try:
        df = ak.stock_zh_index_spot_sina()
        if not df.empty:
            row = df[df['代码'] == spot_code]
            if not row.empty:
                return float(row.iloc[0]['涨跌幅']) / 100.0
        return 0.0
    except Exception:
        return 0.0
