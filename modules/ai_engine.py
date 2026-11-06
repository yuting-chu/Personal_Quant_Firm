#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Personal Quant Firm | 全域 AI 智慧推理與自動容錯備援引擎 (AI Engine)
============================================================
功能：
1. 封裝 Google Gemini 官方最新模型調用介面。
2. 實作自動容錯與多模型備援機制 (Auto-Failover)：
   依序嘗試：gemini-3.5-flash -> gemini-flash-latest -> gemini-3.6-flash -> gemini-pro-latest
3. 杜絕因特定模型版本過期 (如 404 gemini-1.5-flash) 或單一配額限制 (429) 導致的前端異常。
"""

import google.generativeai as genai

# 最新高可用備援模型候選清單 (嚴格依使用者指定之優先順序排列)
AI_MODEL_CANDIDATES = [
    "gemini-flash-latest",
    "gemini-3.6-flash",
    "gemini-pro-latest",
    "gemini-3.5-flash"
]


def generate_content_with_fallback(api_key: str, prompt: str, timeout: int = 20) -> str:
    """
    調用 Gemini 模型並具備自動備援切換功能。
    依序嘗試：gemini-flash-latest -> gemini-3.6-flash -> gemini-pro-latest -> gemini-3.5-flash
    若首選模型遇到 404 (版本廢棄)、超時或臨時配額問題，自動嘗試下一個候選模型。
    """
    if not api_key:
        raise ValueError("未提供有效的 Gemini API Key")

    genai.configure(api_key=api_key)
    last_exception = None

    for model_name in AI_MODEL_CANDIDATES:
        try:
            model = genai.GenerativeModel(model_name)
            # 設置請求超時防止單一節點掛起
            response = model.generate_content(
                prompt,
                request_options={"timeout": timeout}
            )
            if response and response.text:
                return response.text
        except Exception as err:
            last_exception = err
            continue

    raise RuntimeError(f"所有備援模型均無法完成生成，最新錯誤訊息: {last_exception}")
