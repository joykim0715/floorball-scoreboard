@echo off
chcp 65001 >nul
cd /d "%~dp0"
python sync_to_mysql.py --full
pause
