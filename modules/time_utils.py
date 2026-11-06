#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Personal Quant Firm | 全球時區標準化模組 (Timezone Normalization Engine)
=====================================================================
功能：
1. 嚴格錨定台北標準時間 (Asia/Taipei, UTC+8) 與美東華爾街市場時間 (America/New_York, ET)。
2. 徹底消除跨雲端容器 (AWS/Streamlit Cloud 預設 UTC) 造成的日夜顛倒與日期偏離。
3. 提供跨模組標準化時間格式生成函式。
"""

from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    TZ_TAIPEI = ZoneInfo("Asia/Taipei")
    TZ_NEWYORK = ZoneInfo("America/New_York")
except Exception:
    # 針對極端環境之靜態固定時區備援
    TZ_TAIPEI = timezone(timedelta(hours=8), name="CST")
    TZ_NEWYORK = timezone(timedelta(hours=-5), name="EST")


def now_taipei() -> datetime:
    """取得台北標準時間 (UTC+8) 的 datetime 物件"""
    return datetime.now(TZ_TAIPEI)


def now_newyork() -> datetime:
    """取得華爾街美東時間 (ET) 的 datetime 物件"""
    return datetime.now(TZ_NEWYORK)


def get_dual_clock_str() -> tuple[str, str]:
    """
    返回 (台北時間字串, 美東時間字串)
    格式範例: ('2026-11-07 00:30:00', '2026-11-06 11:30:00 ET')
    """
    tpe_str = now_taipei().strftime("%Y-%m-%d %H:%M:%S")
    nyc_str = now_newyork().strftime("%Y-%m-%d %H:%M:%S ET")
    return tpe_str, nyc_str


def get_taipei_datestr() -> str:
    """返回台北標準日期字串: YYYY-MM-DD"""
    return now_taipei().strftime("%Y-%m-%d")


def get_taipei_timestamp() -> str:
    """返回台北標準完整時間字串: YYYY-MM-DD HH:MM:SS"""
    return now_taipei().strftime("%Y-%m-%d %H:%M:%S")
