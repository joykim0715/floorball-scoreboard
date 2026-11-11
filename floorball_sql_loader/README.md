# 🏑 플로어볼 경기 데이터 로컬 MySQL 로더 (`floorball_sql_loader`)

Copyright © 2026 김인홍. All rights reserved. 상위 폴더 `COPYRIGHT.txt`.

점수판 HTML이나 서버 코드를 건드리지 않고, `https://floorball-api.recead0715.workers.dev/matches` (`GET`)에서 경기 데이터를 읽어 내 PC의 로컬 MySQL(`floorball` DB)에 적재하는 독립 로더입니다.

---

## 1. 로컬 설정 (`.env`)
같은 폴더의 `.env` 파일에 내 PC의 MySQL 비밀번호만 입력해 두면 됩니다 (`.env`는 로컬에만 보관).
```ini
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=여기에_로컬_MySQL_비밀번호_입력
MYSQL_DATABASE=floorball
MYSQL_BIN=C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe
MATCHES_API_URL=https://floorball-api.recead0715.workers.dev/matches
```

---

## 2. 실행 방법

### ① 변경분만 가져오기 (기본 · `?since=lastUpdatedAt` 증분 동기화)
- `동기화_실행.bat` 더블클릭 또는 터미널에서:
```powershell
python sync_to_mysql.py
```
- 첫 실행 시 전체 경기를 가져와 `floorball` DB에 upsert하고 `sync_state.json`에 `lastUpdatedAt`을 기록합니다.
- 다음 실행부터는 `?since={lastUpdatedAt}`으로 새로 추가·수정된 경기만 가져와 반영합니다.

### ② 전체 다시 맞추기 (서버에서 삭제된 경기까지 MySQL에서 정리)
- `전체_다시맞추기.bat` 더블클릭 또는 터미널에서:
```powershell
python sync_to_mysql.py --full
```
- `?since=` 없이 서버 전체 목록을 조회하여, 서버에서 지워진 `match_id`를 로컬 MySQL(`matches`, `match_players`, `match_logs`)에서도 삭제한 뒤 전체 경기를 다시 맞춥니다.

### ③ 실시간 주기적 자동 동기화 (선택)
```powershell
python sync_to_mysql.py --watch 30
```
- 30초마다 자동으로 변경분을 확인해 MySQL에 반영합니다.

---

### ④ 자동 동기화 (Windows 작업 스케줄러)
- 작업 이름 `Floorball MySQL Sync`: 로그인 상태에서 1분마다 창 없이 `sync_to_mysql.py`를 실행합니다.
- 실행 결과는 `sync.log`에 쌓입니다.
- 끄기/켜기: `자동동기화_끄기.bat` / `자동동기화_켜기.bat`

---

## 3. 참고
- `matches.played_at`은 `DATETIME(3)`이며 **한국시간**으로 저장됩니다 (서버의 UTC `playedAt`을 +9시간 변환).
  예: `SELECT * FROM matches WHERE DATE(played_at) = '2026-11-14' ORDER BY played_at;`
