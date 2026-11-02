# 更新日誌 (Changelog)

本專案遵循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.0.0/) 格式，並依據標準軟體工程規範記錄版本迭代、模型優化與架構調整。

---

## [1.1.0] - 2026-11-03

### 🏛️ 里程碑：借鑑高盛 gs-quant 利率架構，升級總經與美債傳導戰情室

#### 新增 (Added)
- **美債殖利率曲線與流動性傳導矩陣 (`views/tab_macro.py`)**：
  - 導入 10 年期美債殖利率 (`DGS10`) 與 2 年期美債殖利率 (`DGS2`)，作為全球權益資產無風險折現基準。
  - 實作 10Y - 2Y 殖利率利差 (`T10Y2Y`) 動態形態判別（倒掛 Inverted / 陡峭化解掛 Un-inverting / 正常正斜率 Normal），建立景氣衰退預警機制。
  - 整合 10 年期 TIPS 實質殖利率 (`DFII10`)，量化真實資金成本，直接連動黃金與大宗商品估值分析。
  - 納入高收益債信用利差 (`BAMLH0A0HYM2`)，即時監控金融體系流動性與企業信用違約風險。
- **高盛級利率可視化圖表 (Yield Curve Term Structure)**：
  - 採用 Plotly 建立長短天期殖利率與期限利差結構圖，即時標註當前利率曲線斜率與實質緊縮程度。
- **五大資產類別操作方針升級**：
  - 跨資產定價指引全面納入美債與實質利率維度，涵蓋固定收益存續期（Duration）、權益資產折現、外匯美日利差（Carry Trade）與選擇權波動度。
- **高強健性 REST API 連線機制**：
  - 在 `views/tab_macro.py` 中導入純標準庫之 REST 數據抓取函式，消除套件相依與連線異常風險。

---

## [1.0.0] - 2026-11-01

### 🚀 里程碑：量化與總經戰情中心基礎設施建立與雲端上線

#### 新增 (Added)
- **版本控制與開源基礎設施**：
  - 初始化 Git 版本控制與遠端儲存庫管線。
  - 導入標準軟體工程專案結構與模組化分層架構。
- **Streamlit 主入口架構 (`app.py`)**：
  - 構建 `Personal Quant Office | 旗艦戰情中心` 主頁面。
  - 設計五大核心業務 Tab 導航（總經、產業、回測、風控、稽核）。
  - 實作側邊欄 API 金鑰配置介面（支援 Gemini 與 FRED API）與全域風控模式切換開關。
- **基礎設施層 (`modules/`)**：
  - `database.py`：實作 SQLite 本地資料庫初始化與交易審計日誌 (`trade_logs`) 存取介面。
  - `news_fetcher.py`：串接全球財經即時新聞 RSS 資訊流。
  - `tradingview.py`：封裝 TradingView 互動式行情圖表組件。
- **戰情業務邏輯層 (`views/`)**：
  - `tab_macro.py`：整合總體經濟數據與公債殖利率曲線（10Y-2Y / 10Y-3M 利差）及 AI 總經情勢導讀。
  - `tab_industry.py`：各大板塊與 ETF 輪動分析、技術面多空訊號。
  - `tab_backtest.py`：多因子策略回測框架、累計報酬率與滾動最大回撤（MDD）可視化。
  - `tab_risk.py`：即時部位曝險評估、保證金佔用率監控與 VaR（風險值）計算模組。
  - `tab_audit.py`：交易日誌檢視、每日已實現損益（PnL）統計與風控審查。
- **相依套件與文檔**：
  - `requirements.txt`：列舉核心套件依賴，支援雲端自動化環境建置。
  - `.env.example`：提供標準環境變數結構範本。
  - `README.md`：撰寫專案功能概覽、啟動說明與雲端部署指南。

#### 安全性 (Security)
- **機密憑證防護**：
  - 配置 `.gitignore`，徹底隔離環境變數、本地資料庫及暫存快取檔案，杜絕真實 API Key 推送至公開儲存庫。
  - 在 `app.py` 中導入雲端環境變數自動相容機制，支援 Streamlit Community Cloud 安全託管。

#### 移除與優化 (Removed)
- 移除未模組化之舊版腳本，確保架構符合單一真理原則（Single Source of Truth）。
- 移除各類離線除錯腳本與暫存測試檔案。

#### 部署 (Deployment)
- 成功連動 GitHub 與 Streamlit Community Cloud，完成持續部署（CD）管線串接。

---

## [待辦進度 / Next Roadmap]
- [ ] **總經模組**：加入時間序列平穩性檢定（ADF Test）與 Probit 景氣衰退機率預測模型。
- [ ] **策略回測**：實作真實摩擦成本（手續費、滑價）與 Deflated Sharpe Ratio 顯著性檢驗。
- [ ] **風控模組**：導入歷史模擬法與蒙地卡羅法計算 CVaR（條件風險值 / 預期損失）。
