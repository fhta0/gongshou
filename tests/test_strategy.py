"""tests/test_strategy.py"""
import pandas as pd
import pytest
from strategy import calculate_rolling_percentile


def test_rolling_percentile_basic():
    """滚动百分位：已知序列的百分位计算"""
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = calculate_rolling_percentile(series, window=5)
    assert result.iloc[-1] == pytest.approx(1.0, abs=0.01)
    assert result.iloc[4] == pytest.approx(1.0, abs=0.01)


def test_rolling_percentile_with_window():
    """滚动百分位：窗口外的值不影响"""
    series = pd.Series([10.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
    result = calculate_rolling_percentile(series, window=5)
    assert result.iloc[-1] == pytest.approx(1.0, abs=0.01)


def test_rolling_percentile_nan_for_insufficient_data():
    """数据不足窗口时返回 NaN"""
    series = pd.Series([1.0, 2.0, 3.0])
    result = calculate_rolling_percentile(series, window=5)
    assert result.iloc[:4].isna().all()
