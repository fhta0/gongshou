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


def calculate_ratio_percentile(ratio_series: pd.Series, window: int = 750) -> pd.Series:
    """
    计算比值的滚动百分位（历史位置）
    Args:
        ratio_series: 比值序列
        window: 滚动窗口（交易日）
    Returns:
        百分位序列（0~1）
    """
    rolling_rank = ratio_series.rolling(window=window).rank()
    return rolling_rank / window


def calculate_momentum_percentile(momentum_series: pd.Series, window: int = 250) -> pd.Series:
    """
    计算动量的滚动百分位（自适应门槛）
    Args:
        momentum_series: 动量序列
        window: 滚动窗口（交易日）
    Returns:
        百分位序列（0~1）
    """
    rolling_rank = momentum_series.rolling(window=window).rank()
    return rolling_rank / window


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


def generate_combined_signals(
    df: pd.DataFrame,
    window: int = None,
    apply_cooldown: bool = True
) -> pd.Series:
    """
    组合策略：比值位置 + 双动量（使用动量百分位作为自适应门槛）
    包含绝对动量下限（动量 > 0）作为安全网

    Args:
        df: 包含 close_cy, close_hl, ratio 的 DataFrame
        window: 动量窗口
        apply_cooldown: 是否应用冷却期（默认 True）
    Returns:
        信号序列：1=创业板, -1=红利, 0=空仓
    """
    if window is None:
        window = STRATEGY_CONFIG['momentum_window']

    # 计算动量
    cy_mom = calculate_momentum(df['close_cy'], window)
    hl_mom = calculate_momentum(df['close_hl'], window)

    # 计算比值百分位
    pct_window = STRATEGY_CONFIG['percentile_window']
    ratio_pct = calculate_ratio_percentile(df['ratio'], pct_window)

    # 计算动量百分位（自适应门槛）
    mom_pct_window = STRATEGY_CONFIG['momentum_percentile_window']
    cy_mom_pct = calculate_momentum_percentile(cy_mom, mom_pct_window)
    hl_mom_pct = calculate_momentum_percentile(hl_mom, mom_pct_window)

    # 阈值参数
    low_pct = STRATEGY_CONFIG['low_percentile']
    high_pct = STRATEGY_CONFIG['high_percentile']
    low_cy_threshold = STRATEGY_CONFIG['low_cy_mom_pct_threshold']
    mid_threshold = STRATEGY_CONFIG['mid_mom_pct_threshold']
    high_cy_threshold = STRATEGY_CONFIG['high_cy_mom_pct_threshold']
    low_hl_threshold = STRATEGY_CONFIG['low_hl_mom_pct_threshold']
    high_hl_threshold = STRATEGY_CONFIG['high_hl_mom_pct_threshold']

    # 向量化条件（包含绝对动量下限 > 0）
    cy_stronger = cy_mom > hl_mom  # 平局归红利
    hl_stronger = ~cy_stronger
    cy_positive = cy_mom > 0  # 绝对动量下限
    hl_positive = hl_mom > 0

    # 低位区域
    low_mask = ratio_pct <= low_pct
    low_cy_buy = low_mask & cy_stronger & cy_positive & (cy_mom_pct > low_cy_threshold)
    low_hl_buy = low_mask & hl_stronger & hl_positive & (hl_mom_pct > low_hl_threshold)

    # 中间区域
    mid_mask = (ratio_pct > low_pct) & (ratio_pct < high_pct)
    mid_cy_buy = mid_mask & cy_stronger & cy_positive & (cy_mom_pct > mid_threshold)
    mid_hl_buy = mid_mask & hl_stronger & hl_positive & (hl_mom_pct > mid_threshold)

    # 高位区域
    high_mask = ratio_pct >= high_pct
    high_cy_buy = high_mask & cy_stronger & cy_positive & (cy_mom_pct > high_cy_threshold)
    high_hl_buy = high_mask & hl_stronger & hl_positive & (hl_mom_pct > high_hl_threshold)

    # 合并信号
    raw_signals = pd.Series(0, index=df.index, dtype=float)
    raw_signals[low_cy_buy | mid_cy_buy | high_cy_buy] = 1.0
    raw_signals[low_hl_buy | mid_hl_buy | high_hl_buy] = -1.0

    # 数据不足时设为 NaN
    raw_signals[cy_mom.isna() | ratio_pct.isna() | cy_mom_pct.isna()] = np.nan

    # 应用冷却期
    if apply_cooldown:
        return _apply_cooldown(raw_signals)

    return raw_signals


def calculate_signal(
    cy_momentum: float,
    hl_momentum: float,
    prev_state: str,
    days_since_last_switch: int = 999
) -> Tuple[dict, str, Optional[dict]]:
    """
    实时信号计算（用于 UI 卡片）
    使用 compare_momentum 统一平局处理（平局归红利）
    接入冷却期：days_since_last_switch < cooldown_days 时不切换

    Args:
        cy_momentum: 创业板当前动量（20天涨跌幅）
        hl_momentum: 红利当前动量（20天涨跌幅）
        prev_state: 上一次状态 ('cy' / 'hl' / 'cash')
        days_since_last_switch: 距离上次切换的天数（用于冷却期判断）
    Returns:
        (display_info, new_state, event_or_none)
    """
    rf_period = STRATEGY_CONFIG['risk_free_rate'] * STRATEGY_CONFIG['momentum_window'] / 252
    cooldown_days = STRATEGY_CONFIG['cooldown_days']

    # 使用统一的比较函数
    leader = compare_momentum(cy_momentum, hl_momentum)

    # 判断原始新状态（不考虑冷却）
    if leader == 'cy' and cy_momentum > rf_period:
        raw_state = 'cy'
    elif leader == 'hl' and hl_momentum > rf_period:
        raw_state = 'hl'
    else:
        raw_state = 'cash'

    # 应用冷却期：如果在冷却期内且状态变化，则保持原状态
    if raw_state != prev_state and days_since_last_switch < cooldown_days:
        new_state = prev_state  # 冷却期内不切换
    else:
        new_state = raw_state

    # 判断是否产生事件
    event = None
    if prev_state != new_state:
        if new_state in ('cy', 'hl'):
            event = _state_to_event(new_state, action_type='entry')
        elif new_state == 'cash':
            event = _state_to_event('cash', action_type='exit')

    return _get_display_info(new_state, cy_momentum, hl_momentum), new_state, event


def _state_to_event(state: str, action_type: str,
                    cy_momentum: float = None, hl_momentum: float = None) -> dict:
    """将状态转为事件字典"""
    rf_period = STRATEGY_CONFIG['risk_free_rate'] * STRATEGY_CONFIG['momentum_window'] / 252

    # 空仓描述：根据实际动量值动态生成
    if state == 'cash':
        if cy_momentum is not None and hl_momentum is not None:
            both_neg = cy_momentum < 0 and hl_momentum < 0
            if both_neg:
                desc = f'两者动量均为负（创业板 {cy_momentum:+.2%}，红利 {hl_momentum:+.2%}）'
            else:
                desc = f'动量未达门槛（需 > {rf_period:.2%}），当前：创业板 {cy_momentum:+.2%}，红利 {hl_momentum:+.2%}'
        else:
            desc = '动量条件不满足'
    else:
        desc = None  # 使用默认描述

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
            'description': desc or '动量条件不满足',
            'action': '持有现金/货币基金',
            'type': action_type
        }
    }
    return events[state]


def _get_display_info(state: str, cy_momentum: float = None,
                      hl_momentum: float = None) -> dict:
    """返回当前状态的展示信息"""
    return _state_to_event(state, action_type='hold',
                           cy_momentum=cy_momentum, hl_momentum=hl_momentum)
