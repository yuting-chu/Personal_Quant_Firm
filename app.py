import streamlit as st
import os
from datetime import datetime
from dotenv import load_dotenv
from modules.database import get_trade_logs, get_today_realized_pnl

import importlib
import modules.ai_engine
import modules.time_utils
import modules.ibkr_engine
from modules.ibkr_engine import get_ibkr_engine
from modules.time_utils import get_dual_clock_str
from views import (
    tab_daemon,
    tab_macro,
    tab_industry,
    tab_backtest,
    tab_risk,
    tab_audit
)

# 強制動態熱重載 (Hot-Reloading)，確保磁碟上的最新 AI 模型與指標邏輯即時生效，不被 Python 記憶體快取鎖定
importlib.reload(modules.ai_engine)
importlib.reload(modules.time_utils)
importlib.reload(modules.ibkr_engine)
importlib.reload(tab_daemon)
importlib.reload(tab_macro)
importlib.reload(tab_industry)
importlib.reload(tab_backtest)
importlib.reload(tab_risk)
importlib.reload(tab_audit)

load_dotenv()

# ==========================================
# 1. 全域設定與 Sticky Tab 樣式注入
# ==========================================
st.set_page_config(
    page_title="Personal Quant Office | 旗艦戰情中心",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    div[data-testid="stTabs"] > div:first-child {
        position: sticky;
        top: 2.875rem;
        background-color: var(--background-color, #ffffff);
        z-index: 999;
        padding-top: 8px;
        padding-bottom: 8px;
        border-bottom: 1px solid rgba(128, 128, 128, 0.2);
    }
    button[data-baseweb="tab"] {
        font-size: 15px !important;
        font-weight: 600 !important;
        padding: 6px 14px !important;
    }
</style>
""", unsafe_allow_html=True)

if 'strategies' not in st.session_state:
    st.session_state['strategies'] = [
        {
            "id": 1,
            "name": "Hedged Carry Trade (USD/JPY)",
            "type": "核心對衝",
            "weight": 50,
            "logic": "做多 USD、放空 JPY 賺取息差，搭配 20MA 硬停損與 OTM Put 防範政策干預閃崩。",
            "active": True
        },
        {
            "id": 2,
            "name": "Delta-Neutral Options (SPY)",
            "type": "核心對衝",
            "weight": 20,
            "logic": "雙賣 SPY 跨式/垂直價差收割 Theta，動態調整現貨使 Delta 中性，DTE<10 天平倉滾動。",
            "active": True
        },
        {
            "id": 3,
            "name": "Volatility Arbitrage (VRP)",
            "type": "核心對衝",
            "weight": 5,
            "logic": "做空 IV - HV 波動率溢價，VIX < 13 時自動縮小開倉部位。",
            "active": True
        },
        {
            "id": 4,
            "name": "Pair Trading (AUD vs NZD)",
            "type": "統計套利",
            "weight": 0,
            "logic": "基於 AUD/USD 與 NZD/USD 滾動 OLS 與 Z-score 均值回歸套利。",
            "active": False
        }
    ]

# ==========================================
# 2. 側邊欄控制中心 (Sidebar Command Center)
# ==========================================
with st.sidebar:
    st.title("🏛️ 個人投資公司")
    st.caption("Personal Quant Firm OS v5.0")
    st.markdown("---")

    st.subheader("💰 資本配置控制台")
    default_cap = int(st.session_state.get('synced_ib_capital', 1000000))
    total_capital = st.number_input("總本金規模 (USD)：", min_value=10000, max_value=100000000, value=default_cap, step=50000)

    core_alloc = st.slider("75% 核心量化對衝 (%)", 50, 90, 75, 5)
    satellite_alloc = 100 - core_alloc
    st.caption(f"• 主觀高凸性衛星: **{satellite_alloc}%** (`${total_capital * (satellite_alloc/100):,.0f} USD`)")

    st.markdown("---")
    st.subheader("🛡️ 全域風控模式")
    risk_mode = st.selectbox(
        "模式切換：",
        [
            "🟢 標準收租",
            "🟡 謹慎防禦",
            "🔴 極限熔斷 (Risk-Off)",
            "⚡ Prop Firm 考核模式 (Max DD 4.0%, Daily 1.5%)"
        ],
        index=0
    )

    st.markdown("---")
    st.subheader("📡 IBKR 模擬交易連線 (TWS)")
    col_ib1, col_ib2 = st.columns([1, 1])
    with col_ib1:
        btn_check_ib = st.button("🔌 檢測連線", use_container_width=True)
    with col_ib2:
        btn_sync_cap = st.button("🔄 同步資金", use_container_width=True)

    engine = get_ibkr_engine(port=7497, client_id=10)
    ib_summary = engine.get_account_summary()
    st.session_state["ib_summary"] = ib_summary

    if ib_summary.get("is_connected"):
        st.markdown(
            f"""
            <div style="background-color: rgba(16, 185, 129, 0.12); border-left: 4px solid #10b981; padding: 10px; border-radius: 6px; font-size: 12px; line-height: 1.5;">
                <b>🟢 TWS 模擬帳戶已連線</b><br>
                • 帳號：<code>{ib_summary['account_id']}</code><br>
                • 即時淨資產：<b>${ib_summary['net_liquidation']:,.0f} USD</b><br>
                • 總購買力：<b>${ib_summary['buying_power']:,.0f} USD</b>
            </div>
            """,
            unsafe_allow_html=True
        )
        if btn_sync_cap:
            st.session_state['synced_ib_capital'] = int(ib_summary['net_liquidation'])
            st.rerun()
    else:
        st.markdown(
            """
            <div style="background-color: rgba(239, 68, 68, 0.08); border-left: 4px solid #ef4444; padding: 10px; border-radius: 6px; font-size: 12px;">
                <b>⚪ TWS 尚未連線</b><br>
                請確認 TWS 已開啟並啟用 Socket API (Port 7497)
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("---")
    with st.expander("🔑 系統 API 金鑰與連線設定", expanded=False):
        loaded_gemini_key = os.getenv("GEMINI_API_KEY", "")
        if not loaded_gemini_key:
            try:
                loaded_gemini_key = st.secrets.get("GEMINI_API_KEY", "")
            except Exception:
                pass
        has_gemini = bool(loaded_gemini_key)
        user_gemini_key = st.text_input(
            "Gemini API Key：",
            type="password",
            placeholder="● 已由後端安全載入 (金鑰已隱藏保護)" if has_gemini else "未檢測到金鑰，請手動輸入",
            help="系統已由後端環境變數或 Secrets 自動安全注入，外部造訪者無法透過 F12 檢視您的真實金鑰。" if has_gemini else "請輸入您的 Gemini API Key"
        )
        api_key = user_gemini_key.strip() if user_gemini_key.strip() else loaded_gemini_key

        loaded_fred_key = os.getenv("FRED_API_KEY", "")
        if not loaded_fred_key:
            try:
                loaded_fred_key = st.secrets.get("FRED_API_KEY", "")
            except Exception:
                pass
        has_fred = bool(loaded_fred_key)
        user_fred_key = st.text_input(
            "FRED API Key：",
            type="password",
            placeholder="● 已由後端安全載入 (金鑰已隱藏保護)" if has_fred else "未檢測到金鑰，請手動輸入",
            help="系統已由後端環境變數或 Secrets 自動安全注入，外部造訪者無法透過 F12 檢視您的真實金鑰。" if has_fred else "請輸入您的 FRED API Key"
        )
        fred_key = user_fred_key.strip() if user_fred_key.strip() else loaded_fred_key
        st.session_state['fred_key'] = fred_key

        st.selectbox("交易環境：", ["IBKR TWS 模擬交易 (Port 7497)", "IG Group CFD (Live)"])
        if st.button("🔄 清除快取並重新整理行情"):
            st.cache_data.clear()
            st.rerun()

    st.markdown("---")
    tpe_clock, nyc_clock = get_dual_clock_str()
    st.markdown(
        f'''
        <div style="font-size: 11px; color: #a0aec0; background-color: #1a1d24; padding: 10px; border-radius: 6px; border: 1px solid #2d3748; line-height: 1.6;">
            <div>🇹🇼 <b>台北時間 (HQ)</b>:<br><code style="color: #63b3ed;">{tpe_clock}</code></div>
            <div style="margin-top: 6px;">🇺🇸 <b>美東時間 (ET)</b>:<br><code style="color: #ecc94b;">{nyc_clock}</code></div>
        </div>
        ''',
        unsafe_allow_html=True
    )

# ==========================================
# 3. 頂部動態資產戰情看板與回撤熔斷檢查
# ==========================================
# 熔斷機制接真實資料：從 quant_firm.db 撈今日已實現損益
today_realized_pnl = get_today_realized_pnl()
current_nav = total_capital + today_realized_pnl

if 'peak_nav' not in st.session_state:
    st.session_state['peak_nav'] = float(current_nav)
else:
    if current_nav > st.session_state['peak_nav']:
        st.session_state['peak_nav'] = float(current_nav)

peak_nav = st.session_state['peak_nav']

daily_drawdown_pct = round((today_realized_pnl / total_capital) * 100, 2) if total_capital else 0.0
trailing_dd_dollars = max(peak_nav - current_nav, 0.0)
trailing_dd_pct = (trailing_dd_dollars / peak_nav * 100.0) if peak_nav > 0 else 0.0

is_prop_mode = "Prop Firm" in risk_mode
max_drawdown_limit = -1.50  # 單日最大虧損限額 (DLL)
max_trailing_limit = 4.00   # Prop Firm 動態回撤上限 (MTD)

# Prop Firm 動態爆倉警戒線 (High-Water Mark - 4.0%)
prop_breach_line = peak_nav * (1.0 - (max_trailing_limit / 100.0))
buffer_to_breach_dollars = current_nav - prop_breach_line
buffer_to_breach_pct = (buffer_to_breach_dollars / peak_nav * 100.0) if peak_nav > 0 else 0.0

if is_prop_mode:
    if trailing_dd_pct >= max_trailing_limit:
        st.error(
            f"🚨 **【觸發 Prop Firm 最大動態回撤爆倉硬熔斷】** 當前高水位回撤達 {trailing_dd_pct:.2f}% (超過上限 {max_trailing_limit}%)！"
            f"資產已跌破違規警戒線 (${prop_breach_line:,.0f} USD)，帳號立即停權，請立刻終止所有交易！"
        )
    elif daily_drawdown_pct <= max_drawdown_limit:
        st.error(
            f"🚨 **【觸發 Prop Firm 單日最大虧損熔斷 (DLL)】** 今日累計虧損已達 {daily_drawdown_pct}% (超過單日上限 {max_drawdown_limit}%)！"
            f"今日嚴禁再開立任何新倉位！"
        )
else:
    if daily_drawdown_pct <= max_drawdown_limit:
        st.error(f"🚨 **【觸發單日回撤硬熔斷】** 今日累計回撤已達 {daily_drawdown_pct}% (超過上限 {max_drawdown_limit}%)！請立即停止所有 25% 衛星部位交易！")

# 保證金佔用率隨風控模式變動，這組數字會原封不動傳給 tab_risk，避免兩個分頁各自寫死
est_margin_ratio = 18.5 if is_prop_mode else (30.9 if "標準" in risk_mode else (22.5 if "謹慎" in risk_mode else 12.0))
est_margin_used = total_capital * (est_margin_ratio / 100)
est_theta = round(total_capital * 0.000485, 2)

st.markdown("## 📊 總體資產戰情室 (CIO & Risk Dashboard)")

if is_prop_mode:
    col_nav, col_peak, col_buffer, col_daily, col_margin = st.columns([1.2, 1.2, 1.3, 1.2, 1.1])
    with col_nav:
        pnl_pct = (today_realized_pnl / total_capital * 100) if total_capital else 0.0
        st.metric("當前資產 (Current NAV)", f"${current_nav:,.0f}", f"{today_realized_pnl:+,.0f} ({pnl_pct:+.2f}%) 今日已實現")
    with col_peak:
        st.metric("歷史最高水線 (Peak NAV)", f"${peak_nav:,.0f}", f"動態回撤: -{trailing_dd_pct:.2f}%")
    with col_buffer:
        b_color = "🟢 安全" if buffer_to_breach_pct >= 2.0 else ("🟡 警戒" if buffer_to_breach_pct >= 1.0 else "🔴 瀕臨違規")
        st.metric(f"距離爆倉線緩衝 ({b_color})", f"${buffer_to_breach_dollars:,.0f}", f"違規線: ${prop_breach_line:,.0f} ({buffer_to_breach_pct:.2f}%)", delta_color="normal")
    with col_daily:
        st.metric("今日虧損 / DLL 上限", f"{daily_drawdown_pct}%", f"單日上限 {max_drawdown_limit}%", delta_color="normal")
    with col_margin:
        m_color = "🟢 安全" if est_margin_ratio < 40 else "🟡 警戒"
        st.metric(f"保證金佔用 ({m_color})", f"${est_margin_used:,.0f} ({est_margin_ratio}%)", "上限 55.0%", delta_color="inverse")
else:
    col_nav, col_margin, col_greeks, col_risk = st.columns([1.2, 1.2, 1.4, 1.2])
    with col_nav:
        pnl_pct = (today_realized_pnl / total_capital * 100) if total_capital else 0.0
        st.metric("總資產淨值 (NAV)", f"${total_capital:,.0f}", f"{today_realized_pnl:+,.0f} ({pnl_pct:+.2f}%) 今日已實現")
    with col_margin:
        m_color = "🟢 安全" if est_margin_ratio < 40 else "🟡 警戒"
        st.metric(f"保證金佔用 ({m_color})", f"${est_margin_used:,.0f} ({est_margin_ratio}%)", "上限 55.0%", delta_color="inverse")
    with col_greeks:
        st.metric("組合 Greeks", f"Δ -0.04 | +${est_theta:,.0f}/日", "Vega: -$120/點")
    with col_risk:
        st.metric("今日回撤 / 預算上限", f"{daily_drawdown_pct}%", f"上限 {max_drawdown_limit}%", delta_color="normal")

st.markdown("---")

# ==========================================
# 4. 六大部門分頁路由 (新增全自動交易與研報看板)
# ==========================================
tab_d, tab_m, tab_i, tab_b, tab_r, tab_a = st.tabs([
    "🤖 全自動交易看板",
    "🌍 總經戰情室",
    "🏭 產業研究與個股圖表",
    "🧪 策略管理與執行指令",
    "🛡️ 風控與壓力測試",
    "📝 稽核覆盤與 AI 投委會"
])

with tab_d:
    tab_daemon.render(api_key)

with tab_m:
    tab_macro.render(api_key)

with tab_i:
    tab_industry.render(api_key)

with tab_b:
    tab_backtest.render(total_capital, api_key)

with tab_r:
    tab_risk.render(total_capital, api_key, est_margin_ratio, est_margin_used, risk_mode=risk_mode, peak_nav=peak_nav)

with tab_a:
    tab_audit.render(total_capital, api_key)