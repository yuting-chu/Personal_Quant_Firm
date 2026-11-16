#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Personal Quant Firm | 全自動量化守護進程與交易結果看板 (Autonomous Daemon & Results Tab)
====================================================================================
功能：
1. 守護進程狀態監控 (Active / Inactive, PID, Heartbeat, TWS 連線)。
2. 一鍵啟動 / 停止背景進程，一鍵執行單次輪詢，一鍵緊急撤單。
3. 9 大多元資產多空體制 (50 EMA) 與 15M ATR 動態定價看板 (Multi-Asset Regime & ATR Matrix)。
4. 9 大多元資產 30 日滾動相關性熱圖 (30-Day Rolling Correlation Heatmap)。
5. 即時宏觀情緒核心監控 (Sentiment Index, Volatility Shock, Risk Multiplier)。
6. 11 大產業板塊與標的價格雙軸動態掃描表 (超買過熱懲罰指標)。
7. 今日自動交易結果審計明細與損益統計 (SQLite trade_logs)。
8. 自動產出之宏觀與產業研究報告歷史瀏覽器 (SQLite macro_daily_reports)。
"""

import os
import sys
import json
import time
import subprocess
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from modules.database import get_trade_logs, get_today_realized_pnl, get_macro_reports
from modules.ibkr_engine import get_ibkr_engine
from modules.sentiment_engine import get_market_sentiment
from modules.industry_engine import update_and_generate_industry_report

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATUS_FILE = os.path.join(PROJECT_ROOT, "daemon_status.json")
DAEMON_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "daemon_auto_trader.py")

# 9 大核心資產元數據配置
ASSET_METADATA = [
    {"sym": "/MES", "name": "微型標普 500 期貨", "asset_class": "美股指數核心 (Beta 1.0)", "yf": "ES=F"},
    {"sym": "/MNQ", "name": "微型那斯達克 100 期貨", "asset_class": "科技成長進攻 (High Beta)", "yf": "NQ=F"},
    {"sym": "/M2K", "name": "微型羅素 2000 期貨", "asset_class": "小型股規模因子 (SMB)", "yf": "RTY=F"},
    {"sym": "/MBT", "name": "微型比特幣期貨", "asset_class": "全球 M2 流動性衛星", "yf": "BTC-USD"},
    {"sym": "USDJPY", "name": "美元/日圓 外匯現貨", "asset_class": "全球利差交易 (Carry)", "yf": "USDJPY=X"},
    {"sym": "/MGC", "name": "微型黃金期貨 (COMEX)", "asset_class": "實質利率與抗通膨避險", "yf": "GC=F"},
    {"sym": "TLT", "name": "美國 20+ 年期公債 ETF", "asset_class": "存續期間與通縮衰退避險", "yf": "TLT"},
    {"sym": "EURUSD", "name": "歐元/美元 外匯現貨", "asset_class": "跨大西洋央行政策差", "yf": "EURUSD=X"},
    {"sym": "/MCL", "name": "微型輕原油期貨 (NYMEX)", "asset_class": "大宗商品與供給側避險", "yf": "CL=F"}
]


def read_daemon_status() -> dict:
    """讀取守護進程狀態檔案"""
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"is_running": False, "pid": None, "last_heartbeat": "未知", "tws_connected": False}


def is_pid_alive(pid: int) -> bool:
    """檢測 PID 是否在 Windows 系統中存活用戶進程"""
    if not pid:
        return False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False


@st.cache_data(ttl=900)
def fetch_multi_asset_correlation():
    """
    計算 9 大多元資產近 30 天之日報酬相關係數矩陣 (Pearson Correlation Matrix)
    """
    import yfinance as yf
    tickers_map = {item["sym"]: item["yf"] for item in ASSET_METADATA}
    try:
        raw = yf.download(list(tickers_map.values()), period="1mo", interval="1d", progress=False)["Close"]
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        reverse_map = {v: k for k, v in tickers_map.items()}
        raw = raw.rename(columns=reverse_map)
        rets = raw.pct_change().dropna()
        cols = [item["sym"] for item in ASSET_METADATA]
        valid_cols = [c for c in cols if c in rets.columns]
        corr = rets[valid_cols].corr().round(2)
        return corr
    except Exception as e:
        return pd.DataFrame()


def render(api_key: str = ""):
    col_head1, col_head2 = st.columns([3, 1.2])
    with col_head1:
        st.markdown("## 🤖 全自動量化守護進程與多資產中心")
        st.caption("Autonomous Multi-Asset Quant Engine, Dynamic ATR Sizing & Execution Audit")
    with col_head2:
        auto_refresh = st.toggle("🔄 啟用 15 秒實時自動更新", value=False, help="開啟後網頁將每隔 15 秒非同步拉取最新心跳、委託與損益數據")

    @st.fragment(run_every=15 if auto_refresh else None)
    def render_live_sections():
        status_data = read_daemon_status()
        raw_running = status_data.get("is_running", False)
        pid = status_data.get("pid")
        is_active = raw_running and is_pid_alive(pid) if pid else False

        # 1. 頂部狀態橫幅與關鍵績效指標
        col_stat1, col_stat2, col_stat3, col_stat4 = st.columns([1.5, 1.2, 1.2, 1.5])

        with col_stat1:
            if is_active:
                st.success(f"🟢 **守護進程運行中** (PID: `{pid}`)")
            else:
                st.warning("⚪ **守護進程處於離線狀態**")
            st.caption(f"最後心跳: `{status_data.get('last_heartbeat', '無紀錄')}`")

        with col_stat2:
            tws_conn = status_data.get("tws_connected", False)
            if tws_conn:
                st.info(f"🔌 **TWS 模擬帳戶**: `{status_data.get('account_id', 'DUR346381')}`")
            else:
                st.error("🔌 **TWS 連線離線**")

        with col_stat3:
            today_pnl = status_data.get("today_realized_pnl", 0.0) or get_today_realized_pnl()
            net_liq = float(status_data.get("net_liquidation", 1000000.0))
            if net_liq > 0 and today_pnl == 0.0:
                today_pnl = round(net_liq - 1000000.0, 2)

            cb_triggered = status_data.get("circuit_breaker_triggered", False)
            if cb_triggered:
                st.error(f"🚨 **硬熔斷已觸發**: 損益 ${today_pnl:+,.2f}")
            else:
                pnl_color = "green" if today_pnl >= 0 else "red"
                st.markdown(f"💰 **今日已實現損益**<br><span style='color:{pnl_color}; font-weight:bold; font-size:16px;'>${today_pnl:+,.2f} USD</span>", unsafe_allow_html=True)

        with col_stat4:
            active_orders = status_data.get("open_trades_count", 0)
            st.metric("TWS 活躍委託數", f"{active_orders} 筆", f"風控乘數: {status_data.get('risk_multiplier', 1.0)}x")

        st.markdown("---")

        # 2. 控制按鈕組
        btn_c1, btn_c2, btn_c3, btn_c4, btn_c5 = st.columns([1, 1, 1, 1.1, 1.3])

        with btn_c1:
            if not is_active:
                if st.button("▶️ 啟動背景進程", use_container_width=True, type="primary"):
                    try:
                        proc = subprocess.Popen(
                            [sys.executable, DAEMON_SCRIPT, "--interval", "20", "--port", "7497"],
                            cwd=PROJECT_ROOT,
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                        )
                        st.toast(f"✅ 守護進程已成功啟動！(PID: {proc.pid})")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"啟動進程失敗: {e}")
            else:
                st.button("🟢 進程運行中", disabled=True, use_container_width=True)

        with btn_c2:
            if is_active:
                if st.button("⏹️ 停止守護進程", use_container_width=True):
                    try:
                        if pid:
                            import signal
                            os.kill(pid, signal.SIGTERM)
                        st.toast("🛑 已發送終止信號，進程正在退出...")
                        time.sleep(1.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"停止失敗: {e}")
            else:
                st.button("⚪ 已停止", disabled=True, use_container_width=True)

        with btn_c3:
            if st.button("🔄 立即單次輪詢", use_container_width=True):
                with st.spinner("正在執行單次即時輪詢 (--once)..."):
                    try:
                        res = subprocess.run(
                            [sys.executable, DAEMON_SCRIPT, "--once", "--port", "7497"],
                            cwd=PROJECT_ROOT,
                            capture_output=True,
                            text=True,
                            timeout=45
                        )
                        st.toast("✅ 單次輪詢執行完畢！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"單次執行異常: {e}")

        with btn_c4:
            if st.button("🚨 緊急全撤單", use_container_width=True):
                with st.spinner("正在向 TWS 發送全面撤單指令..."):
                    try:
                        engine = get_ibkr_engine(port=7497, client_id=99)
                        if engine.connect():
                            engine.ib.reqAllOpenOrders()
                            time.sleep(0.5)
                            trades = engine.ib.openTrades()
                            canceled_cnt = len(trades)
                            for t in trades:
                                engine.ib.cancelOrder(t.order)
                            engine.disconnect()
                            st.toast(f"🛑 已成功撤銷 {canceled_cnt} 筆活動委託！")
                            st.rerun()
                        else:
                            st.error("無法連線至 TWS (Port 7497)")
                    except Exception as e:
                        st.error(f"撤單失敗: {e}")

        with btn_c5:
            from datetime import datetime
            is_sun = datetime.now().weekday() == 6
            btn_label = "📧 寄送每週交易週報至 Gmail" if is_sun else "📧 寄送今日日報至 Gmail"
            if st.button(btn_label, use_container_width=True):
                report_kind = "每週量化交易週報" if is_sun else "每日量化交易郵報"
                with st.spinner(f"正在編譯並寄送 {report_kind}..."):
                    try:
                        from modules.time_utils import get_taipei_datestr
                        d_today = get_taipei_datestr()
                        if is_sun:
                            from scripts.daily_report_dispatcher import dispatch_weekly_report
                            ok = dispatch_weekly_report(d_today)
                        else:
                            from scripts.daily_report_dispatcher import dispatch_daily_report
                            ok = dispatch_daily_report(d_today)
                        if ok:
                            st.success(f"✅ 已成功寄出 {d_today} {report_kind}！")
                        else:
                            st.error("發送失敗，請確認 .env 之 Gmail 配置。")
                    except Exception as e:
                        st.error(f"發送異常: {e}")

        st.markdown("---")

        # 3. 📈 9 大多元資產多空體制與 15M ATR 動態定價看板
        st.subheader("📈 9 大多元資產多空體制與 15M ATR 動態定價看板 (Multi-Asset Regime & ATR Matrix)")
        st.caption("核心亮點：採用 14 期 Wilder ATR 計算動態進出場緩衝與停損空間；依據 50 EMA 均線斜率判定 BULL (回調做多) / BEAR (反彈做空) / NEUTRAL (中性震盪)")

        cached_regimes = status_data.get("asset_regimes", {})
        daily_trades = status_data.get("daily_trades_counter", {})
        sentiment_score = status_data.get("sentiment_score", 0.0)

        matrix_rows = []
        for item in ASSET_METADATA:
            sym = item["sym"]
            info = cached_regimes.get(sym, {})
            regime = info.get("regime", "NEUTRAL")
            atr = info.get("atr", 0.0)
            price = info.get("price", 0.0)
            ema50 = info.get("ema50", 0.0)
            cnt = daily_trades.get(sym, 0)

            if regime == "BULL":
                reg_display = "🟢 多頭 (BULL)"
                action_sugg = "🟢 回調做多 (BUY dips)"
            elif regime == "BEAR":
                reg_display = "🔴 空頭 (BEAR)"
                action_sugg = "🔴 反彈做空 (SELL rallies)"
            else:
                reg_display = "🟡 震盪 (NEUTRAL)"
                if sentiment_score >= 0.20:
                    action_sugg = "🟢 宏觀偏多 (BUY)"
                elif sentiment_score <= -0.20:
                    action_sugg = "🔴 宏觀偏空 (SELL)"
                else:
                    action_sugg = "⚪ 震盪抑制 (HOLD)"

            matrix_rows.append({
                "標的代碼": sym,
                "資產名稱": item["name"],
                "資產屬性定位": item["asset_class"],
                "50 EMA 趨勢體制": reg_display,
                "15M ATR 波動度": f"{atr:.4f}" if (atr > 0 and atr < 1) else (f"{atr:.2f}" if atr > 0 else "計算中"),
                "最新參考價": f"{price:,.4f}" if (price > 0 and price < 2) else (f"{price:,.2f}" if price > 0 else "連線中"),
                "50 EMA 基準": f"{ema50:,.4f}" if (ema50 > 0 and ema50 < 2) else (f"{ema50:,.2f}" if ema50 > 0 else "連線中"),
                "當前策略建議動作": action_sugg,
                "今日開倉計數": f"{cnt} / 4 次"
            })

        df_matrix = pd.DataFrame(matrix_rows)
        st.dataframe(df_matrix, use_container_width=True, hide_index=True)

        st.markdown("---")

        # 4. 雙欄布局：左側情緒核心與產業價格，右側交易結果與最新日誌
        col_left, col_right = st.columns([1.1, 0.9])

        with col_left:
            st.subheader("🌐 即時宏觀情緒核心 (Sentiment Engine)")
            col_s1, col_s2, col_s3 = st.columns([1, 1, 1.2])
            score = status_data.get("sentiment_score", 0.0)
            label = status_data.get("regime_label", "中性觀望")
            mult = status_data.get("risk_multiplier", 1.0)

            with col_s1:
                st.metric("情緒得分 (Score)", f"{score:+.2f}", label)
            with col_s2:
                st.metric("部位調整乘數", f"{mult}x", "黑天鵝時自動減半")
            with col_s3:
                shock_flag = status_data.get("volatility_shock_flag", False)
                if shock_flag:
                    st.error("⚠️ **突發黑天鵝高波動警告**")
                else:
                    st.success("🛡️ **宏觀流動性平穩**")

            st.markdown(
                """
                <div style="font-size:12px; color:#6b7280; margin-bottom:12px;">
                    💡 <b>自建模型接口規範</b>：本模組遵循 <code>docs/SENTIMENT_ENGINE_SPEC.md</code> 標準架構，未來可無痛熱插拔自定義深度學習模型。
                </div>
                """,
                unsafe_allow_html=True
            )

            st.subheader("📊 11 大產業板塊與標的價格雙軸矩陣")
            st.caption("定期收盤掃描，整合 50MA 乖離 Z-Score、14D RSI 與『超買追高懲罰機制』")
            try:
                from modules.industry_engine import scan_industry_and_prices
                df_ind = scan_industry_and_prices()
                if not df_ind.empty:
                    st.dataframe(
                        df_ind[["代碼", "名稱", "最新價格 ($)", "單日漲跌 (%)", "相對 Alpha (%)", "14D RSI", "價格估值狀態"]],
                        use_container_width=True,
                        height=280
                    )
                else:
                    st.info("尚無即時產業價格快照，點擊單次輪詢即可生成。")
            except Exception as err:
                st.warning(f"產業價格矩陣加載異常: {err}")

        with col_right:
            st.subheader("📝 今日量化交易委託與成交結果 (Execution Blotter)")
            trade_logs = get_trade_logs()
            if not trade_logs.empty:
                st.dataframe(
                    trade_logs[["timestamp", "symbol", "action", "strategy_type", "audit_status"]].head(8),
                    use_container_width=True,
                    height=260
                )
            else:
                st.info("今日尚無自動交易成交紀錄。")

            st.subheader("📡 守護進程實時運行日誌 (Heartbeat Logs)")
            recent_logs = status_data.get("recent_logs", ["尚未收到日誌紀錄"])
            log_text = "\n".join(recent_logs)
            st.code(log_text if log_text else "暫無日誌", language="bash")

        st.markdown("---")

        # 5. 🌐 9 大多元資產 30 日滾動相關性熱圖 (30-Day Rolling Correlation Heatmap)
        st.subheader("🌐 9 大多元資產 30 日滾動相關性矩陣 (30-Day Rolling Correlation Heatmap)")
        st.caption("基於 Pearson 日收益率協方差：量化不同資產對 S&P 500 的避險對衝效果與分散化收益 (Diversification Benefits)")

        corr_df = fetch_multi_asset_correlation()
        if not corr_df.empty:
            col_heat, col_heat_desc = st.columns([1.6, 1.0])
            with col_heat:
                fig_corr = px.imshow(
                    corr_df,
                    text_auto=True,
                    color_continuous_scale="RdBu_r",
                    zmin=-1.0,
                    zmax=1.0,
                    aspect="auto",
                    labels=dict(color="相關係數 ρ")
                )
                fig_corr.update_layout(
                    template="plotly_dark",
                    height=400,
                    margin=dict(l=10, r=10, t=30, b=10),
                    xaxis=dict(tickangle=45)
                )
                st.plotly_chart(fig_corr, use_container_width=True)

            with col_heat_desc:
                st.markdown(
                    """
                    <div style="background-color: rgba(30, 41, 59, 0.7); border: 1px solid rgba(148, 163, 184, 0.2); padding: 16px; border-radius: 8px; font-size: 13px; line-height: 1.7;">
                        <h4 style="margin-top:0; color:#38bdf8;">📊 計量經濟學對衝解讀：</h4>
                        <ul>
                            <li><b>🛡️ 負相關避險資產</b>：<br>
                                <code>TLT</code> (公債)、<code>EURUSD</code> (歐元)、<code>/MCL</code> (原油) 與美股大盤指數呈現顯著負相關或微弱負相關，在美股市場遭受流動性拋售時提供非對稱保護。</li>
                            <li><b>⚡ 高 Beta 進攻資產</b>：<br>
                                <code>/MES</code>、<code>/MNQ</code>、<code>/M2K</code>、<code>/MBT</code> 彼此相關性高達 <code>+0.70 ~ +0.95</code>，在牛市週期共振上漲，屬攻擊性部位。</li>
                            <li><b>🪙 宏觀正交資產</b>：<br>
                                <code>/MGC</code> (微型黃金) 與股票指數相關性極低 (約 <code>+0.20</code>)，主要受實質利率 (TIPS) 與地緣政治主導，具備極佳的資產配置分散化能力。</li>
                        </ul>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
        else:
            st.info("相關性矩陣正在後台連線計算中，請稍候...")

        st.markdown("---")

        # 6. 下方：自動生成之研報庫歷史瀏覽器
        st.subheader("📚 自動研究報告與投研簡報庫 (Autonomous Research Archive)")
        st.caption("由守護進程每日/每小時定時分析、自動撰寫並存入資料庫的完整研究報告")

        reports_df = get_macro_reports(limit=20)
        if not reports_df.empty:
            report_options = [
                f"[{r['timestamp']}] {r['report_type']} - {r['title']}"
                for _, r in reports_df.iterrows()
            ]
            selected_rep_idx = st.selectbox("請選擇欲查閱之研究報告：", range(len(report_options)), format_func=lambda x: report_options[x])
            selected_row = reports_df.iloc[selected_rep_idx]

            with st.expander(f"📖 點擊展開研報全文：{selected_row['title']}", expanded=True):
                st.markdown(selected_row["content_markdown"])
                if selected_row.get("metrics_snapshot"):
                    with st.expander("🔍 檢視該報告結構化計量快照 (JSON)"):
                        try:
                            snap_json = json.loads(selected_row["metrics_snapshot"])
                            st.json(snap_json)
                        except Exception:
                            st.text(selected_row["metrics_snapshot"])
        else:
            st.info("資料庫中尚無歷史研報，守護進程定時輪詢後將自動產出。")

    render_live_sections()
