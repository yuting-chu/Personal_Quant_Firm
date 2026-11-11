@echo off
chcp 65001 >nul
echo =======================================================================
echo   Personal Quant Firm | 全自動背景監控交易守護進程 (Autonomous Daemon)
echo =======================================================================
echo.
echo [1/2] 正在檢查本地 Python 環境與 TWS Port 7497 連線...
python -c "import socket; s = socket.socket(); res = s.connect_ex(('127.0.0.1', 7497)); s.close(); print('TWS Port 7497 狀態: 在線' if res == 0 else '⚠️ 警告: TWS Port 7497 未在線，請確認 TWS 已開啟！')"

echo.
echo [2/2] 啟動全自動量化守護進程 (Daemon Trader)...
echo 守護進程將每 20 秒定時輪詢監控、自動評估情緒核心、產業定價與風控熔斷。
echo 隨時可按 Ctrl + C 優雅退出。
echo -----------------------------------------------------------------------
python scripts/daemon_auto_trader.py --interval 20 --port 7497

pause
