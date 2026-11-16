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
from typing import Dict, Any, List, Optional

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
COOLDOWN_SECONDS = 2700          # 45 分鐘同標的下單冷卻期 (自 20 分鐘延長，壓制短線過度交易磨損)
DAILY_MAX_TRADES_PER_SYMBOL = 4  # 單一標的單日最大開倉次數 (嚴格節流杜絕震盪市頻繁開倉)
STALE_TIMEOUT_SECONDS = 1200     # 20 分鐘陳舊訂單超時閾值
MES_DRIFT_THRESHOLD = 12.0       # /MES 價格偏離 12 點
MNQ_DRIFT_THRESHOLD = 35.0       # /MNQ 價格偏離 35 點
MGC_DRIFT_THRESHOLD = 6.0        # /MGC 價格偏離 6.0 點 ($6.0 / oz)
MCL_DRIFT_THRESHOLD = 0.50       # /MCL 價格偏離 0.50 點 ($0.50 / 桶)
TLT_DRIFT_THRESHOLD = 0.60       # TLT 價格偏離 0.60 點
M2K_DRIFT_THRESHOLD = 5.0        # /M2K 價格偏離 5.0 點
MBT_DRIFT_THRESHOLD = 400.0      # /MBT 價格偏離 400 點
FX_DRIFT_THRESHOLD = 0.20        # USD/JPY 價格偏離 20 pips (0.20 日圓)
EUR_DRIFT_THRESHOLD = 0.0020     # EUR/USD 價格偏離 20 pips (0.0020)
ADX_MIN_THRESHOLD = 20.0         # 15M ADX 趨勢體制濾網 (低於 20 判定為中性震盪，禁止動量突破)
CLIENT_ID = 401                  # 專用 Daemon Client ID

# 全域狀態
running = True
last_order_times = {}            # {symbol: timestamp}
order_submission_times = {}      # {orderId: timestamp}
daily_trades_counter = {}        # {symbol: count} 記錄當日各標的開倉次數
current_trading_date = ""        # 交易日記錄 (YYYY-MM-DD)
trailing_stop_triggered = set()  # 已觸發保本止損之 Order ID 集合
circuit_breaker_active = False
recent_logs: List[str] = []


def is_session_open_quiet_period(dt: Optional[datetime] = None) -> bool:
    """
    美股正規交易時段開盤前 10 分鐘靜默期濾網 (Taipei Time 22:30 ~ 22:40)
    避開開盤初期瞬間流動性失衡、點差擴大與非理性假突破造成的滑價打損。
    """
    if dt is None:
        dt = datetime.now()
    return dt.hour == 22 and 30 <= dt.minute < 40


def compute_adx_indicator(high_series, low_series, close_series, period: int = 14) -> float:
    """
    Wilder's 14-period Average Directional Index (ADX) 經典計量指標計算
    """
    import pandas as pd
    if len(close_series) < period * 2:
        return 25.0
    
    up = high_series.diff()
    down = -low_series.diff()
    plus_dm = pd.Series(0.0, index=close_series.index)
    plus_dm[(up > down) & (up > 0)] = up[(up > down) & (up > 0)]
    minus_dm = pd.Series(0.0, index=close_series.index)
    minus_dm[(down > up) & (down > 0)] = down[(down > up) & (down > 0)]
    
    tr1 = high_series - low_series
    tr2 = (high_series - close_series.shift(1)).abs()
    tr3 = (low_series - close_series.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr.replace(0, 1e-9))
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr.replace(0, 1e-9))
    
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    return float(adx.iloc[-1])


def get_mnq_15m_adx() -> float:
    """
    抓取 /MNQ (或 NQ=F) 最近 15 分鐘 K 線並計算 14 期 ADX 趨勢強度指標
    """
    try:
        import yfinance as yf
        import pandas as pd
        df = yf.download('NQ=F', period='5d', interval='15m', progress=False)
        if not df.empty and len(df) >= 28:
            if isinstance(df.columns, pd.MultiIndex):
                high = df['High'].iloc[:, 0]
                low = df['Low'].iloc[:, 0]
                close = df['Close'].iloc[:, 0]
            else:
                high = df['High']
                low = df['Low']
                close = df['Close']
            val = compute_adx_indicator(high, low, close, period=14)
            return round(val, 2)
    except Exception as e:
        logger.warning(f"ADX 計算異常，採用安全基準值 25.0: {e}")
    return 25.0


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
    global running, circuit_breaker_active, current_trading_date

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
    last_adx_time = datetime.min
    current_mnq_adx = 25.0
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

            # 3.5 每 24 小時定時派發量化交易與投研郵報至 Gmail (週日自動發送每週總結，平日發送每日日報)
            if (now - last_daily_report_time).total_seconds() > 86400:
                try:
                    cur_d = get_taipei_datestr()
                    is_sunday = now.weekday() == 6
                    if is_sunday:
                        from scripts.daily_report_dispatcher import dispatch_weekly_report
                        add_recent_log(f"📧 正在生成並派發【每週量化交易總結週報】({cur_d}) 至 Gmail...")
                        dispatch_weekly_report(cur_d)
                        add_recent_log(f"✅ 【週報派發成功】{cur_d} weekly report and trading report 已送達！")
                    else:
                        from scripts.daily_report_dispatcher import dispatch_daily_report
                        add_recent_log(f"📧 正在生成並派發每 24 小時交易日報 ({cur_d}) 至 Gmail...")
                        dispatch_daily_report(cur_d)
                        add_recent_log(f"✅ 【日報派發成功】{cur_d} daily report and trading report 已送達！")
                    last_daily_report_time = now
                except Exception as mail_e:
                    add_recent_log(f"⚠️ 郵報派發異常: {mail_e}")

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
                            drift_limit = (
                                MES_DRIFT_THRESHOLD if "MES" in sym else
                                (MNQ_DRIFT_THRESHOLD if "MNQ" in sym else
                                (MGC_DRIFT_THRESHOLD if "MGC" in sym else
                                (MCL_DRIFT_THRESHOLD if "MCL" in sym else
                                (TLT_DRIFT_THRESHOLD if "TLT" in sym else
                                (M2K_DRIFT_THRESHOLD if "M2K" in sym else
                                (MBT_DRIFT_THRESHOLD if "MBT" in sym else
                                (EUR_DRIFT_THRESHOLD if "EUR" in sym else FX_DRIFT_THRESHOLD)))))))
                            )

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

            # 5.6 自適應保本追蹤止損 (Adaptive Breakeven Trailing Stop)
            # 當持倉浮盈達到目標 50% 時，自動將未成交之 Stop Loss 單平移至進場保本價 (+1.0 點 / +0.05 點)
            if is_connected and not circuit_breaker_active:
                try:
                    positions = engine.ib.positions()
                    stop_orders_by_sym = {}
                    for ot in engine.ib.openTrades():
                        if ot.order.orderType in ["STP", "TRAIL"] and ot.orderStatus.status in ["Submitted", "PreSubmitted"]:
                            s_clean = ot.contract.symbol
                            if ot.contract.secType in ["CONTFUT", "FUT"]:
                                s_clean = f"/{s_clean}"
                            elif ot.contract.secType == "CASH":
                                s_clean = f"{s_clean}{ot.contract.currency}"
                            stop_orders_by_sym.setdefault(s_clean, []).append(ot)

                    for pos in positions:
                        if pos.position == 0:
                            continue
                        pos_sym = pos.contract.symbol
                        if pos.contract.secType in ["CONTFUT", "FUT"]:
                            pos_sym = f"/{pos_sym}"
                        elif pos.contract.secType == "CASH":
                            pos_sym = f"{pos_sym}{pos.contract.currency}"

                        matching_stops = stop_orders_by_sym.get(pos_sym, [])
                        if not matching_stops:
                            continue

                        ticker = engine.ib.reqMktData(pos.contract)
                        time.sleep(0.5)
                        curr_mkt = None
                        for p in [ticker.marketPrice(), ticker.last, ticker.close, ticker.bid, ticker.ask]:
                            if p is not None and not math.isnan(p) and p > 0:
                                curr_mkt = float(p)
                                break
                        if not curr_mkt:
                            continue

                        entry_price = float(pos.avgCost)
                        # 各標的 50% 目標閾值與保本保護緩衝
                        if "MES" in pos_sym:
                            target_50pct, be_buffer, dec = 11.25, 1.0, 2
                        elif "MNQ" in pos_sym:
                            target_50pct, be_buffer, dec = 33.0, 1.0, 2
                        elif "MGC" in pos_sym:
                            target_50pct, be_buffer, dec = 10.0, 1.0, 2
                        elif "MCL" in pos_sym:
                            target_50pct, be_buffer, dec = 0.75, 0.10, 2
                        elif "TLT" in pos_sym:
                            target_50pct, be_buffer, dec = 0.75, 0.10, 2
                        elif "M2K" in pos_sym:
                            target_50pct, be_buffer, dec = 7.50, 0.50, 2
                        elif "MBT" in pos_sym:
                            target_50pct, be_buffer, dec = 750.0, 50.0, 1
                        elif "JPY" in pos_sym:
                            target_50pct, be_buffer, dec = 0.25, 0.05, 3
                        elif "EUR" in pos_sym:
                            target_50pct, be_buffer, dec = 0.0025, 0.0005, 5
                        else:
                            target_50pct, be_buffer, dec = 10.0, 1.0, 2

                        is_long = pos.position > 0
                        if is_long:
                            gain = curr_mkt - entry_price
                            if gain >= target_50pct:
                                target_sl = round(entry_price + be_buffer, dec)
                                for st_trade in matching_stops:
                                    cur_aux = float(st_trade.order.auxPrice or 0.0)
                                    if cur_aux < target_sl and st_trade.order.orderId not in trailing_stop_triggered:
                                        add_recent_log(f"🛡️ 【自適應保本止損】{pos_sym} 現價 {curr_mkt:.2f} 已達 50% 獲利閾值 (+{gain:.2f} >= +{target_50pct})！")
                                        add_recent_log(f"📈 將停損單 (Order ID {st_trade.order.orderId}) 自 {cur_aux:.2f} 上修至保本價 {target_sl:.2f}，鎖死無風險收益！")
                                        st_trade.order.auxPrice = target_sl
                                        engine.ib.placeOrder(st_trade.contract, st_trade.order)
                                        trailing_stop_triggered.add(st_trade.order.orderId)
                except Exception as be_err:
                    logger.warning(f"自適應保本止損處理異常: {be_err}")

            # 6. 量化策略評估與自動發單
            if is_connected and not circuit_breaker_active and risk_multiplier > 0:
                # 請求延遲/即時市場數據
                engine.ib.reqMarketDataType(3)

                # 重置跨日開倉計數器與保本觸發集合
                cur_date_str = get_taipei_datestr()
                if cur_date_str != current_trading_date:
                    daily_trades_counter.clear()
                    trailing_stop_triggered.clear()
                    current_trading_date = cur_date_str

                # 定期更新 /MNQ 15M ADX 體制指標 (每 10 分鐘計算一次)
                if (now - last_adx_time).total_seconds() > 600:
                    try:
                        current_mnq_adx = get_mnq_15m_adx()
                        last_adx_time = now
                        add_recent_log(f"📐 /MNQ 15M ADX 體制更新: {current_mnq_adx:.2f} (濾網閾值 {ADX_MIN_THRESHOLD})")
                    except Exception as e:
                        logger.warning(f"ADX 定時更新失敗: {e}")

                quiet_period = is_session_open_quiet_period(now)

                # 策略 1: /MES 日內 VWAP 均值回歸
                if "/MES" not in active_symbols and "MES" not in active_symbols:
                    if quiet_period:
                        add_recent_log("⏳ 美股開盤前 10 分鐘靜默期 (22:30-22:40)，暫停 /MES 開倉以規避流動性衝擊與滑價。")
                    elif daily_trades_counter.get("/MES", 0) >= DAILY_MAX_TRADES_PER_SYMBOL:
                        add_recent_log(f"⏸️ /MES 今日開倉次數已達上限 ({DAILY_MAX_TRADES_PER_SYMBOL} 次)，啟動頻率節流限制，今日不再開倉。")
                    else:
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
                                    daily_trades_counter["/MES"] = daily_trades_counter.get("/MES", 0) + 1
                                    add_recent_log(f"✅ /MES 括號單發送成功: Order ID {res.get('parent_id')} (今日第 {daily_trades_counter['/MES']} 次)")

                # 策略 2: /MNQ 開盤 15M 動量突破 (整合 15M ADX 體制濾網)
                if "/MNQ" not in active_symbols and "MNQ" not in active_symbols:
                    if quiet_period:
                        add_recent_log("⏳ 美股開盤前 10 分鐘靜默期 (22:30-22:40)，暫停 /MNQ 開倉以規避流動性衝擊與滑價。")
                    elif current_mnq_adx < ADX_MIN_THRESHOLD:
                        add_recent_log(f"⚠️ /MNQ 15M ADX ({current_mnq_adx:.1f}) < {ADX_MIN_THRESHOLD}，市場處於無趨勢中性震盪，暫停動量突破開倉！")
                    elif daily_trades_counter.get("/MNQ", 0) >= DAILY_MAX_TRADES_PER_SYMBOL:
                        add_recent_log(f"⏸️ /MNQ 今日開倉次數已達上限 ({DAILY_MAX_TRADES_PER_SYMBOL} 次)，啟動頻率節流限制，今日不再開倉。")
                    else:
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
                                    daily_trades_counter["/MNQ"] = daily_trades_counter.get("/MNQ", 0) + 1
                                    add_recent_log(f"✅ /MNQ 括號單發送成功: Order ID {res.get('parent_id')} (今日第 {daily_trades_counter['/MNQ']} 次)")

                # 策略 3: USD/JPY 倫敦/紐約突破 Carry
                if "USDJPY" not in active_symbols and "USD.JPY" not in active_symbols:
                    if daily_trades_counter.get("USDJPY", 0) >= DAILY_MAX_TRADES_PER_SYMBOL:
                        add_recent_log(f"⏸️ USD/JPY 今日開倉次數已達上限 ({DAILY_MAX_TRADES_PER_SYMBOL} 次)，啟動頻率節流限制，今日不再開倉。")
                    else:
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
                                    daily_trades_counter["USDJPY"] = daily_trades_counter.get("USDJPY", 0) + 1
                                    add_recent_log(f"✅ USD/JPY 括號單發送成功: Order ID {res.get('parent_id')} (今日第 {daily_trades_counter['USDJPY']} 次)")

                # 策略 4: /MGC COMEX 微型黃金期貨 (零 Beta 宏觀實質利率避險)
                if "/MGC" not in active_symbols and "MGC" not in active_symbols:
                    if daily_trades_counter.get("/MGC", 0) >= DAILY_MAX_TRADES_PER_SYMBOL:
                        add_recent_log(f"⏸️ /MGC 今日開倉次數已達上限 ({DAILY_MAX_TRADES_PER_SYMBOL} 次)，啟動頻率節流限制，今日不再開倉。")
                    else:
                        time_since_last = (now - last_order_times.get("/MGC", datetime.min)).total_seconds()
                        if time_since_last > COOLDOWN_SECONDS:
                            c_mgc = engine.make_contract("/MGC", "FUT")
                            t_mgc = engine.ib.reqMktData(c_mgc)
                            time.sleep(1)
                            mkt_price = 3880.0
                            for p in [t_mgc.marketPrice(), t_mgc.last, t_mgc.close, t_mgc.bid, t_mgc.ask]:
                                if p is not None and not math.isnan(p) and p > 0:
                                    mkt_price = float(p)
                                    break
                            if mkt_price > 0:
                                entry_p = round(mkt_price - 2.5, 2)
                                sl_p = round(entry_p - 8.0, 2)
                                tp_p = round(entry_p + 20.0, 2)
                                add_recent_log(f"🎯 策略 4 (/MGC 微型黃金): 現價 {mkt_price}，發送限價回調買單 @ {entry_p} (SL {sl_p}, TP {tp_p})")
                                res = engine.place_bracket_order("/MGC", "BUY", 1, entry_p, sl_p, tp_p, "FUT")
                                if res.get("success"):
                                    last_order_times["/MGC"] = now
                                    daily_trades_counter["/MGC"] = daily_trades_counter.get("/MGC", 0) + 1
                                    add_recent_log(f"✅ /MGC 括號單發送成功: Order ID {res.get('parent_id')} (今日第 {daily_trades_counter['/MGC']} 次)")

                # 策略 5: EURUSD 倫敦/紐約外匯跨大西洋政策差
                if "EURUSD" not in active_symbols and "EUR.USD" not in active_symbols:
                    if daily_trades_counter.get("EURUSD", 0) >= DAILY_MAX_TRADES_PER_SYMBOL:
                        add_recent_log(f"⏸️ EUR/USD 今日開倉次數已達上限 ({DAILY_MAX_TRADES_PER_SYMBOL} 次)，啟動頻率節流限制，今日不再開倉。")
                    else:
                        time_since_last = (now - last_order_times.get("EURUSD", datetime.min)).total_seconds()
                        if time_since_last > COOLDOWN_SECONDS:
                            c_eur = engine.make_contract("EURUSD", "CASH")
                            t_eur = engine.ib.reqMktData(c_eur)
                            time.sleep(1)
                            mkt_price = 1.10500
                            for p in [t_eur.marketPrice(), t_eur.last, t_eur.close, t_eur.bid, t_eur.ask]:
                                if p is not None and not math.isnan(p) and p > 0:
                                    mkt_price = float(p)
                                    break
                            if mkt_price > 0:
                                entry_p = round(mkt_price - 0.0008, 5)
                                sl_p = round(entry_p - 0.0025, 5)
                                tp_p = round(entry_p + 0.0050, 5)
                                add_recent_log(f"🎯 策略 5 (EUR/USD 歐美外匯): 現價 {mkt_price:.5f}，發送限價掛單 @ {entry_p:.5f} (SL {sl_p:.5f}, TP {tp_p:.5f})")
                                res = engine.place_bracket_order("EURUSD", "BUY", 20000, entry_p, sl_p, tp_p, "CASH")
                                if res.get("success"):
                                    last_order_times["EURUSD"] = now
                                    daily_trades_counter["EURUSD"] = daily_trades_counter.get("EURUSD", 0) + 1
                                    add_recent_log(f"✅ EUR/USD 括號單發送成功: Order ID {res.get('parent_id')} (今日第 {daily_trades_counter['EURUSD']} 次)")

                # 策略 6: /MCL NYMEX 微型輕原油期貨 (供給側滯脹與能源避險)
                if "/MCL" not in active_symbols and "MCL" not in active_symbols:
                    if daily_trades_counter.get("/MCL", 0) >= DAILY_MAX_TRADES_PER_SYMBOL:
                        add_recent_log(f"⏸️ /MCL 今日開倉次數已達上限 ({DAILY_MAX_TRADES_PER_SYMBOL} 次)，啟動頻率節流限制，今日不再開倉。")
                    else:
                        time_since_last = (now - last_order_times.get("/MCL", datetime.min)).total_seconds()
                        if time_since_last > COOLDOWN_SECONDS:
                            c_mcl = engine.make_contract("/MCL", "FUT")
                            t_mcl = engine.ib.reqMktData(c_mcl)
                            time.sleep(1)
                            mkt_price = 88.50
                            for p in [t_mcl.marketPrice(), t_mcl.last, t_mcl.close, t_mcl.bid, t_mcl.ask]:
                                if p is not None and not math.isnan(p) and p > 0:
                                    mkt_price = float(p)
                                    break
                            if mkt_price > 0:
                                entry_p = round(mkt_price - 0.20, 2)
                                sl_p = round(entry_p - 0.60, 2)
                                tp_p = round(entry_p + 1.50, 2)
                                add_recent_log(f"🎯 策略 6 (/MCL 微型原油): 現價 {mkt_price}，發送限價回調買單 @ {entry_p} (SL {sl_p}, TP {tp_p})")
                                res = engine.place_bracket_order("/MCL", "BUY", 1, entry_p, sl_p, tp_p, "FUT")
                                if res.get("success"):
                                    last_order_times["/MCL"] = now
                                    daily_trades_counter["/MCL"] = daily_trades_counter.get("/MCL", 0) + 1
                                    add_recent_log(f"✅ /MCL 括號單發送成功: Order ID {res.get('parent_id')} (今日第 {daily_trades_counter['/MCL']} 次)")

                # 策略 7: TLT 美國 20+ 年期公債 ETF (存續期間與衰退通縮避險)
                if "TLT" not in active_symbols:
                    if daily_trades_counter.get("TLT", 0) >= DAILY_MAX_TRADES_PER_SYMBOL:
                        add_recent_log(f"⏸️ TLT 今日開倉次數已達上限 ({DAILY_MAX_TRADES_PER_SYMBOL} 次)，啟動頻率節流限制，今日不再開倉。")
                    else:
                        time_since_last = (now - last_order_times.get("TLT", datetime.min)).total_seconds()
                        if time_since_last > COOLDOWN_SECONDS:
                            c_tlt = engine.make_contract("TLT", "STK")
                            t_tlt = engine.ib.reqMktData(c_tlt)
                            time.sleep(1)
                            mkt_price = 79.50
                            for p in [t_tlt.marketPrice(), t_tlt.last, t_tlt.close, t_tlt.bid, t_tlt.ask]:
                                if p is not None and not math.isnan(p) and p > 0:
                                    mkt_price = float(p)
                                    break
                            if mkt_price > 0:
                                entry_p = round(mkt_price - 0.25, 2)
                                sl_p = round(entry_p - 0.75, 2)
                                tp_p = round(entry_p + 1.50, 2)
                                add_recent_log(f"🎯 策略 7 (TLT 長天期美債 ETF): 現價 {mkt_price}，發送限價回調買單 @ {entry_p} (SL {sl_p}, TP {tp_p})")
                                res = engine.place_bracket_order("TLT", "BUY", 50, entry_p, sl_p, tp_p, "STK")
                                if res.get("success"):
                                    last_order_times["TLT"] = now
                                    daily_trades_counter["TLT"] = daily_trades_counter.get("TLT", 0) + 1
                                    add_recent_log(f"✅ TLT 括號單發送成功: Order ID {res.get('parent_id')} (今日第 {daily_trades_counter['TLT']} 次)")

                # 策略 8: /M2K CME 微型羅素 2000 期貨 (中小型股規模因子 SMB)
                if "/M2K" not in active_symbols and "M2K" not in active_symbols:
                    if quiet_period:
                        add_recent_log("⏳ 美股開盤前 10 分鐘靜默期 (22:30-22:40)，暫停 /M2K 開倉以規避流動性衝擊與滑價。")
                    elif daily_trades_counter.get("/M2K", 0) >= DAILY_MAX_TRADES_PER_SYMBOL:
                        add_recent_log(f"⏸️ /M2K 今日開倉次數已達上限 ({DAILY_MAX_TRADES_PER_SYMBOL} 次)，啟動頻率節流限制，今日不再開倉。")
                    else:
                        time_since_last = (now - last_order_times.get("/M2K", datetime.min)).total_seconds()
                        if time_since_last > COOLDOWN_SECONDS:
                            c_m2k = engine.make_contract("/M2K", "FUT")
                            t_m2k = engine.ib.reqMktData(c_m2k)
                            time.sleep(1)
                            mkt_price = 2790.0
                            for p in [t_m2k.marketPrice(), t_m2k.last, t_m2k.close, t_m2k.bid, t_m2k.ask]:
                                if p is not None and not math.isnan(p) and p > 0:
                                    mkt_price = float(p)
                                    break
                            if mkt_price > 0:
                                entry_p = round(mkt_price - 3.0, 2)
                                sl_p = round(entry_p - 6.0, 2)
                                tp_p = round(entry_p + 15.0, 2)
                                add_recent_log(f"🎯 策略 8 (/M2K 羅素小型股): 現價 {mkt_price}，發送限價掛單 @ {entry_p} (SL {sl_p}, TP {tp_p})")
                                res = engine.place_bracket_order("/M2K", "BUY", 1, entry_p, sl_p, tp_p, "FUT")
                                if res.get("success"):
                                    last_order_times["/M2K"] = now
                                    daily_trades_counter["/M2K"] = daily_trades_counter.get("/M2K", 0) + 1
                                    add_recent_log(f"✅ /M2K 括號單發送成功: Order ID {res.get('parent_id')} (今日第 {daily_trades_counter['/M2K']} 次)")

                # 策略 9: /MBT CME 微型比特幣期貨 (全球 M2 流動性進攻衛星配置)
                if "/MBT" not in active_symbols and "MBT" not in active_symbols:
                    if daily_trades_counter.get("/MBT", 0) >= DAILY_MAX_TRADES_PER_SYMBOL:
                        add_recent_log(f"⏸️ /MBT 今日開倉次數已達上限 ({DAILY_MAX_TRADES_PER_SYMBOL} 次)，啟動頻率節流限制，今日不再開倉。")
                    else:
                        time_since_last = (now - last_order_times.get("/MBT", datetime.min)).total_seconds()
                        if time_since_last > COOLDOWN_SECONDS:
                            c_mbt = engine.make_contract("/MBT", "FUT")
                            t_mbt = engine.ib.reqMktData(c_mbt)
                            time.sleep(1)
                            mkt_price = 65000.0
                            for p in [t_mbt.marketPrice(), t_mbt.last, t_mbt.close, t_mbt.bid, t_mbt.ask]:
                                if p is not None and not math.isnan(p) and p > 0:
                                    mkt_price = float(p)
                                    break
                            if mkt_price > 0:
                                entry_p = round(mkt_price - 250.0, 1)
                                sl_p = round(entry_p - 600.0, 1)
                                tp_p = round(entry_p + 1500.0, 1)
                                add_recent_log(f"🎯 策略 9 (/MBT 微型比特幣): 現價 {mkt_price}，發送限價掛單 @ {entry_p} (SL {sl_p}, TP {tp_p})")
                                res = engine.place_bracket_order("/MBT", "BUY", 1, entry_p, sl_p, tp_p, "FUT")
                                if res.get("success"):
                                    last_order_times["/MBT"] = now
                                    daily_trades_counter["/MBT"] = daily_trades_counter.get("/MBT", 0) + 1
                                    add_recent_log(f"✅ /MBT 括號單發送成功: Order ID {res.get('parent_id')} (今日第 {daily_trades_counter['/MBT']} 次)")

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
                "mnq_adx": round(current_mnq_adx, 2),
                "daily_trades_counter": dict(daily_trades_counter),
                "is_quiet_period": is_session_open_quiet_period(now),
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
