"""tests/test_strategy.py — 双动量策略测试"""
import pandas as pd
import numpy as np
import pytest
from strategy import calculate_momentum, calculate_smoothed_momentum, generate_signals, calculate_signal


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


# ===== calculate_smoothed_momentum 测试 =====

def test_smoothed_momentum_basic():
    """多窗口平滑 = 各窗口动量的均值"""
    series = pd.Series([100.0, 105, 110, 108, 115, 120, 118, 125, 130, 128])
    result = calculate_smoothed_momentum(series, windows=[2, 3])
    mom_2 = calculate_momentum(series, 2)
    mom_3 = calculate_momentum(series, 3)
    # 从第3个值开始两个窗口都有值
    expected = (mom_2 + mom_3) / 2
    assert result.iloc[3] == pytest.approx(expected.iloc[3], abs=0.001)
    assert result.iloc[-1] == pytest.approx(expected.iloc[-1], abs=0.001)


def test_smoothed_momentum_single_window():
    """单窗口时等同于普通动量"""
    series = pd.Series([100.0, 105, 110, 108, 115])
    result = calculate_smoothed_momentum(series, windows=[2])
    expected = calculate_momentum(series, 2)
    assert result.iloc[2] == pytest.approx(expected.iloc[2], abs=0.001)
    assert result.iloc[-1] == pytest.approx(expected.iloc[-1], abs=0.001)


def test_smoothed_momentum_reduces_volatility():
    """平滑后动量的日间跳变更小"""
    np.random.seed(42)
    # 构造有大幅波动的价格序列
    series = pd.Series(100 * np.cumprod(1 + np.random.normal(0, 0.05, 100)))
    smooth = calculate_smoothed_momentum(series, windows=[5, 10, 20])
    raw_5 = calculate_momentum(series, 5)
    # 比较日间跳变（一阶差分）的波动
    smooth_diff = smooth.dropna().diff().dropna().std()
    raw_diff = raw_5.dropna().diff().dropna().std()
    assert smooth_diff < raw_diff


def test_smoothed_momentum_default_windows():
    """默认使用 config 中的 momentum_windows"""
    series = pd.Series(100 * np.cumprod(1 + np.random.normal(0, 0.02, 50)))
    result = calculate_smoothed_momentum(series)
    # 数据长度50，最大窗口40，应该有有效值
    assert result.iloc[-1] > 0 or result.iloc[-1] < 0  # 不是 NaN
    assert not pd.isna(result.iloc[-1])


# ===== generate_signals 测试 =====

def test_generate_signals_cy_stronger():
    """创业板动量更强且为正 → 信号=1"""
    df = pd.DataFrame({
        'close_cy': [100] * 20 + [120],
        'close_hl': [100] * 20 + [105],
    })
    signals = generate_signals(df, window=20, apply_cooldown=False)
    assert signals.iloc[-1] == 1.0


def test_generate_signals_hl_stronger():
    """红利动量更强且为正 → 信号=-1"""
    df = pd.DataFrame({
        'close_cy': [100] * 20 + [105],
        'close_hl': [100] * 20 + [120],
    })
    signals = generate_signals(df, window=20, apply_cooldown=False)
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


def test_realtime_cooldown_blocks_switch():
    """实时端冷却期：冷却期内不切换"""
    from strategy import calculate_signal
    # 第一次切换：cy 领先
    _, state1, _ = calculate_signal(0.05, 0.02, 'cash', days_since_last_switch=999)
    assert state1 == 'cy'

    # 冷却期内：hl 领先但不允许切换
    _, state2, _ = calculate_signal(0.02, 0.05, 'cy', days_since_last_switch=2)
    assert state2 == 'cy'  # 保持 cy，不切换

    # 冷却期外：允许切换
    _, state3, _ = calculate_signal(0.02, 0.05, 'cy', days_since_last_switch=15)
    assert state3 == 'hl'  # 切换为 hl


def test_cooldown_first_load_not_blocked():
    """首次加载（days_since_last_switch=999）不受冷却期限制

    回归测试：页面刷新后 prev_state 默认 'cash'，如果 last_switch_date 是当天，
    days_since_switch=0 会错误地阻止切换到真实信号。
    修复：首次加载时传入 days_since_last_switch=999。
    """
    from strategy import calculate_signal
    # 红利明显领先（hl=+3.7%, cy=-4.1%），首次加载应直接给出 hl 信号
    _, state, _ = calculate_signal(-0.041, 0.037, 'cash', days_since_last_switch=999)
    assert state == 'hl'


def test_cooldown_same_day_blocks_when_state_was_set():
    """非首次加载：当天内切换过就应阻止再次切换"""
    from strategy import calculate_signal
    # prev_state='cash' 是本次 session 设置的（非首次加载），当天内不允许切换
    _, state, _ = calculate_signal(-0.041, 0.037, 'cash', days_since_last_switch=0)
    assert state == 'cash'  # 冷却中，保持 cash


# ===== 空仓描述动态化测试 =====

def test_cash_description_both_negative():
    """两者动量均为负时，描述应包含'均为负'"""
    from strategy import calculate_signal
    display, state, _ = calculate_signal(-0.02, -0.01, 'cy', days_since_last_switch=999)
    assert state == 'cash'
    assert '均为负' in display['description']


def test_cash_description_below_threshold():
    """动量为正但未达门槛时，描述应包含'未达门槛'"""
    from strategy import calculate_signal
    # hl=+0.05% > 0 但 < rf_period=0.12%
    display, state, _ = calculate_signal(-0.02, 0.0005, 'hl', days_since_last_switch=999)
    assert state == 'cash'
    assert '未达门槛' in display['description']
    assert '+0.05%' in display['description']


def test_cash_description_includes_actual_values():
    """空仓描述应包含实际动量数值"""
    from strategy import calculate_signal
    display, state, _ = calculate_signal(-0.03, -0.01, 'cy', days_since_last_switch=999)
    assert state == 'cash'
    assert '-3.00%' in display['description']
    assert '-1.00%' in display['description']


# ===== 趋势过滤测试 =====

def test_trend_filter_blocks_when_long_momentum_negative():
    """长周期平滑动量为负时，信号强制为 0"""
    from strategy import generate_signals
    # 构造"熊市反弹"：长期下行 200 天，然后 50 天强反弹
    # 短周期动量 [10,20,40] 在反弹段为正 → 原信号=1
    # 长周期趋势 [60,120,200] 仍为负（跨越反弹→下跌段）→ 趋势过滤应阻止
    np.random.seed(99)
    n = 250
    # CY：200 天从 3000 跌到 1800，然后 50 天强反弹到 2200
    cy_decline = list(np.linspace(3000, 1800, 200))
    cy_rebound = list(np.linspace(1820, 2200, 50))
    cy = cy_decline + cy_rebound
    # HL：更弱下跌，小幅反弹 → CY 短期动量更强
    hl_decline = list(np.linspace(2500, 1600, 200))
    hl_rebound = list(np.linspace(1610, 1700, 50))
    hl = hl_decline + hl_rebound
    df = pd.DataFrame({'close_cy': cy, 'close_hl': hl})
    # 不启用趋势过滤：CY 短期动量更强且为正 → 信号=1
    signals_no_tf = generate_signals(df, window=3, apply_cooldown=False, apply_trend_filter=False)
    # 启用趋势过滤（默认 [60,120,200]）：长周期趋势为负 → 信号应为 0
    signals_tf = generate_signals(df, window=3, apply_cooldown=False, apply_trend_filter=True)
    assert signals_no_tf.iloc[-1] == 1.0, f"Expected 1.0 without TF, got {signals_no_tf.iloc[-1]}"
    assert signals_tf.iloc[-1] == 0.0, f"Expected 0.0 with TF, got {signals_tf.iloc[-1]}"


def test_trend_filter_preserves_signal_when_positive():
    """长周期平滑动量为正时，不改变原信号"""
    from strategy import generate_signals
    # 构造：长期上行，短期也上行
    n = 250
    cy = list(np.linspace(1000, 2500, 200)) + list(np.linspace(2520, 2900, 50))
    hl = list(np.linspace(900, 2000, 200)) + list(np.linspace(2010, 2100, 50))
    df = pd.DataFrame({'close_cy': cy, 'close_hl': hl})
    signals_no_tf = generate_signals(df, window=3, apply_cooldown=False, apply_trend_filter=False)
    signals_tf = generate_signals(df, window=3, apply_cooldown=False, apply_trend_filter=True)
    # 两者都应该是 1（CY 更强且长期趋势向上）
    assert signals_no_tf.iloc[-1] == 1.0
    assert signals_tf.iloc[-1] == 1.0


def test_trend_filter_nan_during_warmup():
    """趋势窗口数据不足时，信号保持 NaN（不把无数据当看空）"""
    from strategy import generate_signals
    # 只有 10 天数据，趋势窗口 20 天不足
    df = pd.DataFrame({
        'close_cy': [100.0] * 10,
        'close_hl': [100.0] * 10,
    })
    signals = generate_signals(df, window=3, apply_cooldown=False, apply_trend_filter=True, trend_filter_windows=[20])
    # 所有信号都应该是 NaN（趋势数据不足）
    assert signals.isna().all()


def test_trend_filter_blocks_hl_when_hl_trend_negative():
    """红利持仓：红利长周期趋势为负时，强制空仓"""
    from strategy import generate_signals
    # HL 长期下跌 200 天，CY 更惨 → HL 相对更强
    # 但 HL 长周期趋势仍为负 → 趋势过滤应阻止 HL 持仓
    n = 250
    cy_decline = list(np.linspace(3000, 1500, 200))
    cy_rebound = list(np.linspace(1510, 1580, 50))
    cy = cy_decline + cy_rebound
    hl_decline = list(np.linspace(2500, 1700, 200))
    hl_rebound = list(np.linspace(1720, 1900, 50))
    hl = hl_decline + hl_rebound
    df = pd.DataFrame({'close_cy': cy, 'close_hl': hl})
    # 不启用趋势过滤：HL 更强 → 信号 -1
    signals_no_tf = generate_signals(df, window=3, apply_cooldown=False, apply_trend_filter=False)
    assert signals_no_tf.iloc[-1] == -1.0
    # 启用趋势过滤：HL 长周期趋势为负 → 信号应为 0
    signals_tf = generate_signals(df, window=3, apply_cooldown=False, apply_trend_filter=True)
    assert signals_tf.iloc[-1] == 0.0


def test_trend_filter_default_off():
    """默认不启用趋势过滤（保持向后兼容，A/B 验证前不影响现有行为）"""
    from strategy import generate_signals
    n = 250
    cy = list(np.linspace(3000, 1800, 200)) + list(np.linspace(1820, 2200, 50))
    hl = list(np.linspace(2500, 1600, 200)) + list(np.linspace(1610, 1700, 50))
    df = pd.DataFrame({'close_cy': cy, 'close_hl': hl})
    # 不传 apply_trend_filter 时，应与 apply_trend_filter=False 一致
    signals_default = generate_signals(df, window=3, apply_cooldown=False)
    signals_off = generate_signals(df, window=3, apply_cooldown=False, apply_trend_filter=False)
    pd.testing.assert_series_equal(signals_default, signals_off)


# ===== 动量衰竭退出测试 =====

def test_decay_exit_blocks_when_momentum_percentile_low():
    """动量百分位低于阈值时，信号强制为 0"""
    from strategy import generate_signals
    # 构造：CY 突然反弹使短期动量为正且领先，但长期百分位仍很低
    # 300 天平稳数据建立高百分位基线，最后突然 CY 下跌后微反弹
    np.random.seed(42)
    n = 300
    # 前 295 天：两者平稳上涨
    cy_base = list(np.linspace(1000, 1500, 295))
    hl_base = list(np.linspace(900, 1400, 295))
    # 最后 5 天：CY 急跌后微反弹（短期动量可能仍为正但百分位下降）
    cy_tail = [1480, 1460, 1450, 1455, 1460]
    hl_tail = [1390, 1395, 1398, 1400, 1402]
    cy = cy_base + cy_tail
    hl = hl_base + hl_tail
    df = pd.DataFrame({'close_cy': cy, 'close_hl': hl})
    # 启用衰竭退出（高阈值 0.80 以确保触发）
    signals = generate_signals(df, window=3, apply_cooldown=False, apply_decay_exit=True, decay_exit_threshold=0.80)
    # CY 刚急跌，百分位应很低；如果信号是 1（买 CY），应被衰竭退出阻止
    if not pd.isna(signals.iloc[-1]):
        # 要么信号已经是 0（原本就没有入场条件），要么被衰竭退出阻止为 0
        assert signals.iloc[-1] == 0.0


def test_decay_exit_preserves_strong_momentum():
    """动量百分位高时，信号不变"""
    from strategy import generate_signals
    # 300 天加速上涨（动量递增 → 百分位接近 1.0），CY 一直比 HL 强
    n = 300
    cy = 1000 * np.cumprod(1 + np.linspace(0.001, 0.005, n))
    hl = 900 * np.cumprod(1 + np.linspace(0.0005, 0.003, n))
    df = pd.DataFrame({'close_cy': cy, 'close_hl': hl})
    signals_no_exit = generate_signals(df, window=3, apply_cooldown=False, apply_decay_exit=False)
    signals_exit = generate_signals(df, window=3, apply_cooldown=False, apply_decay_exit=True, decay_exit_threshold=0.20)
    # 动量百分位高（加速上涨），衰竭退出不应该阻止
    assert signals_no_exit.iloc[-1] == 1.0
    assert signals_exit.iloc[-1] == 1.0


def test_decay_exit_default_off():
    """默认不启用衰竭退出"""
    from strategy import generate_signals
    np.random.seed(42)
    n = 300
    cy = list(np.linspace(1000, 1500, n))
    hl = list(np.linspace(900, 1400, n))
    df = pd.DataFrame({'close_cy': cy, 'close_hl': hl})
    signals_default = generate_signals(df, window=3, apply_cooldown=False)
    signals_off = generate_signals(df, window=3, apply_cooldown=False, apply_decay_exit=False)
    pd.testing.assert_series_equal(signals_default, signals_off)


# ===== calculate_ratio_percentile 测试 =====

def test_ratio_percentile_basic():
    """百分位计算正确性"""
    from strategy import calculate_ratio_percentile
    # 递增序列：最后一个值应在最高位
    ratio = pd.Series([0.3, 0.4, 0.5, 0.6, 0.7])
    result = calculate_ratio_percentile(ratio, window=5)
    assert result.iloc[-1] > 0.8

def test_ratio_percentile_low_at_bottom():
    """序列底部值百分位低"""
    from strategy import calculate_ratio_percentile
    # 突然跌到最低
    ratio = pd.Series([0.5, 0.5, 0.5, 0.5, 0.2])
    result = calculate_ratio_percentile(ratio, window=5)
    assert result.iloc[-1] < 0.3

def test_ratio_percentile_nan_for_insufficient():
    """数据不足窗口时返回 NaN"""
    from strategy import calculate_ratio_percentile
    ratio = pd.Series([0.5, 0.6, 0.7])
    result = calculate_ratio_percentile(ratio, window=5)
    assert result.isna().all()


# ===== calculate_momentum_percentile 测试 =====

def test_momentum_percentile_basic():
    """动量百分位计算正确性"""
    from strategy import calculate_momentum_percentile
    # 递增序列：最后一个值应在最高位
    momentum = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05])
    result = calculate_momentum_percentile(momentum, window=5)
    assert result.iloc[-1] > 0.8

def test_momentum_percentile_low_at_bottom():
    """动量处于低位时百分位低"""
    from strategy import calculate_momentum_percentile
    momentum = pd.Series([0.05, 0.04, 0.03, 0.02, 0.01])
    result = calculate_momentum_percentile(momentum, window=5)
    assert result.iloc[-1] < 0.3


