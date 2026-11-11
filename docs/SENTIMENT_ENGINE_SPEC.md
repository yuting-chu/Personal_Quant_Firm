# 跨資產量化情緒核心規範書 (Sentiment Engine Specification)

> **版本**：v1.0.0  
> **建立時間**：2026-11-11  
> **作者**：首席計量經濟學家與資料分析工程師  
> **用途**：為全自動交易守護進程（Trading Daemon）與多因子資產定價模型提供**非結構化文本情緒結構化量化指標**。本規格書定義了標準輸入輸出、計量架構、風控乘數演算法與自定義模型/平台的熱插拔接口規範，方便後續對接自建深度學習模型或獨立情緒分析平台。

---

## 1. 核心計量哲學與學理依據 (Econometric Rationale)

在傳統量化模型中，純價格與成交量指標具有**滯後性（Lagging Nature）**。依據現代實證資產定價文獻（*Tetlock 2007 JF, Engle et al. 2020 RFS*）：
1. **非結構化新聞與即時外電**反映了市場微觀主體對未來宏觀政策、利率路徑與企業自由現金流的**前瞻性預期（Forward-looking Expectations）**。
2. **定位不是高頻預測，而是外生衝擊與波動率閘門**：
   - 散戶誤區：拿新聞當作微秒級追價信號（必遭 HFT 收割與流動性滑點）。
   - 機構定位：將新聞量化為 **「宏觀情緒得分（Sentiment Score）」** 與 **「突發黑天鵝衝擊標籤（Volatility Shock Flag）」**，作為交易部位規模調整（Position Sizing）與動態風控閘門（Risk Governor）。

---

## 2. 標準化輸出介面契約 (API Data Contract)

自定義模型或本引擎之標準函數 `get_market_sentiment() -> Dict[str, Any]` 必須回傳符合以下 JSON Schema 之字典結構：

```json
{
  "timestamp": "2026-11-11T23:45:00+08:00",
  "sentiment_score": 0.42,
  "regime_label": "偏多樂觀 (Risk-On)",
  "volatility_shock_flag": false,
  "confidence_score": 0.88,
  "key_drivers": [
    "美聯儲降息預期升溫，長端美債殖利率下行",
    "大型科技股 AI CapEx 資本支出展望穩健",
    "原油價格回跌，通膨二次抬頭壓力緩解"
  ],
  "macro_factors": {
    "inflation_pressure": -0.25,
    "liquidity_outlook": 0.60,
    "geopolitical_risk": 0.10,
    "earnings_quality": 0.50
  },
  "risk_multiplier": 1.0,
  "execution_recommendation": "放行所有日內動量與均值回歸策略，維持常態 1.0x 倉位",
  "model_source": "Gemini-3.6-Flash-Ensemble-v1"
}
```

### 關鍵欄位定義與數值邊界：

| 欄位名稱 | 型態 | 數值範圍 | 定義與計量意涵 |
| :--- | :--- | :--- | :--- |
| `sentiment_score` | `float` | `[-1.0, +1.0]` | **綜合市場情緒得分**。<br>• `[-1.0, -0.6)`: 極度恐慌 (Panic / Extreme Risk-Off)<br>• `[-0.6, -0.2)`: 偏空謹慎 (Cautious)<br>• `[-0.2, +0.2]`: 中性觀望 (Neutral)<br>• `(+0.2, +0.6]`: 溫和樂觀 (Moderate Risk-On)<br>• `(+0.6, +1.0]`: 極度貪婪 (Euphoria / Extreme Risk-On) |
| `volatility_shock_flag` | `bool` | `True / False` | **突發黑天鵝 / 高波動警報**。<br>若偵測到重大突發地緣衝突、突發非常規利率決議或系統性流動性危機，此旗標為 `True`。 |
| `risk_multiplier` | `float` | `[0.0, 1.2]` | **動態風控乘數**。<br>直接乘上交易策略之基礎開倉口數/金額。<br>• 當觸發 `volatility_shock_flag` 或得分 `< -0.6` 時，乘數自動降為 `0.0`（暫停開倉）或 `0.5`（部位減半）。 |
| `regime_label` | `str` | 列舉字串 | 情緒環境文字標籤（直接用於前端圖表展示與研報生成）。 |
| `key_drivers` | `List[str]` | 3~5 條條列 | 本次情緒評分之核心基本面與外電驅動因素摘要。 |

---

## 3. 現階段架構實作 (Current Implementation)

當前代碼位於 [modules/sentiment_engine.py](file:///C:/Users/朱郁庭/github/Personal_Quant_Company/modules/sentiment_engine.py)：
1. **數據獲取**：[modules/news_fetcher.py](file:///C:/Users/朱郁庭/github/Personal_Quant_Company/modules/news_fetcher.py) 自動抓取 Yahoo Finance Global RSS 與即時總經國際頭條。
2. **語意解析**：調用 [modules/ai_engine.py](file:///C:/Users/朱郁庭/github/Personal_Quant_Company/modules/ai_engine.py)（Gemini-3.6-flash 自動備援鏈），經由嚴格的 Prompt 模板將非結構化文本映射至 JSON 數值。
3. **無依賴容錯備援（Zero-Dependency Heuristic Fallback）**：
   - 若發生外部網路中斷、API Key 耗盡或 429 速率限制，引擎內建金融詞典啟發式評分算法（Lexicon Fallback），**保證 100% 不會向交易守護進程拋出例外崩潰**。
4. **持久化**：每次評分均自動儲存至 SQLite `macro_daily_reports` 資料庫，支援歷史回溯與圖表展示。

---

## 4. 未來自定義模型 / 外部平台無縫替換指南 (How to Plug-in Your Custom Model)

當你自行研發的深度學習模型（例如基於 FinBERT、Llama-3-Fin、自訓練 Transformer 或外部情緒平台）上線時，只需在 [modules/sentiment_engine.py](file:///C:/Users/朱郁庭/github/Personal_Quant_Company/modules/sentiment_engine.py) 中切換自定義適配器，**無需修改任何交易守護進程與資料庫代碼**：

### 替換範例：
```python
# 在 modules/sentiment_engine.py 中
USE_CUSTOM_MODEL_ENDPOINT = True # 改為 True
CUSTOM_MODEL_URL = "http://localhost:8000/api/v1/sentiment" # 你的自建模型 API

def get_market_sentiment() -> Dict[str, Any]:
    if USE_CUSTOM_MODEL_ENDPOINT:
        try:
            # 1. 呼叫你自己的模型微服務
            resp = requests.post(CUSTOM_MODEL_URL, json={"news": fetch_raw_news()}, timeout=5)
            data = resp.json()
            # 2. 確保回傳字典包含 sentiment_score, risk_multiplier, volatility_shock_flag 即可
            return data
        except Exception as e:
            logger.warning(f"自建模型呼叫失敗，自動降級至預設備援引擎: {e}")
            
    # 預設執行 Gemini / RSS 流程...
```

---

## 5. 跨聊天室快速喚起指引 (Prompt to Resume in a New Chat)

在未來的對話中，若你想要讓新的 AI 助理立刻掌握情緒模組並進行升級，直接在對話中複製以下提示詞：

> **「請閱讀專案中的 `docs/SENTIMENT_ENGINE_SPEC.md`。我現在要針對情緒核心進行（升級自建模型接口 / 調整計量打分邏輯 / 串接外部平台），請基於該規範書的契約標準與 `modules/sentiment_engine.py` 繼續開發。」**
