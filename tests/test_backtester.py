"""tests/test_backtester.py"""
import pandas as pd
import pytest
from backtester import run_backtest
from config import STRATEGY_CONFIG


@pytest.fixture
def sample_data():
    """构造测试数据：100天，前50天比值低（抄底区），后50天比值高（逃顶区）"""
    dates = pd.date_range('2020-01-01', periods=100, freq='B')
    ratio_low = [0.3] * 50
    ratio_high = [0.8] * 50

    df = pd.DataFrame({
        'date': dates,
        'close_cy': [100 + i * 0.5 for i in range(100)],
        'close_hl': [200 - i * 0.2 for i in range(100)],
        'ratio': ratio_low + ratio_high
    })
    return df


def test_backtest_returns_dataframe_with_nav(sample_data):
    """回测应返回包含净值列的 DataFrame"""
    result = run_backtest(sample_data, window=20)
    assert 'strategy_nav' in result.columns
    assert 'cy_nav' in result.columns
    assert 'hl_nav' in result.columns
    assert 'position' in result.columns
    assert len(result) == len(sample_data)


def test_backtest_t1_execution(sample_data):
    """T+1 执行：信号日不交易，次日才建仓"""
    result = run_backtest(sample_data, window=20)
    assert pd.isna(result['position'].iloc[0])


def test_backtest_position_values(sample_data):
    """仓位值应为 1（抄底）、-1（逃顶）或 0（中性）"""
    result = run_backtest(sample_data, window=20)
    actual_positions = set(result['position'].dropna().unique())
    assert actual_positions.issubset({1.0, -1.0, 0.0})


def test_backtest_nav_starts_at_1(sample_data):
    """净值曲线应从 1 开始"""
    result = run_backtest(sample_data, window=20)
    first_valid = result['strategy_nav'].dropna().iloc[0]
    assert first_valid == pytest.approx(1.0, abs=0.01)
