@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "亂世演算_征佔紀元_V10_啟動.py"
) else (
    python "亂世演算_征佔紀元_V10_啟動.py"
)
if errorlevel 1 (
    echo.
    echo 啟動失敗。請先安裝 Python 3.10 以上，再執行：pip install -r requirements.txt
    pause
)
