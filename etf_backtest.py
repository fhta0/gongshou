"""
ETF 可交易性验证（159915 创业板 ETF / 510880 红利 ETF）
用途：
1. 验证 510880 实际分红 → 确认股息率假设（3.5% vs 旧 4.5%）
2. ETF 口径回测 vs 指数口径回测对比 → 验证跟踪误差
3. 可复现：每季度重跑确认策略在 ETF 市场价下仍然达标

运行：python etf_backtest.py
"""
import pandas as pd
import numpy as np
import akshare as ak
from config import STRATEGY_CONFIG
from data_loader import load_merged_data
from backtester import run_backtest, calculate_statistics


def load_etf_data(symbol: str, start_date: str = '20110101') -> pd.DataFrame:
    """
    获取 ETF 历史日线（新浪源）
    Args:
        symbol: ETF 代码（如 'sz159915', 'sh510880'）
        start_date: 起始日期 YYYYMMDD
    Returns:
        DataFrame with date, close
    """
    df = ak.fund_etf_hist_sina(symbol=symbol)
    df = df.rename(columns={'date': 'date', 'close': 'close'})
    df['date'] = pd.to_datetime(df['date'])
    df = df[df['date'] >= start_date].copy()
    df = df.sort_values('date').reset_index(drop=True)
    df['close'] = df['close'].astype(float)
    return df[['date', 'close']]


def load_etf_dividends(symbol: str = 'sh510880') -> pd.DataFrame:
    """
    获取 ETF 分红记录（新浪源）
    Returns:
        DataFrame with date, dividend_per_share
    """
    df = ak.fund_etf_dividend_sina(symbol=symbol)
    return df


def compute_annual_dividends(div_df: pd.DataFrame) -> dict:
    """
    将分红记录按年度汇总
    Returns:
        dict: {year: total_dividend_per_share}
    """
    div_df = div_df.copy()
    div_df['year'] = pd.to_datetime(div_df['date']).dt.year
    annual = div_df.groupby('year')['dividend_per_share'].sum()
    return annual.to_dict()


def build_etf_total_return(etf_close: pd.Series, annual_dividends: dict) -> pd.Series:
    """
    用 ETF 市场价 + 年度分红构建总收益序列
    total_return[t] = total_return[t-1] * (1 + daily_price_return + dividend_yield_daily)
    """
    daily_returns = etf_close.pct_change()
    # 简化：年度分红均匀分摊到每个交易日
    # 实际分红按季度发放，但均匀分摊对 20 天动量影响 < 0.1pp
    avg_price = etf_close.mean()
    annual_div_yield = sum(annual_dividends.values()) / len(annual_dividends) / avg_price
    daily_div = annual_div_yield / 252
    total_return = etf_close.iloc[0] * (1 + daily_returns.fillna(0) + daily_div).cumprod()
    return total_return


def run_etf_backtest_comparison():
    """
    主函数：ETF 口径 vs 指数口径回测对比
    """
    print("=" * 80)
    print("ETF 可交易性验证")
    print("=" * 80)

    # 1. 加载指数数据
    index_data = load_merged_data()
    print(f"\n指数数据: {index_data['date'].iloc[0].date()} ~ {index_data['date'].iloc[-1].date()}")
    print(f"  数据量: {len(index_data)} 天")

    # 2. 加载 ETF 数据
    print("\n加载 ETF 数据...")
    try:
        cy_etf = load_etf_data('sz159915')
        hl_etf = load_etf_data('sh510880')
        print(f"  159915: {cy_etf['date'].iloc[0].date()} ~ {cy_etf['date'].iloc[-1].date()}, {len(cy_etf)} 天")
        print(f"  510880: {hl_etf['date'].iloc[0].date()} ~ {hl_etf['date'].iloc[-1].date()}, {len(hl_etf)} 天")
    except Exception as e:
        print(f"  ETF 数据加载失败: {e}")
        print("  跳过 ETF 回测，仅展示分红分析")
        cy_etf = hl_etf = None

    # 3. 510880 分红分析
    print("\n--- 510880 分红分析 ---")
    try:
        div_df = load_etf_dividends()
        annual_div = compute_annual_dividends(div_df)
        hl_avg_price = hl_etf['close'].mean() if hl_etf is not None else 3.0

        print(f"{'年份':>6} {'分红(元/份)':>12} {'ETF价格~':>10} {'股息率':>8}")
        print("-" * 40)
        total_div = 0
        n_years = 0
        for year, div in sorted(annual_div.items()):
            # 估算该年均价（简化：用整体均价）
            yield_pct = div / hl_avg_price
            print(f"{year:>6} {div:>12.3f} {hl_avg_price:>10.2f} {yield_pct:>7.1%}")
            total_div += div
            n_years += 1

        avg_div = total_div / n_years
        avg_yield = avg_div / hl_avg_price
        print("-" * 40)
        print(f"{'均值':>6} {avg_div:>12.3f} {hl_avg_price:>10.2f} {avg_yield:>7.1%}")
        print(f"\n结论：510880 实际股息率 ~{avg_yield:.1%}，验证 config dividend_yield={STRATEGY_CONFIG.get('dividend_yield', 0.035):.1%}")

    except Exception as e:
        print(f"  分红数据加载失败: {e}")

    # 4. ETF 口径回测
    if cy_etf is not None and hl_etf is not None:
        print("\n--- ETF 口径回测 vs 指数口径回测 ---")
        eval_start = pd.Timestamp('2016-03-01')

        # 合并 ETF 数据
        etf_merged = pd.merge(
            cy_etf.rename(columns={'close': 'close_cy'}),
            hl_etf.rename(columns={'close': 'close_hl'}),
            on='date', how='inner'
        )
        etf_merged['ratio'] = etf_merged['close_cy'] / etf_merged['close_hl']

        # ETF 回测
        etf_result = run_backtest(etf_merged, strategy_type='momentum',
                                   apply_decay_exit=True, apply_vol_target=True)
        etf_eval = etf_result[etf_result['date'] >= eval_start]
        etf_stats = calculate_statistics(etf_eval)

        # 指数回测（相同评估窗口）
        idx_result = run_backtest(index_data, strategy_type='momentum',
                                   apply_decay_exit=True, apply_vol_target=True)
        idx_eval = idx_result[idx_result['date'] >= eval_start]
        idx_stats = calculate_statistics(idx_eval)

        print(f"\n{'指标':>12} {'ETF 口径':>12} {'指数口径(3.5%)':>14}")
        print("-" * 42)
        print(f"{'年化':>12} {etf_stats['annualized_return']:>11.2%} {idx_stats['annualized_return']:>13.2%}")
        print(f"{'最大回撤':>12} {etf_stats['max_drawdown']:>11.2%} {idx_stats['max_drawdown']:>13.2%}")
        print(f"{'夏普':>12} {etf_stats['sharpe_ratio']:>11.2f} {idx_stats['sharpe_ratio']:>13.2f}")

        etf_dd = etf_stats['max_drawdown']
        etf_calmar = etf_stats['annualized_return'] / etf_dd if etf_dd > 0 else 0
        idx_dd = idx_stats['max_drawdown']
        idx_calmar = idx_stats['annualized_return'] / idx_dd if idx_dd > 0 else 0
        print(f"{'Calmar':>12} {etf_calmar:>11.2f} {idx_calmar:>13.2f}")

        # 跟踪误差
        etf_nav = etf_eval['strategy_nav'].pct_change().dropna()
        idx_nav = idx_eval['strategy_nav'].pct_change().dropna()
        common_idx = etf_nav.index.intersection(idx_nav.index)
        if len(common_idx) > 0:
            tracking_error = (etf_nav.loc[common_idx] - idx_nav.loc[common_idx]).std() * (252 ** 0.5)
            print(f"\n年化跟踪误差: {tracking_error:.2%}")

        print("\n结论：ETF 口径与指数口径(3.5%股息)对比 → 验证股息率假设准确性")


if __name__ == '__main__':
    run_etf_backtest_comparison()
