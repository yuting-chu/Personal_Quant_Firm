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
from ib_insync import MarketOrder
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

# 9 大多元資產計量參數與合約配置中樞 (ATR 動態乘數與資產屬性)
ASSET_CONFIG = {
    "/MES": {
        "yf": "ES=F", "dec": 2, "sec": "FUT", "qty": 1, "is_index": True,
        "k1": 0.6, "k2": 1.5, "k3": 2.5, "min_sl": 8.0, "default_price": 7530.0,
        "name": "微型標普", "tick": 0.25
    },
    "/MNQ": {
        "yf": "NQ=F", "dec": 2, "sec": "FUT", "qty": 1, "is_index": True,
        "k1": 0.5, "k2": 1.8, "k3": 2.8, "min_sl": 25.0, "default_price": 27680.0,
        "name": "微型那指", "tick": 0.25
    },
    "USDJPY": {
        "yf": "USDJPY=X", "dec": 3, "sec": "CASH", "qty": 10000, "is_index": False,
        "k1": 0.6, "k2": 1.8, "k3": 2.5, "min_sl": 0.15, "default_price": 159.50,
        "name": "美元日圓", "tick": 0.001
    },
    "/MGC": {
        "yf": "GC=F", "dec": 2, "sec": "FUT", "qty": 1, "is_index": False,
        "k1": 0.6, "k2": 1.8, "k3": 2.8, "min_sl": 4.0, "default_price": 3870.0,
        "name": "微型黃金", "tick": 0.10
    },
    "EURUSD": {
        "yf": "EURUSD=X", "dec": 5, "sec": "CASH", "qty": 20000, "is_index": False,
        "k1": 0.6, "k2": 2.0, "k3": 3.0, "min_sl": 0.0015, "default_price": 1.1050,
        "name": "歐美外匯", "tick": 0.00005
    },
    "/MCL": {
        "yf": "CL=F", "dec": 2, "sec": "FUT", "qty": 1, "is_index": False,
        "k1": 0.6, "k2": 2.0, "k3": 3.0, "min_sl": 0.40, "default_price": 88.0,
        "name": "微型原油", "tick": 0.01
    },
    "TLT": {
        "yf": "TLT", "dec": 2, "sec": "STK", "qty": 50, "is_index": False,
        "k1": 0.6, "k2": 2.0, "k3": 3.0, "min_sl": 0.40, "default_price": 79.5,
        "name": "長天期美債", "tick": 0.01
    },
    "/M2K": {
        "yf": "RTY=F", "dec": 2, "sec": "FUT", "qty": 1, "is_index": True,
        "k1": 0.6, "k2": 1.8, "k3": 2.8, "min_sl": 4.0, "default_price": 2790.0,
        "name": "微型羅素", "tick": 0.10
    },
    "/MBT": {
        "yf": "BTC-USD", "dec": 1, "sec": "FUT", "qty": 1, "is_index": False,
        "k1": 0.6, "k2": 1.8, "k3": 2.8, "min_sl": 300.0, "default_price": 65000.0,
        "name": "微型比特幣", "tick": 5.0
    }
}

# 全域狀態
running = True
last_order_times = {}            # {symbol: timestamp}
order_submission_times = {}      # {orderId: timestamp}
daily_trades_counter = {}        # {symbol: count} 記錄當日各標的開倉次數
current_trading_date = ""        # 交易日記錄 (YYYY-MM-DD)
trailing_stop_triggered = set()  # 已觸發保本止損之 Order ID 集合
circuit_breaker_active = False
recent_logs: List[str] = []


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


def fetch_multi_asset_regimes_and_atr() -> Dict[str, Dict[str, Any]]:
    """
    批次計算 9 大資產近 5 日 15 分鐘之 Wilder 14 期 ATR、14 期 ADX 與具備遲滯帶 (Hysteresis Band) 之 50 EMA 體制
    回傳字典: {symbol: {'regime': 'BULL'|'BEAR'|'NEUTRAL', 'atr': float, 'adx': float, 'price': float, 'ema50': float, 'band': float}}
    """
    import yfinance as yf
    import pandas as pd

    results = {}
    try:
        yf_list = [cfg["yf"] for cfg in ASSET_CONFIG.values()]
        data = yf.download(yf_list, period="5d", interval="15m", group_by="ticker", progress=False)

        for sym, cfg in ASSET_CONFIG.items():
            yf_t = cfg["yf"]
            try:
                df = data[yf_t] if yf_t in data else pd.DataFrame()
                if df.empty or len(df.dropna()) < 25:
                    results[sym] = {"regime": "NEUTRAL", "atr": 1.0, "adx": 25.0, "price": cfg["default_price"], "ema50": cfg["default_price"], "band": 0.25}
                    continue
                high = df["High"].dropna()
                low = df["Low"].dropna()
                close = df["Close"].dropna()

                tr1 = high - low
                tr2 = (high - close.shift(1)).abs()
                tr3 = (low - close.shift(1)).abs()
                tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                atr = float(tr.ewm(alpha=1/14, adjust=False).mean().iloc[-1])

                ema50 = close.ewm(span=50, adjust=False).mean()
                cur_p = float(close.iloc[-1])
                cur_ema = float(ema50.iloc[-1])
                prev_ema = float(ema50.iloc[-4]) if len(ema50) >= 5 else cur_ema

                # 14 期 ADX 趨勢強度指標
                adx_val = compute_adx_indicator(high, low, close, period=14)

                # 體制切換遲滯帶 (Hysteresis Band: delta = 0.25 * ATR)
                delta = 0.25
                hysteresis_band = delta * atr

                # 趨勢判定：價格實質突破 50EMA + 遲滯帶且均線向上為多頭；
                # 價格實質跌破 50EMA - 遲滯帶且均線向下為空頭；其餘為震盪/維持中性 (防止均線邊界穿梭噪訊)
                if cur_p > (cur_ema + hysteresis_band) and cur_ema >= prev_ema:
                    regime = "BULL"
                elif cur_p < (cur_ema - hysteresis_band) and cur_ema <= prev_ema:
                    regime = "BEAR"
                else:
                    regime = "NEUTRAL"

                results[sym] = {
                    "regime": regime,
                    "atr": round(atr, 5),
                    "adx": round(adx_val, 2),
                    "price": round(cur_p, cfg["dec"]),
                    "ema50": round(cur_ema, cfg["dec"]),
                    "band": round(hysteresis_band, cfg["dec"])
                }
            except Exception:
                results[sym] = {"regime": "NEUTRAL", "atr": 1.0, "adx": 25.0, "price": cfg["default_price"], "ema50": cfg["default_price"], "band": 0.25}
    except Exception as e:
        logger.warning(f"批次 ATR/Regime 下載異常: {e}")
        for sym, cfg in ASSET_CONFIG.items():
            results[sym] = {"regime": "NEUTRAL", "atr": 1.0, "adx": 25.0, "price": cfg["default_price"], "ema50": cfg["default_price"], "band": 0.25}

    return results


def is_session_open_quiet_period(dt: Optional[datetime] = None) -> bool:
    """
    美股正規交易時段開盤前 10 分鐘靜默期濾網 (Taipei Time 22:30 ~ 22:40)
    避開開盤初期瞬間流動性失衡、點差擴大與非理性假突破造成的滑價打損。
    """
    if dt is None:
        dt = datetime.now()
    return dt.hour == 22 and 30 <= dt.minute < 40


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
    last_regime_time = datetime.min
    current_mnq_adx = 25.0
    current_sentiment = {}
    cached_regimes = {}
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

            # 3.2 定期更新 9 大多元資產 15M ATR 與 50EMA 趨勢體制快照 (每 10 分鐘)
            if (now - last_regime_time).total_seconds() > 600 or not cached_regimes:
                try:
                    cached_regimes = fetch_multi_asset_regimes_and_atr()
                    last_regime_time = now
                    bull_cnt = sum(1 for v in cached_regimes.values() if v.get("regime") == "BULL")
                    bear_cnt = sum(1 for v in cached_regimes.values() if v.get("regime") == "BEAR")
                    neutral_cnt = sum(1 for v in cached_regimes.values() if v.get("regime") == "NEUTRAL")
                    add_recent_log(f"📊 9 大資產體制快照更新: 多頭 BULL({bull_cnt}) | 空頭 BEAR({bear_cnt}) | 震盪 NEUTRAL({neutral_cnt})")
                except Exception as e:
                    logger.warning(f"ATR/Regime 批次更新失敗: {e}")

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
                        gain = (curr_mkt - entry_price) if is_long else (entry_price - curr_mkt)
                        if gain >= target_50pct:
                            target_sl = round(entry_price + be_buffer, dec) if is_long else round(entry_price - be_buffer, dec)
                            for st_trade in matching_stops:
                                cur_aux = float(st_trade.order.auxPrice or 0.0)
                                should_adjust = (cur_aux < target_sl) if is_long else (cur_aux > target_sl or cur_aux == 0.0)
                                if should_adjust and st_trade.order.orderId not in trailing_stop_triggered:
                                    dir_str = "多單" if is_long else "空單"
                                    action_str = "上修" if is_long else "下修"
                                    add_recent_log(f"🛡️ 【自適應保本止損】{pos_sym} ({dir_str}) 現價 {curr_mkt:.{dec}f} 已達 50% 獲利閾值 (+{gain:.{dec}f} >= +{target_50pct:.{dec}f})！")
                                    add_recent_log(f"📈 將停損單 (Order ID {st_trade.order.orderId}) 自 {cur_aux:.{dec}f} {action_str}至保本價 {target_sl:.{dec}f}，鎖死無風險收益！")
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

                # 抓取當前帳戶持倉字典，支援【淨部位智能沖銷 (Netting Engine)】
                pos_dict = {}
                try:
                    current_positions = engine.ib.positions()
                    for p in current_positions:
                        if p.position == 0:
                            continue
                        p_sym = p.contract.symbol
                        if p.contract.secType in ["CONTFUT", "FUT"]:
                            pos_dict[f"/{p_sym}"] = float(p.position)
                            pos_dict[p_sym] = float(p.position)
                        elif p.contract.secType == "CASH":
                            pos_dict[f"{p_sym}{p.contract.currency}"] = float(p.position)
                            pos_dict[p_sym] = float(p.position)
                        else:
                            pos_dict[p_sym] = float(p.position)
                except Exception as pos_e:
                    logger.warning(f"持倉字典抓取異常: {pos_e}")

                # 6. 多資產動態 ATR 訂價與多空體制狀態機執行迴圈
                for sym, cfg in ASSET_CONFIG.items():
                    sym_clean = sym.replace("/", "").strip()

                    # 美股指數期貨開盤前 10 分鐘靜默期保護
                    if cfg.get("is_index") and quiet_period:
                        add_recent_log(f"⏳ 美股開盤前 10 分鐘靜默期 (22:30-22:40)，暫停 {sym} 開倉以規避流動性衝擊與滑價。")
                        continue

                    # /MNQ 專屬 15M ADX 體制濾網 (低於閾值判定為震盪，禁止動量追單)
                    if sym == "/MNQ" and current_mnq_adx < ADX_MIN_THRESHOLD:
                        add_recent_log(f"⚠️ /MNQ 15M ADX ({current_mnq_adx:.1f}) < {ADX_MIN_THRESHOLD}，市場處於無趨勢中性震盪，暫停動量突破開倉！")
                        continue

                    # 單日交易頻率上限檢查
                    if daily_trades_counter.get(sym, 0) >= DAILY_MAX_TRADES_PER_SYMBOL:
                        add_recent_log(f"⏸️ {sym} 今日開倉次數已達上限 ({DAILY_MAX_TRADES_PER_SYMBOL} 次)，啟動頻率節流限制，今日不再開倉。")
                        continue

                    # 冷卻時間檢查
                    time_since_last = (now - last_order_times.get(sym, datetime.min)).total_seconds()
                    if time_since_last <= COOLDOWN_SECONDS:
                        continue

                    # 體制判斷 (Regime & Sentiment State Machine)
                    regime_info = cached_regimes.get(sym, {})
                    asset_regime = regime_info.get("regime", "NEUTRAL")
                    atr_val = regime_info.get("atr", 1.0)
                    sentiment_score = current_sentiment.get("sentiment_score", 0.0)

                    # 多空狀態機決定交易方向
                    action = None
                    if asset_regime == "BULL":
                        action = "BUY"
                    elif asset_regime == "BEAR":
                        action = "SELL"
                    else:  # NEUTRAL
                        if sentiment_score >= 0.20:
                            action = "BUY"
                        elif sentiment_score <= -0.20:
                            action = "SELL"
                        else:
                            # 中性震盪且無宏觀方向性，不盲目開倉
                            continue

                    # 檢查當前實盤持倉，執行【淨部位智能沖銷機制 (Position Netting)】
                    curr_pos = pos_dict.get(sym, 0.0) or pos_dict.get(sym_clean, 0.0)

                    # Case 1: 目前持有多頭庫存 (curr_pos > 0)，但體制轉為空頭 (SELL)
                    if curr_pos > 0 and action == "SELL":
                        add_recent_log(f"⚠️ 【淨部位智能沖銷】{sym} 體制轉為空頭 (BEAR)，但帳戶持有多頭庫存 {curr_pos} 口/股！")
                        add_recent_log(f"🛑 立即撤銷 {sym} 現存掛單並送出市價平多單，杜絕逆勢鎖倉！")
                        for ot in list(engine.ib.openTrades()):
                            c_s = ot.contract.symbol
                            if c_s == sym_clean or f"/{c_s}" == sym:
                                engine.ib.cancelOrder(ot.order)
                        time.sleep(0.5)
                        c_close = engine.make_contract(sym, cfg["sec"])
                        close_order = MarketOrder("SELL", abs(curr_pos))
                        engine.ib.placeOrder(c_close, close_order)
                        add_recent_log(f"✅ {sym} 多頭部位平倉單已送出 (Order ID {close_order.orderId})，淨敞口歸零。")
                        last_order_times[sym] = now
                        continue

                    # Case 2: 目前持有多頭庫存 (curr_pos > 0)，且體制同為多頭 (BUY)
                    elif curr_pos > 0 and action == "BUY":
                        # 已順勢持有，由自適應保本止損保護，不重疊加倉
                        continue

                    # Case 3: 目前持有空頭庫存 (curr_pos < 0)，但體制轉為多頭 (BUY)
                    elif curr_pos < 0 and action == "BUY":
                        add_recent_log(f"⚠️ 【淨部位智能沖銷】{sym} 體制轉為多頭 (BULL)，但帳戶持有空頭庫存 {abs(curr_pos)} 口/股！")
                        add_recent_log(f"🛑 立即撤銷 {sym} 現存掛單並送出市價平空單，杜絕逆勢鎖倉！")
                        for ot in list(engine.ib.openTrades()):
                            c_s = ot.contract.symbol
                            if c_s == sym_clean or f"/{c_s}" == sym:
                                engine.ib.cancelOrder(ot.order)
                        time.sleep(0.5)
                        c_close = engine.make_contract(sym, cfg["sec"])
                        close_order = MarketOrder("BUY", abs(curr_pos))
                        engine.ib.placeOrder(c_close, close_order)
                        add_recent_log(f"✅ {sym} 空頭部位平倉單已送出 (Order ID {close_order.orderId})，淨敞口歸零。")
                        last_order_times[sym] = now
                        continue

                    # Case 4: 目前持有空頭庫存 (curr_pos < 0)，且體制同為空頭 (SELL)
                    elif curr_pos < 0 and action == "SELL":
                        # 已順勢持有，由自適應保本止損保護，不重疊加倉
                        continue

                    # Case 5: curr_pos == 0 (無持倉淨敞口)，若已在活動委託名單中則不重複下單
                    if sym in active_symbols or sym_clean in active_symbols:
                        continue

                    # 抓取 TWS 即時或延遲市場現價
                    c = engine.make_contract(sym, cfg["sec"])
                    t = engine.ib.reqMktData(c)
                    time.sleep(0.8)
                    curr_mkt = None
                    for p in [t.marketPrice(), t.last, t.close, t.bid, t.ask]:
                        if p is not None and not math.isnan(p) and p > 0:
                            curr_mkt = float(p)
                            break
                    if not curr_mkt:
                        curr_mkt = regime_info.get("price", cfg["default_price"])

                    if not curr_mkt or curr_mkt <= 0:
                        continue

                    # 依 14 期 Wilder ATR 與 ADX 動態計算進場緩衝、停損與停利空間 (Improvement 2)
                    dec = cfg["dec"]
                    k1_base, k2, k3 = cfg["k1"], cfg["k2"], cfg["k3"]
                    min_sl = cfg["min_sl"]

                    # 自適應 ADX 進場因子動態調節
                    asset_adx = regime_info.get("adx", 25.0)
                    if asset_adx >= 30.0:
                        # 強趨勢動量：壓縮進場緩衝至 0.5 倍 (下限 0.20)，貼近現價避免踏空單邊行情
                        eff_k1 = max(0.20, round(k1_base * 0.50, 2))
                        k1_tag = f"強動量貼緊 (ADX {asset_adx:.1f} >= 30, k1={eff_k1})"
                    elif asset_adx <= 20.0:
                        # 弱震盪整理：放大進場緩衝至 1.35 倍 (上限 0.90)，要求深幅回調提高安全邊際
                        eff_k1 = min(0.90, round(k1_base * 1.35, 2))
                        k1_tag = f"弱震盪深幅 (ADX {asset_adx:.1f} <= 20, k1={eff_k1})"
                    else:
                        eff_k1 = k1_base
                        k1_tag = f"常態體制 (ADX {asset_adx:.1f}, k1={eff_k1})"

                    buffer_dist = round(eff_k1 * atr_val, dec)
                    sl_dist = round(max(k2 * atr_val, min_sl), dec)
                    tp_dist = round(max(k3 * atr_val, min_sl * 1.5), dec)

                    tick_size = cfg.get("tick", 0.01)

                    def _to_tick(val: float) -> float:
                        if tick_size <= 0:
                            return round(val, dec)
                        return round(round(val / tick_size) * tick_size, dec)

                    if action == "BUY":
                        raw_entry = curr_mkt - buffer_dist
                        entry_p = _to_tick(raw_entry)
                        sl_p = _to_tick(entry_p - sl_dist)
                        tp_p = _to_tick(entry_p + tp_dist)
                        action_desc = "回調做多 (BULL / 50EMA+遲滯帶上方)" if asset_regime == "BULL" else "宏觀偏多做多 (NEUTRAL 震盪)"
                    else:  # SELL
                        raw_entry = curr_mkt + buffer_dist
                        entry_p = _to_tick(raw_entry)
                        sl_p = _to_tick(entry_p + sl_dist)
                        tp_p = _to_tick(entry_p - tp_dist)
                        action_desc = "反彈做空 (BEAR / 50EMA-遲滯帶下方)" if asset_regime == "BEAR" else "宏觀偏空做空 (NEUTRAL 震盪)"

                    add_recent_log(
                        f"🎯 [{cfg['name']}] {action} 策略啟動 | 體制: {asset_regime} (ATR: {atr_val}, {k1_tag}) | {action_desc} | "
                        f"現價 {curr_mkt:.{dec}f} -> 限價 {entry_p:.{dec}f} (SL {sl_p:.{dec}f}, TP {tp_p:.{dec}f})"
                    )

                    res = engine.place_bracket_order(sym, action, cfg["qty"], entry_p, sl_p, tp_p, cfg["sec"])
                    if res.get("success"):
                        last_order_times[sym] = now
                        daily_trades_counter[sym] = daily_trades_counter.get(sym, 0) + 1
                        add_recent_log(f"✅ {sym} ({cfg['name']}) 括號單發送成功: Order ID {res.get('parent_id')} (今日第 {daily_trades_counter[sym]} 次)")

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
                "asset_regimes": cached_regimes,
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

    # 標記狀態為停止 (保留體制快照與日誌)
    logger.info("正在退出守護進程並更新狀態檔案...")
    if "status_data" in locals() and isinstance(status_data, dict):
        status_data["is_running"] = False
        status_data["pid"] = None
        status_data["last_heartbeat"] = get_taipei_timestamp()
        status_data["tws_connected"] = False
        update_status_file(status_data)
    else:
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
