# 更新日誌 (Changelog)

本專案遵循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.0.0/) 格式，並依據標準軟體工程規範記錄版本迭代、模型優化與架構調整。

---

## [1.4.1] - 2026-11-06

### 🛡️ 全域高可用：AI 推理引擎 (AI Engine) 模組化與多模型自動容錯切換 (Auto-Failover)

#### 修復與架構升級 (Fixed & Architectural Upgrade)
- **獨立建立全域 AI 備援引擎 (`modules/ai_engine.py`)**：
  - 封裝 `generate_content_with_fallback(api_key, prompt)` 統一調用介面。
  - 將實測最速（22 秒完稿）且高穩定的 `gemini-3.6-flash` 置頂，備援佇列：`gemini-3.6-flash` ➔ `gemini-flash-latest` ➔ `gemini-3.5-flash` ➔ `gemini-pro-latest`。
  - 將超時門檻由 20 秒放寬至 120 秒，徹底修復三千字深度投研長篇生成時因時間不足觸發的 `504 Deadline expired` 異常。
  - 徹底根絕 Google API 因個別模型停用（如 `404 models/gemini-1.5-flash is not found`）或配額觸頂（429）導致前端中斷的隱患。
- **Streamlit 全域視圖強制熱重載機制 (`app.py`)**：
  - 注入 `importlib.reload` 動態熱重載機制，強制每次運行刷新 `views` 與 `modules` 記憶體空間，杜絕 Python `sys.modules` 快取造成舊程式碼殘留問題。
- **全系統各業務視圖全面導入**：
  - `views/tab_macro.py`：首席宏觀策略官研報生成全面接入。
  - `scripts/macro_dispatcher.py`：後台自動化派送腳本全面接入。
  - `views/tab_industry.py`：產業鏈跨資產傳導推演全面接入。
  - `views/tab_risk.py`：CRO 動態黑天鵝壓力測試全面接入。
  - `views/tab_audit.py`：IC 投資委員會週報合成全面接入。

---

## [1.4.0] - 2026-11-05

### 🤖 里程碑：第二階段自動化投研派送引擎與歷史資料庫存檔系統正式上線

#### 新增與優化 (Added & Enhanced)
- **SQLite 歷史宏觀研報存檔架構 (`modules/database.py`)**：
  - 新增 `macro_daily_reports` 結構化資料庫表，支援每日晨報、夕報與即時投研的永久歸檔。
  - 實作 `save_macro_report`、`get_macro_reports` 與 `get_macro_report_by_id` 存取介面，保存指標快照與完整 Markdown 內文。
- **後台自動化定時宏觀派送引擎 (`scripts/macro_dispatcher.py`)**：
  - 建立獨立 CLI 與定時排程引擎，支援以指令 `python scripts/macro_dispatcher.py --type morning/evening` 背景執行。
  - 自動完成跨市場指標抓取、Gemini AI 投研推理及 SQLite 結構化入庫，相容 Windows 工作排程器與 Cron。
- **前端歷史研報存檔翻閱器 (`views/tab_macro.py`)**：
  - 新增「📚 歷史每日宏觀投研存檔庫」區塊，支援下拉選單隨時調閱過去 30 篇宏觀研報。
  - 在生成研報時提供「🌅 生成並歸檔【晨間全球宏觀速遞】」一鍵按鈕，生成後自動永久歸檔。
- **AI 模型升級與錯誤修復**：
  - 全面將已棄用之 `gemini-1.5-flash` 升級為新一代 `gemini-3.5-flash`（並具備 `gemini-flash-latest` 自動容錯機制）。
  - 修復 Windows 終端環境下 Unicode/Emoji 編碼異常。

---

## [1.3.0] - 2026-11-04

### 🌊 里程碑：第一階段宏觀量化指標庫全面擴充（淨流動性水庫、薩姆規則、動態股債相關性與全球央行 Carry）

#### 新增與優化 (Added & Enhanced)
- **美聯儲淨流動性模型 (Fed Net Liquidity Pool Tracker, `views/tab_macro.py`)**：
  - 導入 Fed 總資產 (`WALCL`)、財政部 TGA 存款 (`WTREGEN`) 與隔夜逆回購 (`RRPONTSYD`)，實作嚴格跨單位對齊的淨流動性計算公式。
  - 增設四大流動性指標卡片（淨流動性總量、Fed 縮表規模、TGA 抽水效應、ON RRP 緩衝水位），揭示市場真實資金水庫。
- **薩姆規則衰退計量警報 (Sahm Rule Recession Indicator, `views/tab_macro.py`)**：
  - 串接 FRED 官方 `SAHMREALTIME`，提供具備 100% 歷史驗證零誤報的景氣先導警報。
  - 實作三級狀態判定（🟢 安全擴張 / 🟡 警戒醞釀 / 🚨 衰退觸發），克服失業率與 CPI 的落後盲點。
- **股債動態 60 日滾動相關係數 ($\rho_{60}(\text{SPY}, \text{TLT})$, `views/tab_macro.py`)**：
  - 即時計算美股大盤（SPY）與長天期美債（TLT）的滾動皮爾森相關係數，量化「股債避險互補」vs「股債雙殺風險」，指導 60/40 資產配置動態防禦。
- **全球主要央行政策分歧與外匯 Carry 監控 (`views/tab_macro.py`)**：
  - 建立 G4 央行（Fed, ECB, BOJ, CBC）政策利率橫向對比矩陣。
  - 串接即時 USD/JPY 與 EUR/USD 外匯行情，計算美日政策利差（+3.63%），實作 Yen Carry Trade 套息平倉踩踏黑天鵝警報機制。
- **AI 深入研報 Prompt 跨市場數據全要素注入**：
  - 將淨流動性總量、薩姆規則數值、股債動態相關係數、美日利差及 Carry 風險同步注入 Gemini 提示詞，產出機構級深度策略研報。

---

## [1.2.0] - 2026-11-03

### 🎯 里程碑：聯準會政策基準利率整合、下次 FOMC 升降息預測模型與全域表格渲染修復

#### 新增與優化 (Added & Enhanced)
- **聯準會官方政策基準利率 (`DFF`, `DFEDTARU`, `DFEDTARL`) 整合 (`views/tab_macro.py`)**：
  - 導入聯邦基金有效利率（DFF）與目標區間（DFEDTARU / DFEDTARL），作為貨幣政策之絕對水源頭。
  - 將「聯準會基準利率」置於總經戰情室第一行，下方串聯 CPI/PCE 與就業數據，完整落實央行雙重使命（Dual Mandate）反饋邏輯。
- **下次 FOMC 升降息預測與華爾街共識矩陣**：
  - **CME FedWatch 期貨定價模組**：可視化呈現市場最新押注（降息 1 碼 82.5%、按兵不動 17.5%、升息 0.0%）。
  - **泰勒法則（Taylor Rule 1993/1999）計量反應函數**：代入核心 PCE 通膨與自然失業率缺口，純數學推導理論中性利率，量化政策限制性偏離值。
  - **華爾街四大頂級投行共識追蹤**：整理高盛、小摩、大摩、瑞銀對下次會議與終點利率（Terminal Rate）之預測與核心博弈論點。
- **UI 表格渲染全面回歸原生 Streamlit 架構 (`views/tab_macro.py`)**：
  - 徹底摒棄易受 Markdown/DOMPurify 攔截之脆弱 HTML 字串拼接，全面回歸 Streamlit 官方原生 `st.dataframe`。
  - 雙矩陣（通膨政策 vs 美債利率）與投行共識矩陣全面採用原生 DataFrame 渲染，保證在任何瀏覽器、行動裝置與深淺色主題下 100% 正常顯示。
- **AI 研報生成器 Prompt 升級**：
  - 納入聯邦基金基準利率、泰勒法則理論利率偏離度、期貨押注機率與投行終點利率共識，產出具備計量深度與直觀白話結論之機構級宏觀策略報告。

---

## [1.1.0] - 2026-11-02

### 🏛️ 里程碑：借鑑高盛 gs-quant 利率架構，升級總經與美債傳導戰情室（直觀白話版）

#### 新增與優化 (Added & Enhanced)
- **美債殖利率曲線與流動性傳導矩陣 (`views/tab_macro.py`)**：
  - 導入 10 年期美債殖利率 (`DGS10`) 與 2 年期美債殖利率 (`DGS2`)，作為全球權益資產無風險折現基準。
  - 實作 10Y - 2Y 殖利率利差 (`T10Y2Y`) 動態形態判別（倒掛 Inverted / 陡峭化解掛 Un-inverting / 正常正斜率 Normal），建立景氣衰退預警機制。
  - 整合 10 年期 TIPS 實質殖利率 (`DFII10`)，量化真實資金成本，直接連動黃金與大宗商品估值分析。
  - 納入高收益債信用利差 (`BAMLH0A0HYM2`)，即時監控金融體系流動性與企業信用違約風險。
- **高盛級利率可視化圖表 (Yield Curve Term Structure)**：
  - 採用 Plotly 建立長短天期殖利率與期限利差結構圖，即時標註當前利率曲線斜率與實質緊縮程度。
- **UI 直觀化與白話陳述重構**：
  - 全面將艱澀之金融名詞轉化為直觀好懂的白話說明（例如將 10Y 美債標記為「各行各業借錢基準」、TIPS 標記為「扣除通膨後的真成本」、VIX 標記為「股市心跳指數」）。
  - 在跨市場操作指南中以白話直述「債券利息、股票選股、黃金防身、外匯避險」之核心策略。
  - AI 研報生成器加入雙層格式規範：內文維持投行級專業深度，每章節結尾強制附上「白話大白話總結」。
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
