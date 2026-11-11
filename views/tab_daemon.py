#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Personal Quant Firm | 全自動量化守護進程與交易結果看板 (Autonomous Daemon & Results Tab)
====================================================================================
功能：
1. 守護進程狀態監控 (Active / Inactive, PID, Heartbeat, TWS 連線)。
2. 一鍵啟動 / 停止背景進程，一鍵執行單次輪詢，一鍵緊急撤單。
3. 即時宏觀情緒核心監控 (Sentiment Index, Volatility Shock, Risk Multiplier)。
4. 11 大產業板塊與標的價格雙軸動態掃描表 (超買過熱懲罰指標)。
5. 今日自動交易結果審計明細與損益統計 (SQLite trade_logs)。
6. 自動產出之宏觀與產業研究報告歷史瀏覽器 (SQLite macro_daily_reports)。
"""

import os
import sys
import json
import time
import subprocess
import pandas as pd
import streamlit as st
from datetime import datetime

from modules.database import get_trade_logs, get_today_realized_pnl, get_macro_reports
from modules.ibkr_engine import get_ibkr_engine
from modules.sentiment_engine import get_market_sentiment
from modules.industry_engine import update_and_generate_industry_report

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATUS_FILE = os.path.join(PROJECT_ROOT, "daemon_status.json")
DAEMON_SCRIPT = os.path.join(PROJECT_ROOT, "scripts", "daemon_auto_trader.py")


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


def render(api_key: str = ""):
    st.markdown("## 🤖 全自動量化守護進程與交易結果中心")
    st.caption("Autonomous Quantitative Trading Daemon & Execution Audit Center")

    status_data = read_daemon_status()
    raw_running = status_data.get("is_running", False)
    pid = status_data.get("pid")
    is_active = raw_running and is_pid_alive(pid) if pid else False

    # 1. 頂部狀態橫幅與一鍵控制列
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
    btn_c1, btn_c2, btn_c3, btn_c4 = st.columns([1, 1, 1, 1.2])

    with btn_c1:
        if not is_active:
            if st.button("▶️ 啟動背景進程", use_container_width=True, type="primary"):
                try:
                    # 透過 subprocess 在背景非阻塞啟動
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
        if st.button("🔄 立即執行單次輪詢", use_container_width=True):
            with st.spinner("正在執行單次即時輪詢 (--once)..."):
                try:
                    res = subprocess.run(
                        [sys.executable, DAEMON_SCRIPT, "--once", "--port", "7497"],
                        cwd=PROJECT_ROOT,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    st.toast("✅ 單次輪詢執行完畢！")
                    st.rerun()
                except Exception as e:
                    st.error(f"單次執行異常: {e}")

    with btn_c4:
        if st.button("🚨 緊急撤銷 TWS 全部委託", use_container_width=True):
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

    st.markdown("---")

    # 3. 雙欄布局：左側情緒核心與產業價格，右側交易結果與最新日誌
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

    # 4. 下方：自動生成之研報庫歷史瀏覽器 (符合使用者「有時候看看研究報告」之需求)
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
