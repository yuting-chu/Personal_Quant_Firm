@echo off
cd /d "%~dp0"
echo =================================================================
echo  Personal Quant Firm | 啟動本地量化戰情室 (串接本地 TWS 7497)
echo =================================================================
echo [INFO] 正在以 Python 啟動 Streamlit 服務...
python -m streamlit run app.py
pause
