#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Personal Quant Firm | 全球宏觀投研自動化派發與歸檔引擎 (Macro Dispatcher)
==============================================================
功能：
1. 定時抓取最新 FRED 總經指標、美債殖利率、美聯儲淨流動性與外匯利差。
2. 調用 Gemini AI 首席宏觀策略官生成機構級晨報 / 夕報。
3. 自動將研報結構化存入 SQLite 資料庫 (quant_firm.db)，供前端戰情室即時翻閱。
4. 支援 Windows 工作排程器 (Task Scheduler) 與 CLI 離線呼叫。

使用範例：
    python scripts/macro_dispatcher.py --type morning
    python scripts/macro_dispatcher.py --type evening
"""

import sys
import os
import json
import argparse
from datetime import datetime

# Windows 終端編碼相容性設定
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# 將專案根目錄加入路徑
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import unittest.mock as mock
for _mod in ["streamlit", "plotly", "plotly.graph_objects"]:
    if _mod not in sys.modules:
        try:
            __import__(_mod)
        except ImportError:
            sys.modules[_mod] = mock.MagicMock()

from modules.database import save_macro_report
from views.tab_macro import fetch_macro_matrix
from modules.ai_engine import generate_content_with_fallback
import google.generativeai as genai


def load_env_file(filepath):
    """手動解析 .env 檔案，避免外部相依問題"""
    env_vars = {}
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()
    return env_vars


def run_dispatcher(report_type: str = "morning", custom_gemini_key: str = None, custom_fred_key: str = None):
    print("=" * 65)
    print(f"[START] Macro Dispatcher 啟動宏觀投研自動化流程 ({report_type.upper()})")
    print(f"[TIME]  執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    # 讀取金鑰
    env_dict = load_env_file(os.path.join(PROJECT_ROOT, ".env"))
    fred_key = custom_fred_key or env_dict.get("FRED_API_KEY") or os.getenv("FRED_API_KEY", "")
    gemini_key = custom_gemini_key or env_dict.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", "")

    if not gemini_key:
        print("[ERROR] 未偵測到 GEMINI_API_KEY，請於 .env 或環境變數中設定。")
        return False

    # 1. 抓取最新總經矩陣
    print("[INFO] 正在串接美國聯準會 (FRED) 與全球跨市場即時指標...")
    m, is_live = fetch_macro_matrix(fred_key)
    print(f"       連線狀態: {'即時官方連線 (LIVE)' if is_live else '離線基準數據 (OFFLINE)'}")
    print(f"       基準利率: {m['dff_cur']:.2f}% | 淨流動性: ${m['net_liq']:.3f}T | 薩姆規則: {m['sahm_val']:.2f}%")
    print(f"       10Y 美債: {m['dgs10_cur']:.2f}% | USD/JPY: {m['usdjpy']:.2f}")

    # 2. 構建機構級 Prompt
    r_star = 1.0
    taylor_rate = r_star + m['pce_cur'] + 0.5 * (m['pce_cur'] - 2.0) - 1.0 * (m['unrate_cur'] - 4.2)
    rate_gap = m['dff_cur'] - taylor_rate
    us_jp_spread = m['dff_cur'] - 0.25

    type_title = "晨間全球宏觀速遞 (Morning Macro Brief)" if report_type == "morning" else "傍晚跨市場覆盤報告 (Evening Macro Recap)"

    prompt = f"""
    你是一位華爾街頂級全球宏觀對衝基金的 Chief Global Macro Strategist（首席全球宏觀策略官兼計量經濟學家）。
    請針對今日【{type_title}】進行深度跨資產研報分析：

    【底層即時宏觀指標快照】：
    - 聯準會有效基準利率 (DFF)：{m['dff_cur']:.2f}% (目標區間 {m['target_l']:.2f}% ~ {m['target_u']:.2f}%)
    - 計量泰勒法則推薦利率 (Taylor Rule Rate)：{taylor_rate:.2f}% (利率偏離值 {rate_gap:+.2f}%)
    - 美聯儲淨流動性總量：{m['net_liq']:.3f} 兆美元 (週變動 {m['net_liq_diff']:+.3f} 兆, WALCL {m['walcl_t']:.3f}T, TGA {m['wtregen_t']:.3f}T, RRP {m['rrp_t']:.3f}T)
    - 薩姆規則衰退指標 (Sahm Rule)：{m['sahm_val']:.2f}%
    - 股債 60 日滾動相關係數 ρ(SPY, TLT)：{m['stock_bond_corr']:+.3f}
    - 10 年期美債殖利率 (DGS10)：{m['dgs10_cur']}% (1D 變化 {m['dgs10_diff']:+.2f}%)
    - 2 年期美債殖利率 (DGS2)：{m['dgs2_cur']}% (1D 變化 {m['dgs2_diff']:+.2f}%)
    - 10Y - 2Y 殖利率利差 (T10Y2Y)：{m['t10y2y_cur']}%
    - 10 年期 TIPS 實質利率 (DFII10)：{m['dfii10_cur']}%
    - 外匯與 Carry Trade：USD/JPY {m['usdjpy']:.2f}, 美日利差 {us_jp_spread:+.2f}%
    - 官方失業率：{m['unrate_cur']}%, 核心 PCE：{m['pce_cur']}%
    - CBOE VIX 恐慌指數：{m['vix_cur']}

    【研報架構與格式規範】：
    1. 【核心宏觀論點與流動性池解碼】：剖析 Fed 淨流動性對資產價格的實質支撐，結合薩姆規則評估衰退機率。
    2. 【利率曲線與期限結構導航】：解析 10Y-2Y 曲線陡峭化進程與降息終點利率。
    3. 【跨市場套利與匯率防禦】：美日利差下的 Yen Carry Trade 穩定度與匯率推演。
    4. 【多資產配置權重指引】：明確列出權益（美股/台股）、公債（存續期 Duration 配置）、黃金/原油與外匯的具體配置比例（%）。
    5. **強制要求**：在每個章節結尾，務必用【白話大白話總結】附上一句大眾能懂的白話直言，說明這對投資人錢包到底有何影響。
    """

    # 3. 呼叫 Gemini AI
    print("[INFO] 正在呼叫 Gemini AI 旗艦模型生成機構級深度研報...")
    try:
        report_markdown = generate_content_with_fallback(gemini_key, prompt)
        print(f"[SUCCESS] 研報生成完成！長度: {len(report_markdown)} 字元")
    except Exception as e:
        print(f"[ERROR] AI 生成失敗: {e}")
        return False

    # 4. 儲存至 SQLite 資料庫
    report_title = f"{datetime.now().strftime('%Y-%m-%d')} {type_title}"
    summary_text = f"淨流動性 ${m['net_liq']:.2f}T | 基準利率 {m['dff_cur']:.2f}% | 薩姆指標 {m['sahm_val']:.2f}% | 股債相關 {m['stock_bond_corr']:+.2f}"
    metrics_json = json.dumps(m, ensure_ascii=False)

    print("[INFO] 正在將研報結構化歸檔至 SQLite 資料庫...")
    rep_id = save_macro_report(
        report_type=report_type.upper(),
        title=report_title,
        summary=summary_text,
        content_markdown=report_markdown,
        metrics_snapshot=metrics_json
    )

    print(f"[SUCCESS] 研報已正式入庫！記錄 ID: {rep_id}")
    print(f"[TITLE]   研報標題: {report_title}")
    print("=" * 65)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Macro Dispatcher - 定時宏觀研報派發引擎")
    parser.add_argument("--type", type=str, choices=["morning", "evening", "manual"], default="morning", help="研報類型 (morning / evening)")
    args = parser.parse_args()

    run_dispatcher(report_type=args.type)
