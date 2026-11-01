# 更新日誌 (Changelog)

本專案遵循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.0.0/) 格式，並依據標準軟體工程規範記錄每日開發進度、模型優化與架構調整。

---

## [1.0.0] - 2026-11-01

### 🚀 里程碑：個人量化戰情中心基礎設施建立與雲端上線

#### 新增 (Added)
- **版本控制與遠端儲存庫**：
  - 初始化 Git 版本控制，並建立 GitHub 遠端儲存庫 `yuting-chu/Personal_Quant_Company`。
  - 將專案標準化遷移至本地正規開發目錄：`C:\Users\朱郁庭\github\Personal_Quant_Company`。
- **Streamlit 主入口架構 (`app.py`)**：
  - 構建 `Personal Quant Office | 旗艦戰情中心` 主頁面。
  - 設計五大核心業務 Tab 導航（總經、產業、回測、風控、稽核）。
  - 實作側邊欄 API 金鑰配置介面（支援 Gemini 與 FRED API）與全域風控模式切換開關。
- **基礎設施層 (`modules/`)**：
  - `database.py`：實作 SQLite 本地資料庫初始化與交易審計日誌 (`trade_logs`) 存取函式。
  - `news_fetcher.py`：串接 Yahoo Finance 即時財經新聞 RSS 資訊流。
  - `tradingview.py`：封裝 TradingView 前端互動式行情圖表組件。
- **戰情業務邏輯層 (`views/`)**：
  - `tab_macro.py`：整合 FRED 數據與公債殖利率曲線（10Y-2Y / 10Y-3M 利差）及 AI 總經情勢導讀。
  - `tab_industry.py`：美股各大板塊與 ETF 輪動分析、技術面多空訊號。
  - `tab_backtest.py`：多因子策略回測框架、累計報酬率與滾動最大回撤（MDD）圖表。
  - `tab_risk.py`：即時部位曝險評估、保證金佔用率監控與 VaR（風險值）計算模組。
  - `tab_audit.py`：交易日誌檢視、每日已實現損益（PnL）統計與風控審查。
- **環境設定與文檔**：
  - `requirements.txt`：列舉 9 項核心套件依賴，支援雲端自動化環境建置。
  - `.env.example`：提供標準環境變數結構範本。
  - `README.md`：撰寫專案功能概覽、本地啟動與雲端部署完整指南。

#### 安全性 (Security)
- **金鑰隱私防護**：
  - 配置 `.gitignore`，徹底隔離 `.env`、`quant_firm.db` 及快取檔案，杜絕真實 API Key 推送至 GitHub 公開儲存庫。
  - 在 `app.py` 中導入 `st.secrets` 自動相容機制，支援 Streamlit Community Cloud 安全儲存金鑰。

#### 移除與清理 (Removed)
- 移除未模組化之舊版腳本 `finance.py`，保持架構單一真理原則（Single Source of Truth）。
- 移除獨立測試腳本 `views/test_fetch.py`。
- 排除與生產環境無關之本機 Jupyter Notebook（`*.ipynb`）與彭博終端純文字紀錄。

#### 部署 (Deployment)
- 成功連動 GitHub 與 Streamlit Community Cloud，完成持續部署（CD）管線串接。

---

## [待辦進度 / Next Roadmap]
- [ ] **總經模組**：加入單根定態檢定（ADF Test）與 Probit 景氣衰退機率預測模型。
- [ ] **策略回測**：實作真實摩擦成本（手續費、滑價）與 Deflated Sharpe Ratio 顯著性檢驗。
- [ ] **風控模組**：導入歷史模擬法與蒙地卡羅法計算 CVaR（條件風險值 / 預期損失）。
