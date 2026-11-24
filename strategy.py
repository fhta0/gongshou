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


def calculate_smoothed_momentum(
    close_series: pd.Series,
    windows: list = None
) -> pd.Series:
    """
    多窗口平滑动量：取多个窗口动量的均值
    减少单一窗口因基准价跳变导致的动量不稳定

    Args:
        close_series: 收盘价序列
        windows: 回看窗口列表，默认 [10, 20, 40]

    Returns:
        平滑后的动量序列
    """
    if windows is None:
        windows = STRATEGY_CONFIG.get('momentum_windows', [10, 20, 40])

    momenta = [calculate_momentum(close_series, w) for w in windows]
    # 按列拼接后取行均值（自动忽略 NaN）
    combined = pd.concat(momenta, axis=1)
    return combined.mean(axis=1, skipna=True)


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


def _apply_momentum_decay_exit(
    raw_signals: pd.Series,
    cy_mom_pct: pd.Series,
    hl_mom_pct: pd.Series,
    threshold: float = None
) -> pd.Series:
    """
    动量衰竭退出：信号为买入某标的但该标的动量百分位 < threshold 时改为空仓。
    阈值(0.20) < 所有入场门槛(0.30~0.70)，只影响"曾经满足入场后衰减"的持仓。

    Args:
        raw_signals: 原始信号序列
        cy_mom_pct: 创业板动量百分位
        hl_mom_pct: 红利动量百分位
        threshold: 衰竭阈值，默认取 config 值

    Returns:
        衰竭退出后的信号序列
    """
    if threshold is None:
        threshold = STRATEGY_CONFIG.get('decay_exit_threshold', 0.20)

    result = raw_signals.copy()
    # CY 持仓但动量百分位过低 → 空仓
    result[(result == 1) & (cy_mom_pct < threshold)] = 0.0
    # HL 持仓但动量百分位过低 → 空仓
    result[(result == -1) & (hl_mom_pct < threshold)] = 0.0
    return result


def apply_pe_filter(
    signals: pd.Series,
    cy_pe_pct: pd.Series,
    hl_pe_pct: pd.Series,
    threshold: float = None
) -> pd.Series:
    """
    估值过滤：当推荐买入的指数 PE 百分位超过阈值时，改为空仓。

    Args:
        signals: 原始信号序列（1=CY, -1=HL, 0=空仓）
        cy_pe_pct: 创业板 PE 百分位
        hl_pe_pct: 红利 PE 百分位
        threshold: 高估阈值，默认取 config 值

    Returns:
        过滤后的信号序列
    """
    if threshold is None:
        threshold = STRATEGY_CONFIG.get('pe_percentile_threshold', 0.80)

    result = signals.copy()

    # 买入创业板但创业板高估 → 空仓
    result[(result == 1) & (cy_pe_pct > threshold)] = 0.0

    # 买入红利但红利高估 → 空仓
    result[(result == -1) & (hl_pe_pct > threshold)] = 0.0

    return result


def _apply_trend_filter(
    raw_signals: pd.Series,
    close_cy: pd.Series,
    close_hl: pd.Series,
    windows: list = None
) -> pd.Series:
    """
    长周期趋势过滤：持有标的的长周期平滑动量必须 > 0，否则强制空仓。
    与短周期一致的平滑口径（calculate_smoothed_momentum）。

    Args:
        raw_signals: 原始信号序列（1=CY, -1=HL, 0=空仓, NaN=数据不足）
        close_cy: 创业板收盘价序列
        close_hl: 红利收盘价序列
        windows: 长周期窗口列表，默认 [60, 120, 200]

    Returns:
        过滤后的信号序列
    """
    if windows is None:
        windows = STRATEGY_CONFIG.get('trend_filter_windows', [60, 120, 200])

    cy_trend = calculate_smoothed_momentum(close_cy, windows)
    hl_trend = calculate_smoothed_momentum(close_hl, windows)

    result = raw_signals.copy()
    # CY 持仓但 CY 长周期趋势 ≤ 0 → 空仓
    result[(result == 1) & ~(cy_trend > 0)] = 0.0
    # HL 持仓但 HL 长周期趋势 ≤ 0 → 空仓
    result[(result == -1) & ~(hl_trend > 0)] = 0.0
    # 趋势数据不足（暖机期）→ 保持 NaN，不把"无数据"当"看空"
    result[cy_trend.isna() | hl_trend.isna()] = np.nan
    return result


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
    apply_cooldown: bool = True,
    apply_trend_filter: bool = False,
    trend_filter_windows: list = None,
    apply_decay_exit: bool = False,
    decay_exit_threshold: float = None,
    apply_pe_filter_flag: bool = False,
    cy_pe_pct: pd.Series = None,
    hl_pe_pct: pd.Series = None,
    pe_threshold: float = None
) -> pd.Series:
    """
    向量化生成全量信号（用于回测）
    Args:
        df: 包含 close_cy, close_hl 的 DataFrame
        window: 动量窗口
        apply_cooldown: 是否应用冷却期（默认 True）
        apply_trend_filter: 是否应用长周期趋势过滤（默认 False）
        trend_filter_windows: 趋势过滤窗口列表（默认取 config 值）
        apply_decay_exit: 是否应用动量衰竭退出（默认 False）
        decay_exit_threshold: 衰竭退出阈值（默认取 config 值）
        apply_pe_filter_flag: 是否应用估值过滤（默认 False）
        cy_pe_pct: 创业板 PE 百分位序列（用于估值过滤）
        hl_pe_pct: 红利 PE 百分位序列（用于估值过滤）
        pe_threshold: 估值过滤阈值（默认取 config 值）
    Returns:
        信号序列：1=创业板, -1=红利, 0=空仓
    """
    if window is None:
        window = STRATEGY_CONFIG['momentum_window']

    rf_period = STRATEGY_CONFIG['risk_free_rate'] * window / 252

    cy_mom = calculate_smoothed_momentum(df['close_cy'])
    hl_mom = calculate_smoothed_momentum(df['close_hl'])

    # 向量化条件（平局归红利：cy_stronger 需要严格大于）
    cy_stronger = cy_mom > hl_mom
    cy_positive = cy_mom > rf_period
    hl_positive = hl_mom > rf_period

    raw_signals = pd.Series(0, index=df.index, dtype=float)
    raw_signals[cy_stronger & cy_positive] = 1.0
    raw_signals[~cy_stronger & hl_positive] = -1.0

    # 数据不足时设为 NaN
    raw_signals[cy_mom.isna()] = np.nan

    # 趋势过滤（冷却期之前）
    if apply_trend_filter:
        raw_signals = _apply_trend_filter(raw_signals, df['close_cy'], df['close_hl'], trend_filter_windows)

    # 应用冷却期（在衰减退出之前，与实时端一致）
    if apply_cooldown:
        raw_signals = _apply_cooldown(raw_signals)

    # 动量衰竭退出（冷却期之后，安全退出不该被冷却挡住）
    if apply_decay_exit:
        mom_pct_window = STRATEGY_CONFIG['momentum_percentile_window']
        cy_mom_pct = calculate_momentum_percentile(cy_mom, mom_pct_window)
        hl_mom_pct = calculate_momentum_percentile(hl_mom, mom_pct_window)
        raw_signals = _apply_momentum_decay_exit(raw_signals, cy_mom_pct, hl_mom_pct, decay_exit_threshold)

    # 估值过滤（最后应用）
    if apply_pe_filter_flag and cy_pe_pct is not None and hl_pe_pct is not None:
        raw_signals = apply_pe_filter(raw_signals, cy_pe_pct, hl_pe_pct, pe_threshold)

    return raw_signals


def calculate_signal(
    cy_momentum: float,
    hl_momentum: float,
    prev_state: str,
    days_since_last_switch: int = 999,
    cy_pe_pct: float = None,
    hl_pe_pct: float = None,
    apply_pe_filter_flag: bool = False,
    pe_threshold: float = None
) -> Tuple[dict, str, Optional[dict]]:
    """
    实时信号计算（用于 UI 卡片）
    使用 compare_momentum 统一平局处理（平局归红利）
    接入冷却期：days_since_last_switch < cooldown_days 时不切换

    Args:
        cy_momentum: 创业板当前动量（多窗口平滑动量）
        hl_momentum: 红利当前动量（多窗口平滑动量）
        prev_state: 上一次状态 ('cy' / 'hl' / 'cash')
        days_since_last_switch: 距离上次切换的天数（用于冷却期判断）
        cy_pe_pct: 创业板当前 PE 百分位（用于估值过滤）
        hl_pe_pct: 红利当前 PE 百分位（用于估值过滤）
        apply_pe_filter_flag: 是否应用估值过滤
        pe_threshold: 估值过滤阈值

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

    # 估值过滤
    if apply_pe_filter_flag and raw_state in ('cy', 'hl'):
        if pe_threshold is None:
            pe_threshold = STRATEGY_CONFIG.get('pe_percentile_threshold', 0.80)

        if raw_state == 'cy' and cy_pe_pct is not None and cy_pe_pct > pe_threshold:
            raw_state = 'cash'  # 创业板高估，改为空仓
        elif raw_state == 'hl' and hl_pe_pct is not None and hl_pe_pct > pe_threshold:
            raw_state = 'cash'  # 红利高估，改为空仓

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
