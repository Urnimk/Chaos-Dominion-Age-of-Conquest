@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "啟動遊戲.py"
) else (
    python "啟動遊戲.py"
)
if errorlevel 1 (
    echo 請先安裝 Python 並執行 pip install -r requirements.txt
    pause
)
