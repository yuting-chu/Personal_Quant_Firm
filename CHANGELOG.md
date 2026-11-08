# 更新日誌 (Changelog)

本專案遵循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.0.0/) 格式，並依據標準軟體工程規範記錄版本迭代、模型優化與架構調整。

---

## [1.8.0] - 2026-11-08

### 🚀 里程碑：第四階段（Phase 4.3）Brinson 績效歸因瀑布圖、實盤訂單審計與 AI 投委會治理正式上線

#### 新增與優化 (Added & Enhanced)
- **🏆 Brinson-Fachler 績效歸因計量引擎 (`views/tab_audit.py`)**：
  - **嚴格正交分解 Active Alpha**：將宏觀輪動的超額收益精確拆解為資產配置效應 (Allocation Effect)、標的選擇效應 (Selection Effect) 與交互效應 (Interaction Effect)。
  - **Plotly 歸因瀑布圖 (Waterfall Chart)**：以視覺化階梯直觀展示基準大盤報酬如何疊加配置 Alpha 形成最終組合報酬。
  - **11 大板塊 Alpha 貢獻橫向長條圖與計量矩陣**：清晰標註科技股超配、公用事業低配等對超額報酬的精確數值貢獻。
- **📋 實盤調倉訂單審計與摩擦追蹤 (`views/tab_audit.py` & `modules/database.py`)**：
  - **完整接軌 Tab 3 調倉指令**：全面追蹤 SQLite `trade_logs` 中的調倉動作、整股股數、實現損益與摩擦滑價。
  - **手續費與滑價精算**：累計已發生的調倉交易摩擦，保證回測假設與實盤記帳無縫對齊。
  - **一鍵批量審計核可**：新增 `update_all_pending_trades_status`，支援投審會一鍵核准所有待審計調倉單。
- **🏛️ 多 Agent 投資審計委員會 (IC Governance Meeting - Gemini-3.6-flash)**：
  - **三方聯席審計**：整合首席投資官 (CIO)、首席風控官 (CRO) 與首席量化交易員 (Quant Trader) 之專業視角。
  - **合規決議備忘錄 (IC Resolution & Mandate)**：自動輸出治理評級 (AAA/AA)、調倉授權許可、風險對衝指引與白話決策總結。

---

## [1.7.0] - 2026-11-08

### 🚀 里程碑：第四階段（Phase 4.2）四重宏觀風控熔斷閘門、蒙地卡羅 10,000 次 VaR/CVaR 與尾部 Put 對衝精算正式上線

#### 新增與優化 (Added & Enhanced)
- **🚨 四重宏觀條件動態風控熔斷閘門 (`views/tab_risk.py`)**：
  - **薩姆規則衰退熔斷 (≥ 0.50%)**：全域監控衰退指標，破標時自動觸發 Risk-Off 硬防禦警報，建議將高 Beta 成長板塊減半轉移至現金或短天期國庫券。
  - **維持保證金佔用率警報 (≥ 55.0%)**：嚴格鎖定維持保證金上限，超過 55% 自動啟動硬熔斷，嚴禁任何新增部位，僅准平倉減碼。
  - **USD/JPY Carry 拆倉監控 (跌破 20MA)**：實時監測日圓套利平倉風險，跌破 20MA 時自動亮起停損與科技股流動性踩踏避險信號。
  - **股債同向雙殺警報 (ρ > +0.30)**：60D 滾動相關係數翻正過高時提示長債避險失效，指引存續期收縮。
- **🎲 蒙地卡羅 10,000 次多資產相關路徑模擬 (VaR & CVaR Engine)**：
  - **喬里斯基分解 (Cholesky Factorization)**：對股票、公債、外匯、黃金之協方差矩陣 $\Sigma$ 進行分解 ($\Sigma = L L^T$)，保留跨市場動態耦合結構。
  - **巴塞爾協議 III 規範在險價值輸出**：精算 1-Day VaR (95%/99%)、1-Day CVaR (Expected Shortfall 期望損失) 與 10-Day VaR 監管儲備資本。
  - **損益分佈直方圖與分位切線**：以 Plotly 繪製 10,000 次情境損益機率分佈，直觀標註 VaR 95%、VaR 99% 與 CVaR 95% 極端尾部分界線。
- **🔄 全資產實時持倉、槓桿與保證金結構**：
  - 動態匯總股票、外匯 Carry、選擇權與黃金之名目本金 (Gross Exposure)、總槓桿倍數、淨系統性 Delta 與 Vega，搭配雙色儀表盤實時警示保證金佔用率。
- **🛡️ 尾部黑天鵝 Put 選擇權對衝精算機**：
  - 輸入對衝保護覆蓋率與標的 (SPY/QQQ)，自動精算 30DTE 5% OTM Put 所需買進口數、預估總權利金支出、每月保險費率 (% of NAV) 與崩盤保護力。
- **⚡ 歷史極端危機情境動態回放**：
  - 依據目前投資組合真實持倉結構，動態模擬重現 2020 疫情崩盤 (VIX 82)、2024 日圓拆倉暴跌、2022 Fed 暴力升息與 2008 雷曼次貸風暴之預估損益衝擊。
- **🤖 升級版首席風控官 (AI CRO Agent - Gemini-3.6-flash)**：
  - 自動注入即時 VaR/CVaR、保證金率、宏觀四重熔斷狀態與財經快訊，生成投行級風險審計備忘錄與白話防禦指引。

---

## [1.6.0] - 2026-11-08

### 🚀 里程碑：第四階段（Phase 4.1）宏觀輪動實盤調倉指令計算機與 3 年滾動回測引擎正式上線

#### 新增與優化 (Added & Enhanced)
- **⚡ 宏觀輪動實盤調倉指令計算機 (`views/tab_backtest.py`)**：
  - **自動對接 Tab 2 宏觀目標配置**：無縫讀取 11 大 S&P 板塊動態權重與跨資產疊加指引，精算目標美元資金。
  - **整股調倉與最小敏感度過濾**：設定可調敏感度閾值（預設 0.5%），自動剔除微幅隨機噪聲，避免過度交易；買進單整股向下取整以防保證金超標。
  - **精確交易摩擦模型**：納入 5 bps 滑價與 0.02% 手續費損耗精算，實時揭示預估摩擦成本與調倉後現金留存水位。
  - **雙持倉模式**：支援「全現金全新建倉」與「自訂既有部位 Delta 調倉」。
  - **批次寫入審計日誌庫**：點擊「確認模擬執行」即可透過 `modules/database.py` 的 `insert_batch_trade_logs` 將整批調倉指令自動記錄至 SQLite，杜絕紙上談兵。
- **📈 宏觀板塊動態輪動 3 年滾動回測引擎 (`views/tab_backtest.py`)**：
  - **嚴格剔除前視偏誤 (No Look-ahead Bias)**：每月首個交易日依據過去歷史窗口的多因子宏觀適應度與動量超額進行月度再平衡。
  - **真實換手摩擦損耗扣除**：每筆換手均依據 Turnover 扣除滑價與券商佣金。
  - **基準對比與水下回撤圖**：同時對比 SPY（標普 500 買入持有）與 60/40 經典股債組合，清晰呈現 2022 年抗通膨急遽升息期間的優異防守能力（最大回撤顯著優於基準）。
  - **八大機構級計量指標**：完整輸出 CAGR、年化波動率、夏普比率 (Sharpe)、索提諾比率 (Sortino)、最大回撤 (MDD)、卡爾瑪比率 (Calmar)、資訊比率 (IR vs SPY)、詹森阿爾法 (Alpha) 與貝塔 (Beta)。
  - **歷史動態板塊持倉演變面積圖**：視覺化展示過去 3 年中科技、能源、金融、公用事業等板塊之動態權重流轉。
- **🔬 核心量化對衝子策略矩陣保留與整合**：
  - 維持 Hedged Carry (USD/JPY 20MA)、SPY Delta-Neutral (DTE 換約與 Theta 監控)、VRP 波動率溢價套利、Pair Trading 與策略庫自訂管理功能。
- **SQLite 批次交易記錄支援 (`modules/database.py`)**：
  - 新增 `insert_batch_trade_logs(trades: list) -> int`，支援以單一資料庫事務批次儲存多筆調倉指令與手續費記帳。

---

## [1.5.0] - 2026-11-07

### 🚀 里程碑：第三階段宏觀向 11 大 S&P 產業板塊傳導雷達、雙時區時鐘與自動化排程派送正式上線

#### 修復與防禦 (Fixed & Resilience)
- **修復 Tab 2 產業頁 etch_macro_matrix 元組解包異常 (iews/tab_industry.py)**：
  - 修正接收 etch_macro_matrix 回傳之 (data_dict, is_live) Tuple 結構，杜絕 	uple object has no attribute 'get' 導致的前端崩潰。
  - 於 calculate_macro_sector_allocation 注入防禦型型別檢查，相容 Tuple 與 Dict 雙重輸入格式。

#### 新增與優化 (Added & Enhanced)
- **全球雙時區標準化模組 (`modules/time_utils.py`)**：
  - 嚴格錨定台北時間 (`Asia/Taipei`, UTC+8) 與美東時間 (`America/New_York`, ET)，杜絕雲端容器預設 UTC 導致的時間偏離。
  - 側邊欄注入美觀實時的雙時鐘指示卡片，清晰標註台北 HQ 時間與華爾街美東交易時間。
  - 全域 SQLite 資料庫交易日誌、損益統計及宏觀研報存檔時間戳全面轉為台北標準時間。
- **宏觀向 11 大 S&P 產業板塊傳導雷達 (`views/tab_industry.py`)**：
  - **全域宏觀情境定位橫幅 (Macro Regime Banner)**：動態識別「流動性擴張與金髮女孩軟著陸」、「衰退防禦」、「利差倒掛壓制」等不同景氣週期階段。
  - **四大底層宏觀指標聯動**：直接同步美聯儲淨水庫水位 ($\text{Net Liq}$)、薩姆衰退指標 ($\text{Sahm}$)、10Y-2Y 殖利率曲線與股債 60 日相關性。
  - **多因子敏感度反應函數 (Sector Macro Betas)**：建立 11 大板塊對流動性、衰退、曲線斜率、降息與通膨之學理計量 Beta 矩陣。
  - **動態推薦權重與投資委員會姿態 (IC Stance)**：輸出宏觀適應評分、強烈超配/中性/防禦低配決議，並計算加總 100% 之板塊配置推薦比例。
  - **雙圖表視覺化對比**：直觀對照「宏觀輪動建議權重 (%)」與「近 1 個月市場實際超額 Alpha (%)」，揭示潛在定價錯估與超額套利機會。
  - **跨資產防禦與對衝疊加建議 (Cross-Asset Overlay)**：提供長天期美債 TLT 存續期調整、黃金 GLD 實質利率避險、以及日圓 USD/JPY 套息踩踏風控指引。
  - **升級版跨資產產業研究員 Agent**：提問時自動將當前宏觀情境、對應板塊評分與上游指標全要素注入 Prompt，產出深度跨資產研報。
- **Windows 工作排程一鍵配置與自動派送腳本 (`scripts/`)**：
  - 新增 `scripts/run_daily_dispatch.bat`：一鍵背景喚醒 Python 執行宏觀派送與資料庫歸檔。
  - 新增 `scripts/setup_windows_scheduler.bat`：一鍵透過 Windows `schtasks` 註冊每日上午 07:00 (台北時間) 的定時派送任務。

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
