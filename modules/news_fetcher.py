# -*- coding: utf-8 -*-

"""
Personal Quant Firm | 全球宏觀財經新聞即時擷取與聚合器 (News Fetcher)
============================================================
支援雙軌架構：
1. 主通道：IBKR TWS 原生 Generic Tick 292 與機構專線 (Briefing, Dow Jones)。
2. 備援通道：Yahoo Finance RSS 網絡爬蟲。
"""

import urllib.request
import xml.etree.ElementTree as ET
import logging
from typing import List, Dict, Any

try:
    import streamlit as st
    cache_decorator = st.cache_data(ttl=120)
except Exception:
    def cache_decorator(func):
        return func

logger = logging.getLogger("NewsFetcher")


def fetch_tws_api_news(limit: int = 10) -> List[Dict[str, Any]]:
    """
    透過本地 TWS / IB Gateway API 獲取機構級原生新聞 (Generic Tick 292 / Historical News)
    支援 Briefing (BRFG), Dow Jones (DJNL) 等機構專線。
    """
    try:
        from modules.ibkr_engine import get_ibkr_engine
        engine = get_ibkr_engine()
        if engine.is_connected() or engine.connect(timeout=2):
            items = engine.get_recent_news(symbol="SPY", limit=limit)
            if items:
                formatted = []
                for it in items:
                    formatted.append({
                        "title": it.get("title", ""),
                        "headline": it.get("headline", ""),
                        "link": "#",
                        "date": it.get("date", ""),
                        "provider": it.get("provider", "TWS"),
                        "source": it.get("source", "IBKR TWS API")
                    })
                return formatted
    except Exception as e:
        logger.debug(f"TWS API 新聞獲取略過: {e}")
    return []


def fetch_yahoo_finance_rss(limit: int = 6) -> List[Dict[str, Any]]:
    """Yahoo Finance RSS 網絡爬蟲備援源"""
    url = "https://finance.yahoo.com/news/rssindex"
    news_items = []
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            root = ET.fromstring(response.read())
            for item in root.findall('.//item')[:limit]:
                title = item.find('title').text if item.find('title') is not None else "無標題"
                link = item.find('link').text if item.find('link') is not None else "#"
                pub_date = item.find('pubDate').text[:22] if item.find('pubDate') is not None else ""
                news_items.append({
                    "title": title,
                    "headline": title,
                    "link": link,
                    "date": pub_date,
                    "provider": "Yahoo",
                    "source": "Yahoo Finance RSS"
                })
    except Exception as e:
        logger.debug(f"Yahoo RSS 抓取異常: {e}")
    return news_items


@cache_decorator
def fetch_latest_macro_news(limit: int = 10, prefer_tws: bool = True) -> List[Dict[str, Any]]:
    """
    全域宏觀財經新聞聚合器：
    優先級 1：IBKR TWS 原生 Generic Tick 292 / Briefing / Dow Jones 機構專線 (低延遲、無反爬蟲)
    優先級 2：Yahoo Finance RSS 網絡備援
    優先級 3：預設安全中性占位符
    """
    if prefer_tws:
        tws_news = fetch_tws_api_news(limit=limit)
        if tws_news:
            return tws_news

    yahoo_news = fetch_yahoo_finance_rss(limit=min(limit, 6))
    if yahoo_news:
        return yahoo_news

    return [{"title": "即時總經新聞連線中...", "headline": "即時總經新聞連線中...", "link": "#", "date": "", "source": "系統預設"}]


# 向下相容別名
fetch_yahoo_finance_news = fetch_latest_macro_news
