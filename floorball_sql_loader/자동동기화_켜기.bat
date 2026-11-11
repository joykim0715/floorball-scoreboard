@echo off
chcp 65001 >nul
schtasks /Change /TN "Floorball MySQL Sync" /ENABLE
echo 자동 동기화를 켰습니다. PC가 켜져 있는 동안 1분마다 서버 결과를 MySQL로 가져옵니다.
pause
