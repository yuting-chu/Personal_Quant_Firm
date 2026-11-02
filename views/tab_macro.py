import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import urllib.request
import json
import plotly.graph_objects as go
from datetime import datetime
import google.generativeai as genai
from modules.news_fetcher import fetch_yahoo_finance_news


def fetch_fred_series_urllib(api_key: str, series_id: str, limit: int = 15):
    """
    透過標準 REST API 抓取 FRED 數據，具備零套件相依、高容錯特性。
    """
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={api_key}&file_type=json&sort_order=desc&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        obs = [o for o in data.get("observations", []) if o.get("value") not in (".", "", None)]
        return obs


def fetch_macro_matrix(fred_api_key: str):
    is_live = False
    data_dict = {}

    if fred_api_key:
        try:
            # 1. 實體經濟數據 (物價與失業率)
            cpi_obs = fetch_fred_series_urllib(fred_api_key, "CPIAUCSL", limit=16)
            pce_obs = fetch_fred_series_urllib(fred_api_key, "PCEPILFE", limit=16)
            unrate_obs = fetch_fred_series_urllib(fred_api_key, "UNRATE", limit=16)

            cpi_cur = (float(cpi_obs[0]["value"]) / float(cpi_obs[12]["value"]) - 1) * 100
            cpi_mom_ann = ((float(cpi_obs[0]["value"]) / float(cpi_obs[3]["value"])) ** 4 - 1) * 100

            pce_cur = (float(pce_obs[0]["value"]) / float(pce_obs[12]["value"]) - 1) * 100
            pce_mom_ann = ((float(pce_obs[0]["value"]) / float(pce_obs[3]["value"])) ** 4 - 1) * 100

            unrate_cur = float(unrate_obs[0]["value"])
            unrate_diff = unrate_cur - float(unrate_obs[1]["value"])
            unrate_3m_change = unrate_cur - float(unrate_obs[3]["value"])

            # 2. 美債與利率數據 (10Y, 2Y, 利差, TIPS 實質利率, 信用利差)
            dgs10_obs = fetch_fred_series_urllib(fred_api_key, "DGS10", limit=10)
            dgs2_obs = fetch_fred_series_urllib(fred_api_key, "DGS2", limit=10)
            t10y2y_obs = fetch_fred_series_urllib(fred_api_key, "T10Y2Y", limit=10)
            dfii10_obs = fetch_fred_series_urllib(fred_api_key, "DFII10", limit=10)
            hy_spread_obs = fetch_fred_series_urllib(fred_api_key, "BAMLH0A0HYM2", limit=10)

            dgs10_val = float(dgs10_obs[0]["value"])
            dgs10_diff = dgs10_val - float(dgs10_obs[1]["value"])

            dgs2_val = float(dgs2_obs[0]["value"])
            dgs2_diff = dgs2_val - float(dgs2_obs[1]["value"])

            t10y2y_val = float(t10y2y_obs[0]["value"])
            t10y2y_diff = t10y2y_val - float(t10y2y_obs[1]["value"])

            dfii10_val = float(dfii10_obs[0]["value"])
            dfii10_diff = dfii10_val - float(dfii10_obs[1]["value"])

            hy_val = float(hy_spread_obs[0]["value"])
            hy_diff = hy_val - float(hy_spread_obs[1]["value"])

            data_dict = {
                "cpi_cur": round(cpi_cur, 1), "cpi_mom": round(cpi_mom_ann, 2),
                "pce_cur": round(pce_cur, 1), "pce_mom": round(pce_mom_ann, 2),
                "unrate_cur": round(unrate_cur, 1), "unrate_diff": round(unrate_diff, 2),
                "unrate_3m": round(unrate_3m_change, 2),
                "dgs10_cur": round(dgs10_val, 2), "dgs10_diff": round(dgs10_diff, 2),
                "dgs2_cur": round(dgs2_val, 2), "dgs2_diff": round(dgs2_diff, 2),
                "t10y2y_cur": round(t10y2y_val, 2), "t10y2y_diff": round(t10y2y_diff, 2),
                "dfii10_cur": round(dfii10_val, 2), "dfii10_diff": round(dfii10_diff, 2),
                "hy_spread_cur": round(hy_val, 2), "hy_spread_diff": round(hy_diff, 2),
                "rates_date": dgs10_obs[0]["date"]
            }
            is_live = True
        except Exception:
            is_live = False

    if not is_live:
        data_dict = {
            "cpi_cur": 3.4, "cpi_mom": 3.12,
            "pce_cur": 2.7, "pce_mom": 2.35,
            "unrate_cur": 4.1, "unrate_diff": 0.05,
            "unrate_3m": 0.15,
            "dgs10_cur": 4.98, "dgs10_diff": -0.07,
            "dgs2_cur": 4.61, "dgs2_diff": -0.06,
            "t10y2y_cur": 0.38, "t10y2y_diff": +0.01,
            "dfii10_cur": 2.63, "dfii10_diff": -0.04,
            "hy_spread_cur": 3.44, "hy_spread_diff": +0.18,
            "rates_date": datetime.now().strftime("%Y-%m-%d")
        }

    # 3. CBOE VIX 恐慌指數
    try:
        vix_df = yf.download("^VIX", period="5d", interval="1d", progress=False)
        vix_c = vix_df['Close'].iloc[:, 0] if isinstance(vix_df.columns, pd.MultiIndex) else vix_df['Close']
        cur_vix = float(vix_c.iloc[-1])
        vix_diff = cur_vix - float(vix_c.iloc[-2])
    except Exception:
        cur_vix, vix_diff = 15.67, 0.54

    data_dict["vix_cur"] = round(cur_vix, 2)
    data_dict["vix_diff"] = round(vix_diff, 2)

    return data_dict, is_live


def render(api_key: str):
    st.subheader("🌐 全球總經與美債利率戰情室")
    st.caption("即時串接美國聯準會 (FRED) 官方數據。用最白話的方式，帶你看懂利率、通膨與跨市場資金的流向。")

    loaded_fred_key = st.session_state.get('fred_key', '')
    m, is_live = fetch_macro_matrix(loaded_fred_key)

    if is_live:
        st.success(f"● 官方即時連線中：最新美債與總經數據截至 {m.get('rates_date', '')}")
    else:
        st.warning("● 目前使用離線基準數據 (請於左側欄確認 FRED API Key)")

    # ==========================================
    # 1. 雙矩陣：實體經濟 vs 美債利率 (白話直觀版)
    # ==========================================
    col_rates, col_macro = st.columns(2)

    with col_rates:
        st.markdown("#### 🏛️ 美債利率與借錢成本 (資金水位晴雨表)")
        st.caption("美債殖利率是全球金融市場的「借錢成本基準」。利率越高，市場資金越吃緊。")

        # 利差白話判斷
        spread_val = m["t10y2y_cur"]
        if spread_val < 0:
            curve_signal = "🚨 倒掛警報（經濟可能要降溫或衰退）"
        elif spread_val < 0.20:
            curve_signal = "⚡ 解除倒掛中（市場正迎接降息拐點，常伴隨波動）"
        else:
            curve_signal = "🟢 正常正斜率（借長天期利息比短天期高，經濟健康）"

        # 實質利率白話判斷
        tips_val = m["dfii10_cur"]
        if tips_val >= 2.0:
            tips_signal = "🛑 偏貴（實質借錢成本很高，壓抑黃金與高估值科技股）"
        elif tips_val >= 1.0:
            tips_signal = "⚖️ 適中（中規中矩的實質利率）"
        else:
            tips_signal = "🚀 寬鬆便宜（錢不值錢，有利黃金與抗通膨資產）"

        rates_rows = [
            {
                "指標 (白話說明)": "10年期美債殖利率 (各行各業借錢基準)",
                "最新數值": f"{m['dgs10_cur']}%",
                "今日漲跌": f"{m['dgs10_diff']:+.2f}%",
                "白話意思": "全球資產定價基準，此數字越高，科技股估值壓力越大"
            },
            {
                "指標 (白話說明)": "2年期美債殖利率 (市場預期Fed近況)",
                "最新數值": f"{m['dgs2_cur']}%",
                "今日漲跌": f"{m['dgs2_diff']:+.2f}%",
                "白話意思": "市場猜測聯準會未來 1~2 年到底會升息還是降息"
            },
            {
                "指標 (白話說明)": "10Y-2Y 利差 (景氣長短天期氣壓計)",
                "最新數值": f"{m['t10y2y_cur']}% ({spread_val * 100:+.0f}點)",
                "今日漲跌": f"{m['t10y2y_diff']:+.2f}%",
                "白話意思": curve_signal
            },
            {
                "指標 (白話說明)": "10年期實質利率 (扣除通膨後的真成本)",
                "最新數值": f"{m['dfii10_cur']}%",
                "今日漲跌": f"{m['dfii10_diff']:+.2f}%",
                "白話意思": tips_signal
            },
            {
                "指標 (白話說明)": "垃圾債違約風險利差 (企業倒閉機率)",
                "最新數值": f"{m['hy_spread_cur']}%",
                "今日漲跌": f"{m['hy_spread_diff']:+.2f}%",
                "白話意思": "企業信用良好，大家不怕違約" if m['hy_spread_cur'] < 4.0 else "企業借錢變難，市場開始警惕倒閉潮"
            }
        ]
        st.dataframe(pd.DataFrame(rates_rows), use_container_width=True, hide_index=True)

    with col_macro:
        st.markdown("#### 📊 物價通膨與失業率 (百姓生活與就業體溫)")
        st.caption("聯準會 (Fed) 掌管利率最重要的兩大指標：有沒有人人有工作？東西有沒有變太貴？")

        matrix_rows = [
            {
                "指標 (白話說明)": "總體 CPI (一般百姓物價年增率)",
                "最新數值": f"{m['cpi_cur']}%",
                "近期3個月動向": f"{m['cpi_mom']}% (年化)",
                "白話意思": "物價算聽話，通膨在可控範圍" if m['cpi_mom'] < 2.8 else "東西還在漲，通膨有點難降"
            },
            {
                "指標 (白話說明)": "核心 PCE (官員最在意的通膨標竿)",
                "最新數值": f"{m['pce_cur']}%",
                "近期3個月動向": f"{m['pce_mom']}% (年化)",
                "白話意思": "通膨達標，官員較願意考慮降息" if m['pce_mom'] <= 2.5 else "通膨稍微偏頑固，不敢太快降息"
            },
            {
                "指標 (白話說明)": "失業率 (大家有沒有工作)",
                "最新數值": f"{m['unrate_cur']}%",
                "近期3個月動向": f"{m['unrate_diff']:+.2f}% (月增)",
                "白話意思": "就業非常強，不怕失業" if m['unrate_cur'] <= 4.0 else ("就業很健康穩健" if m['unrate_cur'] <= 4.3 else "找工作開始變難了")
            },
            {
                "指標 (白話說明)": "VIX 恐慌指數 (股市心跳指數)",
                "最新數值": f"{m['vix_cur']}",
                "近期3個月動向": f"{m['vix_diff']:+.2f} 點",
                "白話意思": "市場風平浪靜，適合穩健收租" if m['vix_cur'] < 20 else "市場大震盪，大家都在買保險避險"
            }
        ]
        st.dataframe(pd.DataFrame(matrix_rows), use_container_width=True, hide_index=True)

    st.markdown("---")

    # ==========================================
    # 2. 利率結構視覺化 (直觀圖表)
    # ==========================================
    st.markdown("#### 📈 美債長短天期利率一覽")
    col_chart, col_curve_info = st.columns([1.6, 1.0])

    with col_chart:
        fig_curve = go.Figure()
        terms = ["2年期 (短期政策)", "10年期 (長期基準)", "長短利差 (倒掛指標)", "實質利率 (扣除通膨)"]
        vals = [m["dgs2_cur"], m["dgs10_cur"], m["t10y2y_cur"], m["dfii10_cur"]]
        colors = ["#268bd2", "#2aa198", "#d33682" if m["t10y2y_cur"] < 0 else "#27ae60", "#f39c12"]

        fig_curve.add_trace(go.Bar(
            x=terms,
            y=vals,
            text=[f"{v:.2f}%" for v in vals],
            textposition="auto",
            marker_color=colors
        ))
        fig_curve.update_layout(
            height=280,
            margin=dict(l=20, r=20, t=30, b=20),
            paper_bgcolor="#161922",
            plot_bgcolor="#161922",
            font=dict(color="#e6edf3"),
            yaxis=dict(title="利率水準 (%)", gridcolor="#2d3139"),
            xaxis=dict(gridcolor="#2d3139")
        )
        st.plotly_chart(fig_curve, use_container_width=True)

    with col_curve_info:
        st.markdown(f"""
        <div style="background-color: #1a1e29; border: 1px solid #2d3139; border-radius: 8px; padding: 16px; font-size: 13px; line-height: 1.8; color: #c9d1d9;">
            <div style="font-weight: bold; color: #58a6ff; font-size: 14px; margin-bottom: 8px;">
                💡 30 秒白話讀懂這張圖
            </div>
            1. <b>借錢基準</b>：10年期美債在 <b>{m['dgs10_cur']}%</b>。銀行房貸、大企業發債都要加這個數字當底標。<br>
            2. <b>利差看景氣</b>：正常情況借錢越久、利息要越高。現在利差為 <b>{m['t10y2y_cur']}%</b>（{curve_signal}）。<br>
            3. <b>黃金與資產天敵</b>：實質利率高達 <b>{m['dfii10_cur']}%</b>，借錢放在銀行拿真利息就很誘人，這會讓不生利息的黃金與高估值股票受到壓抑。
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ==========================================
    # 3. 聯準會九宮格自動定位 (白話生活化說明)
    # ==========================================
    pce_val = m['pce_mom']
    unrate_val = m['unrate_cur']

    if unrate_val <= 4.0:
        labor_label = "就業旺 (失業率 ≤ 4.0%)"
        target_row = 0
    elif unrate_val <= 4.4:
        labor_label = "就業穩 (失業率 4.1%~4.4%)"
        target_row = 1
    else:
        labor_label = "就業疲 (失業率 > 4.4%)"
        target_row = 2

    if pce_val > 2.9:
        inf_label = "通膨熱 (>2.9%)"
        target_col = 2
    elif pce_val >= 2.3:
        inf_label = "通膨溫 (2.3%~2.9%)"
        target_col = 1
    else:
        inf_label = "通膨涼 (<2.3%)"
        target_col = 0

    col_grid, col_trans = st.columns([1.2, 1.3])

    with col_grid:
        st.markdown(f"#### 🎯 聯準會現在處在哪裡？ (【{labor_label.split(' ')[0]} × {inf_label.split(' ')[0]}】)")
        grid_matrix = [
            ["溫和成長", "小心觀望", "升息壓力"],
            ["預防性降息", "按兵不動", "兩難困境"],
            ["衰退式降息", "轉向降息", "停滯性通膨"]
        ]
        row_headers = ["【工作很好找 (低失業)】", "【就業算正常 (中失業)】", "【找工作變難 (高失業)】"]
        col_headers = ["物價舒服 (<2.3%)", "物價還好 (2.3%~2.9%)", "物價很貴 (>2.9%)"]

        table_html = """
        <table style="width:100%; border-collapse: collapse; font-size: 13px; text-align: center; background-color: #161922; border-radius: 8px; overflow: hidden; border: 1px solid #2d3139;">
            <thead>
                <tr style="background-color: #1f2430; color: #8b949e; border-bottom: 2px solid #2d3139;">
                    <th style="padding: 10px; border-right: 1px solid #2d3139;">就業狀況 \\ 物價漲勢</th>
        """
        for ch in col_headers:
            table_html += f"<th style='padding: 10px; border-right: 1px solid #2d3139;'>{ch}</th>"
        table_html += "</tr></thead><tbody>"

        for r in range(3):
            table_html += f"<tr><td style='padding: 10px 8px; font-weight: bold; background-color: #1a1e29; color: #c9d1d9; border-right: 1px solid #2d3139; border-bottom: 1px solid #2d3139;'>{row_headers[r]}</td>"
            for c in range(3):
                is_cur = (r == target_row and c == target_col)
                if is_cur:
                    bg = "rgba(0, 204, 150, 0.25)"
                    border_style = "border: 2px solid #00cc96;"
                    text_color = "#00ffbe; font-weight: bold;"
                    marker = "<br><span style='font-size:10px; color:#00ffbe;'>📍[現在位置]</span>"
                else:
                    bg = "transparent"
                    border_style = "border-right: 1px solid #2d3139; border-bottom: 1px solid #2d3139;"
                    text_color = "#e6edf3;"
                    marker = ""
                table_html += f"<td style='padding: 9px 6px; background-color: {bg}; color: {text_color}; {border_style}'>{grid_matrix[r][c]}{marker}</td>"
            table_html += "</tr>"

        table_html += "</tbody></table>"
        st.markdown(table_html, unsafe_allow_html=True)

    with col_trans:
        st.markdown("#### ⚡ 跨市場實戰白話指引 (現在該怎麼投資？)")
        st.markdown(f"""
        <div style="background-color: #0d2820; border: 1px solid #00cc96; border-radius: 8px; padding: 14px 18px; color: #ffffff; min-height: 220px; font-size: 13px; line-height: 1.8;">
            <div style="font-weight: bold; color: #00cc96; font-size: 14px; margin-bottom: 6px;">
                【五大市場快速白話指南：美債 {m['dgs10_cur']}% × 實質利率 {m['dfii10_cur']}%】
            </div>
            • 🏛️ <b>債券 (固定利息)：</b> 現在 10 年美債有接近 5% 左右的收益，買中天期公債 (約5~7年) 鎖住利息很香，不用過度賭太長期的債券避免波動過大。<br>
            • 📈 <b>股票 (美股/台股)：</b> 借錢成本高時，只會講夢想、沒賺現金的公司會很慘；多挑選「現金流滿滿、賺錢容易」的大龍頭公司。<br>
            • 🪙 <b>黃金與商品：</b> 實質利率在高檔，拿現金放銀行都很划算，黃金不要盲目追高，維持 5~8% 當作打仗或亂世防身保險就好。<br>
            • 💵 <b>外匯 (美金換日圓)：</b> 美日利息差還是很大，美金依舊強勢；但要隨時留意若美國真要快速降息，日圓可能快速升值，要設好停損。<br>
            • 🛡️ <b>選擇權策略：</b> 恐慌指數 VIX 目前為 {m['vix_cur']}，市場波動不大，適合穩穩賣出價差合約收時間租金。
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # ==========================================
    # 4. 首席宏觀策略官 (Gemini AI Global Macro Strategist)
    # ==========================================
    st.markdown("#### 🤖 首席宏觀策略官 (AI 深入研報生成)")
    st.caption("研報將保持華爾街投行級的嚴謹計量術語，同時在每個核心結論後附上白話解讀。")
    if st.button("🚀 產出機構級深度研究報告", key="btn_macro_ai_upgrade"):
        if not api_key:
            st.error("請在側邊欄設定 Gemini API Key！")
        else:
            with st.spinner("首席宏觀策略官正在整合美債殖利率曲線、實質利率與全球流動性..."):
                try:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    prompt = f"""
                    你是一位華爾街頂級對衝基金的 Chief Global Macro Strategist（首席全球宏觀策略官）。
                    請根據以下即時數據進行深度跨資產研報分析：
                    - 10 年期美債殖利率 (DGS10)：{m['dgs10_cur']}% (1D 變化 {m['dgs10_diff']:+.2f}%)
                    - 2 年期美債殖利率 (DGS2)：{m['dgs2_cur']}% (1D 變化 {m['dgs2_diff']:+.2f}%)
                    - 10Y - 2Y 殖利率利差 (T10Y2Y)：{m['t10y2y_cur']}% (形態：{curve_signal})
                    - 10 年期 TIPS 實質利率 (DFII10)：{m['dfii10_cur']}%
                    - 高收益債信用利差：{m['hy_spread_cur']}%
                    - 總體 CPI 3M 年化動量：{m['cpi_mom']}%
                    - 核心 PCE 3M 年化動量：{m['pce_mom']}%
                    - 官方失業率：{m['unrate_cur']}% (MoM 變化 {m['unrate_diff']:+.2f}%)
                    - CBOE VIX 恐慌指數：{m['vix_cur']}
                    - 聯準會九宮格定位：【{labor_label.split(' ')[0]} x {inf_label.split(' ')[0]}】

                    【格式與風格要求】：
                    1. 保持華爾街投行級專業深度，詳細分析（利差期限結構、折現率、實質利率傳導）。
                    2. **重點要求**：在每個章節或核心推論結尾，務必用【白話大白話總結】附上一句大眾能懂的白話解讀，說明這對投資人錢包到底有何影響。
                    3. 內容需包含：
                       - 美債曲線與景氣衰退預警
                       - 聯準會基準利率路徑推算
                       - 跨資產（股票、債券存續期、黃金商品、外匯 Carry）配置百分比與操作建議
                    """
                    res = model.generate_content(prompt)
                    st.info(res.text)
                except Exception as e:
                    st.error(f"連線失敗: {e}")

    st.markdown("---")

    # ==========================================
    # 5. Yahoo Finance 全球即時財經頭條
    # ==========================================
    st.markdown("#### 📰 即時全球財經頭條")
    news_list = fetch_yahoo_finance_news()

    if not news_list:
        st.info("暫無即時新聞或連線載入中...")
    else:
        for idx, item in enumerate(news_list[:5]):
            st.markdown(f"""
            <div style="background-color: #161922; border-left: 4px solid #00cc96; padding: 14px 18px; border-radius: 6px; margin-bottom: 12px; border-top: 1px solid #232733; border-right: 1px solid #232733; border-bottom: 1px solid #232733;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                    <div style="font-size: 15px; font-weight: bold; color: #ffffff; line-height: 1.4; margin-bottom: 6px;">
                        📌 {item['title']}
                    </div>
                    <span style="font-size: 11px; color: #8b949e; white-space: nowrap; margin-left: 15px; background: #212634; padding: 2px 8px; border-radius: 4px;">
                        🕒 {item['date']}
                    </span>
                </div>
                <div style="font-size: 13px; color: #a0aec0; line-height: 1.5; margin-top: 4px; margin-bottom: 8px;">
                    【白話重點解讀】該事件涉及重要資金與市場流向，可能連帶影響科技股與大盤短期波動。
                </div>
                <div>
                    <a href="{item['link']}" target="_blank" style="color: #00cc96; text-decoration: none; font-size: 13px; font-weight: 600; display: inline-flex; align-items: center;">
                        🔗 點擊閱讀 Yahoo Finance 完整原始報導 &rarr;
                    </a>
                </div>
            </div>
            """, unsafe_allow_html=True)
