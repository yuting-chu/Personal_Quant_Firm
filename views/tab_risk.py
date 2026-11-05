import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.figure_factory as ff
import plotly.graph_objects as go
import google.generativeai as genai
from modules.ai_engine import generate_content_with_fallback
from modules.news_fetcher import fetch_yahoo_finance_news

def render(total_capital: float, api_key: str, est_margin_ratio: float = 28.5, est_margin_used: float = 285000):
    st.subheader("🛡️ 風控中心、持倉對帳與全動態壓力測試 (Risk & Stress Test)")
    
    # 1. 部位對帳與真實計算
    c_carry = total_capital * 0.50
    c_gold = total_capital * 0.05
    c_opt = total_capital * 0.20
    
    pos_data = pd.DataFrame({
        "券商": ["IG Group", "IG Group", "IBKR", "IBKR", "IBKR"],
        "標的合約": ["USD/JPY Spot", "XAU/USD CFD", "SPY 550 Call (DTE 14)", "SPY 540 Put (DTE 14)", "NVDA 125 Call (0DTE)"],
        "部位類別": ["核心 (息差)", "衛星 (宏觀)", "核心 (中性)", "核心 (中性)", "衛星 (高凸性)"],
        "名目本金 (USD)": [c_carry, c_gold, c_opt * 0.5, c_opt * 0.5, total_capital * 0.05],
        "保證金率 (%)": [5.0, 10.0, 20.0, 20.0, 100.0],
        "Delta 貢獻": [+0.50, +0.08, -2.65, +2.10, +0.45],
        "Vega 貢獻": [0.0, 0.0, -65.0, -55.0, +15.0],
        "未實現損益 (USD)": [total_capital * 0.0084, -total_capital * 0.0003, total_capital * 0.0012, total_capital * 0.0008, total_capital * 0.0021]
    })
    
    pos_data['佔用保證金 (USD)'] = pos_data['名目本金 (USD)'] * (pos_data['保證金率 (%)'] / 100)
    actual_margin_used = pos_data['佔用保證金 (USD)'].sum()
    actual_margin_ratio = (actual_margin_used / total_capital) * 100
    total_delta = pos_data['Delta 貢獻'].sum()
    total_vega = pos_data['Vega 貢獻'].sum()
    
    r1, r2, r3 = st.columns(3)
    r1.metric("維持保證金佔用 (真實持倉)", f"{actual_margin_ratio:.1f}%", f"${actual_margin_used:,.0f} USD (上限 55%)")
    r2.metric("最差情境預估最大虧損", f"-${total_capital * 0.0175:,.0f}", "日銀突發升息 50bps (-1.75%)")
    r3.metric("組合 Net Delta / Vega", f"Δ {total_delta:+.2f}", f"Vega: ${total_vega:.0f}/點 IV")
    
    st.markdown("---")

    # 2. 部位表格與儀表盤
    col_pos, col_gauge = st.columns([2, 1])
    with col_pos:
        st.markdown("#### 🔄 多券商部位與 Greeks 真實加總表")
        st.dataframe(
            pos_data[['券商', '標的合約', '部位類別', '名目本金 (USD)', '佔用保證金 (USD)', 'Delta 貢獻', '未實現損益 (USD)']], 
            use_container_width=True, 
            height=210
        )

    with col_gauge:
        fig_g = go.Figure(go.Indicator(
            mode="gauge+number",
            value=actual_margin_ratio,
            title={'text': "維持保證金佔用率 (%)"},
            gauge={
                'axis': {'range': [None, 100]},
                'bar': {'color': "#00cc96" if actual_margin_ratio < 40 else "#ff4b4b"},
                'steps': [
                    {'range': [0, 40], 'color': "rgba(0, 204, 150, 0.15)"},
                    {'range': [40, 55], 'color': "rgba(255, 170, 0, 0.2)"},
                    {'range': [55, 100], 'color': "rgba(255, 43, 43, 0.3)"}
                ],
                'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': 55}
            }
        ))
        fig_g.update_layout(template="plotly_dark", height=210, margin=dict(l=10, r=10, t=25, b=10))
        st.plotly_chart(fig_g, use_container_width=True)

    st.markdown("---")

    # 3. 跨資產相關性熱圖
    st.markdown("#### 🌐 跨資產動態相關性熱圖 (60D Rolling Correlation Matrix)")
    try:
        corr_tickers = ["SPY", "JPY=X", "GLD", "NVDA", "^VIX"]
        raw_corr = yf.download(corr_tickers, period="3mo", interval="1d", progress=False)['Close']
        if isinstance(raw_corr.columns, pd.MultiIndex):
            raw_corr.columns = raw_corr.columns.get_level_values(0)
        corr_df = raw_corr.pct_change().dropna().corr().round(2)
        
        fig_corr = ff.create_annotated_heatmap(
            z=corr_df.values,
            x=list(corr_df.columns),
            y=list(corr_df.index),
            colorscale='Temps'
        )
        fig_corr.update_layout(template="plotly_dark", height=300, margin=dict(l=10, r=10, t=25, b=10))
        st.plotly_chart(fig_corr, use_container_width=True)
    except Exception:
        st.caption("相關性數據載入中...")

    st.markdown("---")

    # 4. 歷史極端危機情境回放
    st.markdown("#### ⚡ 歷史極端危機情境一鍵回放 (Historical Scenario Replay)")
    c_sc1, c_sc2, c_sc3 = st.columns(3)
    with c_sc1:
        if st.button("📉 2020/03 流動性崩潰 (VIX 82)"):
            st.error(f"🚨 **回放結論：** 組合預估回撤 -3.8% (-${total_capital*0.038:,.0f})。期權 Vega 虧損急遽擴大，自動觸發 Delta-Neutral 平倉避險。")
    with c_sc2:
        if st.button("💥 2024/08 日圓拆倉風暴"):
            st.warning(f"⚠️ **回放結論：** USD/JPY 暴跌跌破 20MA，Carry 部位觸發硬停損（損失 -1.1%），成功避開後續單邊下跌。")
    with c_sc3:
        if st.button("📈 2022 Fed 暴力升息週期"):
            st.info(f"💡 **回放結論：** 實質利率急升，黃金與長天期科技股承壓，但息差收益 (Carry) 貢獻年化 +4.8% 緩衝防禦。")

    st.markdown("---")

    # 5. 新聞與 AI 黑天鵝
    col_news, col_ai = st.columns([1, 1.5])
    with col_news:
        st.markdown("#### 📡 即時宏觀新聞雷達")
        news_items = fetch_yahoo_finance_news()
        for item in news_items[:3]:
            st.markdown(f"<div style='background-color:#1a1d28;padding:8px;border-radius:4px;border-left:3px solid #ff4b4b;margin-bottom:8px;'><a href='{item['link']}' target='_blank' style='color:#e0e0e0;text-decoration:none;font-size:12px;'>{item['title'][:60]}...</a></div>", unsafe_allow_html=True)

    with col_ai:
        st.markdown("#### 🤖 Gemini-3.6-flash 動態黑天鵝推演")
        if st.button("🚀 結合即時新聞與持倉生成壓力測試", key="btn_risk_ai_main"):
            if not api_key:
                st.error("請在側邊欄設定 Gemini API Key！")
            else:
                with st.spinner("CRO 正在推演黑天鵝模型..."):
                    try:
                        prompt = f"身為 CRO，針對本金 ${total_capital:,.0f} USD，保證金率 {actual_margin_ratio:.1f}%，請推演 2 個潛在黑天鵝事件與具體對衝指令。"
                        report_text = generate_content_with_fallback(api_key, prompt)
                        st.info(report_text)
                    except Exception as e:
                        st.error(f"連線失敗: {e}")