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


from strategy import calculate_signal


def test_signal_buy_when_percentile_low():
    """分位 ≤ 0.1 时触发抄底信号"""
    display, new_state, event = calculate_signal(
        current_ratio=0.25,
        rolling_percentile=0.05,
        prev_state='neutral'
    )
    assert new_state == 'buy'
    assert event is not None
    assert event['signal'] == '抄底'
    assert event['type'] == 'entry'


def test_signal_sell_when_percentile_high():
    """分位 ≥ 0.9 时触发逃顶信号"""
    display, new_state, event = calculate_signal(
        current_ratio=0.85,
        rolling_percentile=0.95,
        prev_state='neutral'
    )
    assert new_state == 'sell'
    assert event is not None
    assert event['signal'] == '逃顶'
    assert event['type'] == 'entry'


def test_signal_neutral_in_middle():
    """分位在 0.1~0.9 之间为中性"""
    display, new_state, event = calculate_signal(
        current_ratio=0.5,
        rolling_percentile=0.5,
        prev_state='neutral'
    )
    assert new_state == 'neutral'
    assert event is None  # 中性到中性，无事件


def test_signal_no_event_when_state_unchanged():
    """状态不变时不触发事件"""
    display, new_state, event = calculate_signal(
        current_ratio=0.25,
        rolling_percentile=0.05,
        prev_state='buy'  # 已经是 buy
    )
    assert new_state == 'buy'
    assert event is None  # buy → buy，无事件


def test_signal_exit_event_when_returning_to_neutral():
    """从抄底/逃顶回归中性时触发 exit 事件"""
    display, new_state, event = calculate_signal(
        current_ratio=0.5,
        rolling_percentile=0.5,
        prev_state='buy'  # 从 buy 变到 neutral
    )
    assert new_state == 'neutral'
    assert event is not None
    assert event['signal'] == '中性'
    assert event['type'] == 'exit'


def test_display_info_always_returned():
    """始终返回展示信息"""
    display, _, _ = calculate_signal(0.5, 0.5, 'neutral')
    assert 'signal' in display
    assert 'emoji' in display
    assert 'description' in display
    assert 'action' in display
