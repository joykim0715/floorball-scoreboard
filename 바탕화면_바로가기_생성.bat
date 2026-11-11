@echo off
chcp 65001 > nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\플로어볼 스코어보드.lnk'); $s.TargetPath = '%~dp0플로어볼_점수판_실행.exe'; $s.WorkingDirectory = '%~dp0'; $s.IconLocation = '%~dp0[시스템_내부파일]\scoreboard.ico,0'; $s.Description = '플로어볼 공식 스코어보드'; $s.Save()"
echo 바탕화면에 [플로어볼 스코어보드] 바로가기가 성공적으로 생성되었습니다!
timeout /t 2 > nul
