"""
创业板/中证红利双动量信号系统 - Streamlit 主入口
策略：比较两指数的N天动量，选择更强的一方；若均为负则空仓。
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

from config import STRATEGY_CONFIG
from data_loader import load_merged_data, get_realtime_change
from strategy import calculate_signal, calculate_momentum
from backtester import run_backtest, calculate_statistics


st.set_page_config(
    page_title="双动量信号系统",
    page_icon="📊",
    layout="wide"
)


def is_trading_hours() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    hour, minute = now.hour, now.minute
    morning = (hour == 9 and minute >= 30) or (hour == 10) or (hour == 11 and minute <= 30)
    afternoon = (hour == 13) or (hour == 14)
    return morning or afternoon


def main():
    st.title("📊 创业板/中证红利 双动量信号系统")

    with st.spinner("加载历史数据..."):
        merged_data = load_merged_data()

    if merged_data.empty:
        st.error("数据加载失败，请刷新页面重试")
        st.stop()

    st.session_state['merged_data'] = merged_data
    last_update = merged_data['date'].iloc[-1].strftime('%Y-%m-%d')
    st.caption(f"历史数据截至: {last_update}")

    if is_trading_hours():
        st_autorefresh(interval=5 * 60 * 1000, key="realtime_refresh")
        st.info("🔴 盘中模式：每 5 分钟自动刷新")

    tab1, tab2 = st.tabs(["📡 实时信号", "📊 历史回测"])

    with tab1:
        render_signal_tab(merged_data)
    with tab2:
        render_backtest_tab(merged_data)


def render_signal_tab(merged_data: pd.DataFrame):
    render_realtime_card(merged_data)
    st.subheader("比值走势与动量")
    render_ratio_chart(merged_data)
    st.subheader("指数对比")
    render_index_comparison(merged_data)


@st.fragment(run_every=300)
def render_realtime_card(merged_data: pd.DataFrame):
    st.subheader("当前信号")

    # 计算历史动量
    window = STRATEGY_CONFIG['momentum_window']
    cy_mom_series = calculate_momentum(merged_data['close_cy'], window)
    hl_mom_series = calculate_momentum(merged_data['close_hl'], window)

    # 昨日动量
    cy_mom_hist = cy_mom_series.iloc[-1]
    hl_mom_hist = hl_mom_series.iloc[-1]

    # 盘中实时修正
    cy_change = get_realtime_change(STRATEGY_CONFIG['symbol_a']['spot_code'])
    hl_change = get_realtime_change(STRATEGY_CONFIG['symbol_b']['spot_code'])

    cy_close_today = merged_data['close_cy'].iloc[-1] * (1 + cy_change)
    hl_close_today = merged_data['close_hl'].iloc[-1] * (1 + hl_change)

    # 用今天的价格重算动量
    cy_mom_today = (cy_close_today / merged_data['close_cy'].iloc[-window]) - 1 if len(merged_data) > window else 0
    hl_mom_today = (hl_close_today / merged_data['close_hl'].iloc[-window]) - 1 if len(merged_data) > window else 0

    rf_period = STRATEGY_CONFIG['risk_free_rate'] * window / 252

    prev_state = st.session_state.get('prev_state', 'cash')
    display, new_state, event = calculate_signal(cy_mom_today, hl_mom_today, prev_state)
    st.session_state['prev_state'] = new_state

    # 指标卡片
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "创业板动量",
            f"{cy_mom_today:+.2%}",
            delta=f"昨日 {cy_mom_hist:+.2%}" if not pd.isna(cy_mom_hist) else None
        )
    with col2:
        st.metric(
            "红利动量",
            f"{hl_mom_today:+.2%}",
            delta=f"昨日 {hl_mom_hist:+.2%}" if not pd.isna(hl_mom_hist) else None
        )
    with col3:
        st.metric("状态", f"{display['emoji']} {display['signal']}")

    # 信号描述
    if display['color'] == 'blue':
        st.success(f"**{display['description']}**\n\n操作建议：{display['action']}")
    elif display['color'] == 'orange':
        st.info(f"**{display['description']}**\n\n操作建议：{display['action']}")
    else:
        st.warning(f"**{display['description']}**\n\n操作建议：{display['action']}")

    # 策略说明
    with st.expander("📖 策略说明"):
        st.markdown(f"""
        **双动量策略**（回看窗口: {window}天，无风险利率: {STRATEGY_CONFIG['risk_free_rate']:.1%}/年）
        - 🔵 **买入创业板**：创业板动量 > 红利动量 且 > {rf_period:.2%}（{window}天无门槛收益）
        - 🟠 **买入红利**：红利动量 > 创业板动量 且 > {rf_period:.2%}
        - ⚪ **空仓观望**：两者动量均为负
        """)

    if event and event['type'] == 'entry':
        st.balloons()
        st.toast(f"🔔 新信号：{event['signal']}！", icon="🚨")


def render_ratio_chart(merged_data: pd.DataFrame):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    window = STRATEGY_CONFIG['momentum_window']
    ratio = merged_data['ratio']
    ratio_ma = ratio.rolling(window).mean()

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.03,
                        row_heights=[0.6, 0.4])

    # 上图：比值 + MA
    fig.add_trace(go.Scattergl(
        x=merged_data['date'], y=ratio,
        mode='lines', name='比值',
        line=dict(color='royalblue', width=2)
    ), row=1, col=1)
    fig.add_trace(go.Scattergl(
        x=merged_data['date'], y=ratio_ma,
        mode='lines', name=f'{window}日均线',
        line=dict(color='gray', width=1, dash='dash')
    ), row=1, col=1)

    # 下图：动量对比
    cy_mom = calculate_momentum(merged_data['close_cy'], window)
    hl_mom = calculate_momentum(merged_data['close_hl'], window)

    fig.add_trace(go.Scattergl(
        x=merged_data['date'], y=cy_mom,
        mode='lines', name='创业板动量',
        line=dict(color='blue', width=1.5)
    ), row=2, col=1)
    fig.add_trace(go.Scattergl(
        x=merged_data['date'], y=hl_mom,
        mode='lines', name='红利动量',
        line=dict(color='orange', width=1.5)
    ), row=2, col=1)
    fig.add_hline(y=0, line_dash='solid', line_color='black', line_width=0.5, row=2, col=1)

    fig.update_xaxes(title_text="日期", row=2, col=1)
    fig.update_yaxes(title_text="比值", row=1, col=1)
    fig.update_yaxes(title_text="动量 (N天涨跌幅)", row=2, col=1)
    fig.update_layout(height=500, hovermode='x unified', legend=dict(orientation='h', y=1.05))
    st.plotly_chart(fig, use_container_width=True)


def render_index_comparison(merged_data: pd.DataFrame):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scattergl(x=merged_data['date'], y=merged_data['close_cy'],
                     name=STRATEGY_CONFIG['symbol_a']['name'], line=dict(color='blue')),
        secondary_y=False
    )
    fig.add_trace(
        go.Scattergl(x=merged_data['date'], y=merged_data['close_hl'],
                     name=STRATEGY_CONFIG['symbol_b']['name'], line=dict(color='orange')),
        secondary_y=True
    )

    fig.update_xaxes(title_text="日期")
    fig.update_yaxes(title_text=STRATEGY_CONFIG['symbol_a']['name'], secondary_y=False)
    fig.update_yaxes(title_text=STRATEGY_CONFIG['symbol_b']['name'], secondary_y=True)
    fig.update_layout(height=400, hovermode='x unified')
    st.plotly_chart(fig, use_container_width=True)


def render_backtest_tab(merged_data: pd.DataFrame):
    st.subheader("历史回测")
    with st.form("backtest_form"):
        st.markdown("点击按钮开始回测（可能需要几秒钟）")
        submitted = st.form_submit_button("🚀 开始回测")

    if submitted:
        with st.spinner("正在计算回测..."):
            backtest_result = run_backtest(merged_data)
            stats = calculate_statistics(backtest_result)

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("毛收益率", f"{stats['gross_return']:.2%}")
        with col2:
            st.metric("净收益率", f"{stats['net_return']:.2%}",
                      help="扣除单边0.1%交易成本后的收益")
        with col3:
            st.metric("年化净收益", f"{stats['annualized_return']:.2%}")
        with col4:
            st.metric("最大回撤", f"{stats['max_drawdown']:.2%}")
        with col5:
            st.metric("夏普比率", f"{stats['sharpe_ratio']:.2f}")

        col6, col7, col8, col9 = st.columns(4)
        with col6:
            st.metric("日胜率", f"{stats['win_rate']:.2%}")
        with col7:
            st.metric("交易胜率", f"{stats['trade_win_rate']:.2%}",
                      help="按持仓期统计，每次开平仓算一次交易")
        with col8:
            st.metric("切换次数", f"{stats['trade_count']}次",
                      help="仓位切换次数（含首次建仓）")
        with col9:
            avg_cost = stats['trade_count'] * 0.001
            st.metric("累计成本", f"{avg_cost:.2%}",
                      help="交易成本估算（单边0.1%×切换次数）")

        # 持仓分布
        pos = backtest_result['position'].dropna()
        total = len(pos)
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            cy_days = (pos == 1).sum()
            st.metric("持有创业板", f"{cy_days}天 ({cy_days/total:.1%})")
        with col_c2:
            hl_days = (pos == -1).sum()
            st.metric("持有红利", f"{hl_days}天 ({hl_days/total:.1%})")
        with col_c3:
            cash_days = (pos == 0).sum()
            st.metric("空仓", f"{cash_days}天 ({cash_days/total:.1%})")

        st.subheader("策略累计收益曲线")
        render_nav_chart(backtest_result)
        st.subheader("信号切换记录")
        render_signal_table(backtest_result)


def render_nav_chart(backtest_result: pd.DataFrame):
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_trace(go.Scattergl(
        x=backtest_result['date'], y=backtest_result['strategy_nav'],
        mode='lines', name='策略净值', line=dict(color='purple', width=2)
    ))
    fig.add_trace(go.Scattergl(
        x=backtest_result['date'], y=backtest_result['cy_nav'],
        mode='lines', name='创业板基准', line=dict(color='blue', dash='dash')
    ))
    fig.add_trace(go.Scattergl(
        x=backtest_result['date'], y=backtest_result['hl_nav'],
        mode='lines', name='红利基准', line=dict(color='orange', dash='dash')
    ))
    fig.update_layout(
        xaxis_title="日期", yaxis_title="净值",
        hovermode='x unified', height=400
    )
    fig.update_traces(connectgaps=True)
    st.plotly_chart(fig, use_container_width=True)


def render_signal_table(backtest_result: pd.DataFrame):
    """显示信号切换记录"""
    # 找到持仓发生变化的日期
    pos = backtest_result['position'].fillna(0)
    changes = pos.diff().fillna(pos)
    switch_mask = changes != 0
    signals = backtest_result[switch_mask].copy()

    if signals.empty:
        st.info("回测期间无信号切换")
        return

    display_df = signals[['date', 'position', 'ratio', 'cy_momentum', 'hl_momentum']].copy()
    display_df['date'] = display_df['date'].dt.strftime('%Y-%m-%d')
    display_df['ratio'] = display_df['ratio'].apply(lambda x: f"{x:.4f}")
    display_df['cy_momentum'] = display_df['cy_momentum'].apply(lambda x: f"{x:+.2%}" if pd.notna(x) else '-')
    display_df['hl_momentum'] = display_df['hl_momentum'].apply(lambda x: f"{x:+.2%}" if pd.notna(x) else '-')
    display_df['position'] = display_df['position'].map({
        1.0: '🔵 创业板', -1.0: '🟠 红利', 0.0: '⚪ 空仓'
    })
    display_df.columns = ['日期', '切换至', '比值', '创业板动量', '红利动量']
    st.dataframe(display_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
