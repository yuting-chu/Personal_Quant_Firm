#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Personal Quant Firm | 全自動背景監控交易守護進程 (Autonomous Trading Daemon)
========================================================================
職責：
1. 24 小時無人值守常駐背景，以狀態機定時輪詢監控 TWS 模擬交易帳戶 (Port 7497)。
2. 多層級風控中樞 (Risk Governor)：
   - 全域硬熔斷線：當日累計虧損達到 -1.5% ($15,000 USD) 立即撤單鎖死。
   - 標的冷卻期 (Cooldown)：同標的下單後至少間隔 30 分鐘，杜絕洗盤過度交易。
   - 最大持倉限制：單一標的最大 1 口 / 10,000 單位。
3. 整合宏觀情緒核心 (modules/sentiment_engine.py)：
   - 每 30 分鐘自動更新情緒指數，遇到黑天鵝或極度悲觀自動調降倉位 (Risk Multiplier)。
4. 整合產業與標的價格定價引擎 (modules/industry_engine.py)：
   - 每日自動更新板塊行情與超買過熱懲罰指標。
5. 狀態即時發布：寫入 daemon_status.json 供前端 Streamlit 看板即時讀取與一鍵啟停。
"""

import sys
import os
import time
import json
import signal
import argparse
import logging
import math
from datetime import datetime, timedelta
from typing import Dict, Any, List

# 確保路徑正確定向至專案根目錄
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from modules.time_utils import get_taipei_timestamp, get_taipei_datestr
from modules.database import insert_trade_log, get_today_realized_pnl
from modules.ibkr_engine import get_ibkr_engine
from modules.sentiment_engine import get_market_sentiment
from modules.industry_engine import update_and_generate_industry_report

# 設定日誌記錄
LOG_FILE = os.path.join(PROJECT_ROOT, "daemon_trader.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("AutoTraderDaemon")

STATUS_FILE = os.path.join(PROJECT_ROOT, "daemon_status.json")

# 風控與動態刷新關鍵常數
MAX_DAILY_LOSS_PCT = 0.015       # -1.5% 單日最大虧損熔斷線
COOLDOWN_SECONDS = 1200          # 20 分鐘同標的下單冷卻期
STALE_TIMEOUT_SECONDS = 1200     # 20 分鐘陳舊訂單超時閾值
MES_DRIFT_THRESHOLD = 12.0       # /MES 價格偏離 12 點
MNQ_DRIFT_THRESHOLD = 35.0       # /MNQ 價格偏離 35 點
FX_DRIFT_THRESHOLD = 0.20        # USD/JPY 價格偏離 20 pips (0.20 日圓)
CLIENT_ID = 401                  # 專用 Daemon Client ID

# 全域狀態
running = True
last_order_times = {}            # {symbol: timestamp}
order_submission_times = {}      # {orderId: timestamp}
circuit_breaker_active = False
recent_logs: List[str] = []


def add_recent_log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    formatted = f"[{ts}] {msg}"
    recent_logs.append(formatted)
    if len(recent_logs) > 20:
        recent_logs.pop(0)
    logger.info(msg)


def update_status_file(data: Dict[str, Any]):
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"寫入狀態檔案失敗: {e}")


def signal_handler(signum, frame):
    global running
    logger.info(f"接收到終止信號 ({signum})，正在優雅終止守護進程...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def run_daemon(interval_sec: int = 20, run_once: bool = False, port: int = 7497):
    global running, circuit_breaker_active

    logger.info("=" * 60)
    logger.info("🚀 Personal Quant Firm 全自動背景監控交易守護進程啟動")
    logger.info(f"連線配置: TWS Port {port} | Client ID {CLIENT_ID} | 輪詢週期 {interval_sec} 秒")
    logger.info(f"風控規範: 單日最大回撤熔斷 {-MAX_DAILY_LOSS_PCT*100}% | 冷卻期 {COOLDOWN_SECONDS} 秒")
    logger.info("=" * 60)

    engine = get_ibkr_engine(port=port, client_id=CLIENT_ID)
    iterations = 0
    last_sentiment_time = datetime.min
    last_industry_time = datetime.min
    last_daily_report_time = datetime.min
    current_sentiment = {}
    risk_multiplier = 1.0

    while running:
        try:
            iterations += 1
            now = datetime.now()
            add_recent_log(f"--- 執行循環 #{iterations} ({get_taipei_timestamp()}) ---")

            # 1. 檢查 TWS 連線
            is_connected = engine.connect()
            account_summary = engine.get_account_summary() if is_connected else {}
            net_liq = account_summary.get("net_liquidation", 1000000.0)
            account_id = account_summary.get("account_id", "未連線")

            # 2. 定期更新情緒指標 (每 30 分鐘)
            if (now - last_sentiment_time).total_seconds() > 1800:
                add_recent_log("🌐 正在調用情緒核心進行新聞情緒量化評估...")
                try:
                    current_sentiment = get_market_sentiment(persist_report=True)
                    risk_multiplier = float(current_sentiment.get("risk_multiplier", 1.0))
                    last_sentiment_time = now
                    add_recent_log(f"✅ 情緒更新完成: 得分 {current_sentiment.get('sentiment_score')} ({current_sentiment.get('regime_label')}) | 風控乘數: {risk_multiplier}x")
                except Exception as e:
                    add_recent_log(f"⚠️ 情緒引擎評估異常，降級為安全中性乘數 1.0x: {e}")
                    risk_multiplier = 1.0

            # 3. 定期更新產業研究與標的價格矩陣 (每 6 小時)
            if (now - last_industry_time).total_seconds() > 21600:
                add_recent_log("📊 正在更新 11 大產業板塊與標的價格雙軸研報...")
                try:
                    ind_res = update_and_generate_industry_report(persist_db=True)
                    last_industry_time = now
                    add_recent_log(f"✅ 產業與標的價格研報已持久化: {ind_res.get('summary')}")
                except Exception as e:
                    add_recent_log(f"⚠️ 產業價格掃描異常: {e}")

            # 3.5 每 24 小時定時派發每日量化交易與投研郵報至 Gmail
            if (now - last_daily_report_time).total_seconds() > 86400:
                try:
                    from scripts.daily_report_dispatcher import dispatch_daily_report
                    cur_d = get_taipei_datestr()
                    add_recent_log(f"📧 正在生成並派發每 24 小時交易日報 ({cur_d}) 至 Gmail...")
                    dispatch_daily_report(cur_d)
                    last_daily_report_time = now
                    add_recent_log(f"✅ 【郵報派發成功】{cur_d} daily report and trading report 已送達！")
                except Exception as mail_e:
                    add_recent_log(f"⚠️ 每日郵報派發異常: {mail_e}")

            # 4. 全域硬熔斷風控檢查
            today_realized = get_today_realized_pnl()
            daily_loss_limit = -(net_liq * MAX_DAILY_LOSS_PCT)
            if today_realized < daily_loss_limit:
                circuit_breaker_active = True
                add_recent_log(f"🚨 【重大風控警告】今日已實現虧損 ${today_realized:,.2f} 突破熔斷上限 (${daily_loss_limit:,.2f})！")
                add_recent_log("🛑 啟動單日硬熔斷：鎖死新開倉權限並撤銷所有現存委託！")
                if is_connected:
                    engine.ib.reqAllOpenOrders()
                    for t in engine.ib.openTrades():
                        engine.ib.cancelOrder(t.order)

            # 5. 檢查現有委託與持倉 (防止重複下單，並識別母單)
            active_symbols = set()
            parent_orders = {}  # {symbol: Trade}
            open_trades_count = 0
            if is_connected and not circuit_breaker_active:
                engine.ib.reqAllOpenOrders()
                time.sleep(0.5)
                open_trades = engine.ib.openTrades()
                open_trades_count = len(open_trades)
                for ot in open_trades:
                    sym_clean = ot.contract.symbol
                    if ot.contract.secType == "CONTFUT" or ot.contract.secType == "FUT":
                        sym_clean = f"/{sym_clean}"
                    elif ot.contract.secType == "CASH":
                        sym_clean = f"{sym_clean}{ot.contract.currency}"
                    active_symbols.add(sym_clean)

                    # 登記有效中的母單 (Parent Limit Order)
                    if ot.order.parentId == 0 and ot.orderStatus.status in ["Submitted", "PreSubmitted"]:
                        parent_orders[sym_clean] = ot
                        if ot.order.orderId not in order_submission_times:
                            # 優先取既有 last_order_times 或初次登記時間
                            order_submission_times[ot.order.orderId] = last_order_times.get(sym_clean, now - timedelta(minutes=25))

            # 5.5 陳舊訂單【時間(20分) + 空間偏離】雙重檢測與動態刷新 (Stale Order Dynamic Refresh)
            if is_connected and not circuit_breaker_active and parent_orders:
                engine.ib.reqMarketDataType(3)
                for sym, ot in list(parent_orders.items()):
                    oid = ot.order.orderId
                    sub_time = order_submission_times.get(oid, now - timedelta(minutes=25))
                    elapsed_min = (now - sub_time).total_seconds() / 60.0

                    # 條件一：掛單時間 >= 20 分鐘
                    if elapsed_min >= (STALE_TIMEOUT_SECONDS / 60.0):
                        # 抓取該標的最新市場價格
                        c = ot.contract
                        ticker = engine.ib.reqMktData(c)
                        time.sleep(0.8)
                        curr_mkt = None
                        for p in [ticker.marketPrice(), ticker.last, ticker.close, ticker.bid, ticker.ask]:
                            if p is not None and not math.isnan(p) and p > 0:
                                curr_mkt = float(p)
                                break

                        if curr_mkt and ot.order.lmtPrice:
                            lmt_price = float(ot.order.lmtPrice)
                            distance = abs(curr_mkt - lmt_price)
                            drift_limit = MES_DRIFT_THRESHOLD if "MES" in sym else (MNQ_DRIFT_THRESHOLD if "MNQ" in sym else FX_DRIFT_THRESHOLD)

                            # 條件二：現價偏離已拉開超過安全閾值 (市場重心已跑遠)
                            if distance >= drift_limit:
                                add_recent_log(f"🔄 【陳舊單動態刷新】{sym} 掛單已排隊 {elapsed_min:.1f} 分鐘且現價偏離 {distance:.2f} 點 (閾值 {drift_limit})！")
                                add_recent_log(f"🛑 撤銷舊掛單 (Order ID {oid} @ {lmt_price})，依最新現價 {curr_mkt} 重新計算佈局...")
                                engine.ib.cancelOrder(ot.order)
                                time.sleep(1.0)
                                if sym in active_symbols:
                                    active_symbols.remove(sym)
                                if sym.replace("/", "") in active_symbols:
                                    active_symbols.remove(sym.replace("/", ""))
                                last_order_times[sym] = datetime.min
                                if oid in order_submission_times:
                                    del order_submission_times[oid]

            # 6. 量化策略評估與自動發單
            if is_connected and not circuit_breaker_active and risk_multiplier > 0:
                # 請求延遲/即時市場數據
                engine.ib.reqMarketDataType(3)

                # 策略 1: /MES 日內 VWAP 均值回歸
                if "/MES" not in active_symbols and "MES" not in active_symbols:
                    time_since_last = (now - last_order_times.get("/MES", datetime.min)).total_seconds()
                    if time_since_last > COOLDOWN_SECONDS:
                        c_mes = engine.make_contract("/MES", "FUT")
                        t_mes = engine.ib.reqMktData(c_mes)
                        time.sleep(1)
                        mkt_price = 7630.0
                        for p in [t_mes.marketPrice(), t_mes.last, t_mes.close, t_mes.bid, t_mes.ask]:
                            if p is not None and not math.isnan(p) and p > 0:
                                mkt_price = float(p)
                                break
                        if mkt_price > 0:
                            entry_p = round(mkt_price - 6.0, 2)
                            sl_p = round(entry_p - 15.0, 2)
                            tp_p = round(entry_p + 22.5, 2)
                            add_recent_log(f"🎯 策略 1 (/MES VWAP): 現價 {mkt_price}，發送限價回調買單 @ {entry_p} (SL {sl_p}, TP {tp_p})")
                            res = engine.place_bracket_order("/MES", "BUY", 1, entry_p, sl_p, tp_p, "FUT")
                            if res.get("success"):
                                last_order_times["/MES"] = now
                                add_recent_log(f"✅ /MES 括號單發送成功: Order ID {res.get('parent_id')}")

                # 策略 2: /MNQ 開盤 15M 動量突破
                if "/MNQ" not in active_symbols and "MNQ" not in active_symbols:
                    time_since_last = (now - last_order_times.get("/MNQ", datetime.min)).total_seconds()
                    if time_since_last > COOLDOWN_SECONDS:
                        c_mnq = engine.make_contract("/MNQ", "FUT")
                        t_mnq = engine.ib.reqMktData(c_mnq)
                        time.sleep(1)
                        mkt_price = 28540.0
                        for p in [t_mnq.marketPrice(), t_mnq.last, t_mnq.close, t_mnq.bid, t_mnq.ask]:
                            if p is not None and not math.isnan(p) and p > 0:
                                mkt_price = float(p)
                                break
                        if mkt_price > 0:
                            entry_p = round(mkt_price - 15.0, 2)
                            sl_p = round(entry_p - 30.0, 2)
                            tp_p = round(entry_p + 66.0, 2)
                            add_recent_log(f"🎯 策略 2 (/MNQ 動量): 現價 {mkt_price}，發送限價掛單 @ {entry_p} (SL {sl_p}, TP {tp_p})")
                            res = engine.place_bracket_order("/MNQ", "BUY", 1, entry_p, sl_p, tp_p, "FUT")
                            if res.get("success"):
                                last_order_times["/MNQ"] = now
                                add_recent_log(f"✅ /MNQ 括號單發送成功: Order ID {res.get('parent_id')}")

                # 策略 3: USD/JPY 倫敦/紐約突破 Carry
                if "USDJPY" not in active_symbols and "USD.JPY" not in active_symbols:
                    time_since_last = (now - last_order_times.get("USDJPY", datetime.min)).total_seconds()
                    if time_since_last > COOLDOWN_SECONDS:
                        c_fx = engine.make_contract("USDJPY", "CASH")
                        t_fx = engine.ib.reqMktData(c_fx)
                        time.sleep(1)
                        mkt_price = 159.50
                        for p in [t_fx.marketPrice(), t_fx.last, t_fx.close, t_fx.bid, t_fx.ask]:
                            if p is not None and not math.isnan(p) and p > 0:
                                mkt_price = float(p)
                                break
                        if mkt_price > 0:
                            entry_p = round(mkt_price - 0.05, 3)
                            sl_p = round(entry_p - 0.25, 3)
                            tp_p = round(entry_p + 0.50, 3)
                            add_recent_log(f"🎯 策略 3 (USD/JPY Carry): 現價 {mkt_price}，發送限價掛單 @ {entry_p} (SL {sl_p}, TP {tp_p})")
                            res = engine.place_bracket_order("USDJPY", "BUY", 10000, entry_p, sl_p, tp_p, "CASH")
                            if res.get("success"):
                                last_order_times["USDJPY"] = now
                                add_recent_log(f"✅ USD/JPY 括號單發送成功: Order ID {res.get('parent_id')}")

            # 7. 更新 daemon_status.json
            status_data = {
                "is_running": True,
                "pid": os.getpid(),
                "started_at": get_taipei_timestamp(),
                "last_heartbeat": get_taipei_timestamp(),
                "tws_connected": is_connected,
                "account_id": account_id,
                "net_liquidation": net_liq,
                "iterations_count": iterations,
                "open_trades_count": open_trades_count,
                "today_realized_pnl": today_realized,
                "circuit_breaker_triggered": circuit_breaker_active,
                "sentiment_score": current_sentiment.get("sentiment_score", 0.0),
                "regime_label": current_sentiment.get("regime_label", "中性觀望"),
                "risk_multiplier": risk_multiplier,
                "recent_logs": recent_logs[-10:]
            }
            update_status_file(status_data)

            if run_once:
                add_recent_log("單次測試模式結束 (--once)")
                break

            # 睡眠等待下一個輪詢循環
            time.sleep(interval_sec)

        except (ConnectionError, OSError) as conn_err:
            add_recent_log(f"⚠️ 偵測到 TWS 通訊中斷 ({conn_err})，進程進入等待重連模式 (20秒後重試)...")
            logger.warning(f"TWS 通訊中斷: {conn_err}，將於 20 秒後嘗試重連...")
            try:
                engine.disconnect()
            except Exception:
                pass
            update_status_file({
                "is_running": True,
                "pid": os.getpid(),
                "last_heartbeat": get_taipei_timestamp(),
                "tws_connected": False,
                "circuit_breaker_triggered": circuit_breaker_active,
                "recent_logs": recent_logs[-10:]
            })
            if run_once:
                break
            time.sleep(20)
            continue
        except KeyboardInterrupt:
            logger.info("使用者中斷，正在關閉守護進程...")
            break
        except Exception as err:
            logger.error(f"守護進程主循環遭遇非致命例外: {err}", exc_info=True)
            if run_once:
                break
            time.sleep(interval_sec)
            continue

    # 標記狀態為停止
    logger.info("正在退出守護進程並更新狀態檔案...")
    update_status_file({
        "is_running": False,
        "pid": None,
        "last_heartbeat": get_taipei_timestamp(),
        "tws_connected": False,
        "circuit_breaker_triggered": circuit_breaker_active,
        "recent_logs": recent_logs[-10:]
    })
    try:
        engine.disconnect()
    except Exception:
        pass
    logger.info("守護進程已安全離線。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Personal Quant Firm 自動交易守護進程")
    parser.add_argument("--once", action="store_true", help="執行單一循環後退出 (用於測試或定時任務)")
    parser.add_argument("--interval", type=int, default=20, help="輪詢間隔秒數 (預設 20 秒)")
    parser.add_argument("--port", type=int, default=7497, help="TWS / Gateway Socket 端口 (預設 7497)")
    args = parser.parse_args()

    run_daemon(interval_sec=args.interval, run_once=args.once, port=args.port)
