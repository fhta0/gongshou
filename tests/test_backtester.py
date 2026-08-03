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


from backtester import calculate_statistics


def test_statistics_structure():
    """统计结果应包含关键指标"""
    df = pd.DataFrame({
        'strategy_nav': [1.0, 1.05, 1.10, 1.08, 1.15],
        'cy_nav': [1.0, 1.02, 1.04, 1.03, 1.06],
        'hl_nav': [1.0, 1.01, 1.015, 1.02, 1.025],
        'position': [0, 1, 1, 0, -1],
        'strategy_return': [0.0, 0.05, 0.0476, -0.0182, 0.0648]
    })
    stats = calculate_statistics(df)
    assert 'total_return' in stats
    assert 'annualized_return' in stats
    assert 'max_drawdown' in stats
    assert 'sharpe_ratio' in stats
    assert 'win_rate' in stats


def test_max_drawdown_calculation():
    """最大回撤计算正确"""
    df = pd.DataFrame({
        'strategy_nav': [1.0, 1.2, 1.1, 1.0, 1.3],
        'strategy_return': [0.0, 0.2, -0.0833, -0.0909, 0.3]
    })
    stats = calculate_statistics(df)
    # 从 1.2 跌到 1.0，回撤 = (1.2 - 1.0) / 1.2 = 16.67%
    assert stats['max_drawdown'] == pytest.approx(0.1667, abs=0.01)
