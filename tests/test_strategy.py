"""tests/test_strategy.py — 双动量策略测试"""
import pandas as pd
import numpy as np
import pytest
from strategy import calculate_momentum, generate_signals, calculate_signal


# ===== calculate_momentum 测试 =====

def test_momentum_basic():
    """动量 = N天涨跌幅（pct_change(N)）"""
    series = pd.Series([100, 110, 105, 120, 130], dtype=float)
    result = calculate_momentum(series, window=2)
    # pct_change(2): 当前 vs 2期前
    assert result.iloc[2] == pytest.approx((105 - 100) / 100, abs=0.001)
    assert result.iloc[4] == pytest.approx((130 - 105) / 105, abs=0.001)


def test_momentum_nan_for_insufficient_data():
    """数据不足窗口时返回 NaN"""
    series = pd.Series([100.0, 101.0, 102.0])
    result = calculate_momentum(series, window=5)
    assert result.isna().all()


def test_momentum_window_20():
    """20天窗口"""
    np.random.seed(42)
    series = pd.Series(100 * np.cumprod(1 + np.random.normal(0, 0.02, 50)))
    result = calculate_momentum(series, window=20)
    assert result.iloc[:20].isna().all()
    assert result.iloc[20:].notna().all()


# ===== generate_signals 测试 =====

def test_generate_signals_cy_stronger():
    """创业板动量更强且为正 → 信号=1"""
    df = pd.DataFrame({
        'close_cy': [100] * 20 + [120],
        'close_hl': [100] * 20 + [105],
    })
    signals = generate_signals(df, window=20)
    assert signals.iloc[-1] == 1.0


def test_generate_signals_hl_stronger():
    """红利动量更强且为正 → 信号=-1"""
    df = pd.DataFrame({
        'close_cy': [100] * 20 + [105],
        'close_hl': [100] * 20 + [120],
    })
    signals = generate_signals(df, window=20)
    assert signals.iloc[-1] == -1.0


def test_generate_signals_both_negative():
    """两者动量均为负 → 空仓=0"""
    df = pd.DataFrame({
        'close_cy': [120] * 20 + [100],  # 下跌
        'close_hl': [120] * 20 + [110],  # 下跌
    })
    signals = generate_signals(df, window=20)
    assert signals.iloc[-1] == 0.0


def test_generate_signals_nan_for_insufficient():
    """数据不足时信号为 NaN"""
    df = pd.DataFrame({
        'close_cy': [100.0] * 5,
        'close_hl': [100.0] * 5,
    })
    signals = generate_signals(df, window=20)
    assert signals.isna().all()


# ===== calculate_signal 测试（实时用） =====

def test_signal_cy_entry():
    """创业板动量领先且为正 → 买入创业板"""
    display, new_state, event = calculate_signal(
        cy_momentum=0.05, hl_momentum=0.02, prev_state='cash'
    )
    assert new_state == 'cy'
    assert event is not None
    assert event['signal'] == '买入创业板'
    assert event['type'] == 'entry'


def test_signal_hl_entry():
    """红利动量领先且为正 → 买入红利"""
    display, new_state, event = calculate_signal(
        cy_momentum=-0.01, hl_momentum=0.03, prev_state='cash'
    )
    assert new_state == 'hl'
    assert event is not None
    assert event['signal'] == '买入红利'


def test_signal_cash():
    """两者动量为负 → 空仓"""
    display, new_state, event = calculate_signal(
        cy_momentum=-0.05, hl_momentum=-0.02, prev_state='cy'
    )
    assert new_state == 'cash'
    assert event is not None
    assert event['signal'] == '空仓观望'
    assert event['type'] == 'exit'


def test_signal_no_event_when_state_unchanged():
    """状态不变时不触发事件"""
    display, new_state, event = calculate_signal(
        cy_momentum=0.05, hl_momentum=0.02, prev_state='cy'
    )
    assert new_state == 'cy'
    assert event is None


def test_display_info_always_returned():
    """始终返回展示信息"""
    display, _, _ = calculate_signal(0.05, 0.02, 'cash')
    assert 'signal' in display
    assert 'emoji' in display
    assert 'description' in display
    assert 'action' in display


# ===== compare_momentum 测试 =====

def test_compare_momentum_cy_wins():
    """创业板动量更高时返回 cy"""
    from strategy import compare_momentum
    assert compare_momentum(0.05, 0.03) == 'cy'

def test_compare_momentum_hl_wins():
    """红利动量更高时返回 hl"""
    from strategy import compare_momentum
    assert compare_momentum(0.03, 0.05) == 'hl'

def test_compare_momentum_tie_goes_to_hl():
    """平局归红利"""
    from strategy import compare_momentum
    assert compare_momentum(0.05, 0.05) == 'hl'

def test_compare_momentum_nan():
    """NaN 输入返回 unknown"""
    from strategy import compare_momentum
    assert compare_momentum(float('nan'), 0.05) == 'unknown'
    assert compare_momentum(0.05, float('nan')) == 'unknown'


# ===== 冷却期测试 =====

def test_cooldown_prevents_rapid_switching():
    """冷却期阻止快速切换"""
    from strategy import generate_signals
    # 构造数据：动量快速交替领先
    n = 30
    df = pd.DataFrame({
        'close_cy': [100.0] * 20 + [105, 103, 106, 104, 107, 105, 108, 106, 109, 107],
        'close_hl': [100.0] * 20 + [102, 104, 103, 105, 104, 106, 105, 107, 106, 108],
    })
    signals = generate_signals(df, window=5, apply_cooldown=True)
    # 有冷却期时，信号切换次数应少于无冷却期
    signals_no_cooldown = generate_signals(df, window=5, apply_cooldown=False)
    valid = signals.dropna()
    valid_no_cooldown = signals_no_cooldown.dropna()
    switches_with = (valid.diff().fillna(0) != 0).sum()
    switches_without = (valid_no_cooldown.diff().fillna(0) != 0).sum()
    assert switches_with <= switches_without
