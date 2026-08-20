"""tests/test_data_loader.py — 数据层测试（股息再投资折算）"""
import pandas as pd
import pytest
from data_loader import _apply_dividend_adjustment


def test_dividend_adjustment_first_value_unchanged():
    """首日收盘价保持不变"""
    close = pd.Series([100.0, 101.0, 102.0, 103.0])
    adjusted = _apply_dividend_adjustment(close, dividend_yield=0.045)
    assert adjusted.iloc[0] == pytest.approx(100.0)


def test_dividend_adjustment_increases_close():
    """股息再投资后序列增长快于原价格序列"""
    close = pd.Series([100.0, 101.0, 102.0, 103.0])
    adjusted = _apply_dividend_adjustment(close, dividend_yield=0.045)
    assert adjusted.iloc[-1] > close.iloc[-1]


def test_dividend_adjustment_flat_price_still_grows():
    """价格横盘时股息再投资仍带来正增长"""
    close = pd.Series([100.0, 100.0, 100.0, 100.0])
    adjusted = _apply_dividend_adjustment(close, dividend_yield=0.045)
    assert adjusted.iloc[-1] > 100.0


def test_dividend_adjustment_formula():
    """验证公式：adjusted[t] = adjusted[t-1] × (1 + 价格收益 + 股息/252)"""
    close = pd.Series([100.0, 105.0])
    adjusted = _apply_dividend_adjustment(close, dividend_yield=0.045)
    div_daily = 0.045 / 252
    expected = 100.0 * (1 + 0.05 + div_daily)
    assert adjusted.iloc[-1] == pytest.approx(expected, rel=1e-9)


def test_dividend_adjustment_zero_yield_equals_price():
    """股息率为 0 时序列与原价格一致"""
    close = pd.Series([100.0, 110.0, 105.0, 120.0])
    adjusted = _apply_dividend_adjustment(close, dividend_yield=0.0)
    assert adjusted.iloc[-1] == pytest.approx(close.iloc[-1], rel=1e-9)


def test_dividend_adjustment_empty():
    """空序列直接返回"""
    close = pd.Series(dtype=float)
    adjusted = _apply_dividend_adjustment(close)
    assert adjusted.empty
