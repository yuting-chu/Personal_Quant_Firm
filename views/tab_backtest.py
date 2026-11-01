import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.express as px
import google.generativeai as genai
from datetime import datetime, date

def calculate_quant_metrics(nav_series: pd.Series, rf=0.02):
    daily_ret = nav_series.pct_change().dropna()
    if len(daily_ret) == 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    
    total_days = (nav_series.index[-1] - nav_series.index[0]).days
    years = max(total_days / 365.25, 0.1)
    
    cagr = ((nav_series.iloc[-1] / nav_series.iloc[0]) ** (1 / years) - 1) * 100
    ann_vol = daily_ret.std() * np.sqrt(252) * 100
    excess_ret = (cagr / 100) - rf
    sharpe = excess_ret / (ann_vol / 100) if ann_vol > 0 else 0.0
    cum_max = nav_series.cummax()
    drawdown = (nav_series - cum_max) / cum_max
    mdd = drawdown.min() * 100
    calmar = (cagr / abs(mdd)) if abs(mdd) > 0 else 0.0
    
    return cagr, ann_vol, sharpe, mdd, calmar

def render(total_capital: float, api_key: str):
    st.subheader("🧪 策略管理、動態執行指令與機構級回測引擎")
    st.caption("內建條件驅動進出場邏輯（20MA/Bollinger/Z-Score）+ 交易摩擦成本與滑價模型。")

    # 1. 交易執行部即時指令
    st.markdown("#### ⚡ 交易執行部：即時市場狀態與操作指令 (Live Computed Signals)")
    
    with st.spinner("拉取即時指標..."):
        try:
            live_fx = yf.download("JPY=X", period="2mo", interval="1d", progress=False)
            fx_close = live_fx['Close'].iloc[:, 0] if isinstance(live_fx.columns, pd.MultiIndex) else live_fx['Close']
            cur_usdjpy = float(fx_close.iloc[-1])
            ma20_usdjpy = float(fx_close.rolling(20).mean().iloc[-1])
            usdjpy_status = "ABOVE_20MA" if cur_usdjpy >= ma20_usdjpy else "BELOW_20MA"
        except Exception:
            cur_usdjpy, ma20_usdjpy, usdjpy_status = 155.0, 153.0, "ABOVE_20MA"

        try:
            live_vix = yf.download("^VIX", period="5d", interval="1d", progress=False)
            vix_c = live_vix['Close'].iloc[:, 0] if isinstance(live_vix.columns, pd.MultiIndex) else live_vix['Close']
            cur_vix = float(vix_c.iloc[-1])
        except Exception:
            cur_vix = 14.2

    today = date.today()
    target_expiry = date(today.year, today.month, 18) if today.day <= 18 else (date(today.year, today.month+1, 18) if today.month < 12 else date(today.year+1, 1, 18))
    live_dte = (target_expiry - today).days

    c_sig1, c_sig2, c_sig3, c_sig4 = st.columns(4)
    with c_sig1:
        if usdjpy_status == "ABOVE_20MA":
            st.markdown(f"<div style='background-color:#1a1d28;padding:10px;border-radius:6px;border-left:4px solid #00cc96;'><div style='font-size:11px;color:#888;'>Hedged Carry (USD/JPY)</div><div style='font-weight:bold;color:#00cc96;'>🟢 持倉收息 ({cur_usdjpy:.2f})</div><div style='font-size:11px;'>高於 20MA ({ma20_usdjpy:.2f})</div></div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='background-color:#1a1d28;padding:10px;border-radius:6px;border-left:4px solid #ff4b4b;'><div style='font-size:11px;color:#888;'>Hedged Carry (USD/JPY)</div><div style='font-weight:bold;color:#ff4b4b;'>🔴 觸發停損 ({cur_usdjpy:.2f})</div><div style='font-size:11px;'>跌破 20MA，避險對衝！</div></div>", unsafe_allow_html=True)

    with c_sig2:
        if live_dte <= 10:
            st.markdown(f"<div style='background-color:#1a1d28;padding:10px;border-radius:6px;border-left:4px solid #ff4b4b;'><div style='font-size:11px;color:#888;'>SPY Options</div><div style='font-weight:bold;color:#ff4b4b;'>🔴 執行換約 (DTE: {live_dte}天)</div><div style='font-size:11px;'>Gamma 上升，平倉滾動</div></div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='background-color:#1a1d28;padding:10px;border-radius:6px;border-left:4px solid #00cc96;'><div style='font-size:11px;color:#888;'>SPY Options</div><div style='font-weight:bold;color:#00cc96;'>🟢 正常收 Theta (DTE: {live_dte}天)</div><div style='font-size:11px;'>維持 Delta 中性</div></div>", unsafe_allow_html=True)

    with c_sig3:
        if cur_vix < 13.0:
            st.markdown(f"<div style='background-color:#1a1d28;padding:10px;border-radius:6px;border-left:4px solid #ffaa00;'><div style='font-size:11px;color:#888;'>VRP Arbitrage</div><div style='font-weight:bold;color:#ffaa00;'>🟡 觀望空倉 (VIX: {cur_vix:.2f})</div><div style='font-size:11px;'>溢價薄弱，不建倉</div></div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='background-color:#1a1d28;padding:10px;border-radius:6px;border-left:4px solid #00cc96;'><div style='font-size:11px;color:#888;'>VRP Arbitrage</div><div style='font-weight:bold;color:#00cc96;'>🟢 正常收溢價 (VIX: {cur_vix:.2f})</div><div style='font-size:11px;'>IV 溢價空間充沛</div></div>", unsafe_allow_html=True)

    with c_sig4:
        st.markdown("<div style='background-color:#1a1d28;padding:10px;border-radius:6px;border-left:4px solid #636efa;'><div style='font-size:11px;color:#888;'>25% 衛星部位</div><div style='font-weight:bold;color:#636efa;'>🔵 高凸性佈局</div><div style='font-size:11px;'>產業動量逢回佈局</div></div>", unsafe_allow_html=True)

    st.markdown("---")

    # 2. 策略管理
    with st.expander("🛠️ 管理/修改策略權重與邏輯，或新增自訂策略", expanded=False):
        col_list, col_add = st.columns([3, 2])
        with col_list:
            for idx, strat in enumerate(st.session_state['strategies']):
                c_act, c_name, c_wt, c_del = st.columns([1, 4, 2, 1])
                strat['active'] = c_act.checkbox("啟用", value=strat['active'], key=f"act_{strat['id']}")
                strat['name'] = c_name.text_input("策略名稱", value=strat['name'], key=f"name_{strat['id']}")
                strat['weight'] = c_wt.number_input("權重 (%)", min_value=0, max_value=100, value=strat['weight'], key=f"wt_{strat['id']}")
                if c_del.button("🗑️", key=f"del_{strat['id']}"):
                    st.session_state['strategies'].pop(idx)
                    st.rerun()
        with col_add:
            with st.form("add_strat_form"):
                new_name = st.text_input("策略名稱", "黃金總經動量對衝")
                new_type = st.selectbox("類型", ["核心對衝", "高凸性衛星", "統計套利"])
                new_weight = st.number_input("權重 (%)", min_value=0, max_value=100, value=10)
                new_logic = st.text_area("策略邏輯", "根據美國實質利率 (TIPS) 與美元指數建立部位。")
                if st.form_submit_button("新增至策略庫"):
                    new_id = max([s['id'] for s in st.session_state['strategies']]) + 1 if st.session_state['strategies'] else 1
                    st.session_state['strategies'].append({"id": new_id, "name": new_name, "type": new_type, "weight": new_weight, "logic": new_logic, "active": True})
                    st.rerun()

    st.markdown("---")

    # 3. 條件回測引擎
    st.markdown("#### 🚀 機構級條件回測引擎 (含進出場、停損與交易摩擦模型)")
    col_bt_params, col_bt_chart = st.columns([1, 3])
    
    with col_bt_params:
        bt_start = st.date_input("開始日期", pd.to_datetime("2023-01-01"))
        bt_end = st.date_input("結束日期", pd.to_datetime("2025-12-31"))
        
        st.markdown("##### ⚙️ 交易摩擦成本設定")
        slippage_bps = st.number_input("調倉滑價 (bps)", min_value=0, max_value=50, value=5, help="5 bps = 0.05%")
        fee_rate = st.number_input("每筆交易成本 (%)", min_value=0.0, max_value=0.5, value=0.02, step=0.01)
        
        run_bt = st.button("🚀 執行向量化回測", use_container_width=True)

    with col_bt_chart:
        if run_bt or 'backtest_df' not in st.session_state:
            with st.spinner("計算條件觸發與摩擦損耗中..."):
                try:
                    spy_raw = yf.download("SPY", start=bt_start, end=bt_end, progress=False)
                    vix_raw = yf.download("^VIX", start=bt_start, end=bt_end, progress=False)
                    spy_c = spy_raw['Close'].iloc[:, 0] if isinstance(spy_raw.columns, pd.MultiIndex) else spy_raw['Close']
                    vix_c = vix_raw['Close'].iloc[:, 0] if isinstance(vix_raw.columns, pd.MultiIndex) else vix_raw['Close']
                    dates_idx = spy_c.index

                    friction = (slippage_bps / 10000.0) + (fee_rate / 100.0)

                    # 1. Delta-Neutral (布林通道)
                    spy_ma20 = spy_c.rolling(20).mean()
                    spy_std20 = spy_c.rolling(20).std()
                    vix_aligned = vix_c.reindex(dates_idx).ffill().bfill()
                    opt_signal = (spy_c <= (spy_ma20 + 2 * spy_std20)) & (spy_c >= (spy_ma20 - 2 * spy_std20)) & (vix_aligned < 25.0)
                    opt_pos = opt_signal.shift(1).fillna(False).astype(float)
                    opt_turnover = (opt_pos - opt_pos.shift(1)).abs().fillna(0)
                    
                    spy_ret = spy_c.pct_change().fillna(0)
                    opt_daily_ret = opt_pos * (0.16/252 - 0.5 * (spy_ret**2) * 5) - (opt_turnover * friction)
                    spy_cum = (1 + opt_daily_ret).cumprod()

                    # 2. VRP (VIX < 20MA)
                    vix_ma20 = vix_aligned.rolling(20).mean()
                    vix_pct = vix_aligned.pct_change().fillna(0)
                    vrp_signal = (vix_aligned >= 13.0) & (vix_aligned <= vix_ma20 * 1.1) & (vix_pct < 0.15)
                    vrp_pos = vrp_signal.shift(1).fillna(False).astype(float)
                    vrp_turnover = (vrp_pos - vrp_pos.shift(1)).abs().fillna(0)
                    
                    vrp_daily_ret = vrp_pos * (0.0006 - (0.12 * vix_pct.clip(lower=0))) - (vrp_turnover * friction)
                    vol_cum = (1 + vrp_daily_ret).cumprod()

                    # 3. Carry (USD/JPY 20MA)
                    jpy_raw = yf.download("JPY=X", start=bt_start, end=bt_end, progress=False)
                    jpy_c = jpy_raw['Close'].iloc[:, 0] if isinstance(jpy_raw.columns, pd.MultiIndex) else jpy_raw['Close']
                    jpy_aligned = jpy_c.reindex(dates_idx).ffill().bfill()
                    jpy_ma20 = jpy_aligned.rolling(20).mean()
                    jpy_ret = jpy_aligned.pct_change().fillna(0)
                    
                    carry_signal = (jpy_aligned >= jpy_ma20) & (jpy_ret > -0.010)
                    carry_pos = carry_signal.shift(1).fillna(False).astype(float)
                    carry_turnover = (carry_pos - carry_pos.shift(1)).abs().fillna(0)
                    
                    carry_daily_ret = carry_pos * ((0.048 / 252) + (jpy_ret * 0.5)) - (carry_turnover * friction)
                    carry_cum = (1 + carry_daily_ret).cumprod()

                    # 4. Pair Trading (修復 replace method 報錯)
                    aud_raw = yf.download("AUDUSD=X", start=bt_start, end=bt_end, progress=False)
                    nzd_raw = yf.download("NZDUSD=X", start=bt_start, end=bt_end, progress=False)
                    aud_c = aud_raw['Close'].iloc[:, 0] if isinstance(aud_raw.columns, pd.MultiIndex) else aud_raw['Close']
                    nzd_c = nzd_raw['Close'].iloc[:, 0] if isinstance(nzd_raw.columns, pd.MultiIndex) else nzd_raw['Close']
                    pair_df = pd.DataFrame({'AUD': aud_c, 'NZD': nzd_c}).reindex(dates_idx).ffill().dropna()
                    
                    spread = pair_df['AUD'] - pair_df['NZD']
                    z = (spread - spread.rolling(30).mean()) / spread.rolling(30).std()
                    
                    pair_pos = pd.Series(np.nan, index=pair_df.index)
                    pair_pos[z > 1.5] = -1.0
                    pair_pos[z < -1.5] = 1.0
                    pair_pos[z.abs() < 0.3] = 0.0
                    pair_pos = pair_pos.ffill().fillna(0.0).shift(1).fillna(0.0)
                    pair_turnover = (pair_pos - pair_pos.shift(1)).abs().fillna(0)
                    
                    pair_ret = pair_pos * (pair_df['AUD'].pct_change() - pair_df['NZD'].pct_change()) - (pair_turnover * friction)
                    pair_cum = (1 + pair_ret.fillna(0)).cumprod().reindex(dates_idx).ffill().fillna(1.0)

                    carry_wt = next((s['weight'] for s in st.session_state['strategies'] if "Carry" in s['name'] and s['active']), 0) / 100
                    delta_wt = next((s['weight'] for s in st.session_state['strategies'] if "Delta" in s['name'] and s['active']), 0) / 100
                    vol_wt = next((s['weight'] for s in st.session_state['strategies'] if "Volatility" in s['name'] and s['active']), 0) / 100
                    pair_wt = next((s['weight'] for s in st.session_state['strategies'] if "Pair" in s['name'] and s['active']), 0) / 100

                    res_df = pd.DataFrame({
                        'Hedged Carry ($)': carry_cum * (total_capital * carry_wt),
                        'Delta-Neutral ($)': spy_cum * (total_capital * delta_wt),
                        'Volatility Arbitrage ($)': vol_cum * (total_capital * vol_wt),
                        'Pair Trading ($)': pair_cum * (total_capital * pair_wt)
                    }, index=dates_idx).ffill().dropna()

                    res_df['總資產組合 (Portfolio NAV)'] = res_df.sum(axis=1)
                    st.session_state['backtest_df'] = res_df

                except Exception as e:
                    st.error(f"回測失敗: {e}")

        if 'backtest_df' in st.session_state and not st.session_state['backtest_df'].empty:
            df_plot = st.session_state['backtest_df']
            port_nav = df_plot['總資產組合 (Portfolio NAV)']
            cagr, ann_vol, sharpe, mdd, calmar = calculate_quant_metrics(port_nav)

            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("年化報酬 (CAGR)", f"{cagr:.2f}%")
            k2.metric("年化夏普比率 (Sharpe)", f"{sharpe:.2f}", delta="含滑價/摩擦")
            k3.metric("最大回撤 (Max Drawdown)", f"{mdd:.2f}%", delta_color="inverse")
            k4.metric("卡爾瑪比率 (Calmar)", f"{calmar:.2f}")
            k5.metric("年化波動率", f"{ann_vol:.2f}%")

            fig_nav = px.line(
                df_plot, 
                y=['總資產組合 (Portfolio NAV)', 'Hedged Carry ($)', 'Delta-Neutral ($)', 'Volatility Arbitrage ($)'],
                title=f"資本規模 (${total_capital:,.0f} USD) 含摩擦成本淨值曲線"
            )
            fig_nav.update_layout(template="plotly_dark", height=380, margin=dict(l=10, r=10, t=35, b=10))
            st.plotly_chart(fig_nav, use_container_width=True)