"""
创业板/中证红利双动量信号系统 - Streamlit 主入口
策略：比较两指数的N天动量，选择更强的一方；若均为负则空仓。
"""
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

from config import STRATEGY_CONFIG, VERSION
from data_loader import load_merged_data, get_realtime_change, load_pe_data_for_strategy
from strategy import (
    calculate_signal, calculate_smoothed_momentum,
    calculate_ratio_percentile, calculate_momentum_percentile, apply_pe_filter
)
from backtester import run_backtest, calculate_statistics


st.set_page_config(
    page_title=f"双动量信号系统 v{VERSION}",
    page_icon="📊",
    layout="wide"
)

# 强制覆盖浏览器标题（确保不显示 Streamlit 字样）
st.markdown(f"""
<script>
    document.title = "双动量信号系统 v{VERSION}";
</script>
""", unsafe_allow_html=True)


# ===== 样式注入 =====

def _inject_css():
    """注入自定义 CSS，统一视觉风格"""
    st.markdown("""
    <style>
    /* 全局字体与背景 */
    .stApp {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }

    /* 隐藏 header 后消除顶部空白 */
    .stApp[data-testid="stAppViewContainer"] {
        padding-top: 0;
    }
    .stApp[data-testid="stAppViewContainer"] > .main {
        padding-top: 1rem;
    }

    /* 页面头部标题区 */
    .hero-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 2rem 2.5rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .hero-header h1 {
        margin: 0 0 0.3rem 0;
        font-size: 1.8rem;
        font-weight: 700;
        letter-spacing: -0.02em;
    }
    .hero-header .subtitle {
        font-size: 0.95rem;
        opacity: 0.8;
        font-weight: 400;
    }

    /* 信号卡片 */
    .signal-card {
        padding: 1.5rem;
        border-radius: 12px;
        margin-bottom: 1rem;
        border-left: 5px solid;
        background: white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    .signal-card.cy {
        border-left-color: #1f77b4;
        background: linear-gradient(90deg, #eef5fc 0%, white 30%);
    }
    .signal-card.hl {
        border-left-color: #ff7f0e;
        background: linear-gradient(90deg, #fff4eb 0%, white 30%);
    }
    .signal-card.cash {
        border-left-color: #999999;
        background: linear-gradient(90deg, #f5f5f5 0%, white 30%);
    }
    .signal-card .signal-title {
        font-size: 1.3rem;
        font-weight: 700;
        margin: 0 0 0.4rem 0;
    }
    .signal-card .signal-desc {
        font-size: 0.9rem;
        color: #555;
        margin: 0;
        line-height: 1.5;
    }

    /* 指标分组容器 */
    .metric-group {
        background: white;
        padding: 1.2rem 1.5rem;
        border-radius: 10px;
        margin-bottom: 1rem;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }
    .metric-group-title {
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #888;
        margin-bottom: 0.8rem;
    }

    /* 章节标题 */
    .section-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #1a1a2e;
        margin: 1.5rem 0 0.8rem 0;
        padding-bottom: 0.4rem;
        border-bottom: 2px solid #f0f2f6;
    }

    /* 信号强度标签 */
    .strength-badge {
        display: inline-block;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .strength-badge.strong {
        background: #fef3c7;
        color: #92400e;
    }
    .strength-badge.normal {
        background: #dbeafe;
        color: #1e40af;
    }
    .strength-badge.empty {
        background: #f3f4f6;
        color: #6b7280;
    }

    /* 隐藏 Streamlit 顶部工具栏（汉堡菜单、Deploy 按钮等） */
    header[data-testid="stHeader"] {
        display: none;
    }

    /* 隐藏 "Made with Streamlit" 底部横幅 */
    .stDeployButton,
    [data-testid="stToolbar"],
    [data-testid="stToolbarContent"] {
        display: none !important;
    }

    /* 隐藏 Streamlit 默认 footer */
    footer { visibility: hidden; height: 0; }
    .stApp footer::after {
        visibility: visible;
        content: '仅供研究参考，不构成投资建议';
        display: block;
        text-align: center;
        padding: 1rem;
        font-size: 0.75rem;
        color: #999;
    }

    /* Tab 样式 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.5rem;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 0.6rem 1.2rem;
        border-radius: 8px 8px 0 0;
    }

    /* Metric 数值颜色 */
    [data-testid="stMetricValue"] {
        font-weight: 600;
    }
    </style>
    """, unsafe_allow_html=True)


def _render_hero_header(last_update: str):
    """渲染页面顶部 hero 区域"""
    st.markdown(f"""
    <div class="hero-header">
        <h1>📊 双动量信号系统 <span style="font-size: 0.6em; opacity: 0.7;">v{VERSION}</span></h1>
        <div class="subtitle">创业板 / 中证红利 · 动量轮动策略 · 数据截至 {last_update}</div>
    </div>
    """, unsafe_allow_html=True)


# ===== 冷却状态持久化（内存版，兼容 Streamlit Cloud） =====

# 全局变量：上次切换日期（进程级别，重启后重置）
_last_switch_date = None


def _load_cooldown_state():
    """从内存加载上次切换日期（Streamlit Cloud 不支持文件持久化）"""
    return _last_switch_date


def _save_cooldown_state(date):
    """保存上次切换日期到内存"""
    global _last_switch_date
    _last_switch_date = date


def is_trading_hours() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    hour, minute = now.hour, now.minute
    morning = (hour == 9 and minute >= 30) or (hour == 10) or (hour == 11 and minute <= 30)
    afternoon = (hour == 13) or (hour == 14)
    return morning or afternoon


def main():
    _inject_css()

    with st.spinner("加载历史数据..."):
        merged_data = load_merged_data()

    if merged_data.empty:
        st.error("数据加载失败，请刷新页面重试")
        st.stop()

    st.session_state['merged_data'] = merged_data
    last_update = merged_data['date'].iloc[-1].strftime('%Y-%m-%d')
    _render_hero_header(last_update)

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
    st.markdown('<div class="section-title">📈 比值走势与动量</div>', unsafe_allow_html=True)
    render_ratio_chart(merged_data)
    st.markdown('<div class="section-title">📉 指数对比</div>', unsafe_allow_html=True)
    render_index_comparison(merged_data)


@st.fragment(run_every=300)
def render_realtime_card(merged_data: pd.DataFrame):
    st.subheader("当前信号")

    # 计算历史动量（多窗口平滑 + 单窗口用于对比展示）
    window = STRATEGY_CONFIG['momentum_window']
    momentum_windows = STRATEGY_CONFIG.get('momentum_windows', [10, 20, 40])

    # 平滑动量序列（用于信号和百分位）
    cy_mom_smooth_series = calculate_smoothed_momentum(merged_data['close_cy'])
    hl_mom_smooth_series = calculate_smoothed_momentum(merged_data['close_hl'])

    # 昨日动量
    cy_mom_hist = cy_mom_smooth_series.iloc[-1]
    hl_mom_hist = hl_mom_smooth_series.iloc[-1]

    # 盘中实时修正
    cy_change = get_realtime_change(STRATEGY_CONFIG['symbol_a']['spot_code'])
    hl_change = get_realtime_change(STRATEGY_CONFIG['symbol_b']['spot_code'])

    cy_close_today = merged_data['close_cy'].iloc[-1] * (1 + cy_change)
    hl_close_today = merged_data['close_hl'].iloc[-1] * (1 + hl_change)

    # 用今天的价格重算各窗口动量，然后取均值（平滑）
    n = len(merged_data)
    cy_mom_vals = []
    hl_mom_vals = []
    for w in momentum_windows:
        if n > w:
            cy_mom_vals.append((cy_close_today / merged_data['close_cy'].iloc[-w]) - 1)
            hl_mom_vals.append((hl_close_today / merged_data['close_hl'].iloc[-w]) - 1)
    cy_mom_today = sum(cy_mom_vals) / len(cy_mom_vals) if cy_mom_vals else 0
    hl_mom_today = sum(hl_mom_vals) / len(hl_mom_vals) if hl_mom_vals else 0

    rf_period = STRATEGY_CONFIG['risk_free_rate'] * window / 252

    # 冷却期：从文件加载初始值（防止刷新丢失）
    prev_state = st.session_state.get('prev_state', 'cash')
    last_switch_date = st.session_state.get('last_switch_date', None)
    _first_load = 'prev_state' not in st.session_state  # 是否首次加载（无真实切换历史）
    if last_switch_date is None:
        last_switch_date = _load_cooldown_state()
        if last_switch_date is not None:
            st.session_state['last_switch_date'] = last_switch_date

    # 计算距离上次切换的交易日数（使用merged_data的日期序列）
    # 首次加载时，如果 prev_state 是默认值 'cash'（不是本次 session 真实设置的），
    # 则视为无冷却（days_since_switch=999），避免把默认状态当作"刚切换"
    if last_switch_date is not None and not _first_load:
        dates = merged_data['date']
        last_switch_idx = dates[dates == last_switch_date].index
        if len(last_switch_idx) > 0:
            current_idx = len(dates) - 1
            days_since_switch = current_idx - last_switch_idx[0]
        else:
            days_since_switch = 999
    else:
        days_since_switch = 999

    # 加载 PE 估值数据
    pe_data = load_pe_data_for_strategy()
    cy_pe_pct_today = None
    hl_pe_pct_today = None
    cy_pe_value = None
    hl_pe_value = None

    if not pe_data['cy'].empty:
        cy_pe_df = pe_data['cy'].dropna(subset=['pe_percentile'])
        if not cy_pe_df.empty:
            cy_pe_pct_today = cy_pe_df['pe_percentile'].iloc[-1]
            cy_pe_value = cy_pe_df['pe'].iloc[-1]

    if not pe_data['hl'].empty:
        hl_pe_df = pe_data['hl'].dropna(subset=['pe_percentile'])
        if not hl_pe_df.empty:
            hl_pe_pct_today = hl_pe_df['pe_percentile'].iloc[-1]
            hl_pe_value = hl_pe_df['pe'].iloc[-1]

    # 是否启用估值过滤
    apply_pe_filter_flag = STRATEGY_CONFIG.get('apply_pe_filter', True)
    pe_threshold = STRATEGY_CONFIG.get('pe_percentile_threshold', 0.80)

    display, new_state, event = calculate_signal(
        cy_mom_today, hl_mom_today, prev_state, days_since_switch,
        cy_pe_pct=cy_pe_pct_today,
        hl_pe_pct=hl_pe_pct_today,
        apply_pe_filter_flag=apply_pe_filter_flag,
        pe_threshold=pe_threshold
    )

    # 计算百分位（用于衰减退出 + 展示，纳入今日盘中实时修正）
    mom_pct_window = STRATEGY_CONFIG['momentum_percentile_window']
    cy_close_ext = pd.concat([merged_data['close_cy'], pd.Series([cy_close_today])], ignore_index=True)
    hl_close_ext = pd.concat([merged_data['close_hl'], pd.Series([hl_close_today])], ignore_index=True)
    cy_mom_smooth_ext = calculate_smoothed_momentum(cy_close_ext)
    hl_mom_smooth_ext = calculate_smoothed_momentum(hl_close_ext)
    cy_mom_pct_series = calculate_momentum_percentile(cy_mom_smooth_ext, mom_pct_window)
    hl_mom_pct_series = calculate_momentum_percentile(hl_mom_smooth_ext, mom_pct_window)
    cy_mom_pct_today = cy_mom_pct_series.iloc[-1] if not pd.isna(cy_mom_pct_series.iloc[-1]) else None
    hl_mom_pct_today = hl_mom_pct_series.iloc[-1] if not pd.isna(hl_mom_pct_series.iloc[-1]) else None

    # 衰减退出（与回测对齐）：动量百分位低于阈值时强制空仓
    decay_threshold = STRATEGY_CONFIG.get('decay_exit_threshold', 0.20)
    decay_exit_triggered = False
    if new_state == 'cy' and cy_mom_pct_today is not None and cy_mom_pct_today < decay_threshold:
        new_state = 'cash'
        decay_exit_triggered = True
        display = {'signal': '空仓', 'color': 'red', 'emoji': '⚪',
                   'description': f'动量衰竭退出（创业板动量百分位 {cy_mom_pct_today:.0%} < {decay_threshold:.0%}）',
                   'action': '空仓观望'}
    elif new_state == 'hl' and hl_mom_pct_today is not None and hl_mom_pct_today < decay_threshold:
        new_state = 'cash'
        decay_exit_triggered = True
        display = {'signal': '空仓', 'color': 'red', 'emoji': '⚪',
                   'description': f'动量衰竭退出（红利动量百分位 {hl_mom_pct_today:.0%} < {decay_threshold:.0%}）',
                   'action': '空仓观望'}

    # 估值过滤触发提示
    pe_filter_triggered = False
    if apply_pe_filter_flag:
        # 检查是否因为估值过高被过滤
        # 注意：这里需要在 calculate_signal 之后再检查
        # 如果原信号是 cy/hl 但被估值过滤改为 cash，event 会是 exit
        # 我们通过检查 PE 百分位来判断是否触发了估值过滤
        if cy_pe_pct_today is not None and cy_pe_pct_today > pe_threshold:
            pe_filter_triggered = True
        if hl_pe_pct_today is not None and hl_pe_pct_today > pe_threshold:
            pe_filter_triggered = True

    # 波动率目标仓位缩放（与回测对齐）
    vol_lookback = STRATEGY_CONFIG.get('vol_lookback', 60)
    target_vol = STRATEGY_CONFIG.get('target_vol', 0.14)
    vol_scale = 1.0  # 默认满仓
    if new_state == 'cy' and len(cy_close_ext) > vol_lookback:
        cy_returns = cy_close_ext.pct_change().dropna()
        cy_realized_vol = cy_returns.iloc[-vol_lookback:].std() * (252 ** 0.5)
        if cy_realized_vol > 0:
            vol_scale = min(target_vol / cy_realized_vol, 1.0)
    elif new_state == 'hl' and len(hl_close_ext) > vol_lookback:
        hl_returns = hl_close_ext.pct_change().dropna()
        hl_realized_vol = hl_returns.iloc[-vol_lookback:].std() * (252 ** 0.5)
        if hl_realized_vol > 0:
            vol_scale = min(target_vol / hl_realized_vol, 1.0)

    # 动态计算描述（不依赖 strategy 模块的静态描述）
    # 衰减退出时保留其专属描述，不被 cash 分支覆盖
    if new_state == 'cash' and not decay_exit_triggered:
        both_neg = cy_mom_today < 0 and hl_mom_today < 0
        if both_neg:
            display['description'] = f'两者动量均为负（创业板 {cy_mom_today:+.2%}，红利 {hl_mom_today:+.2%}）'
        else:
            display['description'] = f'动量未达门槛（需 > {rf_period:.2%}），当前：创业板 {cy_mom_today:+.2%}，红利 {hl_mom_today:+.2%}'

    # 更新状态和冷却计时
    if new_state != prev_state:
        switch_date = merged_data['date'].iloc[-1]
        st.session_state['last_switch_date'] = switch_date
        _save_cooldown_state(switch_date)
    st.session_state['prev_state'] = new_state

    pct_window = STRATEGY_CONFIG['percentile_window']
    ratio_pct_series = calculate_ratio_percentile(merged_data['ratio'], pct_window)
    # 注：比值百分位用历史收盘价（不纳入盘中实时修正），组合策略已降级，
    # 此处仅影响信号强度标签展示，不影响交易信号（交易信号仅依赖动量百分位）
    ratio_pct_today = ratio_pct_series.iloc[-1] if not pd.isna(ratio_pct_series.iloc[-1]) else None

    # 信号强度（低位买cy=强信号, 高位买hl=强信号）
    if ratio_pct_today is not None:
        low_pct = STRATEGY_CONFIG['low_percentile']
        high_pct = STRATEGY_CONFIG['high_percentile']
        if new_state == 'cy' and ratio_pct_today <= low_pct:
            signal_strength = "🔥 强信号（低位买创业板）"
        elif new_state == 'hl' and ratio_pct_today >= high_pct:
            signal_strength = "🔥 强信号（高位买红利）"
        elif new_state != 'cash':
            signal_strength = "📊 普通信号"
        else:
            signal_strength = "⚪ 空仓"
    else:
        signal_strength = "数据不足"

    # 指标卡片
    st.markdown('<div class="metric-group">', unsafe_allow_html=True)
    st.markdown('<div class="metric-group-title">核心动量指标</div>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "创业板动量（平滑）",
            f"{cy_mom_today:+.2%}",
            delta=f"昨日 {cy_mom_hist:+.2%}" if not pd.isna(cy_mom_hist) else None,
            help=f"多窗口平滑：{momentum_windows}天动量均值"
        )
    with col2:
        st.metric(
            "红利动量（平滑）",
            f"{hl_mom_today:+.2%}",
            delta=f"昨日 {hl_mom_hist:+.2%}" if not pd.isna(hl_mom_hist) else None,
            help=f"多窗口平滑：{momentum_windows}天动量均值"
        )
    with col3:
        st.metric("状态", f"{display['emoji']} {display['signal']}")

    # 各窗口动量明细
    detail_cols = st.columns(len(momentum_windows))
    for idx, w in enumerate(momentum_windows):
        if n > w:
            cy_w = (cy_close_today / merged_data['close_cy'].iloc[-w]) - 1
            hl_w = (hl_close_today / merged_data['close_hl'].iloc[-w]) - 1
        else:
            cy_w = hl_w = None
        with detail_cols[idx]:
            if cy_w is not None:
                st.caption(f"**{w}天**: 创业板 {cy_w:+.2%} | 红利 {hl_w:+.2%}")
    st.markdown('</div>', unsafe_allow_html=True)

    # 百分位指标
    st.markdown('<div class="metric-group">', unsafe_allow_html=True)
    st.markdown('<div class="metric-group-title">📈 历史百分位（越高=越强/越贵）</div>', unsafe_allow_html=True)
    pct1, pct2, pct3 = st.columns(3)
    with pct1:
        st.metric(
            "创业板动量百分位",
            f"{cy_mom_pct_today:.0%}" if cy_mom_pct_today is not None else "N/A",
            help=f"创业板动量在过去 {mom_pct_window} 天中的位置"
        )
    with pct2:
        st.metric(
            "红利动量百分位",
            f"{hl_mom_pct_today:.0%}" if hl_mom_pct_today is not None else "N/A",
            help=f"红利动量在过去 {mom_pct_window} 天中的位置"
        )
    with pct3:
        st.metric(
            "比值百分位",
            f"{ratio_pct_today:.0%}" if ratio_pct_today is not None else "N/A",
            help=f"创业板/红利比值在过去 {pct_window} 天中的位置"
        )
    st.markdown('</div>', unsafe_allow_html=True)

    # 信号强度 + 波动率仓位
    scale_col, info_col = st.columns([2, 1])
    with scale_col:
        # 信号强度徽章
        if '强信号' in signal_strength:
            badge_cls = 'strong'
        elif '空仓' in signal_strength or '数据不足' in signal_strength:
            badge_cls = 'empty'
        else:
            badge_cls = 'normal'
        st.markdown(f'<span class="strength-badge {badge_cls}">{signal_strength}</span>', unsafe_allow_html=True)
    with info_col:
        if new_state != 'cash':
            st.caption(f"波动率仓位：**{vol_scale:.0%}**（目标 {target_vol:.0%} / 实现波动率）")
        elif decay_exit_triggered:
            st.caption("⚠️ 衰减退出已触发")

    # 信号卡片
    card_cls = 'cy' if new_state == 'cy' else ('hl' if new_state == 'hl' else 'cash')
    st.markdown(f"""
    <div class="signal-card {card_cls}">
        <div class="signal-title">{display['emoji']} {display['signal']}</div>
        <p class="signal-desc">{display['description']}<br><strong>操作建议：</strong>{display['action']}</p>
    </div>
    """, unsafe_allow_html=True)

    # 估值状态展示
    if apply_pe_filter_flag:
        st.markdown('<div class="section-title">📊 估值状态</div>', unsafe_allow_html=True)
        val_col1, val_col2 = st.columns(2)

        with val_col1:
            if cy_pe_pct_today is not None:
                # 估值状态标签
                if cy_pe_pct_today < 0.30:
                    pe_status = "🟢 低估"
                    status_color = "green"
                elif cy_pe_pct_today < 0.70:
                    pe_status = "🟡 适中"
                    status_color = "orange"
                else:
                    pe_status = "🔴 高估"
                    status_color = "red"

                st.metric(
                    label=f"创业板 PE {pe_status}",
                    value=f"{cy_pe_value:.2f}" if cy_pe_value is not None else "N/A",
                    help=f"PE 百分位: {cy_pe_pct_today:.1%} (阈值: {pe_threshold:.0%})"
                )
            else:
                st.metric(label="创业板 PE", value="数据不足")

        with val_col2:
            if hl_pe_pct_today is not None:
                if hl_pe_pct_today < 0.30:
                    pe_status = "🟢 低估"
                    status_color = "green"
                elif hl_pe_pct_today < 0.70:
                    pe_status = "🟡 适中"
                    status_color = "orange"
                else:
                    pe_status = "🔴 高估"
                    status_color = "red"

                st.metric(
                    label=f"红利 PE {pe_status}",
                    value=f"{hl_pe_value:.2f}" if hl_pe_value is not None else "N/A",
                    help=f"PE 百分位: {hl_pe_pct_today:.1%} (阈值: {pe_threshold:.0%})"
                )
            else:
                st.metric(label="红利 PE", value="数据不足")

        # 估值过滤提示
        if pe_filter_triggered:
            st.info(f"⚠️ 估值过滤已启用：PE 百分位 > {pe_threshold:.0%} 的指数不会被推荐买入")

    # 策略说明
    with st.expander("📖 策略说明"):
        st.markdown(f"""
        **双动量策略**（多窗口平滑: {momentum_windows}天，无风险利率: {STRATEGY_CONFIG['risk_free_rate']:.1%}/年）
        - 🔵 **买入创业板**：创业板平滑动量 > 红利平滑动量 且 > {rf_period:.2%}（{window}天无门槛收益）
        - 🟠 **买入红利**：红利平滑动量 > 创业板平滑动量 且 > {rf_period:.2%}
        - ⚪ **空仓观望**：两者平滑动量均为负
        - 📊 **平滑方式**：取 {momentum_windows} 天动量的均值，减少单一窗口因基准价跳变导致的信号不稳定
        - 🛡️ **动量衰竭退出**：持仓标的动量百分位 < {decay_threshold:.0%} 时强制空仓（阈值 {decay_threshold:.0%}）
        - 📉 **波动率目标仓位**：目标年化波动率 {target_vol:.0%}，回看 {vol_lookback} 天实现波动率，仓位 = min(目标/实现, 100%)
        - 💰 **估值过滤**：当推荐买入的指数 PE 百分位 > {pe_threshold:.0%} 时，改为空仓（避免高估追涨）
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

    # 计算百分位
    pct_window = STRATEGY_CONFIG['percentile_window']
    ratio_pct = calculate_ratio_percentile(ratio, pct_window)

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        vertical_spacing=0.03,
                        row_heights=[0.45, 0.30, 0.25])

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

    # 百分位区域着色（上图背景，按时间轴分段）
    low_pct = STRATEGY_CONFIG['low_percentile']
    high_pct = STRATEGY_CONFIG['high_percentile']
    zone_colors = {'low': 'rgba(0,128,0,0.08)', 'mid': 'rgba(128,128,128,0.05)',
                   'high': 'rgba(255,0,0,0.08)'}

    dates_arr = merged_data['date'].values
    pct_arr = ratio_pct.values

    # 找连续同 zone 的段
    prev_zone = None
    zone_start_idx = None
    for i in range(len(pct_arr)):
        if pd.isna(pct_arr[i]):
            if prev_zone is not None:
                fig.add_vrect(x0=dates_arr[zone_start_idx], x1=dates_arr[i - 1],
                              fillcolor=zone_colors[prev_zone], line_width=0,
                              layer="below", row=1, col=1)
                prev_zone = None
            continue
        zone = 'low' if pct_arr[i] <= low_pct else ('high' if pct_arr[i] >= high_pct else 'mid')
        if zone != prev_zone:
            if prev_zone is not None:
                fig.add_vrect(x0=dates_arr[zone_start_idx], x1=dates_arr[i - 1],
                              fillcolor=zone_colors[prev_zone], line_width=0,
                              layer="below", row=1, col=1)
            zone_start_idx = i
            prev_zone = zone
    if prev_zone is not None:
        fig.add_vrect(x0=dates_arr[zone_start_idx], x1=dates_arr[-1],
                      fillcolor=zone_colors[prev_zone], line_width=0,
                      layer="below", row=1, col=1)

    # 中图：动量对比（平滑）
    cy_mom = calculate_smoothed_momentum(merged_data['close_cy'])
    hl_mom = calculate_smoothed_momentum(merged_data['close_hl'])

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

    # 下图：百分位走势
    mom_pct_window = STRATEGY_CONFIG['momentum_percentile_window']
    cy_mom_pct = calculate_momentum_percentile(cy_mom, mom_pct_window)
    hl_mom_pct = calculate_momentum_percentile(hl_mom, mom_pct_window)

    fig.add_trace(go.Scattergl(
        x=merged_data['date'], y=ratio_pct,
        mode='lines', name='比值百分位',
        line=dict(color='purple', width=1.5)
    ), row=3, col=1)
    fig.add_trace(go.Scattergl(
        x=merged_data['date'], y=cy_mom_pct,
        mode='lines', name='创业板动量百分位',
        line=dict(color='blue', width=1, dash='dot')
    ), row=3, col=1)
    fig.add_trace(go.Scattergl(
        x=merged_data['date'], y=hl_mom_pct,
        mode='lines', name='红利动量百分位',
        line=dict(color='orange', width=1, dash='dot')
    ), row=3, col=1)

    # 百分位阈值线
    fig.add_hline(y=low_pct, line_dash='dash', line_color='green', line_width=0.8, row=3, col=1)
    fig.add_hline(y=high_pct, line_dash='dash', line_color='red', line_width=0.8, row=3, col=1)
    fig.add_hline(y=0.5, line_dash='dot', line_color='gray', line_width=0.5, row=3, col=1)

    fig.update_xaxes(title_text="日期", row=3, col=1)
    fig.update_yaxes(title_text="比值", row=1, col=1)
    fig.update_yaxes(title_text="动量", row=2, col=1)
    fig.update_yaxes(title_text="百分位", range=[0, 1], row=3, col=1)

    # 统一样式
    fig.update_layout(
        height=700,
        hovermode='x unified',
        legend=dict(orientation='h', y=1.06, x=0.5, xanchor='center',
                    font=dict(size=11)),
        plot_bgcolor='rgba(250,250,250,0.8)',
        paper_bgcolor='white',
        margin=dict(l=60, r=30, t=50, b=40),
        font=dict(family="-apple-system, BlinkMacSystemFont, sans-serif"),
    )
    # 网格线
    for row_i in range(1, 4):
        fig.update_xaxes(gridcolor='rgba(0,0,0,0.05)', gridwidth=1, row=row_i, col=1)
        fig.update_yaxes(gridcolor='rgba(0,0,0,0.05)', gridwidth=1, row=row_i, col=1)

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
    fig.update_layout(
        height=400,
        hovermode='x unified',
        plot_bgcolor='rgba(250,250,250,0.8)',
        paper_bgcolor='white',
        margin=dict(l=60, r=60, t=30, b=40),
        font=dict(family="-apple-system, BlinkMacSystemFont, sans-serif"),
        legend=dict(orientation='h', y=1.08, x=0.5, xanchor='center'),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_backtest_tab(merged_data: pd.DataFrame):
    st.markdown('<div class="section-title">📊 回测配置</div>', unsafe_allow_html=True)
    with st.form("backtest_form"):
        st.markdown("**当前策略**：纯动量策略（多窗口平滑 + 冷却期 + 动量衰竭退出）")
        compare = st.checkbox("显示详细对比", value=False, help="显示与历史基准的对比")
        st.markdown("**风控机制**（默认启用，与实时信号对齐）")
        col_a, col_b = st.columns(2)
        with col_a:
            use_decay_exit = st.checkbox("动量衰竭退出", value=True,
                help="持仓标的动量百分位 < 20% 时强制空仓")
        with col_b:
            use_vol_target = st.checkbox("波动率目标仓位", value=True,
                help=f"目标年化波动率 {STRATEGY_CONFIG.get('target_vol', 0.14):.0%}，回看 {STRATEGY_CONFIG.get('vol_lookback', 60)} 天")
        st.markdown("点击按钮开始回测（可能需要几秒钟）")
        submitted = st.form_submit_button("🚀 开始回测")

    if submitted:
        with st.spinner("正在计算回测..."):
            backtest_result = run_backtest(merged_data,
                apply_decay_exit=use_decay_exit, apply_vol_target=use_vol_target)
            stats = calculate_statistics(backtest_result)

        _render_backtest_metrics(stats)
        _render_position_distribution(backtest_result)
        st.subheader("策略累计收益曲线")
        render_nav_chart(backtest_result)

        st.subheader("信号切换记录")
        render_signal_table(backtest_result)


def _render_backtest_metrics(stats: dict):
    """渲染回测统计指标"""
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

    col6, col7, col8 = st.columns(3)
    with col6:
        st.metric("交易胜率", f"{stats['trade_win_rate']:.2%}",
                  help="按持仓期统计，每次开平仓算一次交易")
    with col7:
        st.metric("切换次数", f"{stats['trade_count']}次",
                  help="仓位切换次数（含首次建仓）")
    with col8:
        avg_cost = stats['trade_count'] * 0.001
        st.metric("累计成本", f"{avg_cost:.2%}",
                  help="交易成本估算（单边0.1%×切换次数）")


def _render_position_distribution(backtest_result: pd.DataFrame):
    """渲染持仓分布"""
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
        hovermode='x unified', height=400,
        plot_bgcolor='rgba(250,250,250,0.8)',
        paper_bgcolor='white',
        margin=dict(l=60, r=30, t=30, b=40),
        font=dict(family="-apple-system, BlinkMacSystemFont, sans-serif"),
        legend=dict(orientation='h', y=1.1, x=0.5, xanchor='center'),
    )
    fig.update_traces(connectgaps=True)
    st.plotly_chart(fig, use_container_width=True)


def render_signal_table(backtest_result: pd.DataFrame):
    """显示信号切换记录"""
    pos = backtest_result['position'].fillna(0)
    changes = pos.diff().fillna(pos)
    switch_mask = changes != 0
    signals = backtest_result[switch_mask].copy()

    if signals.empty:
        st.info("回测期间无信号切换")
        return

    cols = ['date', 'position', 'ratio', 'cy_momentum', 'hl_momentum']
    if 'signal_strength' in signals.columns:
        cols.append('signal_strength')
    display_df = signals[cols].copy()

    display_df['date'] = display_df['date'].dt.strftime('%Y-%m-%d')
    display_df['ratio'] = display_df['ratio'].apply(lambda x: f"{x:.4f}")
    display_df['cy_momentum'] = display_df['cy_momentum'].apply(lambda x: f"{x:+.2%}" if pd.notna(x) else '-')
    display_df['hl_momentum'] = display_df['hl_momentum'].apply(lambda x: f"{x:+.2%}" if pd.notna(x) else '-')
    display_df['position'] = display_df['position'].map({
        1.0: '🔵 创业板', -1.0: '🟠 红利', 0.0: '⚪ 空仓'
    })
    if 'signal_strength' in display_df.columns:
        display_df['signal_strength'] = display_df['signal_strength'].map({
            '强信号': '🔥 强信号', '普通': '📊 普通', '空仓': '⚪ 空仓'
        })
        col_names = ['日期', '切换至', '比值', '创业板动量', '红利动量', '信号强度']
    else:
        col_names = ['日期', '切换至', '比值', '创业板动量', '红利动量']
    display_df.columns = col_names
    st.dataframe(display_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
