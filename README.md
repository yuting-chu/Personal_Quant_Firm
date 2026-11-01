# Personal Quant Company | 旗艦量化與總經戰情中心

一個基於 Python 與 Streamlit 開發的高階量化投資與總經分析戰情平台。

---

## 📌 模組架構

- **`app.py`**：系統主程式入口與 Tab 導航。
- **`finance.py`**：計量運算核心與市場數據抓取模組。
- **`modules/`**：
  - `database.py`：SQLite 資料庫讀寫與交易日誌記錄。
  - `news_fetcher.py`：財經即時新聞爬取與解析。
  - `tradingview.py`：技術分析圖表串接。
- **`views/`**：
  - `tab_macro.py`：全球總體經濟指標、公債殖利率曲線、FRED 經濟數據。
  - `tab_industry.py`：產業輪動、標的估值與基本面分析。
  - `tab_backtest.py`：多因子量化策略歷史回測與風險報酬指標評估。
  - `tab_risk.py`：部位即時風險暴露、VaR（風險值）與壓力測試。
  - `tab_audit.py`：交易日誌審查與實現損益追蹤。

---

## 🚀 本地端快速啟動

1. **安裝依賴套件**：
   ```bash
   pip install -r requirements.txt
   ```

2. **設定環境變數**：
   複製 `.env.example` 為 `.env`，並填入您的 API 金鑰：
   ```bash
   cp .env.example .env
   ```
   編輯 `.env`：
   ```env
   GEMINI_API_KEY=your_actual_gemini_api_key
   FRED_API_KEY=your_actual_fred_api_key
   ```

3. **啟動 Streamlit 服務**：
   ```bash
   streamlit run app.py
   ```

---

## ☁️ 部署至 Streamlit Community Cloud

1. 將本專案推播（Push）至您的 GitHub 儲存庫。
2. 前往 [Streamlit Community Cloud](https://share.streamlit.io/) 並連結此 Repository。
3. Main file path 選擇 `app.py`。
4. **【重要資安設定】設定 Secrets**：
   在 Streamlit 部署頁面的 **Advanced settings > Secrets**（或部署完成後的 **App settings > Secrets**）貼上以下內容：
   ```toml
   GEMINI_API_KEY = "您的Gemini金鑰"
   FRED_API_KEY = "您的FRED金鑰"
   ```
   平台將安全地注入環境變數，完全無需將金鑰公開於 GitHub 上。
