"""
创业板/中证红利比值信号系统 - Streamlit 主入口
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

from config import STRATEGY_CONFIG
from data_loader import load_merged_data, get_realtime_change
from strategy import calculate_rolling_percentile, calculate_signal
from backtester import run_backtest, calculate_statistics


st.set_page_config(
    page_title="比值信号系统",
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
    st.title("📊 创业板/中证红利 比值信号系统")

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
    st.subheader("比值历史走势")
    percentiles = calculate_rolling_percentile(merged_data['ratio'], STRATEGY_CONFIG['rolling_window'])
    render_ratio_chart(merged_data, percentiles)
    st.subheader("指数对比")
    render_index_comparison(merged_data)


@st.fragment(run_every=300)
def render_realtime_card(merged_data: pd.DataFrame):
    st.subheader("当前信号")
    yesterday_ratio = merged_data['ratio'].iloc[-1]
    cy_change = get_realtime_change(STRATEGY_CONFIG['symbol_a']['spot_code'])
    hl_change = get_realtime_change(STRATEGY_CONFIG['symbol_b']['spot_code'])
    today_ratio = yesterday_ratio * (1 + cy_change) / (1 + hl_change)

    ratio_series = pd.concat([merged_data['ratio'], pd.Series([today_ratio])])
    percentiles = calculate_rolling_percentile(ratio_series, STRATEGY_CONFIG['rolling_window'])
    percentile = percentiles.iloc[-1]

    prev_state = st.session_state.get('prev_state', 'neutral')
    display, new_state, event = calculate_signal(today_ratio, percentile, prev_state)
    st.session_state['prev_state'] = new_state

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("当前比值", f"{today_ratio:.4f}")
    with col2:
        st.metric("滚动分位", f"{percentile:.1%}")
    with col3:
        st.metric("状态", f"{display['emoji']} {display['signal']}")

    if display['color'] == 'red':
        st.error(f"**{display['description']}**\n\n操作建议：{display['action']}")
    elif display['color'] == 'green':
        st.success(f"**{display['description']}**\n\n操作建议：{display['action']}")
    else:
        st.warning(f"**{display['description']}**\n\n操作建议：{display['action']}")

    if event and event['type'] == 'entry':
        st.balloons()
        st.toast(f"🔔 新信号：{event['signal']}！", icon="🚨")


def render_ratio_chart(merged_data: pd.DataFrame, percentiles: pd.Series):
    import plotly.graph_objects as go
    window = STRATEGY_CONFIG['rolling_window']
    fig = go.Figure()

    fig.add_trace(go.Scattergl(
        x=merged_data['date'], y=merged_data['ratio'],
        mode='lines', name='比值', line=dict(color='royalblue', width=2)
    ))

    rolling_low = merged_data['ratio'].rolling(window).quantile(STRATEGY_CONFIG['low_percentile'])
    rolling_high = merged_data['ratio'].rolling(window).quantile(STRATEGY_CONFIG['high_percentile'])

    fig.add_trace(go.Scattergl(
        x=merged_data['date'], y=rolling_low,
        mode='lines', name='抄底边界 (10%)',
        line=dict(dash='dash', color='red', width=1)
    ))
    fig.add_trace(go.Scattergl(
        x=merged_data['date'], y=rolling_high,
        mode='lines', name='逃顶边界 (90%)',
        line=dict(dash='dash', color='green', width=1)
    ))

    fig.update_layout(
        xaxis_title="日期", yaxis_title="比值（创业板/中证红利）",
        hovermode='x unified', height=400
    )
    fig.update_traces(connectgaps=True)
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
            st.metric("总收益率", f"{stats['total_return']:.2%}")
        with col2:
            st.metric("年化收益率", f"{stats['annualized_return']:.2%}")
        with col3:
            st.metric("最大回撤", f"{stats['max_drawdown']:.2%}")
        with col4:
            st.metric("夏普比率", f"{stats['sharpe_ratio']:.2f}")
        with col5:
            st.metric("胜率", f"{stats['win_rate']:.2%}")

        st.subheader("策略累计收益曲线")
        render_nav_chart(backtest_result)
        st.subheader("信号触发记录")
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
    signals = backtest_result[backtest_result['signal'].diff() != 0].copy()
    if signals.empty:
        st.info("回测期间无信号触发")
        return

    display_df = signals[['date', 'signal', 'ratio', 'percentile']].copy()
    display_df['date'] = display_df['date'].dt.strftime('%Y-%m-%d')
    display_df['ratio'] = display_df['ratio'].apply(lambda x: f"{x:.4f}")
    display_df['percentile'] = display_df['percentile'].apply(lambda x: f"{x:.1%}")
    display_df['signal'] = display_df['signal'].map({1: '🔴 抄底', -1: '🟢 逃顶', 0: '🟡 中性'})
    display_df.columns = ['日期', '信号', '比值', '分位']
    st.dataframe(display_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
