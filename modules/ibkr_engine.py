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
    from ib_insync import IB, Stock, Future, ContFuture, Forex, MarketOrder, LimitOrder, util
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
        candidate_ids = [self.client_id, self.client_id + 1, self.client_id + 2, self.client_id + 5, self.client_id + 10]
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
        合約自動適配器 (美股 ETF, CME 微型期貨, 外匯)
        """
        sym_clean = symbol.replace("/", "").strip().upper()

        if sec_type == "FUT" or sym_clean in ["MES", "MNQ", "MGC"]:
            # CME 微型期貨連續合約
            c = ContFuture(sym_clean, "CME")
            self.ib.qualifyContracts(c)
            return c
        elif sec_type == "CASH" or "JPY" in sym_clean or sym_clean == "USDJPY":
            c = Forex("USDJPY")
            self.ib.qualifyContracts(c)
            return c
        else:
            # 美股現貨 / ETF
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

            # 建立括號單三聯件 (Parent + TP + SL)
            bracket = self.ib.bracketOrder(
                action=action_clean,
                quantity=quantity,
                limitPrice=round(entry_price, 2),
                takeProfitPrice=round(take_profit_price, 2),
                stopLossPrice=round(stop_loss_price, 2),
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
            order_desc = f"{action_clean} {quantity} {symbol} @ 限價 ${entry_price:.2f} (停損: ${stop_loss_price:.2f}, 停利: ${take_profit_price:.2f})"
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


# 單例快取實例
_engine_instance: Optional[IBKREngine] = None

def get_ibkr_engine(port: int = 7497, client_id: int = 10) -> IBKREngine:
    global _engine_instance
    if _engine_instance is None or _engine_instance.port != port or _engine_instance.client_id != client_id or not _engine_instance.is_connected():
        _engine_instance = IBKREngine(port=port, client_id=client_id)
    return _engine_instance
