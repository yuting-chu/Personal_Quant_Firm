@echo off
setlocal
echo =================================================================
echo  Personal Quant Firm | Windows 工作排程器 (Task Scheduler) 一鍵配置
echo =================================================================
echo.
set TASK_NAME=PersonalQuant_MacroMorningDispatch
set SCRIPT_PATH=%~dp0run_daily_dispatch.bat

echo [INFO] 正在建立每日上午 07:00 (台北時間) 自動派送任務...
schtasks /create /tn "%TASK_NAME%" /tr "\"%SCRIPT_PATH%\"" /sc daily /st 07:00 /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] 工作排程已成功建立！
    echo 任務名稱: %TASK_NAME%
    echo 執行時間: 每日清晨 07:00 (台北時間)
    echo 執行腳本: %SCRIPT_PATH%
) else (
    echo.
    echo [ERROR] 建立失敗，若權限不足，請對此檔案點右鍵選擇「以系統管理員身分執行」。
)
echo.
pause
