#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Personal Quant Firm | 產業研究與標的價格動態定價引擎 (Industry & Pricing Engine)
========================================================================
功能：
1. 定期自動抓取 11 大 S&P 產業板塊 ETF 與核心資產（SPY, QQQ, NVDA, TLT, GLD）最新收盤行情。
2. 結合「宏觀因子適應度 (Macro Beta)」與「標的價格技術估值 (20MA/50MA 乖離率、14D RSI、Alpha)」。
3. 落實「超買過熱懲罰 (Overbought Penalty)」：杜絕在高估值泡沫點位追高好產業。
4. 自動生成機構級產業研究與標的價格分析報告，持久化至 SQLite 資料庫 (macro_daily_reports)。
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List
import pandas as pd
import numpy as np
import yfinance as yf

from modules.time_utils import get_taipei_timestamp, get_taipei_datestr
from modules.database import save_macro_report

logger = logging.getLogger("IndustryPricingEngine")

# 11 大 S&P 500 精選行業 ETF 官方標的與宏觀 Beta 字典
SECTOR_MAP = {
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

# 核心傳導標的清單
BENCHMARK_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "NVDA", "TSLA"]


def calculate_rsi(series: pd.Series, period: int = 14) -> float:
    """計算 14 日 RSI 相對強弱指標"""
    if len(series) < period + 1:
        return 50.0
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return float(val) if not np.isnan(val) else 50.0


def scan_industry_and_prices(lookback_days: int = 90) -> pd.DataFrame:
    """
    抓取 11 大板塊與關鍵標的最新行情，計算價格動量、MA 偏離度與超買超賣指標
    """
    all_symbols = list(SECTOR_MAP.keys()) + BENCHMARK_ASSETS
    try:
        data = yf.download(all_symbols, period="6mo", interval="1d", progress=False, auto_adjust=True)
        if data.empty or "Close" not in data:
            logger.warning("yfinance 抓取為空，使用基礎備援矩陣")
            return pd.DataFrame()

        close_df = data["Close"]
        rows = []
        spy_close = close_df["SPY"] if "SPY" in close_df else None
        spy_1m_ret = (spy_close.iloc[-1] / spy_close.iloc[-21] - 1.0) if spy_close is not None and len(spy_close) >= 21 else 0.0

        for sym in all_symbols:
            if sym not in close_df or close_df[sym].dropna().empty:
                continue

            s = close_df[sym].dropna()
            if len(s) < 30:
                continue

            latest_price = float(s.iloc[-1])
            prev_price = float(s.iloc[-2])
            pct_change_1d = (latest_price / prev_price - 1.0) * 100.0

            # 1 個月與 3 個月報酬
            p_1m = float(s.iloc[-21]) if len(s) >= 21 else float(s.iloc[0])
            p_3m = float(s.iloc[-63]) if len(s) >= 63 else float(s.iloc[0])
            ret_1m = (latest_price / p_1m - 1.0) * 100.0
            ret_3m = (latest_price / p_3m - 1.0) * 100.0

            # 相對 SPY 的 1 個月超額 Alpha
            alpha_1m = ret_1m - (spy_1m_ret * 100.0)

            # 移動平均線與 Z-score 偏離度 (衡量是否過熱)
            ma20 = float(s.rolling(20).mean().iloc[-1])
            ma50 = float(s.rolling(50).mean().iloc[-1]) if len(s) >= 50 else ma20
            std50 = float(s.rolling(50).std().iloc[-1]) if len(s) >= 50 else 1.0
            z_score = (latest_price - ma50) / (std50 + 1e-9)

            # 14D RSI
            rsi_val = calculate_rsi(s, 14)

            # 價格估值狀態標籤
            if rsi_val >= 72 or z_score >= 2.0:
                price_status = "🔥 嚴重超買 (追高懲罰)"
                val_weight_mult = 0.7  # 降權 30%，防止高位接盤
            elif rsi_val <= 32 or z_score <= -2.0:
                price_status = "💎 超賣偏低 (安全邊際高)"
                val_weight_mult = 1.3  # 獎勵 30%，均值回歸契機
            else:
                price_status = "⚖️ 估值合理"
                val_weight_mult = 1.0

            name = SECTOR_MAP.get(sym, f"核心資產 ({sym})")
            rows.append({
                "代碼": sym,
                "名稱": name,
                "最新價格 ($)": round(latest_price, 2),
                "單日漲跌 (%)": round(pct_change_1d, 2),
                "1M 報酬 (%)": round(ret_1m, 2),
                "3M 報酬 (%)": round(ret_3m, 2),
                "相對 Alpha (%)": round(alpha_1m, 2),
                "50MA 乖離 Z值": round(z_score, 2),
                "14D RSI": round(rsi_val, 1),
                "價格估值狀態": price_status,
                "價格調節乘數": val_weight_mult
            })

        df = pd.DataFrame(rows)
        return df

    except Exception as e:
        logger.error(f"掃描產業與價格數據異常: {e}")
        return pd.DataFrame()


def update_and_generate_industry_report(persist_db: bool = True) -> Dict[str, Any]:
    """
    定期運行核心入口：
    抓取產業與價格，進行雙軸定價權重計算，並持久化至 SQLite 研報庫
    """
    df = scan_industry_and_prices()
    if df.empty:
        return {"success": False, "msg": "無法獲取市場即時價格數據"}

    # 提取超買與超賣名單
    overbought = df[df["價格估值狀態"].str.contains("超買")]["名稱"].tolist()
    oversold = df[df["價格估值狀態"].str.contains("超賣")]["名稱"].tolist()
    top_alpha = df.sort_values(by="相對 Alpha (%)", ascending=False).head(3)
    bottom_alpha = df.sort_values(by="相對 Alpha (%)", ascending=True).head(3)

    summary_msg = f"掃描完成！共覆蓋 {len(df)} 檔產業與核心標的。強勢領漲: {', '.join(top_alpha['代碼'].tolist())}；超買過熱標的: {len(overbought)} 檔。"

    # 組裝 Markdown 研報
    md_lines = [
        f"### 📊 每日產業動態與標的價格雙軸研報 ({get_taipei_datestr()})",
        "",
        f"- **數據更新時間**：`{get_taipei_timestamp()}`",
        f"- **大盤定價環境**：SPY 基底對照，覆蓋 11 大板塊與 6 大核心傳導資產",
        f"- **價格過熱超買 (追價懲罰)**：{', '.join(overbought) if overbought else '無 (估值健康)'}",
        f"- **超賣價值偏低 (安全邊際)**：{', '.join(oversold) if oversold else '無'}",
        "",
        "#### 1. 領先板塊 Top 3 (相對 SPY 超額 Alpha)",
    ]
    for _, r in top_alpha.iterrows():
        md_lines.append(f"- **{r['名稱']} ({r['代碼']})**：最新價 `${r['最新價格 ($)']}` | 1M 報酬 `{r['1M 報酬 (%)']}%` | Alpha `+{r['相對 Alpha (%)']}%` | RSI `{r['14D RSI']}` ({r['價格估值狀態']})")

    md_lines.append("\n#### 2. 落後防禦板塊 Bottom 3")
    for _, r in bottom_alpha.iterrows():
        md_lines.append(f"- **{r['名稱']} ({r['代碼']})**：最新價 `${r['最新價格 ($)']}` | 1M 報酬 `{r['1M 報酬 (%)']}%` | Alpha `{r['相對 Alpha (%)']}%` | RSI `{r['14D RSI']}` ({r['價格估值狀態']})")

    content_markdown = "\n".join(md_lines)

    if persist_db:
        try:
            save_macro_report(
                report_type="每日產業與標的價格動態研報",
                title=f"11大產業與標的價格掃描 ({get_taipei_datestr()})",
                summary=summary_msg,
                content_markdown=content_markdown,
                metrics_snapshot=df.to_json(orient="records", force_ascii=False)
            )
        except Exception as err:
            logger.warning(f"儲存產業報告失敗: {err}")

    return {
        "success": True,
        "dataframe": df,
        "summary": summary_msg,
        "report_markdown": content_markdown
    }


if __name__ == "__main__":
    import sys
    if sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    print("--- 測試產業與標的價格引擎 ---")
    res = update_and_generate_industry_report()
    print("成功狀態:", res["success"])
    print(res["summary"])
    if res["success"]:
        print(res["dataframe"].head(5).to_string())
