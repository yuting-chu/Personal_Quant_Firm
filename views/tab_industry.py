#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Personal Quant Firm | 產業研究與跨資產傳導中心 (Tab 2: Industry & Sector Macro Transmission)
========================================================================================
功能：
1. 宏觀向 11 大 S&P 產業板塊傳導雷達 (Macro-to-Sector Transmission Engine)：
   代入美聯儲淨流動性、薩姆衰退指標、殖利率利差與降息週期，推導 11 大板塊之宏觀適應度與推薦權重。
2. 跨資產防禦與對衝疊加建議 (Cross-Asset Macro Overlay)：TLT 長債、GLD 黃金與日圓 Carry。
3. 產業鏈跨市場即時圖表聯動 (TradingView Charting)。
4. 首席跨資產產業研究員 Agent (Gemini-3.6-flash 自動容錯推理)。
"""

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import os

from modules.tradingview import render_tv_chart
from modules.ai_engine import generate_content_with_fallback
from views.tab_macro import fetch_macro_matrix

# 11 大 S&P 500 精選行業 ETF 官方標的
SECTOR_ETFS = {
    "XLK": "資訊科技 (Technology)",
    "XLC": "通訊服務 (Communication)",
    "XLY": "非必需消費 (Discretionary)",
    "XLF": "金融 (Financials)",
    "XLI": "工業 (Industrials)",
    "XLV": "醫療保健 (Healthcare)",
    "XLP": "必需消費 (Staples)",
    "XLE": "能源 (Energy)",
    "XLB": "原物料 (Materials)",
    "XLRE": "房地產 (Real Estate)",
    "XLU": "公用事業 (Utilities)"
}

# 11 大板塊對宏觀因子的學理與計量敏感度矩陣 (Macro Factor Betas)
SECTOR_MACRO_BETAS = {
    "XLK": {"name": "資訊科技 (Technology)", "liq": 0.85, "sahm": -0.60, "curve": -0.20, "rate": -0.40, "inf": 0.10, "driver": "淨流動性擴張與 AI 算力資本支出 (CapEx)"},
    "XLC": {"name": "通訊服務 (Communication)", "liq": 0.70, "sahm": -0.50, "curve": -0.10, "rate": -0.30, "inf": 0.05, "driver": "數位廣告預算復甦與大型成長股估值擴張"},
    "XLY": {"name": "非必需消費 (Discretionary)", "liq": 0.60, "sahm": -0.85, "curve": 0.20, "rate": -0.35, "inf": -0.20, "driver": "就業市場韌性與消費者耐久財支出意願"},
    "XLF": {"name": "金融 (Financials)", "liq": 0.20, "sahm": -0.70, "curve": 0.80, "rate": 0.20, "inf": 0.10, "driver": "殖利率曲線陡峭化與商業銀行淨利差 (NIM) 走闊"},
    "XLI": {"name": "工業 (Industrials)", "liq": 0.35, "sahm": -0.75, "curve": 0.40, "rate": -0.20, "inf": 0.20, "driver": "全球製造業補庫存週期與實體基建投資"},
    "XLE": {"name": "能源 (Energy)", "liq": 0.10, "sahm": -0.30, "curve": 0.30, "rate": 0.10, "inf": 0.85, "driver": "WTI 原油現貨價格與大宗商品再通膨定價"},
    "XLB": {"name": "原物料 (Materials)", "liq": 0.25, "sahm": -0.65, "curve": 0.35, "rate": -0.10, "inf": 0.65, "driver": "上游基礎工業原料需求與美元走勢反饋"},
    "XLV": {"name": "醫療保健 (Healthcare)", "liq": -0.10, "sahm": 0.75, "curve": -0.10, "rate": -0.15, "inf": 0.00, "driver": "非景氣循環剛性需求與穩健現金流防禦"},
    "XLP": {"name": "必需消費 (Staples)", "liq": -0.20, "sahm": 0.85, "curve": -0.20, "rate": -0.20, "inf": 0.10, "driver": "民生必需終端支出與低 Beta 抗衰退壓艙石"},
    "XLU": {"name": "公用事業 (Utilities)", "liq": -0.30, "sahm": 0.70, "curve": -0.40, "rate": -0.75, "inf": -0.20, "driver": "降息週期資產重估與高股息債券替代屬性 (Bond-Proxy)"},
    "XLRE": {"name": "房地產 (Real Estate)", "liq": 0.40, "sahm": -0.55, "curve": 0.30, "rate": -0.80, "inf": 0.15, "driver": "基準利率下行帶動房貸再融資與不動產評價修復"}
}

INDUSTRY_CHAINS = {
    "🤖 AI、半導體與硬體算力鏈": {
        "sector_code": "XLK",
        "macro_asset": "FX_IDC:USDJPY",
        "macro_name": "上游關鍵匯率：USD/JPY (設備與亞洲供應鏈成本)",
        "equity_asset": "NASDAQ:NVDA",
        "equity_name": "核心標的現貨：NVDA (AI 晶片與資料中心龍頭)",
        "desc": "科技 CapEx 擴張帶動硬體需求；美日利差與日圓走勢直接影響半導體供應鏈設備採購與匯兌損益。"
    },
    "🛢️ 傳統能源、原物料與通膨鏈": {
        "sector_code": "XLE",
        "macro_asset": "TVC:USOIL",
        "macro_name": "上游大宗商品：WTI 原油期貨 (能源通膨定價指標)",
        "equity_asset": "AMEX:XLE",
        "equity_name": "核心板塊 ETF：XLE (能源精煉與油田服務)",
        "desc": "油價直接決定 XLE 能源板塊自由現金流；原油上漲亦會推升 PPI 批發物價，限制 Fed 降息空間。"
    },
    "🪙 宏觀避險、貨幣信用與黃金鏈": {
        "sector_code": "XLB",
        "macro_asset": "OANDA:XAUUSD",
        "macro_name": "大宗定價基準：XAU/USD 現貨黃金 (實質利率抗通膨資產)",
        "equity_asset": "AMEX:SPY",
        "equity_name": "基準股指：SPY (美股大盤信用偏好)",
        "desc": "實質利率下行與地緣風險推升金價；黃金與大盤股指的相對強弱反映市場避險情緒。"
    },
    "🚗 汽車製造、消費與工業鏈": {
        "sector_code": "XLY",
        "macro_asset": "FX_IDC:EURUSD",
        "macro_name": "全球貿易匯率：EUR/USD (歐美消費與製造業動量)",
        "equity_asset": "NASDAQ:TSLA",
        "equity_name": "核心標的：TSLA (電動車、儲能與自駕)",
        "desc": "歐美貨幣購買力與工業金屬成本直接影響耐用消費品需求與車廠毛利率。"
    }
}


def load_and_calculate_sectors():
    """
    抓取 11 大板塊與 SPY 大盤近 3 個月歷史行情，向量化計算 1 個月絕對報酬與相對 SPY 超額 Alpha。
    """
    symbols = list(SECTOR_ETFS.keys()) + ["SPY"]
    rows = []
    
    try:
        raw = yf.download(symbols, period="3mo", interval="1d", progress=False)
        if raw is not None and not raw.empty:
            close_df = raw['Close'] if 'Close' in raw.columns else raw
            close_df = close_df.dropna(how='all').ffill().bfill()
            
            num_rows = len(close_df)
            lookback_idx = max(0, num_rows - 22)
            
            p_latest = close_df.iloc[-1]
            p_base = close_df.iloc[lookback_idx]
            
            ret_series = ((p_latest / p_base) - 1) * 100
            spy_benchmark = float(ret_series.get('SPY', 2.15))
            if pd.isna(spy_benchmark):
                spy_benchmark = 2.15
            
            for sym, name in SECTOR_ETFS.items():
                r_val = float(ret_series.get(sym, 1.50))
                if pd.isna(r_val):
                    r_val = 1.50
                rows.append({
                    "代碼": sym,
                    "產業板塊": name,
                    "近 1 個月報酬 (%)": round(r_val, 2),
                    "1M 相對 SPY 超額 (%)": round(r_val - spy_benchmark, 2)
                })
    except Exception:
        pass

    # 備援兜底數據，確保前端極端網絡異常時亦能正常呈現
    if not rows:
        fallback = {
            "XLK": (4.62, 2.47), "XLC": (3.85, 1.70), "XLF": (2.94, 0.79),
            "XLI": (2.30, 0.15), "XLY": (1.78, -0.37), "XLV": (1.15, -1.00),
            "XLP": (0.82, -1.33), "XLU": (0.45, -1.70), "XLB": (-0.25, -2.40),
            "XLRE": (-0.88, -3.03), "XLE": (-1.55, -3.70)
        }
        for sym, (r_val, a_val) in fallback.items():
            rows.append({
                "代碼": sym,
                "產業板塊": SECTOR_ETFS[sym],
                "近 1 個月報酬 (%)": r_val,
                "1M 相對 SPY 超額 (%)": a_val
            })
            
    return pd.DataFrame(rows).sort_values(by="1M 相對 SPY 超額 (%)", ascending=False).reset_index(drop=True)


def calculate_macro_sector_allocation(macro_matrix: dict, sector_df: pd.DataFrame):
    """
    【核心計量傳導模型】：
    將美聯儲淨流動性、薩姆規則、殖利率利差與降息姿態，透過多因子敏感度反應函數，
    動態評估 11 大板塊之宏觀適應度評分 (Macro Regime Score) 與推薦配置權重 (Target Weight %)。
    """
    if isinstance(macro_matrix, tuple):
        macro_matrix = macro_matrix[0] if len(macro_matrix) > 0 else {}
    if not isinstance(macro_matrix, dict):
        macro_matrix = {}

    net_liq_diff = float(macro_matrix.get('net_liq_diff', 0.024))
    sahm_val = float(macro_matrix.get('sahm_val', 0.00))
    t10y2y = float(macro_matrix.get('t10y2y_cur', 0.05))
    dff = float(macro_matrix.get('dff_cur', 3.88))
    cpi_mom = float(macro_matrix.get('cpi_mom', 2.40))
    sb_corr = float(macro_matrix.get('stock_bond_corr', 0.12))
    dfii10 = float(macro_matrix.get('dfii10_cur', 1.85))

    # 1. 判定當前全域宏觀情境 (Macro Regime)
    if sahm_val >= 0.50:
        regime_title = "🚨 衰退防禦週期 (Recession Shock / Risk-Off)"
        regime_desc = f"薩姆衰退指標觸發警報 ({sahm_val:.2f}% ≥ 0.50%)。歷史經驗顯示景氣急轉直下，市場由擴張轉向硬著陸防禦，必需消費與醫療為避風港。"
    elif t10y2y < -0.20:
        regime_title = "⚠️ 深度倒掛壓制期 (Inverted Yield Curve / Late-Cycle)"
        regime_desc = f"美債長短天期利差倒掛 ({t10y2y:.2f}%)，融資成本高企壓制資本支出與房地產，防禦性資產相對佔優。"
    elif net_liq_diff >= 0 and t10y2y >= 0:
        regime_title = "🌊 流動性擴張與金髮女孩軟著陸 (Goldilocks Liquidity Expansion)"
        regime_desc = f"美聯儲淨水庫水位週回升 ({net_liq_diff:+.3f}T) 且殖利率曲線修復解除倒掛 ({t10y2y:+.2f}%)。流動性充裕有利科技成長與高 Beta 板塊。"
    else:
        regime_title = "⚖️ 溫和過渡與降息預期博弈期 (Easing Transition Regime)"
        regime_desc = f"基準利率進入降息軌道 (DFF {dff:.2f}%)，流動性水位波動整理，宜採取股債均衡與優質板塊啞鈴式配置。"

    # 2. 宏觀因子信號標準化 (Normalized Factor Signals: [-1.0, 1.0])
    liq_f = float(np.clip(net_liq_diff * 8.0, -1.0, 1.0))
    sahm_f = 1.0 if sahm_val >= 0.50 else -0.50
    curve_f = float(np.clip(t10y2y * 2.0, -1.0, 1.0))
    rate_f = float(np.clip((5.50 - dff) / 2.0, -1.0, 1.0)) # 利率愈低，降息刺激力愈大
    inf_f = float(np.clip((cpi_mom - 2.0) / 2.0, -1.0, 1.0))

    # 3. 各板塊多因子加權評分
    alpha_map = dict(zip(sector_df['代碼'], sector_df['1M 相對 SPY 超額 (%)']))
    ret_map = dict(zip(sector_df['代碼'], sector_df['近 1 個月報酬 (%)']))

    results = []
    for sym, b in SECTOR_MACRO_BETAS.items():
        # 學理因子打分
        raw_score = (
            b['liq'] * liq_f +
            b['sahm'] * sahm_f +
            b['curve'] * curve_f +
            b['rate'] * rate_f +
            b['inf'] * inf_f
        )
        # 結合近 1 個月實際市場動量 Alpha 作為確認
        alpha_val = alpha_map.get(sym, 0.0)
        ret_val = ret_map.get(sym, 0.0)
        combined_score = round(0.70 * raw_score + 0.30 * (alpha_val / 5.0), 2)

        results.append({
            "代碼": sym,
            "產業板塊": b['name'],
            "宏觀適應評分": combined_score,
            "近 1M 報酬 (%)": ret_val,
            "近 1M 相對 SPY (%)": alpha_val,
            "核心驅動因子": b['driver']
        })

    out_df = pd.DataFrame(results).sort_values(by="宏觀適應評分", ascending=False).reset_index(drop=True)

    # 4. 動態計算推薦配置權重 (Target Weights %, 基準 9.09%，依評分線性調權後歸一化至 100%)
    base_w = 9.09
    raw_weights = np.maximum(2.5, base_w + out_df['宏觀適應評分'] * 5.5)
    normalized_weights = np.round((raw_weights / raw_weights.sum()) * 100, 1)
    # 微調誤差保證加總剛好 100%
    normalized_weights[0] += round(100.0 - float(normalized_weights.sum()), 1)
    out_df['建議配置比重 (%)'] = normalized_weights

    # 5. 標註 IC 投資委員會姿態
    def assign_stance(sc):
        if sc >= 0.45:
            return "🟢 強烈超配 (Overweight)"
        elif sc >= 0.15:
            return "🟢 溫和超配 (Mild OW)"
        elif sc >= -0.15:
            return "⚪ 中性標配 (Market Weight)"
        elif sc >= -0.45:
            return "🟠 溫和低配 (Mild UW)"
        else:
            return "🔴 防禦低配 (Underweight)"

    out_df['配置決議 (IC Stance)'] = out_df['宏觀適應評分'].apply(assign_stance)

    # 6. 跨資產對衝指引 (Cross-Asset Macro Overlays)
    if sb_corr < 0:
        tlt_rec = f"🟢 **長天期美債 (TLT) 避險強效**：股債滾動相關係數處於負值 (ρ={sb_corr:+.2f})，股債對衝互補性良好，建議配置 20%~25% 長債以捕捉降息資本利得。"
    else:
        tlt_rec = f"🟡 **股債同向 (雙殺防禦)**：股債相關係數翻正 (ρ={sb_corr:+.2f})，長債無法有效對衝美股拉回，建議將存續期縮短至短天期國庫券 (BIL/SGOV，10%~15%)。"

    gld_rec = f"🪙 **實質利率抗通膨 (GLD)**：10 年期 TIPS 實質利率為 {dfii10:.2f}%，通膨動量 {cpi_mom:.1f}%，建議配置 5%~10% 黃金現貨或相關 ETF 作為地緣政治與貨幣信用保險。"
    jpy_rec = f"💴 **外匯 Carry Trade 對衝**：美日利差約 +{dff - 0.25:.2f}%，USD/JPY 處於高檔震盪。當日圓突破 150 關卡時，需防範套息資金急解踩踏，科技股建議搭配 OTM Put 對衝。"

    overlay_info = {
        "regime_title": regime_title,
        "regime_desc": regime_desc,
        "tlt_rec": tlt_rec,
        "gld_rec": gld_rec,
        "jpy_rec": jpy_rec,
        "net_liq": float(macro_matrix.get('net_liq', 5.79)),
        "net_liq_diff": net_liq_diff,
        "sahm_val": sahm_val,
        "t10y2y": t10y2y,
        "dff": dff,
        "sb_corr": sb_corr
    }

    return out_df, overlay_info


def render(api_key: str):
    st.subheader("🏭 產業鏈跨資產聯動研究室 (產業 × 宏觀傳導 × 大宗商品)")
    st.caption("突破單一選股局限：將美聯儲淨水庫水位、薩姆衰退指標與殖利率曲線，精確計量傳導至 11 大 S&P 板塊與關鍵大宗供應鏈。")

    # 讀取 FRED API Key (優先從 session_state，其次由環境變數注入)
    fred_key = st.session_state.get('fred_key', '') or os.getenv('FRED_API_KEY', '').strip()
    res = fetch_macro_matrix(fred_key)
    macro_matrix = res[0] if isinstance(res, tuple) else res
    sector_df = load_and_calculate_sectors()

    # 執行宏觀向 11 大板塊計量傳導模型
    allocation_df, overlay = calculate_macro_sector_allocation(macro_matrix, sector_df)

    # ==========================================
    # 1. 🌊 宏觀流動性與景氣週期板塊配置雷達
    # ==========================================
    st.markdown("#### 🌊 宏觀流動性與景氣週期板塊配置雷達 (Macro-to-Sector Transmission Engine)")
    
    # 宏觀情境橫幅
    st.markdown(
        f"""
        <div style="background-color: #1a1d28; border-left: 4px solid #3182ce; padding: 12px 16px; border-radius: 6px; margin-bottom: 12px;">
            <div style="font-size: 15px; font-weight: 700; color: #63b3ed;">{overlay['regime_title']}</div>
            <div style="font-size: 13px; color: #cbd5e0; margin-top: 4px; line-height: 1.5;">{overlay['regime_desc']}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 四大底層宏觀核心指標卡片
    c_m1, c_m2, c_m3, c_m4 = st.columns(4)
    with c_m1:
        st.metric(
            "美聯儲淨水庫總量",
            f"${overlay['net_liq']:.3f}T",
            f"{overlay['net_liq_diff']:+.3f}T 週變動",
            help="Net Liquidity = Fed 總資產 (WALCL) - 財政部 TGA - 隔夜逆回購 (RRP)"
        )
    with c_m2:
        sahm_color = "🟢 安全" if overlay['sahm_val'] < 0.5 else "🚨 警報"
        st.metric(
            f"薩姆衰退指標 ({sahm_color})",
            f"{overlay['sahm_val']:.2f}%",
            "臨界門檻 0.50%",
            delta_color="inverse"
        )
    with c_m3:
        st.metric(
            "10Y - 2Y 殖利率利差",
            f"{overlay['t10y2y']:+.2f}%",
            "正常陡峭化" if overlay['t10y2y'] >= 0 else "利差倒掛",
            delta_color="normal"
        )
    with c_m4:
        corr_status = "負相關避險有效" if overlay['sb_corr'] < 0 else "正相關同向波動"
        st.metric(
            "股債 60D 相關係數",
            f"{overlay['sb_corr']:+.2f}",
            corr_status,
            delta_color="normal" if overlay['sb_corr'] < 0 else "off"
        )

    st.markdown("##### 📋 11 大 S&P 板塊宏觀適應度評分與動態權重推薦表")
    st.dataframe(
        allocation_df[[
            '代碼', '產業板塊', '宏觀適應評分', '配置決議 (IC Stance)', 
            '建議配置比重 (%)', '近 1M 報酬 (%)', '近 1M 相對 SPY (%)', '核心驅動因子'
        ]],
        use_container_width=True,
        hide_index=True
    )

    # 兩大對比圖表：宏觀推薦權重 vs 近 1 個月市場 Alpha
    col_w_chart, col_alpha_chart = st.columns([1.1, 1.2])
    
    with col_w_chart:
        st.markdown("##### ⚖️ 宏觀輪動建議權重分佈 (%)")
        fig_w = px.bar(
            allocation_df.sort_values(by="建議配置比重 (%)", ascending=True),
            x="建議配置比重 (%)",
            y="代碼",
            orientation='h',
            color="宏觀適應評分",
            color_continuous_scale="Blues",
            hover_data=["產業板塊", "配置決議 (IC Stance)"]
        )
        fig_w.update_layout(
            template="plotly_dark",
            height=340,
            margin=dict(l=10, r=10, t=10, b=10),
            yaxis={'categoryorder': 'total ascending'}
        )
        st.plotly_chart(fig_w, use_container_width=True)

    with col_alpha_chart:
        st.markdown("##### 📊 近 1 個月市場實際超額 Alpha vs SPY (%)")
        fig_a = px.bar(
            allocation_df.sort_values(by="近 1M 相對 SPY (%)", ascending=True),
            x="近 1M 相對 SPY (%)",
            y="代碼",
            orientation='h',
            color="近 1M 相對 SPY (%)",
            color_continuous_scale="Temps",
            hover_data=["產業板塊", "近 1M 報酬 (%)"]
        )
        fig_a.update_layout(
            template="plotly_dark",
            height=340,
            margin=dict(l=10, r=10, t=10, b=10),
            yaxis={'categoryorder': 'total ascending'}
        )
        st.plotly_chart(fig_a, use_container_width=True)

    st.markdown("---")

    # ==========================================
    # 2. 🛡️ 跨資產防禦與對衝疊加建議 (Cross-Asset Macro Overlay)
    # ==========================================
    st.markdown("#### 🛡️ 跨資產防禦與對衝疊加建議 (Cross-Asset Overlay)")
    c_ov1, c_ov2, c_ov3 = st.columns(3)
    with c_ov1:
        st.markdown(
            f"""
            <div style="background-color: #1a1d24; padding: 12px; border-radius: 6px; border: 1px solid #2d3748; min-height: 110px;">
                <div style="font-size: 13px; font-weight: 600; color: #63b3ed;">🏛️ 美債長天期 Duration 指引 (TLT)</div>
                <div style="font-size: 12px; color: #a0aec0; margin-top: 6px; line-height: 1.5;">{overlay['tlt_rec']}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with c_ov2:
        st.markdown(
            f"""
            <div style="background-color: #1a1d24; padding: 12px; border-radius: 6px; border: 1px solid #2d3748; min-height: 110px;">
                <div style="font-size: 13px; font-weight: 600; color: #ecc94b;">🪙 黃金與貨幣信用儲備 (GLD)</div>
                <div style="font-size: 12px; color: #a0aec0; margin-top: 6px; line-height: 1.5;">{overlay['gld_rec']}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with c_ov3:
        st.markdown(
            f"""
            <div style="background-color: #1a1d24; padding: 12px; border-radius: 6px; border: 1px solid #2d3748; min-height: 110px;">
                <div style="font-size: 13px; font-weight: 600; color: #ed8936;">💴 USD/JPY 套息踩踏風控 (Carry)</div>
                <div style="font-size: 12px; color: #a0aec0; margin-top: 6px; line-height: 1.5;">{overlay['jpy_rec']}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("---")

    # ==========================================
    # 3. 🔗 產業鏈跨市場即時圖表聯動
    # ==========================================
    st.markdown("#### 🔗 產業鏈跨市場即時圖表聯動")
    selected_chain = st.selectbox("選擇要深度審查的產業鏈條：", list(INDUSTRY_CHAINS.keys()), index=0)
    chain_info = INDUSTRY_CHAINS[selected_chain]
    
    st.info(f"💡 **產業鏈傳導邏輯：** {chain_info['desc']}")

    col_macro_chart, col_eq_chart = st.columns(2)
    with col_macro_chart:
        st.markdown(f"##### 🌐 {chain_info['macro_name']}")
        render_tv_chart(symbol=chain_info['macro_asset'], height=340)

    with col_eq_chart:
        st.markdown(f"##### 📊 {chain_info['equity_name']}")
        render_tv_chart(symbol=chain_info['equity_asset'], height=340)

    st.markdown("---")

    # ==========================================
    # 4. 🤖 首席跨資產產業研究員 Agent (升級版)
    # ==========================================
    st.markdown("#### 🤖 首席跨資產產業研究員 Agent (全自動宏觀參數注入)")
    st.caption("AI Agent 將自動提取上方宏觀淨水庫水位、薩姆衰退指標與當前板塊評分，產出機構級產業鏈跨資產定價報告。")

    target_sec_code = chain_info.get("sector_code", "XLK")
    matched_sec_row = allocation_df[allocation_df['代碼'] == target_sec_code]
    sec_macro_score = matched_sec_row['宏觀適應評分'].values[0] if not matched_sec_row.empty else 0.0
    sec_stance = matched_sec_row['配置決議 (IC Stance)'].values[0] if not matched_sec_row.empty else "中性"
    sec_weight = matched_sec_row['建議配置比重 (%)'].values[0] if not matched_sec_row.empty else 9.1

    ind_q = st.text_input(
        "輸入跨市場產業問題：",
        f"在當前宏觀情境【{overlay['regime_title']}】下，【{selected_chain}】的上游商品/匯率如何傳導至個股定價與選擇權波動率？"
    )

    if st.button("🚀 向跨資產研究員發送分析請求", key="btn_ind_chain_ai_v2"):
        if not api_key:
            st.error("請在側邊欄設定 Gemini API Key！")
        else:
            with st.spinner("跨資產研究員正在整合宏觀情境、上游商品成本、匯率與個股選擇權曲面進行深度推演..."):
                try:
                    prompt = f"""
                    你是一位頂級全球跨資產對衝基金的 Senior Cross-Asset Equity Researcher（首席跨資產產業研究員）。
                    請針對以下產業鏈與當前底層宏觀計量指標，進行機構級的深度傳導分析：

                    【全域宏觀情境定位】：
                    - 宏觀週期：{overlay['regime_title']} ({overlay['regime_desc']})
                    - 美聯儲淨流動性總量：{overlay['net_liq']:.3f} 兆美元 (週變動 {overlay['net_liq_diff']:+.3f} 兆)
                    - 薩姆衰退指標：{overlay['sahm_val']:.2f}% (臨界值 0.50%)
                    - 10Y-2Y 殖利率曲線：{overlay['t10y2y']:+.2f}%
                    - 股債相關性 ρ(SPY, TLT)：{overlay['sb_corr']:+.2f}

                    【審查產業鏈條與板塊定位】：
                    - 研究鏈條：{selected_chain}
                    - 對應 S&P 板塊：{target_sec_code} (宏觀適應評分: {sec_macro_score:+.2f}, IC 建議姿態: {sec_stance}, 推薦權重: {sec_weight}%)
                    - 上游指標：{chain_info['macro_name']}
                    - 下游資產：{chain_info['equity_name']}
                    - 核心審查問題：{ind_q}

                    【報告輸出標準與章節要求】：
                    請依序產出專業研報，並於每個核心章節末尾附上【白話大白話總結】：
                    1. 【成本與匯率傳導機制】：上游大宗商品/匯率變動如何直接衝擊中下游供應鏈 CapEx、代工毛利與定價權。
                    2. 【跨資產隱含波動率 (IV Surface) 與偏斜 (Skew) 傳導】：匯率或大宗劇烈波動時，下游客戶端選擇權近遠月 IV 與 OTM Put 避險買盤如何演變。
                    3. 【跨市場高凸性與對衝策略 (Trade Ideas)】：具體給出如何結合現貨、外匯/大宗期貨與個股選擇權 (如 Collar, Dispersion, 或 Tail Risk Hedge) 建立非對稱報酬倉位。
                    4. 【研究員總結與風控清單】：列出 2 個關鍵監測臨界點 (Trigger Thresholds) 與相應部位減碼條件。
                    """
                    report_text = generate_content_with_fallback(api_key, prompt)
                    st.info(report_text)
                except Exception as e:
                    st.error(f"連線失敗: {e}")
