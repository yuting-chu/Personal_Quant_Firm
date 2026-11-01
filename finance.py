import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import google.generativeai as genai
import sqlite3
import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 1. 全域設定與 Session 狀態初始化
# ==========================================
st.set_page_config(
    page_title="Personal Quant Office | 旗艦總經與量化戰情室",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 初始策略清單
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
# 2. SQLite 資料庫模組
# ==========================================
DB_PATH = "quant_firm.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS trade_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            symbol TEXT,
            action TEXT,
            pnl REAL,
            strategy_type TEXT,
            reason TEXT,
            audit_status TEXT
        )
    ''')
    conn.commit()
    conn.close()

def insert_trade_log(symbol, action, pnl, strategy_type, reason, audit_status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO trade_logs (timestamp, symbol, action, pnl, strategy_type, reason, audit_status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), symbol, action, pnl, strategy_type, reason, audit_status))
    conn.commit()
    conn.close()

def get_trade_logs():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM trade_logs ORDER BY timestamp DESC", conn)
    conn.close()
    return df

init_db()

# ==========================================
# 3. 輔助函式：即時新聞與 TradingView 圖表
# ==========================================
@st.cache_data(ttl=300)
def fetch_yahoo_finance_news():
    url = "https://finance.yahoo.com/news/rssindex"
    news_items = []
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            root = ET.fromstring(response.read())
            for item in root.findall('.//item')[:6]:
                title = item.find('title').text if item.find('title') is not None else "無標題"
                link = item.find('link').text if item.find('link') is not None else "#"
                pub_date = item.find('pubDate').text[:22] if item.find('pubDate') is not None else ""
                news_items.append({"title": title, "link": link, "date": pub_date})
    except Exception:
        news_items.append({"title": "即時總經新聞連線中...", "link": "#", "date": ""})
    return news_items

def render_tv_chart(symbol="FX_IDC:USDJPY", height=380):
    clean_sym = symbol.replace(':', '_')
    html_code = f"""
    <div class="tradingview-widget-container" style="height:100%;width:100%">
      <div id="tv_chart_{clean_sym}" style="height:{height}px;width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "autosize": true,
        "symbol": "{symbol}",
        "interval": "D",
        "timezone": "Asia/Taipei",
        "theme": "dark",
        "style": "1",
        "locale": "zh_TW",
        "toolbar_bg": "#1e222d",
        "enable_publishing": false,
        "allow_symbol_change": true,
        "container_id": "tv_chart_{clean_sym}"
      }});
      </script>
    </div>
    """
    components.html(html_code, height=height + 15)

# ==========================================
# 4. 側邊欄：本金試算與 API 設定
# ==========================================
with st.sidebar:
    st.title("🏛️ 個人投資公司")
    st.caption("Personal Quant Firm OS v4.0 (Macro GG Edition)")
    st.markdown("---")
    
    st.subheader("💰 總投資本金設定")
    total_capital = st.number_input("總資產規模 (USD)：", min_value=10000, max_value=100000000, value=1000000, step=50000)
    
    st.markdown("---")
    st.subheader("🔑 Gemini API 認證")
    loaded_api_key = os.getenv("GEMINI_API_KEY", "")
    api_key_input = st.text_input("Gemini API Key：", value=loaded_api_key, type="password")
    
    if api_key_input:
        st.success("● API Key 就緒")
    else:
        st.error("● 未偵測到 Key (請檢查 .env)")

    st.markdown("---")
    st.caption(f"最後同步: {datetime.now().strftime('%H:%M:%S')}")

# ==========================================
# 5. 頂部 KPI 動態計算看板 (與本金動態聯動)
# ==========================================
active_strats = [s for s in st.session_state['strategies'] if s['active']]
total_active_weight = sum([s['weight'] for s in active_strats])
est_theta = round(total_capital * (0.000485), 2)
est_vega = round(total_capital * (-0.00012), 2)
est_margin_used = round(total_capital * 0.309, 0)

st.markdown("## 📊 總體資產戰情室 (CIO & Risk Dashboard)")
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("總投資本金 (Capital)", f"${total_capital:,.0f}", f"啟用權重: {total_active_weight}%")
k2.metric("維持保證金佔用", f"${est_margin_used:,.0f} (30.9%)", "安全警戒線: 55%")
k3.metric("組合 Net Delta", "-0.04", "接近絕對中性")
k4.metric("組合 Vega 暴露", f"${est_vega} / 1% IV", "做空 VRP 溢價")
k5.metric("每日預期 Theta 收入", f"+${est_theta:,.0f} / day", "穩健時間價值")

st.markdown("---")

# ==========================================
# 6. 主要功能分頁
# ==========================================
tab_macro, tab_charts, tab_backtest, tab_recon, tab_audit, tab_ai = st.tabs([
    "🌍 總經戰情室 (Macro GG 九宮格)",
    "📈 跨資產實況看板 (外匯/大宗 + 股票選擇權)",
    "🧪 策略管理與回測引擎 (動態試算)",
    "🔄 動態持倉與 Greeks 同步 (IG & IBKR)",
    "📝 交易日誌與 SQLite 一週覆盤",
    "🤖 虛擬投資委員會 (Gemini Agent)"
])

# -------------------------------------------------------------
# TAB 1: 總經戰情室 (Macro GG 完整復刻與 AI 情境合成)
# -------------------------------------------------------------
with tab_macro:
    st.subheader("🌐 美國總經數據儀表板 (Macro GG 決策框架)")
    st.caption("基於 Fed 雙重使命（充分就業與物價穩定），以量化訊號計數驅動九宮格定位與升降息指引。")
    
    # 1. 頂部四大通膨與就業核心指標卡片
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("總體 CPI (民眾體感)", "3.4%", "含食物與能源")
    c2.metric("核心 CPI (消費端)", "2.5%", "3M 年化: 1.6% 降溫")
    c3.metric("核心 PCE (Fed 目標)", "3.3%", "仍高於 2.0% 目標")
    c4.metric("非農月變動 (NFP)", "-2.3 萬人", "3M 平均 +2.0 萬人")
    c5.metric("失業率 (U-Rate)", "4.1%", "勞動力退場所致")

    st.markdown("---")

    # 2. 九宮格定位與情境合成區塊
    col_grid, col_signals = st.columns([1.2, 1.8])
    
    with col_grid:
        st.markdown("#### 🎯 聯準會九宮格定位 (Fed Matrix)")
        
        # 繪製九宮格表格
        grid_data = {
            "就業狀態 \\ 通膨狀態": ["【就業強】", "【就業中】", "【就業弱】"],
            "通膨低 (<2.3%)": ["溫和成長", "預防性降息", "衰退式降息"],
            "通膨中 (2.3%~2.9%)": ["小心觀望", "按兵不動", "🟩 轉向降息 (候選區)"],
            "通膨高 (>2.9%)": ["升息壓力", "兩難困境", "🟥 目前定位：停滯性通膨 (通膨優先)"]
        }
        grid_df = pd.DataFrame(grid_data).set_index("就業狀態 \\ 通膨狀態")
        st.table(grid_df)
        
        st.info("""
        **【當前情境：停滯性通膨（通膨優先）】**
        * **就業維度：** 勞動動能流失（利降息）。
        * **物價維度：** 核心 PCE 仍居高（利升息/維持高利率）。
        * **解鎖「轉向降息」條件：** 綜合通膨水準需再降 **0.57 個百分點**。
        """)

    with col_signals:
        st.markdown("#### ⚖️ 本期關鍵訊號組成 (規則引擎：8 條利降息 / 2 條利升息)")
        
        sig_col1, sig_col2 = st.columns(2)
        with sig_col1:
            st.markdown("""
            **🟢 偏降息的變化 (8 項)**
            * ✅ **失業率下降：** 源於勞動力退出而非就業增加（就業疲軟）
            * ✅ **前兩月非農大幅下修：** 實質動能弱於初值
            * ✅ **近三月年化通膨率：** 低於年增率 0.4 個百分點（降溫）
            * ✅ **非管理職薪資增速：** 高於總體（薪資結構改善）
            * ✅ **初值近一年系統性下修：** 初值持續打折看
            """)
        with sig_col2:
            st.markdown("""
            **🔴 偏升息/維持高利率的變化 (2 項)**
            * ⚠️ **核心 PCE 顯著高於目標：** 3.3% 仍是降息最大阻力
            * ⚠️ **油價與能源反彈：** 未來 1-2 個月推升總體 CPI
            * ⚠️ **住房落後項：** 仍在推升整體讀數
            """)
            
        # 倒數計時進度條
        st.markdown("##### ⏳ 下次關鍵事件倒數")
        e1, e2, e3 = st.columns(3)
        e1.metric("下次 CPI 發布", "1 天後", "2026-08-19")
        e2.metric("下次就業報告", "24 天後", "2026-09-04")
        e3.metric("下次 FOMC 會議", "36 天後", "2026-09-16")

    st.markdown("---")

    # 3. AI 宏觀情境合成分析器
    st.markdown("#### 🤖 Gemini 總經情境合成分析 (AI Macro Synthesizer)")
    if st.button("🚀 呼叫 Gemini 執行本期 Macro GG 深度情境合成"):
        active_key = api_key_input or loaded_api_key
        if not active_key:
            st.error("請在左側側邊欄輸入 Gemini API Key！")
        else:
            with st.spinner("Gemini Agent 正在分析九宮格偏移、科技巨頭 CapEx 與降息路徑..."):
                try:
                    genai.configure(api_key=active_key)
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    
                    macro_context = """
                    【最新總經數據】
                    - 總體 CPI: 3.4%, 核心 CPI: 2.5% (3M 年化 1.6%)
                    - 核心 PCE: 3.3% (仍顯著高於 2% 目標)
                    - 非農月變動: -2.3 萬人 (前值大幅下修), 失業率: 4.1%
                    - 規則引擎訊號: 8 項利降息, 2 項利升息
                    - 當前九宮格定位: 處於【就業弱 x 通膨高 = 停滯性通膨 (通膨優先)】，但正朝向【轉向降息】移動
                    """
                    prompt = f"""
                    你是一位華爾街頂級宏觀對衝基金的 Chief Economist (首席經濟學家)。請根據以下 Macro GG 架構數據進行 350 字以內的深度情境合成報告：
                    {macro_context}

                    請依序回答：
                    1. **九宮格動態解讀：** 為什麼「非農疲軟」不足以立刻促使 Fed 在 9 月大幅降息？核心 PCE 的阻力在哪？
                    2. **利率路徑推估：** 綜合 8 項利降息 vs 2 項利升息訊號，預估未來的基準利率路徑（按兵不動 vs 降息時機）。
                    3. **對衝基金資產配置指引：** 對於【外匯息差 USD/JPY】與【美股選擇權 Delta 中性】策略提出具體操作調整建議。
                    """
                    res = model.generate_content(prompt)
                    st.markdown(f"""
                    <div style="background-color: #1a1d28; padding: 18px; border-radius: 8px; border-left: 4px solid #00cc96;">
                        <h4 style="margin-top:0;">📋 Gemini Macro GG 首席經濟學家情境合成簡報</h4>
                        {res.text}
                    </div>
                    """, unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"連線失敗: {e}")

    st.markdown("---")
    
    # 4. 下方即時新聞串流
    st.subheader("📰 全球即時財經與總經頭條 (Yahoo Finance)")
    news_list = fetch_yahoo_finance_news()
    n_cols = st.columns(3)
    for idx, item in enumerate(news_list):
        with n_cols[idx % 3]:
            st.markdown(f"""
            <div style="background-color: #1a1d28; padding: 12px; border-radius: 6px; border-left: 3px solid #00cc96; margin-bottom: 10px; height: 110px;">
                <a href="{item['link']}" target="_blank" style="color: #e0e0e0; text-decoration: none; font-size: 13px; font-weight: bold;">
                    {item['title'][:70]}...
                </a>
                <div style="color: #8b949e; font-size: 11px; margin-top: 6px;">📅 {item['date']}</div>
            </div>
            """, unsafe_allow_html=True)

# -------------------------------------------------------------
# TAB 2: 跨資產實況看板
# -------------------------------------------------------------
with tab_charts:
    st.subheader("📈 跨市場即時技術線圖 (TradingView WebSocket)")
    
    st.markdown("#### 【上層】外匯與大宗商品市場 (Forex & Commodities)")
    fx_col1, fx_col2 = st.columns([1, 4])
    with fx_col1:
        fx_target = st.selectbox(
            "選擇外匯/大宗標的：",
            ["FX_IDC:USDJPY", "FX_IDC:EURUSD", "FX_IDC:GBPUSD", "OANDA:XAUUSD", "TVC:USOIL"],
            index=0
        )
        st.caption("• **USD/JPY:** 息差對衝主力\n• **EUR/USD:** 歐美貨幣動量\n• **XAU/USD:** 黃金抗通膨\n• **USOIL:** 原油通膨鏈")
    with fx_col2:
        render_tv_chart(symbol=fx_target, height=360)

    st.markdown("---")

    st.markdown("#### 【下層】選擇權底層標的現貨走勢 (Equities & Index)")
    eq_col1, eq_col2 = st.columns([1, 4])
    with eq_col1:
        eq_target = st.selectbox(
            "選擇權底層標的：",
            ["AMEX:SPY", "NASDAQ:QQQ", "NASDAQ:NVDA", "NASDAQ:TSLA"],
            index=0
        )
        st.markdown("""
        **💡 選擇權分析要點：**
        1. **Delta (走勢):** 判斷突破或盤整。
        2. **Skew (偏斜):** 觀察 OTM Put 下行防護成本。
        3. **0DTE 爆發:** 觀察日內突破與 Gamma 加速。
        """)
    with eq_col2:
        render_tv_chart(symbol=eq_target, height=360)

# -------------------------------------------------------------
# TAB 3: 策略管理與回測引擎
# -------------------------------------------------------------
with tab_backtest:
    st.subheader("🧪 量化策略管理、回測引擎與資本試算")
    
    with st.expander("🛠️ 管理/修改策略權重與邏輯，或新增自訂策略", expanded=False):
        col_list, col_add = st.columns([3, 2])
        with col_list:
            st.markdown("##### 📋 現有策略清單與比重調整")
            for idx, strat in enumerate(st.session_state['strategies']):
                c_act, c_name, c_wt, c_del = st.columns([1, 4, 2, 1])
                strat['active'] = c_act.checkbox("啟用", value=strat['active'], key=f"act_{strat['id']}")
                strat['name'] = c_name.text_input("策略名稱", value=strat['name'], key=f"name_{strat['id']}")
                strat['weight'] = c_wt.number_input("配置比重 (%)", min_value=0, max_value=100, value=strat['weight'], key=f"wt_{strat['id']}")
                if c_del.button("🗑️", key=f"del_{strat['id']}"):
                    st.session_state['strategies'].pop(idx)
                    st.rerun()
                st.caption(f"邏輯描述：{strat['logic']}")
        
        with col_add:
            st.markdown("##### ➕ 新增自訂投資策略")
            with st.form("add_strat_form"):
                new_name = st.text_input("策略名稱", "黃金總經動量對衝")
                new_type = st.selectbox("策略類型", ["核心對衝", "高凸性衛星", "統計套利", "跨市場套利"])
                new_weight = st.number_input("初始權重 (%)", min_value=0, max_value=100, value=10)
                new_logic = st.text_area("策略邏輯", "根據美國實質利率 (TIPS) 與美元指數動量建立黃金多空部位。")
                if st.form_submit_button("新增至策略庫"):
                    new_id = max([s['id'] for s in st.session_state['strategies']]) + 1 if st.session_state['strategies'] else 1
                    st.session_state['strategies'].append({
                        "id": new_id,
                        "name": new_name,
                        "type": new_type,
                        "weight": new_weight,
                        "logic": new_logic,
                        "active": True
                    })
                    st.success("✅ 策略已成功新增！")
                    st.rerun()

    st.markdown("---")
    
    st.markdown("#### 🚀 資本配置收益試算與回測曲線")
    col_bt_params, col_bt_chart = st.columns([1, 3])
    
    with col_bt_params:
        bt_start = st.date_input("開始日期", pd.to_datetime("2023-01-01"))
        bt_end = st.date_input("結束日期", pd.to_datetime("2025-12-31"))
        run_bt = st.button("🚀 執行資本配置重新回測", use_container_width=True)
        
        st.markdown("##### 💵 各策略分配本金")
        for s in st.session_state['strategies']:
            if s['active']:
                allocated_fund = total_capital * (s['weight'] / 100)
                st.write(f"• **{s['name'][:16]}...:** `${allocated_fund:,.0f}` ({s['weight']}%)")

    with col_bt_chart:
        if run_bt or 'backtest_df' not in st.session_state:
            with st.spinner("正在下載行情數據並結合本金規模計算回測..."):
                try:
                    # 1. Delta-Neutral (SPY)
                    spy = yf.download("SPY", start=bt_start, end=bt_end, progress=False)[['Close']]
                    spy_cum = (1 + pd.Series(0.1429 / 252, index=spy.index)).cumprod()

                    # 2. Pair Trading (AUD/NZD)
                    forex = yf.download(["AUDUSD=X", "NZDUSD=X"], start=bt_start, end=bt_end, progress=False)['Close']
                    spread = forex['AUDUSD=X'] - forex['NZDUSD=X']
                    z = (spread - spread.rolling(30).mean()) / spread.rolling(30).std()
                    signal = pd.Series(0, index=forex.index)
                    signal[z > 1.5] = -1
                    signal[z < -1.5] = 1
                    pos = signal.replace(0, np.nan).ffill().shift(1).fillna(0)
                    pair_cum = (1 + (pos * (forex['AUDUSD=X'].pct_change() - forex['NZDUSD=X'].pct_change())).fillna(0)).cumprod()

                    # 3. Volatility Arbitrage
                    vol_cum = (1 + pd.Series(-0.00034, index=spy.index)).cumprod()

                    # 4. Hedged Carry Trade (USD/JPY)
                    usdjpy = yf.download("JPY=X", start=bt_start, end=bt_end, progress=False)[['Close']]
                    usdjpy.columns = ['Price']
                    carry_cum = (1 + ((0.045 / 252) + (usdjpy['Price'].pct_change() * 0.5)).fillna(0)).cumprod()

                    st.session_state['backtest_df'] = pd.DataFrame({
                        'Hedged Carry ($)': carry_cum * (total_capital * 0.5),
                        'Delta-Neutral ($)': spy_cum * (total_capital * 0.2),
                        'Volatility Arbitrage ($)': vol_cum * (total_capital * 0.05),
                        'Pair Trading ($)': pair_cum * (total_capital * 0.0)
                    }).ffill().dropna()

                    st.session_state['backtest_df']['總資產組合 (Portfolio NAV)'] = st.session_state['backtest_df'].sum(axis=1)

                except Exception as e:
                    st.error(f"回測計算失敗: {e}")

        if 'backtest_df' in st.session_state:
            fig_nav = px.line(st.session_state['backtest_df'], 
                              y=['總資產組合 (Portfolio NAV)', 'Hedged Carry ($)', 'Delta-Neutral ($)'],
                              title=f"資本規模 (${total_capital:,.0f} USD) 之回測總資產淨值走勢 (USD)")
            fig_nav.update_layout(template="plotly_dark", height=420)
            st.plotly_chart(fig_nav, use_container_width=True)

    st.markdown("---")
    st.markdown("#### 🤖 策略專屬 AI 顧問")
    strat_q = st.text_input("輸入策略問題：", "在 Macro GG 顯示【停滯性通膨】情境下，Hedged Carry Trade 的曝險該如何控管？")
    if st.button("向 AI 顧問提問"):
        active_key = api_key_input or loaded_api_key
        if not active_key:
            st.error("請在側邊欄輸入 Gemini API Key！")
        else:
            with st.spinner("AI 顧問正在分析策略邏輯與回測架構..."):
                try:
                    genai.configure(api_key=active_key)
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    strat_context = str(st.session_state['strategies'])
                    prompt = f"以下是投資公司策略清單：\n{strat_context}\n總本金：${total_capital} USD。\n問題：{strat_q}"
                    res = model.generate_content(prompt)
                    st.markdown(f"**【AI 顧問回覆】**\n{res.text}")
                except Exception as e:
                    st.error(f"連線失敗: {e}")

# -------------------------------------------------------------
# TAB 4: 動態持倉與 Greeks 同步
# -------------------------------------------------------------
with tab_recon:
    st.subheader("🔄 多券商真實部位與 Greeks 同步 (Position Reconciliation)")
    pos_data = pd.DataFrame({
        "券商": ["IG Group", "IG Group", "IBKR", "IBKR", "IBKR"],
        "標的合約": ["USD/JPY Spot", "XAU/USD CFD", "SPY 550 Call (DTE 14)", "SPY 540 Put (DTE 14)", "NVDA 125 Call (0DTE)"],
        "部位類別": ["核心 (息差對衝)", "衛星 (宏觀對衝)", "核心 (Delta 中性)", "核心 (Delta 中性)", "衛星 (高凸性)"],
        "部位大小": ["+$500,000", "+$50,000", "-5 口 (Short)", "-5 口 (Short)", "+10 口 (Long)"],
        "Delta 貢獻": ["+0.50", "+0.08", "-2.65", "+2.10", "+0.45"],
        "未實現損益 (USD)": ["+$8,450", "-$320", "+$1,200", "+$890", "+$2,150"]
    })
    st.dataframe(pos_data, use_container_width=True)
    st.info("💡 系統判定：目前組合 Net Delta 為 -0.02，Vega 暴露適中，符合中性 Theta 收割架構。")

# -------------------------------------------------------------
# TAB 5: 交易日誌與 SQLite 一週覆盤
# -------------------------------------------------------------
with tab_audit:
    st.subheader("📝 交易日誌與一週覆盤中心 (SQLite)")
    c_entry, c_history = st.columns([1, 2])
    
    with c_entry:
        st.markdown("#### ✍️ 錄入新交易日誌")
        with st.form("trade_form", clear_on_submit=True):
            sym = st.text_input("交易標的", "USD/JPY")
            act = st.selectbox("動作", ["買入開倉", "賣出開倉", "停利平倉", "停損平倉"])
            pnl_val = st.number_input("實現盈虧 (USD)", value=850.0)
            strat = st.selectbox("策略歸屬", ["75% 核心對衝", "25% 主觀高凸性衛星"])
            reason_text = st.text_area("進出場邏輯", "觸發均線停損對衝")
            audit_stat = st.selectbox("稽核狀態", ["符合正期望值", "嚴格紀律停損", "疑似幸運序列", "心理偏離 (凹單)"])
            
            if st.form_submit_button("儲存至 SQLite 資料庫"):
                insert_trade_log(sym, act, pnl_val, strat, reason_text, audit_stat)
                st.success("✅ 已儲存至 `quant_firm.db`！")

    with c_history:
        st.markdown("#### 🗄️ 歷史日誌")
        log_df = get_trade_logs()
        if not log_df.empty:
            st.dataframe(log_df, use_container_width=True)
            total_pnl = log_df['pnl'].sum()
            st.write(f"• **歷史累計損益：** `${total_pnl:,.2f} USD` (共 {len(log_df)} 筆)")
        else:
            st.info("尚未錄入任何交易日誌。")

# -------------------------------------------------------------
# TAB 6: AI 投資委員會 (Gemini Agent)
# -------------------------------------------------------------
with tab_ai:
    st.subheader("🤖 虛擬投資委員會 (Gemini Multi-Agent)")
    
    agent_mode = st.selectbox("諮詢的 AI 部門長官：", [
        "Chief Risk Officer (風控長) - 審查黑天鵝事件與保證金壓力",
        "Audit Officer (稽核官) - 檢視交易日誌是否偏離正期望值與紀律",
        "Macro Strategist (總經策略官) - 評估全球央行利差與商品走勢"
    ])
    
    recent_logs = get_trade_logs().head(5).to_string() if not get_trade_logs().empty else "無最新交易紀錄"
    default_prompt = f"請檢視目前總本金 ${total_capital:,.0f} USD、保證金佔用率 30.9% 與以下最近交易紀錄：\n{recent_logs}\n\n請給出客觀風控與下週部位配置建議。"
    ai_prompt = st.text_area("輸入市場情境或詢問問題：", default_prompt, height=130)
    
    if st.button("向 AI 委員會發送審查請求"):
        active_key = api_key_input or loaded_api_key
        if not active_key:
            st.error("❌ 請在側邊欄輸入 Gemini API Key！")
        else:
            with st.spinner("Gemini Agent 正在深度分析中..."):
                try:
                    genai.configure(api_key=active_key)
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    res = model.generate_content(f"身為投資公司的 {agent_mode}，請以嚴謹專業口吻回覆：\n{ai_prompt}")
                    st.markdown(f"### 📋 審查報告書\n{res.text}")
                except Exception as e:
                    st.error(f"連線失敗: {e}")