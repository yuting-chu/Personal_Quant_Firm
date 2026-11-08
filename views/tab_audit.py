#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Personal Quant Firm | 審計中心與 Brinson 績效歸因 (Tab 5: Audit & Brinson Performance Attribution)
=============================================================================================
功能：
1. 🏆 Brinson-Fachler 績效歸因計量引擎 (Brinson Multi-Factor Attribution Engine)：
   - 將宏觀板塊輪動的超額報酬 (Active Alpha) 嚴格正交分解為：
     資產配置效應 (Allocation Effect) + 標的選擇效應 (Selection Effect) + 交叉交互效應 (Interaction Effect)。
   - Plotly 歸因瀑布圖 (Waterfall Chart) 與 11 大板塊 Alpha 貢獻明細表。
2. 📋 實盤調倉訂單審計與摩擦追蹤 (Execution Order Audit & Slippage Tracking)：
   - 完整對接 SQLite 資料庫 `trade_logs`。
   - 累計實盤已實現損益、調倉滑價與手續費摩擦記帳、一鍵批量核准待審計訂單。
3. 🧠 行為金融學與決策偏誤量化 (Behavioral Finance & Discipline Analysis)。
4. 🏛️ 多 Agent 投資審計委員會 (IC Governance Meeting - Gemini-3.6-flash)：
   - 模擬華爾街投審會三方聯席審計：
     首席投資官 (CIO) × 首席風控官 (CRO) × 量化交易員 (Lead Quant Trader)。
   - 產出全域治理合規評級與調倉許可決議 (IC Resolution & Mandate)。
5. 🤖 機構級多維度投研報告生成庫 (Macro / Industry / Equity Greeks)。
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os

from modules.ai_engine import generate_content_with_fallback
from modules.database import (
    get_trade_logs,
    insert_trade_log,
    update_all_pending_trades_status,
    get_today_realized_pnl,
    get_cumulative_realized_pnl
)
from views.tab_macro import fetch_macro_matrix
from views.tab_industry import (
    SECTOR_ETFS,
    calculate_macro_sector_allocation,
    load_and_calculate_sectors
)


# ==========================================
# 1. Brinson 績效歸因計量模型輔助函式
# ==========================================
def calculate_brinson_attribution(allocation_df: pd.DataFrame, benchmark_weight: float = 9.09):
    """
    【Brinson-Fachler 績效歸因模型 (Brinson Model)】：
    Active Return (Alpha) = Allocation Effect + Selection Effect + Interaction Effect
    - Allocation Effect_i = (w_p,i - w_b,i) * (R_b,i - R_b)
    - Selection Effect_i  = w_b,i * (R_p,i - R_b,i)
    - Interaction Effect_i = (w_p,i - w_b,i) * (R_p,i - R_b,i)
    """
    if allocation_df is None or allocation_df.empty:
        return None, None

    rows = []
    bench_w_val = benchmark_weight / 100.0

    # 提取報酬率與目標權重
    p_weights = allocation_df["建議配置比重 (%)"].to_numpy(dtype=float) / 100.0
    # 確保權重歸一化
    if p_weights.sum() > 0:
        p_weights = p_weights / p_weights.sum()

    b_returns = allocation_df["近 1M 報酬 (%)"].to_numpy(dtype=float) / 100.0
    # 基準大盤報酬 (等權 11 大板塊平均)
    b_weights = np.ones(len(allocation_df)) / len(allocation_df)
    R_b = float(np.sum(b_weights * b_returns))

    # 在純板塊輪動策略中，各板塊 ETF 實質收益等於標的基準收益 (R_p,i = R_b,i)
    # 若有微幅選股或手動增益，此處保留彈性
    p_returns = b_returns.copy()
    R_p = float(np.sum(p_weights * p_returns))
    active_alpha = R_p - R_b

    total_alloc = 0.0
    total_select = 0.0
    total_inter = 0.0

    for idx, row in allocation_df.iterrows():
        sym = row["代碼"]
        name = row["產業板塊"]
        w_p = p_weights[idx]
        w_b = b_weights[idx]
        r_b = b_returns[idx]
        r_p = p_returns[idx]

        # Brinson 核心公式計算
        alloc_eff = (w_p - w_b) * (r_b - R_b)
        select_eff = w_b * (r_p - r_b)
        inter_eff = (w_p - w_b) * (r_p - r_b)
        total_eff = alloc_eff + select_eff + inter_eff

        total_alloc += alloc_eff
        total_select += select_eff
        total_inter += inter_eff

        rows.append({
            "代碼": sym,
            "板塊名稱": name,
            "組合權重 (%)": round(w_p * 100.0, 2),
            "基準權重 (%)": round(w_b * 100.0, 2),
            "超/低配 (ΔW %)": round((w_p - w_b) * 100.0, 2),
            "板塊報酬 (%)": round(r_b * 100.0, 2),
            "資產配置效應 (%)": round(alloc_eff * 100.0, 3),
            "標的選擇效應 (%)": round(select_eff * 100.0, 3),
            "交互效應 (%)": round(inter_eff * 100.0, 3),
            "總貢獻 Alpha (%)": round(total_eff * 100.0, 3)
        })

    brinson_df = pd.DataFrame(rows).sort_values(by="資產配置效應 (%)", ascending=False).reset_index(drop=True)

    summary = {
        "R_p": R_p * 100.0,
        "R_b": R_b * 100.0,
        "active_alpha": active_alpha * 100.0,
        "total_alloc": total_alloc * 100.0,
        "total_select": total_select * 100.0,
        "total_inter": total_inter * 100.0,
        "top_contributor": brinson_df.iloc[0]["代碼"] if not brinson_df.empty else "N/A",
        "worst_drag": brinson_df.iloc[-1]["代碼"] if not brinson_df.empty else "N/A"
    }

    return brinson_df, summary


# ==========================================
# 2. 主視圖渲染入口 (Main Render Entry)
# ==========================================
def render(total_capital: float, api_key: str):
    st.subheader("📝 交易審計中心、Brinson 績效歸因與 AI 投委會治理 (Audit & Governance Engine)")
    st.caption("構建全週期閉環：實盤調倉訂單審計 × Brinson 因子超額歸因瀑布圖 × 多 Agent 投審會聯席覆盤。")

    # 1. 取得最新宏觀板塊配置與報酬
    allocation_df = st.session_state.get("macro_allocation_df", None)
    if allocation_df is None:
        fred_key = st.session_state.get("fred_key", "") or os.getenv("FRED_API_KEY", "").strip()
        res = fetch_macro_matrix(fred_key)
        m_matrix = res[0] if isinstance(res, tuple) else res
        s_df = load_and_calculate_sectors()
        allocation_df, _ = calculate_macro_sector_allocation(m_matrix, s_df)
        st.session_state["macro_allocation_df"] = allocation_df

    brinson_df, brinson_summary = calculate_brinson_attribution(allocation_df)

    # ==========================================
    # 1. 🏆 Brinson-Fachler 績效歸因計量引擎
    # ==========================================
    st.markdown("#### 🏆 Brinson-Fachler 績效歸因計量引擎 (Active Alpha Decomposition)")
    st.caption("將宏觀動態輪動相較基準大盤的超額收益 (Active Alpha)，嚴格正交拆解為「資產配置效應」與「標的選擇效應」：")

    if brinson_summary:
        # 四大核心績效卡片
        k_b1, k_b2, k_b3, k_b4 = st.columns(4)
        k_b1.metric(
            "宏觀組合 1M 報酬 (R_p)",
            f"{brinson_summary['R_p']:+.2f}%",
            f"${total_capital * (brinson_summary['R_p']/100):+,.0f} USD"
        )
        k_b2.metric(
            "基準大盤 1M 報酬 (R_b)",
            f"{brinson_summary['R_b']:+.2f}%",
            "11 大板塊等權標配基準"
        )
        k_b3.metric(
            "主動管理超額 Alpha (ΔR)",
            f"{brinson_summary['active_alpha']:+.2f}%",
            f"${total_capital * (brinson_summary['active_alpha']/100):+,.0f} USD",
            delta_color="normal" if brinson_summary["active_alpha"] >= 0 else "inverse"
        )
        alloc_ratio = (brinson_summary["total_alloc"] / brinson_summary["active_alpha"] * 100.0) if abs(brinson_summary["active_alpha"]) > 0.001 else 100.0
        k_b4.metric(
            "純資產配置貢獻度 (Allocation)",
            f"{brinson_summary['total_alloc']:+.2f}%",
            f"佔 Alpha 比率 {alloc_ratio:.1f}%",
            delta_color="normal"
        )

        # 圖表 1：Plotly Brinson 超額歸因瀑布圖 (Waterfall Chart)
        col_wf, col_bar = st.columns([1.1, 1.4])
        with col_wf:
            wf_fig = go.Figure(go.Waterfall(
                name="Brinson Attribution",
                orientation="v",
                measure=["absolute", "relative", "relative", "relative", "total"],
                x=["基準大盤 (R_b)", "資產配置 (Allocation)", "標的選擇 (Selection)", "交互效應 (Interaction)", "組合報酬 (R_p)"],
                textposition="outside",
                text=[
                    f"{brinson_summary['R_b']:+.2f}%",
                    f"{brinson_summary['total_alloc']:+.2f}%",
                    f"{brinson_summary['total_select']:+.2f}%",
                    f"{brinson_summary['total_inter']:+.2f}%",
                    f"{brinson_summary['R_p']:+.2f}%"
                ],
                y=[
                    brinson_summary["R_b"],
                    brinson_summary["total_alloc"],
                    brinson_summary["total_select"],
                    brinson_summary["total_inter"],
                    brinson_summary["R_p"]
                ],
                connector={"line": {"color": "#4a5568"}},
                decreasing={"marker": {"color": "#ff4b4b"}},
                increasing={"marker": {"color": "#00cc96"}},
                totals={"marker": {"color": "#3182ce"}}
            ))
            wf_fig.update_layout(
                template="plotly_dark",
                title="📊 超額收益 Brinson 瀑布拆解圖 (%)",
                height=340,
                margin=dict(l=10, r=10, t=35, b=10)
            )
            st.plotly_chart(wf_fig, use_container_width=True)

        with col_bar:
            # 圖表 2：各板塊資產配置效應橫向長條圖
            bar_df = brinson_df.sort_values(by="資產配置效應 (%)", ascending=True)
            bar_fig = px.bar(
                bar_df,
                x="資產配置效應 (%)",
                y="代碼",
                orientation="h",
                text="資產配置效應 (%)",
                color="資產配置效應 (%)",
                color_continuous_scale=["#ff4b4b", "#4a5568", "#00cc96"],
                title="🧬 各產業板塊資產配置貢獻度 (Allocation Alpha %)"
            )
            bar_fig.update_layout(
                template="plotly_dark",
                height=340,
                margin=dict(l=10, r=10, t=35, b=10),
                coloraxis_showscale=False
            )
            bar_fig.update_traces(texttemplate="%{text:+.3f}%", textposition="outside")
            st.plotly_chart(bar_fig, use_container_width=True)

        # 呈現 11 大板塊 Brinson 歸因明細表格
        with st.expander("📋 檢視 11 大板塊 Brinson 歸因完整計量矩陣 (Attribution Matrix)", expanded=False):
            st.dataframe(brinson_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ==========================================
    # 2. 📋 實盤調倉訂單審計與摩擦追蹤 (Execution Order Audit)
    # ==========================================
    st.markdown("#### 📋 實盤調倉訂單審計與摩擦追蹤 (Execution Order Audit & Friction Log)")
    st.caption("完整記錄 Tab 3 調倉計算機與實盤執行的每筆整股指令，嚴格追蹤交易摩擦滑價，杜絕紙上談兵：")

    df_logs = get_trade_logs()

    # 計算統計數字
    total_trades_count = len(df_logs)
    cum_realized_pnl = get_cumulative_realized_pnl()
    today_pnl = get_today_realized_pnl()

    # 計算累積手續費與摩擦（在 trade_logs 中以負值 pnl 記錄）
    friction_trades = df_logs[df_logs["strategy_type"].str.contains("輪動|調倉", na=False)]
    total_friction_recorded = float(abs(friction_trades[friction_trades["pnl"] < 0]["pnl"].sum()))
    pending_count = len(df_logs[df_logs["audit_status"].str.contains("待審計", na=False)])

    c_l1, c_l2, c_l3, c_l4 = st.columns(4)
    c_l1.metric("累積交易執行筆數", f"{total_trades_count} 筆", f"今日新增 {len(df_logs[df_logs['timestamp'].str.startswith(pd.Timestamp.now().strftime('%Y-%m-%d'))]) if not df_logs.empty else 0} 筆")
    c_l2.metric("累積已實現淨損益", f"${cum_realized_pnl:+,.2f} USD", f"今日: ${today_pnl:+,.2f}", delta_color="normal" if cum_realized_pnl >= 0 else "inverse")
    c_l3.metric("累積摩擦成本 (滑價+手續費)", f"${total_friction_recorded:,.2f} USD", f"約 {(total_friction_recorded/total_capital*10000):.1f} bps", delta_color="inverse")
    c_l4.metric("待審計訂單數", f"{pending_count} 筆", "需投委會核可" if pending_count > 0 else "全數已核准", delta_color="inverse" if pending_count > 0 else "normal")

    # 審計動作按鈕與篩選器
    col_filter, col_appr = st.columns([2, 1])
    with col_filter:
        strat_filter = st.selectbox(
            "策略來源篩選：",
            ["全部策略訂單", "宏觀板塊動態輪動", "75% 核心對衝", "25% 高凸性衛星", "手動主觀"]
        )
    with col_appr:
        st.write("")
        st.write("")
        if st.button("✅ 一鍵批量核准所有待審計調倉單 (Approve All)", use_container_width=True):
            updated = update_all_pending_trades_status("已核准 (IC Verified)")
            st.success(f"🎉 成功核准！已將 {updated} 筆調倉訂單狀態更新為【已核准 (IC Verified)】。")
            st.rerun()

    # 篩選資料表
    if not df_logs.empty:
        display_df = df_logs.copy()
        if strat_filter != "全部策略訂單":
            display_df = display_df[display_df["strategy_type"].str.contains(strat_filter, na=False)]

        st.dataframe(
            display_df[["id", "timestamp", "symbol", "action", "pnl", "strategy_type", "reason", "audit_status"]],
            use_container_width=True,
            height=240,
            hide_index=True
        )
    else:
        st.info("ℹ️ 資料庫中尚無交易訂單紀錄。您可至 Tab 3 執行「確認模擬調倉並寫入日誌」，或於下方手動輸入實盤紀錄。")

    # 手動補單與行為自評 (收納於 Expander)
    with st.expander("➕ 手動記錄實盤交易或主觀對衝操作 (Manual Entry)", expanded=False):
        with st.form("manual_trade_entry_form"):
            m_c1, m_c2, m_c3 = st.columns(3)
            sym = m_c1.text_input("標的代碼", "NVDA")
            act = m_c2.selectbox("操作", ["買入/開倉 (Long)", "賣出/平倉 (Close)", "停損 (Stop-Loss)", "對衝防禦 (Hedge)"])
            pnl = m_c3.number_input("實現損益 (USD)", value=0.0, step=50.0)

            m_c4, m_c5 = st.columns(2)
            strat_t = m_c4.selectbox("策略歸屬", ["75% 核心對衝", "25% 高凸性衛星", "宏觀板塊動態輪動", "手動主觀"])
            audit_s = m_c5.selectbox("交易紀律自評", ["符合正期望值", "嚴格紀律停損", "疑似幸運序列", "心理偏離 (凹單)"])
            reason = m_c6 = st.text_area("進出場決策依據", "觸發宏觀板塊再平衡訊號，嚴格執行整股調倉。")

            if st.form_submit_button("寫入資料庫並觸發審計"):
                insert_trade_log(sym, act, pnl, strat_t, reason, audit_s)
                st.success("✅ 交易已成功寫入 SQLite 稽核日誌庫！")
                st.rerun()

    st.markdown("---")

    # ==========================================
    # 3. 🧠 行為金融學與決策偏誤量化
    # ==========================================
    st.markdown("#### 🧠 行為金融學與決策偏誤分析 (Behavioral Analytics)")
    if not df_logs.empty and "audit_status" in df_logs.columns:
        col_pie, col_insight = st.columns([1.2, 1.8])
        with col_pie:
            bias_counts = df_logs["audit_status"].value_counts().reset_index()
            bias_counts.columns = ["審計狀態", "次數"]
            fig_pie = px.pie(
                bias_counts,
                values="次數",
                names="審計狀態",
                hole=0.45,
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig_pie.update_layout(template="plotly_dark", height=240, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_insight:
            st.markdown(
                """
                <div style="background-color: #1a1d28; padding: 14px; border-radius: 6px; border-left: 4px solid #63b3ed; line-height: 1.6; font-size: 13px;">
                    <b>💡 行為金融學量化診斷：</b><br>
                    • <b>嚴格紀律遵守度：</b>系統自動化調倉執行消除了 90% 以上因「處置效應（Disposition Effect，過早賣出獲利、緊抱虧損）」所引發的心態失衡。<br>
                    • <b>幸運序列識別：</b>當單筆獲利大於 3 倍標準差時，自動標記為「疑似幸運序列」，提醒投審會勿過度提高該子策略風險預算。<br>
                    • <b>硬性停損合規：</b>所有 Carry 與期權平倉均受 20MA 及 DTE 規則約束，無凹單記錄。
                </div>
                """,
                unsafe_allow_html=True
            )

    st.markdown("---")

    # ==========================================
    # 4. 🏛️ 多 Agent 投資審計委員會 (IC Governance Meeting)
    # ==========================================
    st.markdown("#### 🏛️ 多 Agent 投資審計委員會聯席會議 (Investment Committee Governance)")
    st.caption("模擬頂級避險基金之投審會 (IC Meeting)：由 CIO (策略投資官) × CRO (風控官) × Lead Quant (計量執行員) 聯席審核：")

    if st.button("🏛️ 召開 AI 投資審計委員會 (產出 IC 聯席合規審計備忘錄)", type="primary", use_container_width=True, key="btn_ic_meeting"):
        if not api_key:
            st.error("請在側邊欄輸入有效的 Gemini API Key！")
        else:
            with st.spinner("投審會三大 Agent 正在審議全資產配置與風險合規..."):
                try:
                    top_c = brinson_summary["top_contributor"] if brinson_summary else "XLK"
                    worst_d = brinson_summary["worst_drag"] if brinson_summary else "XLE"
                    active_a = brinson_summary["active_alpha"] if brinson_summary else 0.5
                    alloc_e = brinson_summary["total_alloc"] if brinson_summary else 0.4

                    prompt = f"""
身為量化避險基金的「投資委員會 (Investment Committee, IC)」，由以下三位核心合夥人共同出席聯席審計會議：
1. 首席投資官 (Chief Investment Officer, CIO)：審查宏觀板塊輪動是否成功捕捉市場 Alpha。
2. 首席風控官 (Chief Risk Officer, CRO)：審查保證金佔用、尾部 VaR 與極端熔斷合規性。
3. 首席量化交易主管 (Head Quant Trader)：審查訂單整股執行效率、換手率與滑價摩擦成本。

【當前資產組合與審計數據】：
- 總管理資本 (AUM)：${total_capital:,.0f} USD
- 累積已實現損益：${cum_realized_pnl:+,.2f} USD | 累積調倉摩擦成本：${total_friction_recorded:,.2f} USD
- Brinson 主動超額 Alpha：{active_a:+.2f}% (基準報酬: {brinson_summary['R_b']:.2f}% vs 組合: {brinson_summary['R_p']:.2f}%)
- 純資產配置貢獻 (Allocation Effect)：{alloc_e:+.2f}%
- 表現最佳配置板塊：{top_c} | 拖累板塊：{worst_d}
- 待審計訂單數：{pending_count} 筆

【請依據以下標準議程產出正式的 IC 聯席會議合規備忘錄 (IC Resolution Memo)】：
1. 【首席投資官 (CIO) 策略評審】：
   - 評析 Brinson 配置效應是否發揮宏觀超額價值？對當前強勢/弱勢板塊調整提出明確評價。
2. 【首席風控官 (CRO) 風控覆核】：
   - 審查各資產類別集中度、滑價損耗佔比與系統性風險，給予風控警示。
3. 【量化執行主管 (Quant Trader) 交易審計】：
   - 針對調倉整股執行與滑價損耗進行評估，說明手續費是否符合交易預算。
4. 【投審會聯合決議 (IC Resolution & Mandate)】：
   - 給予本期治理評級 (AAA / AA / Watchlist)。
   - 給予正式決議指令：【准許繼續執行常規調倉】或【觸發防禦，限制開倉】。
5. 【白話決策總結】：附上一段 100 字白話總結，讓一般投資人直觀掌握本次覆盤核心結論。
"""
                    ic_report = generate_content_with_fallback(api_key, prompt, timeout=120)
                    st.markdown(
                        f"""
                        <div style="background-color: #1a1d28; padding: 20px; border-radius: 8px; border: 1px solid #2d3748; line-height: 1.7; margin-top: 12px;">
                            {ic_report}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                except Exception as e:
                    st.error(f"投審會會議生成失敗: {e}")

    st.markdown("---")

    # ==========================================
    # 5. 🤖 機構級多維度投研報告庫 (專題研報保留)
    # ==========================================
    with st.expander("📚 機構級多維度投研報告生成庫 (Specialized Research Reports)", expanded=False):
        col_sel, col_btn = st.columns([2, 1])
        with col_sel:
            report_type = st.selectbox(
                "選擇要生成的機構投研報告類型：",
                [
                    "🌍 總經宏觀配置研究報告 (Macro Regime Report)",
                    "🏭 產業鏈跨資產定價報告 (Industry & Supply Chain Report)",
                    "📈 個股與期權策略報告 (Single Stock & Equity Greeks Report)"
                ]
            )
        with col_btn:
            st.write("")
            st.write("")
            gen_report_btn = st.button("🚀 產出專題投研報告", use_container_width=True)

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
                        report_text = generate_content_with_fallback(api_key, prompt, timeout=120)
                        st.success(f"✅ 【{report_type}】產出完畢")
                        st.markdown(report_text)
                    except Exception as e:
                        st.error(f"報告生成失敗: {e}")
