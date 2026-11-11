@echo off
chcp 65001 >nul
schtasks /Change /TN "Floorball MySQL Sync" /DISABLE
echo 자동 동기화를 껐습니다. 다시 켜려면 자동동기화_켜기.bat 을 실행하세요.
pause
