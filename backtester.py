"""
backtester.py — 双动量策略回测引擎
T 日数据生成信号，T+1 日执行交易（避免 look-ahead bias）
"""
import pandas as pd
import streamlit as st
from config import STRATEGY_CONFIG
from strategy import generate_signals, generate_combined_signals, calculate_ratio_percentile, calculate_momentum_percentile


@st.cache_data
def run_backtest(
    df: pd.DataFrame,
    window: int = None,
    transaction_cost: float = 0.001,  # 单边 0.1%（含佣金+印花税+滑点）
    strategy_type: str = 'momentum'  # 'momentum' 或 'combined'
) -> pd.DataFrame:
    """
    运行回测
    Args:
        df: 包含 date, close_cy, close_hl 的 DataFrame（组合策略还需 ratio 列）
        window: 动量窗口（默认使用配置值）
        transaction_cost: 单边交易成本，默认 0.1%
        strategy_type: 'momentum'（纯动量）或 'combined'（组合策略）
    Returns:
        包含信号、持仓、净值的 DataFrame
    """
    if window is None:
        window = STRATEGY_CONFIG['momentum_window']

    result = df.copy()

    # 确保 ratio 列存在
    if 'ratio' not in result.columns:
        result['ratio'] = result['close_cy'] / result['close_hl']

    # 计算百分位（供信号强度和 UI 使用）
    result['ratio_percentile'] = calculate_ratio_percentile(
        result['ratio'], STRATEGY_CONFIG['percentile_window']
    )
    mom_pct_window = STRATEGY_CONFIG['momentum_percentile_window']
    cy_mom_pct = calculate_momentum_percentile(
        result['close_cy'].pct_change(window), mom_pct_window
    )
    hl_mom_pct = calculate_momentum_percentile(
        result['close_hl'].pct_change(window), mom_pct_window
    )

    # 1. 生成信号（T日）
    if strategy_type == 'combined':
        result['signal'] = generate_combined_signals(result, window)
    else:
        result['signal'] = generate_signals(result, window)

    # 1b. 信号强度 + 动量百分位列
    result['cy_momentum_percentile'] = cy_mom_pct
    result['hl_momentum_percentile'] = hl_mom_pct

    signal_strength = pd.Series('空仓', index=result.index)
    signal_strength[result['signal'] == 1] = '普通'
    signal_strength[result['signal'] == -1] = '普通'
    low_mask = result['ratio_percentile'] <= STRATEGY_CONFIG['low_percentile']
    high_mask = result['ratio_percentile'] >= STRATEGY_CONFIG['high_percentile']
    signal_strength[low_mask & (result['signal'] != 0)] = '强信号'
    signal_strength[high_mask & (result['signal'] == 1) & (cy_mom_pct > 0.7)] = '强信号'
    result['signal_strength'] = signal_strength

    # 2. T+1 执行
    result['position'] = result['signal'].shift(1)

    # 3. 检测仓位切换（用于计算交易成本）
    position_change = result['position'].fillna(0).diff().fillna(0)
    result['is_switch'] = (position_change != 0).astype(int)
    # 第一次建仓也算一次切换（但进入空仓不收费）
    if result['position'].notna().any():
        first_valid_idx = result['position'].first_valid_index()
        if first_valid_idx is not None and result.loc[first_valid_idx, 'position'] != 0:
            result.loc[first_valid_idx, 'is_switch'] = 1
        else:
            result.loc[first_valid_idx, 'is_switch'] = 0

    # 4. 计算每日收益
    result['cy_return'] = result['close_cy'].pct_change()
    result['hl_return'] = result['close_hl'].pct_change()

    # 5. 策略收益（毛收益）
    risk_free_daily = STRATEGY_CONFIG['risk_free_rate'] / 252
    result['strategy_return'] = risk_free_daily  # 默认无风险收益
    result.loc[result['position'] == 1, 'strategy_return'] = result.loc[result['position'] == 1, 'cy_return']
    result.loc[result['position'] == -1, 'strategy_return'] = result.loc[result['position'] == -1, 'hl_return']

    # 6. 扣除交易成本（仅在切换仓位时扣除）
    result['transaction_cost'] = result['is_switch'] * transaction_cost
    result['net_return'] = result['strategy_return'] - result['transaction_cost']

    # 7. 累计净值（毛收益 vs 净收益）
    result['strategy_nav'] = (1 + result['strategy_return'].fillna(0)).cumprod()
    result['strategy_nav_net'] = (1 + result['net_return'].fillna(0)).cumprod()
    result['cy_nav'] = (1 + result['cy_return'].fillna(0)).cumprod()
    result['hl_nav'] = (1 + result['hl_return'].fillna(0)).cumprod()

    # 8. 动量列（用于图表展示）
    result['cy_momentum'] = result['close_cy'].pct_change(window)
    result['hl_momentum'] = result['close_hl'].pct_change(window)

    return result


def calculate_statistics(df: pd.DataFrame) -> dict:
    """
    计算回测统计指标
    Returns:
        dict with keys:
        - gross_return, net_return: 毛收益/净收益
        - annualized_return: 年化净收益
        - max_drawdown: 基于净值的最大回撤
        - sharpe_ratio: 基于净收益的夏普
        - win_rate: 日胜率
        - trade_count: 切换次数（含建仓）
        - trade_win_rate: 交易胜率（按持仓期统计）
    """
    nav_net = df['strategy_nav_net'].dropna() if 'strategy_nav_net' in df.columns else df['strategy_nav'].dropna()
    returns_net = df['net_return'].dropna() if 'net_return' in df.columns else df['strategy_return'].dropna()
    returns_gross = df['strategy_return'].dropna()

    if len(nav_net) < 2:
        return {
            'gross_return': 0.0,
            'net_return': 0.0,
            'annualized_return': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0,
            'win_rate': 0.0,
            'trade_count': 0,
            'trade_win_rate': 0.0
        }

    # 毛收益
    gross_return = (df['strategy_nav'].iloc[-1] / df['strategy_nav'].iloc[0]) - 1 if 'strategy_nav' in df.columns else 0.0

    # 净收益
    net_return = (nav_net.iloc[-1] / nav_net.iloc[0]) - 1

    # 年化净收益率（252 交易日）
    n_days = len(nav_net)
    annualized_return = (1 + net_return) ** (252 / n_days) - 1

    # 最大回撤（基于净净值）
    cummax = nav_net.cummax()
    drawdown = (cummax - nav_net) / cummax
    max_drawdown = drawdown.max()

    # 夏普比率（基于净收益）
    risk_free_daily = STRATEGY_CONFIG['risk_free_rate'] / 252
    excess_returns = returns_net - risk_free_daily
    sharpe_ratio = (excess_returns.mean() / excess_returns.std()) * (252 ** 0.5) if excess_returns.std() > 0 else 0.0

    # 日胜率（保留兼容）
    win_rate = (returns_gross > 0).sum() / len(returns_gross) if len(returns_gross) > 0 else 0.0

    # 切换次数
    trade_count = int(df['is_switch'].sum()) if 'is_switch' in df.columns else 0

    # 交易胜率（按持仓期统计）
    trade_win_rate = _calculate_trade_win_rate(df)

    return {
        'gross_return': gross_return,
        'net_return': net_return,
        'annualized_return': annualized_return,
        'max_drawdown': max_drawdown,
        'sharpe_ratio': sharpe_ratio,
        'win_rate': win_rate,
        'trade_count': trade_count,
        'trade_win_rate': trade_win_rate
    }


def _calculate_trade_win_rate(df: pd.DataFrame) -> float:
    """
    按持仓期统计交易胜率
    每次仓位变化（建仓、切换方向、平仓）都结算上一段，统计该持仓期的总收益
    """
    if 'position' not in df.columns:
        return 0.0

    position = df['position'].fillna(0)
    trades = []
    current_trade_return = 0.0
    prev_pos = 0  # 前一个仓位

    for i in range(len(df)):
        pos = position.iloc[i]

        # 检测仓位变化
        if pos != prev_pos:
            # 如果之前在持仓中，结算上一段
            if prev_pos != 0:
                trades.append(current_trade_return)
                current_trade_return = 0.0

            # 如果进入新持仓，重新开始累计
            if pos != 0:
                # 累加当日收益
                if 'net_return' in df.columns:
                    current_trade_return += df['net_return'].iloc[i]
                else:
                    current_trade_return += df['strategy_return'].iloc[i]
        else:
            # 仓位不变
            if pos != 0:
                # 在持仓中，累加当日收益
                if 'net_return' in df.columns:
                    current_trade_return += df['net_return'].iloc[i]
                else:
                    current_trade_return += df['strategy_return'].iloc[i]

        prev_pos = pos

    # 如果最后还在持仓，也算一次交易
    if prev_pos != 0:
        trades.append(current_trade_return)

    if len(trades) == 0:
        return 0.0

    # 盈利交易数 / 总交易数
    winning_trades = sum(1 for t in trades if t > 0)
    return winning_trades / len(trades)
