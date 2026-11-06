@echo off
cd /d "%~dp0.."
echo =================================================================
echo  Personal Quant Firm | 晨間宏觀投研自動化派送與 SQLite 歸檔引擎
echo =================================================================
echo [INFO] 正在啟動 Macro Dispatcher...

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3.11 scripts\macro_dispatcher.py --type morning
) else (
    python scripts\macro_dispatcher.py --type morning
)

echo.
echo [DONE] 晨間宏觀速遞派送與歸檔流程執行完畢。
