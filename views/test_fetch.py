import yfinance as yf
import pandas as pd
import requests

symbols = ["SPY", "XLK", "XLE", "XLU"]
print("=" * 50)
print("🔍 開始測試資料抓取與處理流程...")
print("=" * 50)

# 方法 1: 測試 yfinance 批次抓取
print("\n[測試 1] 透過 yfinance.download 抓取收盤價：")
try:
    df_raw = yf.download(symbols, period="2mo", interval="1d", progress=False)
    print(f"• 抓取到的原始維度: {df_raw.shape}")
    print(f"• 原始欄位結構: {df_raw.columns}")
    
    # 提取 Close
    if 'Close' in df_raw.columns:
        close_df = df_raw['Close']
        print("\n• 成功提取 Close 價格表 (前 3 筆)：")
        print(close_df.head(3))
        
        # 計算報酬率
        ret_1m = ((close_df.iloc[-1] / close_df.iloc[-22]) - 1) * 100
        print("\n• 計算出之近 1 個月報酬率 (%)：")
        print(ret_1m)
        
        spy_ret = float(ret_1m['SPY'])
        print(f"\n• SPY 基準報酬率: {spy_ret:.2f}%")
        for s in ["XLK", "XLE", "XLU"]:
            alpha = float(ret_1m[s]) - spy_ret
            print(f"  -> {s} 相對 SPY Alpha: {alpha:+.2f}%")
    else:
        print("❌ 未在 DataFrame 中找到 'Close' 欄位")
except Exception as e:
    print(f"❌ yfinance 抓取失敗，錯誤訊息: {e}")

# 方法 2: 測試直接連線 Yahoo Chart API
print("\n" + "=" * 50)
print("[測試 2] 透過直接 HTTP API 抓取 SPY：")
try:
    url = "https://query1.finance.yahoo.com/v8/finance/chart/SPY?range=2mo&interval=1d"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=5)
    print(f"• HTTP 回應狀態碼: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        closes = data['chart']['result'][0]['indicators']['quote'][0]['close']
        valid_closes = [c for c in closes if c is not None]
        print(f"• 成功抓到 {len(valid_closes)} 個交易日收盤價")
        print(f"• 最新收盤價: {valid_closes[-1]:.2f}")
    else:
        print("❌ HTTP 請求被拒絕")
except Exception as e:
    print(f"❌ HTTP 抓取失敗: {e}")