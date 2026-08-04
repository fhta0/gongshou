"""
strategy.py — 双动量策略（Dual Momentum）
核心逻辑：比较两指数的 N 天动量，选择更强的一方；
若胜者动量 < 无风险利率，则空仓。
"""
import pandas as pd
import numpy as np
from typing import Tuple, Optional
from config import STRATEGY_CONFIG


def calculate_momentum(close_series: pd.Series, window: int = 20) -> pd.Series:
    """
    计算 N 天收益率（动量）
    Args:
        close_series: 收盘价序列
        window: 回看窗口（交易日）
    Returns:
        动量序列（N 天涨跌幅）
    """
    return close_series.pct_change(window)


def compare_momentum(cy_mom: float, hl_mom: float) -> str:
    """
    比较两指数动量，返回领先方
    平局归红利（因为红利波动小，更稳定）

    Args:
        cy_mom: 创业板动量
        hl_mom: 红利动量

    Returns:
        'cy' 创业板领先, 'hl' 红利领先（含平局）
    """
    if pd.isna(cy_mom) or pd.isna(hl_mom):
        return 'unknown'
    if cy_mom > hl_mom:
        return 'cy'
    else:
        return 'hl'  # 平局归红利


def _apply_cooldown(signals: pd.Series) -> pd.Series:
    """
    应用冷却期：信号切换后 N 天内不再切换
    冷却期只在"状态改变"时重置计时器

    Args:
        signals: 原始信号序列（1, -1, 0, NaN）

    Returns:
        冷却后的信号序列
    """
    cooldown_days = STRATEGY_CONFIG['cooldown_days']
    if cooldown_days <= 0:
        return signals

    result = signals.copy()
    last_switch_idx = -cooldown_days - 1  # 初始值，允许第一次切换

    for i in range(len(signals)):
        if pd.isna(signals.iloc[i]):
            continue

        current = signals.iloc[i]

        # 检查是否有切换
        if i > 0 and not pd.isna(signals.iloc[i - 1]):
            prev = result.iloc[i - 1]  # 使用冷却后的上一个信号
            if current != prev:
                # 检查是否在冷却期内
                if i - last_switch_idx <= cooldown_days:
                    # 在冷却期内，保持上一个信号
                    result.iloc[i] = prev
                else:
                    # 不在冷却期，允许切换
                    last_switch_idx = i
            # 没切换则保持当前信号（已处理）
        else:
            # 第一个有效信号，记录切换时间
            last_switch_idx = i

    return result


def generate_signals(
    df: pd.DataFrame,
    window: int = None,
    apply_cooldown: bool = True
) -> pd.Series:
    """
    向量化生成全量信号（用于回测）
    Args:
        df: 包含 close_cy, close_hl 的 DataFrame
        window: 动量窗口
        apply_cooldown: 是否应用冷却期（默认 True）
    Returns:
        信号序列：1=创业板, -1=红利, 0=空仓
    """
    if window is None:
        window = STRATEGY_CONFIG['momentum_window']

    rf_period = STRATEGY_CONFIG['risk_free_rate'] * window / 252

    cy_mom = calculate_momentum(df['close_cy'], window)
    hl_mom = calculate_momentum(df['close_hl'], window)

    # 向量化条件（平局归红利：cy_stronger 需要严格大于）
    cy_stronger = cy_mom > hl_mom
    cy_positive = cy_mom > rf_period
    hl_positive = hl_mom > rf_period

    raw_signals = pd.Series(0, index=df.index, dtype=float)
    raw_signals[cy_stronger & cy_positive] = 1.0
    raw_signals[~cy_stronger & hl_positive] = -1.0

    # 数据不足时设为 NaN
    raw_signals[cy_mom.isna()] = np.nan

    # 应用冷却期
    if apply_cooldown:
        return _apply_cooldown(raw_signals)

    return raw_signals


def calculate_signal(
    cy_momentum: float,
    hl_momentum: float,
    prev_state: str
) -> Tuple[dict, str, Optional[dict]]:
    """
    实时信号计算（用于 UI 卡片）
    使用 compare_momentum 统一平局处理（平局归红利）

    Args:
        cy_momentum: 创业板当前动量（20天涨跌幅）
        hl_momentum: 红利当前动量（20天涨跌幅）
        prev_state: 上一次状态 ('cy' / 'hl' / 'cash')
    Returns:
        (display_info, new_state, event_or_none)
    """
    rf_period = STRATEGY_CONFIG['risk_free_rate'] * STRATEGY_CONFIG['momentum_window'] / 252

    # 使用统一的比较函数
    leader = compare_momentum(cy_momentum, hl_momentum)

    # 判断新状态
    if leader == 'cy' and cy_momentum > rf_period:
        new_state = 'cy'
    elif leader == 'hl' and hl_momentum > rf_period:
        new_state = 'hl'
    else:
        new_state = 'cash'

    # 判断是否产生事件
    event = None
    if prev_state != new_state:
        if new_state in ('cy', 'hl'):
            event = _state_to_event(new_state, action_type='entry')
        elif new_state == 'cash':
            event = _state_to_event('cash', action_type='exit')

    return _get_display_info(new_state), new_state, event


def _state_to_event(state: str, action_type: str) -> dict:
    """将状态转为事件字典"""
    events = {
        'cy': {
            'signal': '买入创业板',
            'color': 'blue',
            'emoji': '🔵',
            'description': '创业板动量领先且为正',
            'action': '买入创业板指数',
            'type': action_type
        },
        'hl': {
            'signal': '买入红利',
            'color': 'orange',
            'emoji': '🟠',
            'description': '红利动量领先且为正',
            'action': '买入中证红利指数',
            'type': action_type
        },
        'cash': {
            'signal': '空仓观望',
            'color': 'gray',
            'emoji': '⚪',
            'description': '两者动量均为负',
            'action': '持有现金/货币基金',
            'type': action_type
        }
    }
    return events[state]


def _get_display_info(state: str) -> dict:
    """返回当前状态的展示信息"""
    return _state_to_event(state, action_type='hold')
