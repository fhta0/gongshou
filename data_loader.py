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


def get_realtime_change(spot_code: str) -> float:
    """
    获取单指数盘中实时涨跌幅（轻量级）
    使用新浪实时接口，盘中可获取当天最新涨跌幅
    Args:
        spot_code: 如 'sz399006'
    Returns:
        float, 如 0.015 表示涨 1.5%
    """
    try:
        # 新浪实时接口，速度快且盘中实时更新
        df = ak.stock_zh_index_spot_sina(symbol=spot_code)
        if not df.empty:
            return float(df.iloc[0]['涨跌幅']) / 100.0
        return 0.0
    except Exception as e:
        st.warning(f"获取实时行情失败 ({spot_code}): {e}")
        return 0.0
