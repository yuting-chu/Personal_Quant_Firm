# 更新日誌 (Changelog)

本專案遵循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.0.0/) 格式，並依據標準軟體工程規範記錄版本迭代、模型優化與架構調整。

---

## [1.12.0] - 2026-11-11

### 🎯 里程碑：三大日內量化策略實盤模擬括號單全數掛單成功 (Live TWS Bracket Order Deployment)

#### 核心優化與下單實測 (Execution & Enhancements)
- **⚡ CME 微型期貨與外匯括號單 TIF（Time In Force）協定修復**：
  - 修復 IBKR 期貨委託必須指定 `TIF='DAY'` 之規則限制（避免 TWS 預設規則阻斷 `Error 10349`）。
  - 在 `modules/ibkr_engine.py` 括號單建構函式中強制同步 Parent、Take Profit、Stop Loss 三筆子單之 TIF，達成 IBKR 撮合引擎的原子性送單。
- **🚀 三大量化策略全自動掛入 TWS 模擬伺服器 (帳號 DUR346381)**：
  - **策略 1（/MES 日內 VWAP 均值回歸）**：買進 1 口 `/MES`，限價 $7610.00，停利 $7632.50，伺服器硬停損 $7595.00（OrderId: 16, 17, 18）。
  - **策略 2（/MNQ 開盤 15M 動量突破）**：買進 1 口 `/MNQ`，限價 $28350.00，停利 $28416.00，伺服器硬停損 $28320.00（OrderId: 20, 21, 22）。
  - **策略 3（USD/JPY 倫敦突破 Carry）**：買進 10,000 單位 `USD/JPY`，限價 ¥159.50，停利 ¥160.00，伺服器硬停損 ¥159.25（OrderId: 24, 25, 26）。
- **📊 委託狀態即時驗證**：
  - 經由 `ib.openTrades()` 雙向確認：3 筆 Parent 限價單處於 `Submitted` 活躍掛單狀態，6 筆子單處於 `PreSubmitted`（由母單成交後自動觸發）守護狀態。

---

## [1.11.0] - 2026-11-10

### 🚀 里程碑：Interactive Brokers (IBKR) API 實盤模擬交易引擎與 TWS 直送下單正式上線

#### 新增與優化 (Added & Enhanced)
- **🔌 核心 IBKR Socket 交易引擎實作 (`modules/ibkr_engine.py`)**：
  - 基於 `ib_insync` 封裝高可用 Socket 介面，安全對接本地 TWS / IB Gateway 模擬交易通訊埠（Port 7497）。
  - **實時資產與保證金同步**：自動獲取真實模擬帳號（`DUR346381`）、淨資產（NetLiquidation $1,000,000 USD）、總購買力 ($4,000,000 USD) 與持倉明細。
  - **合約智能解析 (Contract Qualifier)**：原生相容 CME 微型期貨連續合約 (`/MES`, `/MNQ`, `/MGC`)、美股現貨/ETF (`SPY`) 與即期外匯 (`USD/JPY`)。
  - **機構級全自動括號單 (Bracket Orders)**：Parent 限價單與伺服器端 Stop-Loss、Take-Profit 三聯單一次性原子送出，保證本地斷線時硬停損仍由 IBKR 主機執行。
- **🏛️ 側邊欄即時連線控制台與資金同步 (`app.py`)**：
  - 新增「📡 IBKR 模擬交易連線」卡片，自動辨識本地 TWS 運行狀態並顯示帳號、即時淨值與購買力。
  - 支援「🔄 一鍵同步資金」：將 TWS 真實淨值直接注入全域資本配置控制台與風控看板。
- **🧪 板塊調倉單一鍵直送 TWS (`views/tab_backtest.py`)**：
  - 新增「🚀 直送 IBKR 模擬帳戶實盤下單」按鈕，可一鍵將 11 大宏觀板塊整股調倉單批量送入 TWS 撮合。
- **⚡ 微型期貨括號單沙盒 (`views/tab_backtest.py`)**：
  - 在第 4 節新增「IBKR 模擬交易即時括號單沙盒」，支援在前端介面手動指定進場、停損與 1.5R 停利點位，並一鍵直發 TWS。

---

## [1.10.0] - 2026-11-09

### ⚡ 里程碑：微型期貨與外匯日內多策略回測實驗室 (Intraday Multi-Strategy Quant Lab) 正式上線

#### 新增與優化 (Added & Enhanced)
- **🚀 微型期貨與外匯日內多策略回測引擎 (`views/tab_backtest.py`)**：
  - **策略 1（/MES 日內 VWAP 均值回歸）**：高勝率 (60%~65%) 偏離 $\pm 2.0\sigma$ 均值回歸模型，具備 ADX 趨勢過濾與 $1.5R$ 目標位，單筆來回扣除 IBKR Pro Tiered $1.24/口。
  - **策略 2（/MNQ 美股開盤 15M 動量突破 ORB）**：捕捉美東 09:30 開盤流動性，放量 1.5 倍突破進場，高盈虧比 ($2.2R$)，單筆來回扣除 $1.24/口。
  - **策略 3（USD/JPY 倫敦開盤突破 Carry）**：捕捉台北 15:00 歐洲外匯流動性，突破亞洲箱體並順政策正利差方向，單筆來回扣除 $4.00/手。
  - **三合一正交疊加組合 (Ensemble Portfolio)**：透過非相關因子對沖，呈現夏普比率疊加 ($SR \approx 1.90+$) 與回撤平滑效應。
- **🏆 Prop Firm 自營考核標準全維度檢驗看板**：
  - **4.0% 動態回撤 (MTD) 即時檢驗**：實時計算峰值回撤，呈現合格/破標警示。
  - **1.5% 單日最大虧損 (DLL) 每日檢驗**：嚴格鎖定單日最差虧損。
  - **Prop +8.0% 達標速度推算**：推算組合在第幾天通過考核門檻（實證約 28 天通關）。
  - **互動視圖切換**：支援「三合一組合」與各單一策略獨立累積淨值曲線、每日盈虧柱狀圖與執行狀態機備忘錄。

---

## [1.9.0] - 2026-11-08

### ⚡ 里程碑：對接 Interactive Brokers (IBKR) 官方真實費率矩陣與 Prop Firm 自營考核風控標準 (Topstep/Apex/FTMO)

#### 新增與優化 (Added & Enhanced)
- **🏛️ 全域頂部戰情室新增「⚡ Prop Firm 自營考核模式」(`app.py`)**：
  - **動態高水位線追蹤 (High-Water Mark, Peak NAV)**：實時記錄歷史最高資產淨值，杜絕傳統靜態本金造成的盲區。
  - **最大動態追蹤回撤硬熔斷 (Max Trailing Drawdown 4.0%)**：計算動態爆倉違規線 $\text{Breach Line} = \text{Peak NAV} \times 96\%$，並實時呈現「距離爆倉線緩衝金額 ($)」與安全警示。
  - **單日最大虧損熔斷 (Daily Loss Limit 1.5%)**：即時聯動 SQLite 真實當日已實現損益，破標時強制發動硬熔斷警報。
- **🛡️ CME 微型期貨與即期外匯 $R$-Unit 倉位精算機 (`views/tab_risk.py`)**：
  - 專為 `/MES` (微型標普)、`/MNQ` (微型那指)、`/MGC` (微型黃金) 與 `USD/JPY` (IDEALPRO 外匯) 打造之自營商考核開倉口數精算器。
  - **全包摩擦成本扣除**：每口成本完整納入 CME/NFA 交易所規費與 IBKR Pro Tiered 來回佣金 ($1.24/口 MES/MNQ, $1.70/口 MGC)。
  - **整數下限 (Floor) 絕對控險**：嚴格依單筆風險預算 ($R\%$) 倒推合規口數，徹底根除情緒化超額下單。
  - **實時考核合規判定**：動態檢核單筆停損是否擊穿當日 DLL (1.5%) 或動態回撤水線。
- **🧪 宏觀板塊調倉單對接 IBKR Pro Tiered 階梯式精算模型 (`views/tab_backtest.py`)**：
  - 支援「IBKR Pro Tiered 階梯式精算」與「保守百分比模型」雙軌切換。
  - 精確套用 IBKR Pro 官方階梯費率（$0.0035/股，低消 $0.35/單）並在賣出時精算 SEC 交易費 (0.00278%) 與 FINRA TAF 規費 ($0.000166/股)。
  - 批次調倉清單與資料庫交易日誌即時記載真實摩擦成本。
- **🤖 首席風控官 (CRO) 審計備忘錄全面整合 Prop 考核維度 (`views/tab_risk.py`)**：
  - AI CRO 提示詞全面導入動態高水位線 (Peak NAV)、距違規線緩衝金額與 Prop 合規姿態診斷。

## [1.8.2] - 2026-11-08

### 🎨 全域深淺色適配：全面修復淺色白底模式下文字對比度，報告改用 Streamlit 原生高對比 Info 容器

#### 修復與優化 (Fixed & Enhanced)
- **徹底移除全域白字樣式強制覆蓋 (`app.py`)**：
  - 拔除先前注入的 `color: #f1f5f9` 等淺白文字強制規則，杜絕在白底淺色模式下產生「白字在白底上」完全無法閱讀的致命衝突。
  - 將頁籤頂部吸頂列底色改為 `var(--background-color)` 響應式 CSS 變數，完美貼合使用者的淺色/深色主題。
- **CRO 風控備忘錄與 IC 投審會決議全面改採原生 `st.info` (`views/tab_risk.py` & `views/tab_audit.py`)**：
  - 比照獲使用者高度認可的 Tab 1 與 Tab 2 研報呈現模式，改用 Streamlit 原生 `st.info(...)`。
  - 在白底淺色模式下自動套用冰藍柔和底色搭配高對比深藍文字 (`#004085`)，在深色模式下自動切換為深藍底白字，100% 免疫任何主題色調錯位。
- **指標卡與狀態橫幅全面改為柔和 `rgba(...)` 半透明色階**：
  - `views/tab_risk.py`：四重宏觀熔斷卡片由原先死黑底色改為柔和紅綠黃 `rgba(...)`，在白底背景下呈現現代清新色調，深色字體層次分明。
  - `views/tab_backtest.py`：即時市場信號卡片全面升級為半透明 `rgba(...)` 現代輕量徽章。
  - `views/tab_industry.py`：宏觀情境橫幅改為輕柔半透明冰藍底色 (`rgba(49, 130, 206, 0.1)`)。

---

## [1.8.1] - 2026-11-08

### 🎨 UI 視覺與對比度全面優化：CRO 風控報告與 IC 投審會備忘錄導入原生高對比卡片

#### 修復與優化 (Fixed & Enhanced)
- **徹底修復 AI 研報在深色背景下字跡不明顯問題 (`views/tab_risk.py` & `views/tab_audit.py`)**：
  - 移除原先硬編碼暗黑底色 (`#1a1d28`) 導致內文與標題對比度不足的 HTML `<div>` 容器。
  - 改用 Streamlit 原生卡片容器 (`st.container(border=True)`) 與高雅漸層職能識別橫幅（CRO 科技天藍橫幅、IC 皇家金靛橫幅）。
  - 將 Gemini 輸出的多段落 Markdown 文字直接交由 Streamlit 原生 Markdown 引擎渲染，完美呈現標題階層、重點加粗與有序/無序清單。
- **全域文字高對比度樣式注入 (`app.py`)**：
  - 在全域 CSS 注入 Markdown 階層色彩規範：
    - `H1~H3` 主標題強化為高亮天藍色 (`#63b3ed`, 700 粗體)；
    - `H4~H5` 副標題強化為暖金色 (`#ecc94b`, 600 粗體)；
    - `strong` 與 `b` 加粗文字強化為金黃亮色 (`#f6e05e`)；
    - 內文段落 `p` 與清單 `li` 採用清晰高雅的高對比白板岩色 (`#f1f5f9`)，並優化行距至 1.7 倍，無論在任何螢幕或深淺模式下均具備極致閱讀舒適度。

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
