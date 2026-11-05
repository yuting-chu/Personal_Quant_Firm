import streamlit as st
import pandas as pd
import json
import plotly.express as px
import google.generativeai as genai
from modules.ai_engine import generate_content_with_fallback
from modules.database import get_trade_logs, insert_trade_log

def render(total_capital: float, api_key: str):
    st.subheader("📝 交易日誌、行為金融學覆盤與 AI 多維度投研報告")
    st.caption("支援產出機構級【總經宏觀報告】、【產業鏈跨資產報告】與【個股與期權策略報告】。")

    df_logs = get_trade_logs()

    # 1. 交易日誌錄入表單
    with st.expander("➕ 記錄今日實盤/模擬交易執行", expanded=False):
        with st.form("trade_entry_form"):
            c1, c2, c3 = st.columns(3)
            sym = c1.text_input("標的代碼", "USD/JPY")
            act = c2.selectbox("操作", ["買入/開倉 (Long)", "賣出/平倉 (Close)", "停損 (Stop-Loss)"])
            pnl = c3.number_input("實現損益 (USD)", value=0.0, step=100.0)
            
            c4, c5 = st.columns(2)
            strat_t = c4.selectbox("策略歸屬", ["75% 核心對衝", "25% 高凸性衛星", "手動主觀"])
            audit_s = c5.selectbox("交易紀律自評", ["符合正期望值", "嚴格紀律停損", "疑似幸運序列", "心理偏離 (凹單)"])
            reason = st.text_area("進出場決策依據", "觸發 20MA 均線停損條件，嚴格執行紀律平倉。")
            
            if st.form_submit_button("寫入資料庫並觸發審計"):
                insert_trade_log(sym, act, pnl, strat_t, reason, audit_s)
                st.success("✅ 交易已寫入資料庫！")
                st.rerun()

    # 2. 統計數據與偏誤圓餅圖
    if not df_logs.empty:
        col_t, col_pie = st.columns([1.8, 1.2])
        with col_t:
            st.markdown("#### 📋 實盤交易日誌 (SQLite 審計軌跡)")
            st.dataframe(df_logs[['timestamp', 'symbol', 'action', 'pnl', 'strategy_type', 'audit_status']], use_container_width=True, height=200)
        
        with col_pie:
            st.markdown("#### 🧠 行為金融學：心理偏離量化")
            bias_counts = df_logs['audit_status'].value_counts().reset_index()
            bias_counts.columns = ['審計狀態', '次數']
            fig_pie = px.pie(bias_counts, values='次數', names='審計狀態', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_pie.update_layout(template="plotly_dark", height=200, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown("---")

    # 3. 三大機構級投研報告一鍵生成引擎
    st.markdown("#### 🤖 機構級多維度投研報告生成引擎 (Multi-Domain Quant Research)")
    
    col_sel, col_btn = st.columns([2, 1])
    with col_sel:
        report_type = st.selectbox(
            "選擇要生成的機構投研報告類型：",
            ["🌍 總經宏觀配置研究報告 (Macro Regime Report)", 
             "🏭 產業鏈跨資產定價報告 (Industry & Supply Chain Report)", 
             "📈 個股與期權策略報告 (Single Stock & Equity Greeks Report)"]
        )
    with col_btn:
        st.write("")
        st.write("")
        gen_report_btn = st.button("🚀 產出機構投研報告", use_container_width=True)

    if gen_report_btn:
        if not api_key:
            st.error("請在側邊欄輸入 Gemini API Key！")
        else:
            with st.spinner(f"AI 量化投研團隊正在合成【{report_type}】..."):
                try:
                    
                    if "總經" in report_type:
                        prompt = f"""
                        你是一位頂級資產管理公司 (Asset Management) 的 Lead Macro Strategist。
                        請產出一份專業的【總體經濟與資產配置週報】：
                        - 總本金規模：${total_capital:,.0f} USD (75% 核心對衝 + 25% 衛星)
                        - 包含架構：
                          1. 【總經象限與貨幣政策】：解析核心 PCE、非農動量與實質利率路徑。
                          2. 【跨資產流動性傳導】：股、債、匯 (USD/JPY)、原油與黃金傳導機制。
                          3. 【投資委員會配置決議 (IC Action)】：給予本週加減碼具體建議。
                        """
                    elif "產業" in report_type:
                        prompt = f"""
                        你是一位 Senior Cross-Asset Industry Researcher。
                        請產出一份專業的【產業鏈跨資產定價與 Alpha 報告】：
                        - 核心重點：聚焦 AI 半導體算力鏈、大宗能源通膨鏈與消費製造鏈。
                        - 包含架構：
                          1. 【板塊相對強弱 Alpha 分析】：對標 S&P 500 之板塊輪動。
                          2. 【上游成本與匯率傳導】：USD/JPY 設備成本與 WTI 原油對毛利的衝擊。
                          3. 【產業對衝與套利策略】：如何利用現貨與 ETF 建立跨市場多空配對。
                        """
                    else:
                        prompt = f"""
                        你是一位 Senior Equity Derivatives & Single Stock Analyst。
                        請產出一份專業的【核心個股與選擇權 Greeks 定價報告】：
                        - 核心標的：NVDA (AI 龍頭) 與 SPY (大盤指數期權)。
                        - 包含架構：
                          1. 【個股基本面與技術動量】：現價支撐壓力與 20MA 趨勢判定。
                          2. 【期權波動率與 Greeks 結構】：Delta-Neutral 避險、Theta 衰減與 Gamma 風險。
                          3. 【具體交易執行指令】：履約價 (Strike)、到期日 (DTE) 與停損條件建議。
                        """
                    
                    report_text = generate_content_with_fallback(api_key, prompt)
                    st.success(f"✅ 【{report_type}】產出完畢")
                    st.markdown(report_text)
                    
                except Exception as e:
                    st.error(f"報告生成失敗: {e}")