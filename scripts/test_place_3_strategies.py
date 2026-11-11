#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os

# 確保 Windows CMD/PowerShell 終端編碼支援 UTF-8
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.ibkr_engine import get_ibkr_engine

engine = get_ibkr_engine(port=7497, client_id=305)
if not engine.connect():
    print("CONNECT_FAILED: Unable to connect to TWS on port 7497")
    sys.exit(1)

ib = engine.ib
ib.reqMarketDataType(3)

print("TWS Connected successfully to account:", ib.managedAccounts())

results = []

# 1. 策略 1: /MES 日內 VWAP 均值回歸
res_mes = engine.place_bracket_order(
    symbol="/MES",
    action="BUY",
    quantity=1,
    entry_price=7610.00,
    stop_loss_price=7595.00,
    take_profit_price=7632.50,
    sec_type="FUT"
)
results.append(("策略 1: /MES VWAP 均值回歸", res_mes))

# 2. 策略 2: /MNQ 開盤 15M 動量突破
res_mnq = engine.place_bracket_order(
    symbol="/MNQ",
    action="BUY",
    quantity=1,
    entry_price=28350.00,
    stop_loss_price=28320.00,
    take_profit_price=28416.00,
    sec_type="FUT"
)
results.append(("策略 2: /MNQ 開盤 15M 動量突破", res_mnq))

# 3. 策略 3: USD/JPY 倫敦突破 Carry
res_fx = engine.place_bracket_order(
    symbol="USDJPY",
    action="BUY",
    quantity=10000,
    entry_price=159.50,
    stop_loss_price=159.25,
    take_profit_price=160.00,
    sec_type="CASH"
)
results.append(("策略 3: USD/JPY 倫敦突破 Carry", res_fx))

print("--- 下單執行結果報告 ---")
for label, r in results:
    status_str = "SUCCESS" if r.get("success") else "FAILED"
    print(f"[{status_str}] {label}: {r.get('msg')}")

# 查詢 TWS 即時活動訂單清單
open_trades = ib.openTrades()
print(f"\nTWS 伺服器端目前活躍委託數: {len(open_trades)} 筆")
for ot in open_trades:
    c = ot.contract
    o = ot.order
    st_name = ot.orderStatus.status
    print(f"  • {c.symbol} ({c.secType}) | {o.action} {o.totalQuantity} | 類型: {o.orderType} | 限價: {o.lmtPrice} | 觸價: {o.auxPrice} | 狀態: {st_name} | OrderId: {o.orderId}")

engine.disconnect()
