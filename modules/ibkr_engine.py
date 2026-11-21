#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Personal Quant Firm | Interactive Brokers (IBKR) API 實盤/模擬交易引擎模組
========================================================================
基於 ib_insync 封裝之高可用 TWS / IB Gateway 本地 Socket 通訊引擎：
1. 實時帳戶概況（淨資產 NetLiquidation、現金、可用保證金、購買力、損益）
2. 即時持倉清單與微觀市值查詢 (Positions)
3. 標的合約自動辨識 (Stock, CME Micro Futures /MES /MNQ, Forex IDEALPRO USD/JPY)
4. 機構級全自動括號限價單 (Bracket Orders: Parent + Stop Loss + Take Profit)
5. 交易日誌自動入庫 SQLite (modules.database)
"""

import logging
from typing import Dict, Any, List, Optional
import pandas as pd
from datetime import datetime

try:
    from ib_insync import IB, Stock, Future, ContFuture, Forex, MarketOrder, LimitOrder, Contract, Bond, Index, util
    HAS_IB_INSYNC = True
except ImportError:
    HAS_IB_INSYNC = False

from modules.database import insert_trade_log

logger = logging.getLogger("IBKREngine")


class IBKREngine:
    """
    IBKR 本地 Socket 連線與交易控制器
    """
    def __init__(self, host: str = "127.0.0.1", port: int = 7497, client_id: int = 10):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib: Optional[Any] = None
        self._connected = False
        self._news_stream: List[Dict[str, Any]] = []
        self._news_sub_contract: Optional[Any] = None
        self._news_callback = None

    def connect(self, timeout: int = 3) -> bool:
        """
        建立與本地 TWS / IB Gateway 的 Socket 連線
        若遭遇 Error 326 (clientId 佔用衝突)，自動輪詢備用 clientId，保證連線不中斷。
        """
        if not HAS_IB_INSYNC:
            logger.error("ib_insync 套件未安裝")
            return False

        if self.ib and self.ib.isConnected():
            self._connected = True
            return True

        # 自動防衝突候選 Client ID 清單
        import random
        candidate_ids = [self.client_id, self.client_id + 5, self.client_id + 15, random.randint(500, 899)]
        for cid in candidate_ids:
            try:
                self.ib = IB()
                self.ib.connect(self.host, self.port, clientId=cid, timeout=timeout)
                if self.ib.isConnected():
                    self.client_id = cid
                    self._connected = True
                    return True
            except Exception as e:
                logger.warning(f"IBKR 連線重試 (clientId {cid}): {e}")
                try:
                    if self.ib:
                        self.ib.disconnect()
                except Exception:
                    pass

        self._connected = False
        return False

    def disconnect(self):
        """中斷連線"""
        if self.ib and self.ib.isConnected():
            try:
                self.ib.disconnect()
            except Exception:
                pass
        self._connected = False

    def is_connected(self) -> bool:
        """檢查連線狀態"""
        return bool(self.ib and self.ib.isConnected())

    def get_account_summary(self) -> Dict[str, Any]:
        """
        抓取即時帳戶資金與保證金結構
        """
        summary_dict = {
            "is_connected": False,
            "account_id": "未連線",
            "net_liquidation": 0.0,
            "total_cash": 0.0,
            "buying_power": 0.0,
            "excess_liquidity": 0.0,
            "init_margin": 0.0,
            "maint_margin": 0.0,
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "currency": "USD"
        }

        if not self.connect():
            return summary_dict

        try:
            accounts = self.ib.managedAccounts()
            account_id = accounts[0] if accounts else "DU_UNKNOWN"
            summary_dict["account_id"] = account_id
            summary_dict["is_connected"] = True

            items = self.ib.accountSummary()
            for it in items:
                if it.tag == "NetLiquidation":
                    summary_dict["net_liquidation"] = float(it.value)
                    summary_dict["currency"] = it.currency
                elif it.tag == "TotalCashValue":
                    summary_dict["total_cash"] = float(it.value)
                elif it.tag == "BuyingPower":
                    summary_dict["buying_power"] = float(it.value)
                elif it.tag == "ExcessLiquidity":
                    summary_dict["excess_liquidity"] = float(it.value)
                elif it.tag in ["InitMarginReq", "FullInitMarginReq"]:
                    summary_dict["init_margin"] = float(it.value)
                elif it.tag in ["MaintMarginReq", "FullMaintMarginReq"]:
                    summary_dict["maint_margin"] = float(it.value)
                elif it.tag == "UnrealizedPnL":
                    summary_dict["unrealized_pnl"] = float(it.value)
                elif it.tag == "RealizedPnL":
                    summary_dict["realized_pnl"] = float(it.value)

            return summary_dict
        except Exception as e:
            logger.error(f"抓取帳戶概況失敗: {e}")
            return summary_dict

    def get_positions(self) -> pd.DataFrame:
        """
        抓取即時持倉明細
        """
        if not self.connect():
            return pd.DataFrame()

        try:
            pos_list = self.ib.positions()
            rows = []
            for p in pos_list:
                sec_type = p.contract.secType
                sym = p.contract.symbol
                if sec_type == "FUT":
                    sym = f"/{p.contract.symbol}"
                elif sec_type == "CASH":
                    sym = f"{p.contract.symbol}/{p.contract.currency}"

                rows.append({
                    "帳號": p.account,
                    "標的代碼": sym,
                    "資產類別": sec_type,
                    "持有股數/口數": p.position,
                    "平均持倉成本 ($)": round(p.avgCost, 2),
                    "合約ID": p.contract.conId
                })
            return pd.DataFrame(rows)
        except Exception as e:
            logger.error(f"抓取持倉失敗: {e}")
            return pd.DataFrame()

    def make_contract(self, symbol: str, sec_type: str = "STK"):
        """
        合約自動適配器 (美股 ETF, CME 微型期貨, COMEX 微型黃金, NYMEX 微型原油, 外匯)
        """
        sym_clean = symbol.replace("/", "").strip().upper()

        if sym_clean in ["MGC", "GC"]:
            # COMEX 微型黃金期貨連續合約 (MGC: 10 oz, GC: 100 oz)
            c = ContFuture(sym_clean, "COMEX")
            self.ib.qualifyContracts(c)
            return c
        elif sym_clean in ["MCL", "CL"]:
            # NYMEX 微型原油期貨連續合約 (MCL: 100 桶, CL: 1,000 桶)
            c = ContFuture(sym_clean, "NYMEX")
            self.ib.qualifyContracts(c)
            return c
        elif sec_type == "FUT" or sym_clean in ["MES", "MNQ", "M2K", "MBT"]:
            # CME 微型期貨連續合約 (MES: S&P, MNQ: 那指, M2K: 羅素2000, MBT: 比特幣)
            c = ContFuture(sym_clean, "CME")
            self.ib.qualifyContracts(c)
            return c
        elif sec_type == "CASH" or sym_clean in ["USDJPY", "EURUSD", "GBPUSD", "AUDUSD"] or "EUR" in sym_clean or "JPY" in sym_clean:
            c = Forex(sym_clean)
            self.ib.qualifyContracts(c)
            return c
        else:
            # 美股現貨 / ETF (包含 TLT, SPY, QQQ, AAPL 等)
            c = Stock(sym_clean, "SMART", "USD")
            self.ib.qualifyContracts(c)
            return c

    def place_bracket_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        entry_price: float,
        stop_loss_price: float,
        take_profit_price: float,
        sec_type: str = "STK"
    ) -> Dict[str, Any]:
        """
        【機構級全自動括號單 (Bracket Order)】：
        同時送出 Parent 進入單 + 伺服器端 Stop Loss 停損單 + Take Profit 停利單。
        即使客戶端本地中斷，IBKR 撮合主機仍保證硬停損觸發！
        """
        if not self.connect():
            return {"success": False, "msg": "無法連線至本地 TWS (Port 7497)"}

        try:
            contract = self.make_contract(symbol, sec_type)
            action_clean = action.upper().strip()
            sym_clean = symbol.replace("/", "").strip().upper()

            # 依交易所合約微觀結構設定最小跳動點 (Minimum Tick Size) 與報價精度
            TICK_SPECS = {
                "MBT": (5.0, 1),
                "MES": (0.25, 2),
                "MNQ": (0.25, 2),
                "M2K": (0.10, 2),
                "MGC": (0.10, 2),
                "GC": (0.10, 2),
                "MCL": (0.01, 2),
                "CL": (0.01, 2),
                "TLT": (0.01, 2),
                "USDJPY": (0.001, 3),
                "EURUSD": (0.00005, 5)
            }
            tick, dec = TICK_SPECS.get(sym_clean, (0.01, 2))

            def _to_tick(p: float) -> float:
                if tick <= 0:
                    return round(p, dec)
                return round(round(p / tick) * tick, dec)

            entry_p = _to_tick(entry_price)
            tp_p = _to_tick(take_profit_price)
            sl_p = _to_tick(stop_loss_price)

            # 建立括號單三聯件 (Parent + TP + SL)
            bracket = self.ib.bracketOrder(
                action=action_clean,
                quantity=quantity,
                limitPrice=entry_p,
                takeProfitPrice=tp_p,
                stopLossPrice=sl_p,
                tif="DAY"
            )

            # 強制設置每筆子單之 TIF 為 DAY，確保 CME 期貨與各商品通過 TWS 預設規則驗證
            for o in bracket:
                o.tif = "DAY"

            # 依序掛單 (由最後一筆 StopLoss transmit=True 觸發原子性全部送出)
            trades = []
            for o in bracket:
                trade = self.ib.placeOrder(contract, o)
                trades.append(trade)
            self.ib.sleep(0.5)

            # 記錄到 SQLite 資料庫
            order_desc = f"{action_clean} {quantity} {symbol} @ 限價 ${entry_p} (停損: ${sl_p}, 停利: ${tp_p})"
            insert_trade_log(
                symbol=symbol,
                action=order_desc,
                pnl=0.0,
                strategy_type="IBKR 模擬帳戶自動交易 (Bracket Order)",
                reason=f"自動發單至帳戶 {self.ib.managedAccounts()}",
                audit_status="已委託 (掛單中)"
            )

            return {
                "success": True,
                "msg": f"✅ 括號單發送成功！主單與停損單已成功掛入 IBKR 模擬伺服器 (Order ID: {bracket[0].orderId})",
                "parent_id": bracket[0].orderId
            }
        except Exception as e:
            logger.error(f"括號單發送失敗: {e}")
            return {"success": False, "msg": f"下單失敗: {e}"}

    def place_market_order(self, symbol: str, action: str, quantity: int, sec_type: str = "STK") -> Dict[str, Any]:
        """
        市價單快速執行
        """
        if not self.connect():
            return {"success": False, "msg": "無法連線至本地 TWS (Port 7497)"}

        try:
            contract = self.make_contract(symbol, sec_type)
            order = MarketOrder(action.upper().strip(), quantity)
            trade = self.ib.placeOrder(contract, order)

            insert_trade_log(
                symbol=symbol,
                action=f"市價單 {action} {quantity} {symbol}",
                pnl=0.0,
                strategy_type="IBKR 市價下單",
                reason="手動觸發市價執行",
                audit_status="已送出"
            )
            return {"success": True, "msg": f"✅ 市價單已送出 (Order ID: {trade.order.orderId})"}
        except Exception as e:
            return {"success": False, "msg": f"下單失敗: {e}"}

    def _on_tick_news(self, news_tick):
        """內部回調：接收 Generic Tick 292 即時新聞推播"""
        try:
            ts = news_tick.timeStamp / 1000.0 if news_tick.timeStamp > 1e11 else news_tick.timeStamp
            dt_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            dt_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        headline_clean = news_tick.headline
        # 清除前綴標籤如 {A:...}
        if headline_clean.startswith("{") and "}" in headline_clean:
            headline_clean = headline_clean.split("}", 1)[1].strip()

        item = {
            "title": headline_clean,
            "headline": headline_clean,
            "date": dt_str,
            "timestamp": dt_str,
            "provider": news_tick.providerCode,
            "article_id": news_tick.articleId,
            "extra_data": getattr(news_tick, "extraData", ""),
            "source": f"TWS-Tick292 ({news_tick.providerCode})"
        }

        # 去重與長度限制 (保留最新 100 筆)
        if not any(x.get("article_id") == news_tick.articleId for x in self._news_stream):
            self._news_stream.insert(0, item)
            if len(self._news_stream) > 100:
                self._news_stream.pop()
            logger.info(f"📰 [TWS Live News] ({news_tick.providerCode}) {headline_clean}")

        if self._news_callback and callable(self._news_callback):
            try:
                self._news_callback(item)
            except Exception as cb_err:
                logger.warning(f"新聞回調執行異常: {cb_err}")

    def subscribe_realtime_news(self, symbol: str = "SPY", sec_type: str = "STK", callback=None) -> bool:
        """
        訂閱 TWS 原生 Generic Tick 292 即時新聞串流 (Realtime News Bulletins)
        支援自動掛載新聞提供商，無縫接收 Briefing, Dow Jones 等即時外電。
        """
        if not self.connect():
            return False
        if callback:
            self._news_callback = callback

        try:
            contract = self.make_contract(symbol, sec_type)
            if not getattr(contract, "conId", 0):
                self.ib.qualifyContracts(contract)

            # 掛載事件監聽
            if hasattr(self.ib, 'tickNewsEvent'):
                if self._on_tick_news not in self.ib.tickNewsEvent:
                    self.ib.tickNewsEvent += self._on_tick_news

            # 傳入 Generic Tick 292 啟用即時新聞推送
            self._news_sub_contract = contract
            self.ib.reqMktData(contract, genericTickList="292", snapshot=False)
            logger.info(f"✅ 已成功訂閱 {symbol} 之 TWS Generic Tick 292 即時新聞串流！")
            return True
        except Exception as e:
            logger.error(f"訂閱 Tick 292 新聞失敗: {e}")
            return False

    def get_news_providers(self) -> List[Dict[str, str]]:
        """查詢 TWS 帳戶已開通之新聞提供商清單 (News Providers)"""
        if not self.connect():
            return []
        try:
            providers = self.ib.reqNewsProviders()
            return [{"code": p.code, "name": p.name} for p in providers]
        except Exception as e:
            logger.warning(f"查詢新聞提供商失敗: {e}")
            return []

    def get_recent_news(self, symbol: str = "SPY", limit: int = 10) -> List[Dict[str, Any]]:
        """
        獲取最新機構財經新聞。優先讀取 Tick 292 即時串流快取，
        若快取為空則調用 reqHistoricalNews 進行歷史新聞回補。
        """
        if not self.connect():
            return []

        # 優先返回即時串流快取
        if self._news_stream:
            return self._news_stream[:limit]

        # 若串流尚未累積，調用 reqHistoricalNews 抓取最新機構新聞
        try:
            providers = self.get_news_providers()
            p_codes = "+".join([p["code"] for p in providers]) if providers else "BRFG+BRFUPDN+DJNL"

            contract = self.make_contract(symbol, "STK")
            if not getattr(contract, "conId", 0):
                self.ib.qualifyContracts(contract)

            hist_items = self.ib.reqHistoricalNews(
                conId=contract.conId,
                providerCodes=p_codes,
                startDateTime="",
                endDateTime="",
                totalResults=limit
            )

            results = []
            for item in hist_items:
                hl = item.headline
                if hl.startswith("{") and "}" in hl:
                    hl = hl.split("}", 1)[1].strip()
                t_str = item.time.strftime("%Y-%m-%d %H:%M:%S") if hasattr(item.time, "strftime") else str(item.time)
                news_dict = {
                    "title": hl,
                    "headline": hl,
                    "date": t_str,
                    "timestamp": t_str,
                    "provider": item.providerCode,
                    "article_id": item.articleId,
                    "source": f"TWS-Historical ({item.providerCode})"
                }
                results.append(news_dict)
                if not any(x.get("article_id") == item.articleId for x in self._news_stream):
                    self._news_stream.append(news_dict)

            return results
        except Exception as e:
            logger.warning(f"TWS 歷史新聞回補失敗: {e}")
            return []

    def get_news_article(self, provider_code: str, article_id: str) -> str:
        """獲取指定新聞之完整內文 (HTML/Text)"""
        if not self.connect():
            return ""
        try:
            art = self.ib.reqNewsArticle(provider_code, article_id)
            return art.articleText if hasattr(art, "articleText") else str(art)
        except Exception as e:
            logger.warning(f"獲取新聞內文失敗 ({article_id}): {e}")
            return ""

    def place_bond_order(
        self,
        symbol_or_cusip: str,
        action: str,
        quantity_in_thousands: int,
        limit_price: Optional[float] = None,
        order_type: str = "LMT",
        currency: str = "USD"
    ) -> Dict[str, Any]:
        """
        固定收益 (Fixed Income) 債券/國庫券專用委託發送方法。
        
        【重要官方規範】：
        1. 數量單位：固定收益商品的數量以 $1,000 面額 (Units of $1k Face Value) 為單位。
           例如 quantity_in_thousands = 10 代表委託面額 $10,000 美元。
        2. 防彈窗卡死提醒：必須在 TWS 設定勾選
           「Global Configuration -> API -> Precautions -> Bypass bond disclaimer for API orders」，
           否則 API 委託會因免責聲明彈窗而受阻。
        """
        if not self.connect():
            return {"success": False, "msg": "無法連線至本地 TWS"}

        try:
            action_clean = action.upper().strip()
            if symbol_or_cusip.startswith("IBCID") or len(symbol_or_cusip) == 9:
                contract = Contract(secType="BOND", exchange="SMART", currency=currency)
                contract.cusip = symbol_or_cusip
            else:
                contract = Contract(secType="BOND", symbol=symbol_or_cusip, exchange="SMART", currency=currency)

            self.ib.qualifyContracts(contract)

            qty = float(quantity_in_thousands)
            if order_type.upper() == "LMT" and limit_price is not None:
                order = LimitOrder(action_clean, qty, limit_price)
            else:
                order = MarketOrder(action_clean, qty)

            trade = self.ib.placeOrder(contract, order)
            self.ib.sleep(0.5)

            order_desc = f"{action_clean} {quantity_in_thousands}k 面額 {symbol_or_cusip} @ {'市價' if limit_price is None else f'${limit_price}'}"
            insert_trade_log(
                symbol=symbol_or_cusip,
                action=f"債券委託: {order_desc}",
                pnl=0.0,
                strategy_type="IBKR 固定收益 (BOND) 交易",
                reason=f"發單至帳戶 {self.ib.managedAccounts()} (單位: $1k 面額)",
                audit_status="已送出 (請確認已開啟 Bypass bond disclaimer)"
            )

            logger.info(f"✅ 固定收益債券委託已送出: {order_desc} (Order ID: {trade.order.orderId})")
            return {
                "success": True,
                "msg": f"✅ 債券委託已發送 (Order ID: {trade.order.orderId})，面額: ${quantity_in_thousands * 1000:,} USD",
                "order_id": trade.order.orderId
            }
        except Exception as e:
            logger.error(f"固定收益委託發送失敗: {e}")
            return {"success": False, "msg": f"債券委託失敗: {e}"}

    def get_vix_term_structure(self) -> Dict[str, float]:
        """
        透過 TWS API 原生獲取 CBOE 波動率指數期限結構 (VIX 30D, VIX3M 90D, VIX9D 9D)。
        機構低延遲專線，若查詢失敗返回空字典。
        """
        if not self.connect():
            return {}
        try:
            contracts = {
                "vix": Index('VIX', 'CBOE'),
                "vix3m": Index('VIX3M', 'CBOE'),
                "vix9d": Index('VIX9D', 'CBOE')
            }
            self.ib.qualifyContracts(*contracts.values())

            results = {}
            for key, contract in contracts.items():
                if getattr(contract, "conId", 0):
                    bars = self.ib.reqHistoricalData(
                        contract,
                        endDateTime='',
                        durationStr='2 D',
                        barSizeSetting='1 day',
                        whatToShow='TRADES',
                        useRTH=True
                    )
                    if bars:
                        results[key] = round(float(bars[-1].close), 2)
            return results
        except Exception as e:
            logger.debug(f"TWS VIX 期限結構查詢失敗: {e}")
            return {}


# 單例快取實例
_engine_instance: Optional[IBKREngine] = None

def get_ibkr_engine(port: int = 7497, client_id: int = 10) -> IBKREngine:
    global _engine_instance
    if _engine_instance is None or _engine_instance.port != port or _engine_instance.client_id != client_id or not _engine_instance.is_connected():
        _engine_instance = IBKREngine(port=port, client_id=client_id)
    return _engine_instance
