#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Personal Quant Firm | 全域宏觀情緒結構化量化引擎 (Sentiment Engine)
============================================================
遵循 docs/SENTIMENT_ENGINE_SPEC.md 規格書定義：
1. 抓取全球即時財經外電新聞 (modules/news_fetcher.py)。
2. 透過 Gemini-3.6-flash 自動備援鏈進行語意結構化解析，輸出標準 JSON：
   - sentiment_score: [-1.0, +1.0]
   - volatility_shock_flag: bool
   - risk_multiplier: float
   - key_drivers: list
3. 內建零依賴金融詞典啟發式備援算法 (Heuristic Fallback)，保證無網路/無 API Key 時永不崩潰。
4. 預留自建模型 / 外部平台無縫插拔開關 (CUSTOM_MODEL_ENDPOINT)。
"""

import os
import json
import re
import logging
from datetime import datetime
from typing import Dict, Any, List

from modules.time_utils import get_taipei_timestamp
from modules.news_fetcher import fetch_yahoo_finance_news
from modules.ai_engine import generate_content_with_fallback
from modules.database import save_macro_report

logger = logging.getLogger("SentimentEngine")

# 自建模型 / 外部平台插拔配置開關 (使用者未來可啟用)
USE_CUSTOM_MODEL = False
CUSTOM_MODEL_URL = os.getenv("CUSTOM_SENTIMENT_MODEL_URL", "http://127.0.0.1:8000/api/v1/sentiment")

# 金融詞典啟發式備援 (當 AI 無法調用時使用)
BULLISH_KEYWORDS = ["surge", "jump", "record", "gain", "rally", "growth", "cut", "stimulus", "profit", "soar", "upgrade", "beat", "positive", "strong"]
BEARISH_KEYWORDS = ["plunge", "fall", "drop", "slump", "war", "crisis", "crash", "hike", "inflation", "tariff", "recession", "down", "downgrade", "miss", "weak", "danger"]
SHOCK_KEYWORDS = ["emergency", "black swan", "halt", "invasion", "default", "catastrophe", "circuit breaker", "sanction"]


def _heuristic_sentiment_analysis(news_items: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    零外部相依金融詞典評分備援算法 (Heuristic Fallback Engine)
    保證即使在離線或無 API Key 時，系統也能穩定運作並提供合理的安全邊際。
    """
    if not news_items:
        return {
            "timestamp": get_taipei_timestamp(),
            "sentiment_score": 0.0,
            "regime_label": "中性觀望 (Neutral)",
            "volatility_shock_flag": False,
            "confidence_score": 0.5,
            "key_drivers": ["無即時新聞輸入，維持系統預設中性基線"],
            "macro_factors": {"inflation_pressure": 0.0, "liquidity_outlook": 0.0, "geopolitical_risk": 0.0},
            "risk_multiplier": 1.0,
            "execution_recommendation": "維持常態部位管理，各策略正常運行",
            "model_source": "Lexicon-Heuristic-Fallback-v1"
        }

    bull_hits = 0
    bear_hits = 0
    shock_detected = False
    drivers = []

    for item in news_items:
        title = item.get("title", "").lower()
        for kw in BULLISH_KEYWORDS:
            if kw in title:
                bull_hits += 1
        for kw in BEARISH_KEYWORDS:
            if kw in title:
                bear_hits += 1
        for kw in SHOCK_KEYWORDS:
            if kw in title:
                shock_detected = True

        if len(drivers) < 3 and item.get("title"):
            drivers.append(item.get("title"))

    total = bull_hits + bear_hits
    if total == 0:
        score = 0.0
    else:
        score = round((bull_hits - bear_hits) / (total + 1), 2)
        score = max(-1.0, min(1.0, score))

    if shock_detected:
        regime = "突發黑天鵝高波動警戒"
        risk_mult = 0.5
    elif score > 0.3:
        regime = "溫和樂觀 (Moderate Risk-On)"
        risk_mult = 1.0
    elif score < -0.3:
        regime = "偏空謹慎 (Cautious Risk-Off)"
        risk_mult = 0.7
    else:
        regime = "中性震盪 (Neutral)"
        risk_mult = 1.0

    return {
        "timestamp": get_taipei_timestamp(),
        "sentiment_score": score,
        "regime_label": regime,
        "volatility_shock_flag": shock_detected,
        "confidence_score": 0.65,
        "key_drivers": drivers if drivers else ["全球財經外電綜合詞彙動態評估"],
        "macro_factors": {
            "inflation_pressure": -0.2 if score > 0 else 0.3,
            "liquidity_outlook": score,
            "geopolitical_risk": 0.8 if shock_detected else 0.2
        },
        "risk_multiplier": risk_mult,
        "execution_recommendation": f"啟發式規則：情緒得分 {score}，部位調整乘數 {risk_mult}x",
        "model_source": "Lexicon-Heuristic-Fallback-v1"
    }


def get_market_sentiment(api_key: str = None, persist_report: bool = True) -> Dict[str, Any]:
    """
    獲取市場當前即時宏觀情緒指標 (遵循 docs/SENTIMENT_ENGINE_SPEC.md 契約)
    1. 優先調用使用者自建模型 (若開啟 USE_CUSTOM_MODEL)。
    2. 次選調用 Gemini-3.6-flash 自動備援鏈進行結構化 Prompt 推理。
    3. 自動容錯降級至詞典啟發式算法，保證永不崩潰。
    """
    # 1. 抓取即時新聞
    news_items = fetch_yahoo_finance_news()
    if not isinstance(news_items, list):
        news_items = []

    # 2. 判斷是否有 API Key
    effective_api_key = api_key or os.getenv("GEMINI_API_KEY", "")

    # 3. 嘗試 AI 結構化推理
    if effective_api_key and len(news_items) > 0:
        news_context = "\n".join([f"- {it.get('title', '')} ({it.get('date', '')})" for it in news_items[:8]])
        prompt = f"""
你是一位機構級計量經濟學家與宏觀對沖基金首席情緒分析師。
請根據以下最新全球即時財經外電新聞，以嚴謹客觀的態度評估當前跨資產市場的「宏觀情緒得分」與「突發系統性風險」：

【即時新聞外電清單】
{news_context}

【任務要求】
請嚴格輸出符合以下 JSON Schema 的純 JSON 字串，切勿夾帶額外的 Markdown 或解釋文字：
{{
  "sentiment_score": <float, 範圍 -1.0 到 +1.0，-1代表極度恐慌/系統性崩潰，0代表中性，+1代表極度貪婪樂觀>,
  "regime_label": <string, 如 "偏多樂觀 (Risk-On)", "偏空避險 (Risk-Off)", "中性震盪 (Neutral)", "突發高波動警戒">,
  "volatility_shock_flag": <boolean, 是否偵測到突發地緣衝突、突發央行異常升息/降息或流動性黑天鵝>,
  "confidence_score": <float, 0.0 到 1.0>,
  "key_drivers": [<3到4條中文重點，總結目前市場核心基本面與外電動態>],
  "macro_factors": {{
    "inflation_pressure": <float, -1.0 到 1.0>,
    "liquidity_outlook": <float, -1.0 到 1.0>,
    "geopolitical_risk": <float, 0.0 到 1.0>
  }},
  "risk_multiplier": <float, 0.0 到 1.2，供交易守護進程調節持倉規模；黑天鵝或極度偏空請給 0.5 或 0.0，平穩期給 1.0>,
  "execution_recommendation": <string, 給交易系統的一句話具體風控操作指示>
}}
"""
        try:
            raw_text = generate_content_with_fallback(effective_api_key, prompt, timeout=20)
            # 提取 JSON 區塊
            match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                parsed["timestamp"] = get_taipei_timestamp()
                parsed["model_source"] = "Gemini-3.6-Flash-Ensemble-v1"
                
                # 自動持久化至 SQLite 研報庫
                if persist_report:
                    try:
                        content_md = f"### 宏觀即時情緒評估報告\n\n" \
                                     f"- **情緒指標**: `{parsed.get('sentiment_score')}` ({parsed.get('regime_label')})\n" \
                                     f"- **部位乘數**: `{parsed.get('risk_multiplier')}x` | **黑天鵝旗標**: `{parsed.get('volatility_shock_flag')}`\n\n" \
                                     f"#### 核心驅動外電\n" + "\n".join([f"- {d}" for d in parsed.get("key_drivers", [])]) + \
                                     f"\n\n**執行建議**：{parsed.get('execution_recommendation')}"
                        save_macro_report(
                            report_type="即時新聞情緒量化簡報",
                            title=f"全球財經情緒指數: {parsed.get('sentiment_score'):+.2f} ({parsed.get('regime_label')})",
                            summary=parsed.get("execution_recommendation", ""),
                            content_markdown=content_md,
                            metrics_snapshot=json.dumps(parsed, ensure_ascii=False)
                        )
                    except Exception as db_err:
                        logger.warning(f"儲存情緒報告至資料庫失敗: {db_err}")

                return parsed
        except Exception as e:
            logger.warning(f"Gemini 情緒推理異常，自動降級至詞典啟發式備援: {e}")

    # 4. 降級備援
    fallback_res = _heuristic_sentiment_analysis(news_items)
    if persist_report:
        try:
            save_macro_report(
                report_type="即時新聞情緒量化簡報 (啟發式備援)",
                title=f"全球財經情緒指數: {fallback_res.get('sentiment_score'):+.2f} ({fallback_res.get('regime_label')})",
                summary=fallback_res.get("execution_recommendation", ""),
                content_markdown=f"### 宏觀情緒啟發式評估\n\n- 情緒得分: `{fallback_res.get('sentiment_score')}`\n- 驅動外電:\n" + "\n".join([f"- {d}" for d in fallback_res.get("key_drivers", [])]),
                metrics_snapshot=json.dumps(fallback_res, ensure_ascii=False)
            )
        except Exception:
            pass

    return fallback_res


def get_sentiment_risk_adjustment() -> float:
    """
    供交易守護進程 (Trading Daemon) 極速獲取當前部位調整乘數 (Risk Multiplier)
    範圍：0.0 (禁止新開倉) 到 1.2 (正常擴張)
    """
    try:
        sentiment = get_market_sentiment(persist_report=False)
        return float(sentiment.get("risk_multiplier", 1.0))
    except Exception as e:
        logger.error(f"獲取情緒風控乘數失敗: {e}")
        return 1.0


if __name__ == "__main__":
    print("--- 測試情緒核心引擎 ---")
    res = get_market_sentiment()
    print(json.dumps(res, indent=2, ensure_ascii=False))
