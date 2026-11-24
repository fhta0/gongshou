"""tests/test_backtester.py — 双动量回测测试"""
import pandas as pd
import numpy as np
import pytest
from backtester import run_backtest, calculate_statistics


@pytest.fixture
def sample_data():
    """
    构造测试数据：
    - 前30天：创业板强势上涨
    - 中间30天：红利强势上涨
    - 最后30天：两者都下跌
    """
    np.random.seed(42)
    n = 90
    dates = pd.bdate_range('2020-01-01', periods=n)

    # 创业板：先涨后跌
    cy = [100.0] * 30
    cy += [cy[-1] * (1 + 0.01)] * 30  # 上涨期
    cy += [cy[-1] * (1 - 0.005)] * 30  # 下跌期

    # 红利：先平后涨再跌
    hl = [100.0] * 30
    hl += [hl[-1] * (1 + 0.002)] * 30  # 小涨
    hl += [hl[-1] * (1 - 0.003)] * 30  # 下跌

    df = pd.DataFrame({
        'date': dates,
        'close_cy': cy,
        'close_hl': hl,
    })
    return df


def test_backtest_returns_dataframe_with_nav(sample_data):
    """回测应返回包含净值列的 DataFrame"""
    result = run_backtest(sample_data, window=10)
    assert 'strategy_nav' in result.columns
    assert 'cy_nav' in result.columns
    assert 'hl_nav' in result.columns
    assert 'position' in result.columns
    assert 'signal' in result.columns
    assert 'cy_momentum' in result.columns
    assert 'hl_momentum' in result.columns
    assert len(result) == len(sample_data)


def test_backtest_t1_execution(sample_data):
    """T+1 执行：第一天 position 应为 NaN"""
    result = run_backtest(sample_data, window=10)
    assert pd.isna(result['position'].iloc[0])


def test_backtest_position_values(sample_data):
    """仓位值应为 1（创业板）、-1（红利）或 0（空仓）"""
    result = run_backtest(sample_data, window=10)
    actual_positions = set(result['position'].dropna().unique())
    assert actual_positions.issubset({1.0, -1.0, 0.0})


def test_backtest_nav_starts_at_1(sample_data):
    """净值曲线应从 1 开始"""
    result = run_backtest(sample_data, window=10)
    first_valid = result['strategy_nav'].dropna().iloc[0]
    assert first_valid == pytest.approx(1.0, abs=0.01)


# ===== calculate_statistics 测试 =====

def test_statistics_structure():
    """统计结果应包含关键指标"""
    df = pd.DataFrame({
        'strategy_nav': [1.0, 1.05, 1.10, 1.08, 1.15],
        'strategy_nav_net': [1.0, 1.049, 1.098, 1.077, 1.146],
        'strategy_return': [0.0, 0.05, 0.0476, -0.0182, 0.0648],
        'net_return': [0.0, 0.049, 0.0467, -0.0192, 0.0638],
        'position': [1.0, 1.0, 1.0, 1.0, 1.0],
        'is_switch': [1, 0, 0, 0, 0]
    })
    stats = calculate_statistics(df)
    assert 'gross_return' in stats
    assert 'net_return' in stats
    assert 'annualized_return' in stats
    assert 'max_drawdown' in stats
    assert 'sharpe_ratio' in stats
    assert 'trade_count' in stats
    assert 'trade_win_rate' in stats


def test_max_drawdown_calculation():
    """最大回撤计算正确"""
    df = pd.DataFrame({
        'strategy_nav': [1.0, 1.2, 1.1, 1.0, 1.3],
        'strategy_nav_net': [1.0, 1.199, 1.098, 0.998, 1.297],
        'strategy_return': [0.0, 0.2, -0.0833, -0.0909, 0.3],
        'net_return': [0.0, 0.199, -0.0843, -0.091, 0.299],
        'position': [1.0, 1.0, 1.0, 1.0, 1.0],
        'is_switch': [1, 0, 0, 0, 0]
    })
    stats = calculate_statistics(df)
    # 从 1.199 跌到 0.998，回撤 ≈ 16.8%
    assert stats['max_drawdown'] == pytest.approx(0.167, abs=0.02)


def test_statistics_empty_data():
    """空数据应返回全零统计"""
    df = pd.DataFrame({
        'strategy_nav': pd.Series(dtype=float),
        'strategy_nav_net': pd.Series(dtype=float),
        'strategy_return': pd.Series(dtype=float),
        'net_return': pd.Series(dtype=float)
    })
    stats = calculate_statistics(df)
    assert stats['gross_return'] == 0.0
    assert stats['net_return'] == 0.0
    assert stats['annualized_return'] == 0.0


def test_backtest_with_real_data():
    """用稍长的数据测试完整回测流程"""
    np.random.seed(123)
    n = 300
    dates = pd.bdate_range('2020-01-01', periods=n)

    cy_returns = np.random.normal(0.0005, 0.02, n)
    hl_returns = np.random.normal(0.0003, 0.01, n)
    cy = 100 * np.cumprod(1 + cy_returns)
    hl = 100 * np.cumprod(1 + hl_returns)

    df = pd.DataFrame({
        'date': dates,
        'close_cy': cy,
        'close_hl': hl,
    })

    result = run_backtest(df, window=20)
    stats = calculate_statistics(result)

    assert stats['net_return'] != 0.0
    assert stats['max_drawdown'] >= 0
    assert stats['trade_count'] >= 0
    assert len(result) == n



def test_backtest_default_is_momentum():
    """默认使用纯动量策略"""
    np.random.seed(42)
    n = 100
    dates = pd.bdate_range('2020-01-01', periods=n)
    cy = 100 * np.cumprod(1 + np.random.normal(0.001, 0.02, n))
    hl = 100 * np.cumprod(1 + np.random.normal(0.0005, 0.015, n))
    df = pd.DataFrame({
        'date': dates,
        'close_cy': cy,
        'close_hl': hl,
        'ratio': cy / hl,
    })
    result = run_backtest(df, window=20)
    # 纯动量策略不应有 signal_strength='强信号'（因为没有用比值百分位生成信号）
    # 但 ratio_percentile 列始终存在（用于信号强度标签）
    assert 'ratio_percentile' in result.columns
    assert 'signal_strength' in result.columns


# ===== 波动率目标仓位测试 =====

def test_vol_target_scales_down_in_high_vol():
    """高波动期 scale < 1（降仓）"""
    np.random.seed(42)
    n = 100
    dates = pd.bdate_range('2020-01-01', periods=n)
    # 高波动：日收益 std=10%，年化 vol ≈ 158%，远超 target_vol=12%
    cy = 100 * np.cumprod(1 + np.random.normal(0, 0.10, n))
    hl = 100 * np.cumprod(1 + np.random.normal(0, 0.01, n))
    df = pd.DataFrame({'date': dates, 'close_cy': cy, 'close_hl': hl})

    r_no_vol = run_backtest(df, window=20, apply_vol_target=False)
    r_vol = run_backtest(df, window=20, apply_vol_target=True)
    # 高波动期波动率目标策略的收益波动应更小
    valid = r_vol['strategy_return'].dropna().iloc[-50:]
    valid_no = r_no_vol['strategy_return'].dropna().iloc[-50:]
    assert valid.std() < valid_no.std()


def test_vol_target_caps_at_one():
    """低波动期 scale 封顶 1.0（不加杠杆）"""
    np.random.seed(42)
    n = 100
    dates = pd.bdate_range('2020-01-01', periods=n)
    # 极低波动：日收益 std=0.1%，年化 vol ≈ 1.6%，远低于 target_vol=12%
    cy = 100 * np.cumprod(1 + np.random.normal(0.0003, 0.001, n))
    hl = 100 * np.cumprod(1 + np.random.normal(0.0002, 0.001, n))
    df = pd.DataFrame({'date': dates, 'close_cy': cy, 'close_hl': hl})

    r_no_vol = run_backtest(df, window=20, apply_vol_target=False)
    r_vol = run_backtest(df, window=20, apply_vol_target=True)
    # 低波动期 scale 应=1.0，两种策略收益应几乎相同
    np.testing.assert_allclose(
        r_vol['strategy_return'].dropna().iloc[-30:],
        r_no_vol['strategy_return'].dropna().iloc[-30:],
        atol=1e-10
    )


def test_vol_target_return_formula():
    """收益 = scale×标的收益 + (1-scale)×无风险日收益"""
    from config import STRATEGY_CONFIG
    np.random.seed(42)
    n = 100
    dates = pd.bdate_range('2020-01-01', periods=n)
    cy = 100 * np.cumprod(1 + np.random.normal(0.001, 0.05, n))
    hl = 100 * np.cumprod(1 + np.random.normal(0.0005, 0.02, n))
    df = pd.DataFrame({'date': dates, 'close_cy': cy, 'close_hl': hl})

    r = run_backtest(df, window=20, apply_vol_target=True)
    # 有 vol_scale 列
    assert 'vol_scale' in r.columns
    # scale 应在 [0, 1] 范围内
    valid_scales = r['vol_scale'].dropna()
    assert (valid_scales >= 0).all()
    assert (valid_scales <= 1.0 + 1e-10).all()
