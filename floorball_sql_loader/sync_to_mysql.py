#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
플로어볼 수신 서버(GET /matches) ➔ 로컬 PC MySQL(floorball DB) 동기화 로더
Copyright © 2026 김인홍. All rights reserved. 폴더 저작권 안내는 상위 COPYRIGHT.txt.
- 기본 실행: sync_state.json의 lastUpdatedAt을 기준으로 ?since= 증분 동기화 (match_id 기준 upsert)
- 전체 다시 맞추기(--full / --resync): 서버 전체 목록을 받아 서버에서 삭제된 경기를 MySQL에서도 삭제 후 전체 재동기화
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
STATE_PATH = os.path.join(BASE_DIR, "sync_state.json")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")
LOG_PATH = os.path.join(BASE_DIR, "sync.log")
LOG_MAX_BYTES = 512 * 1024


def redirect_output_to_log():
    """pythonw(작업 스케줄러)로 실행되면 콘솔이 없으므로 출력을 sync.log에 남긴다."""
    if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > LOG_MAX_BYTES:
        os.replace(LOG_PATH, LOG_PATH + ".old")
    log = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    log.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    sys.stdout = log
    sys.stderr = log


def load_dotenv(path):
    cfg = {}
    if not os.path.exists(path):
        return cfg
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            cfg[k] = v
    return cfg


def get_config():
    file_cfg = load_dotenv(ENV_PATH)
    return {
        "host": os.environ.get("MYSQL_HOST", file_cfg.get("MYSQL_HOST", "127.0.0.1")),
        "port": int(os.environ.get("MYSQL_PORT", file_cfg.get("MYSQL_PORT", "3306")) or 3306),
        "user": os.environ.get("MYSQL_USER", file_cfg.get("MYSQL_USER", "root")),
        "password": os.environ.get("MYSQL_PASSWORD", file_cfg.get("MYSQL_PASSWORD", "")),
        "database": os.environ.get("MYSQL_DATABASE", file_cfg.get("MYSQL_DATABASE", "floorball")),
        "mysql_bin": os.environ.get(
            "MYSQL_BIN",
            file_cfg.get("MYSQL_BIN", r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"),
        ),
        "api_url": os.environ.get(
            "MATCHES_API_URL",
            file_cfg.get("MATCHES_API_URL", "https://floorball-api.recead0715.workers.dev/matches"),
        ),
    }


def load_sync_state():
    if not os.path.exists(STATE_PATH):
        return {"lastUpdatedAt": None}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {"lastUpdatedAt": data.get("lastUpdatedAt")}
    except Exception:
        return {"lastUpdatedAt": None}


def save_sync_state(last_updated_at):
    payload = {
        "lastUpdatedAt": last_updated_at,
        "syncedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def fetch_matches_from_api(api_url, since=None):
    url = api_url
    if since:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}since={urllib.parse.quote(str(since), safe='')}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Floorball-SQL-Loader/1.0",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw)


def sql_str(val):
    if val is None:
        return "NULL"
    s = str(val)
    s = (
        s.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\0", "\\0")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
    return f"'{s}'"


def to_kst_datetime(val):
    """ISO 시각(예: 2026-11-09T07:23:36.375Z)을 MySQL DATETIME(3)용 한국시간 문자열로 변환."""
    s = str(val or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def sql_int(val, default=0):
    try:
        return str(int(val))
    except Exception:
        return str(int(default))


def extract_players(m, home_school, away_school):
    rows = []
    home_obj = m.get("home") if isinstance(m.get("home"), dict) else {}
    away_obj = m.get("away") if isinstance(m.get("away"), dict) else {}

    for side, side_obj, default_school in [
        ("home", home_obj, home_school),
        ("away", away_obj, away_school),
    ]:
        players = side_obj.get("players")
        if isinstance(players, list):
            for p in players:
                if not isinstance(p, dict):
                    continue
                rows.append(
                    {
                        "side": side,
                        "number": str(p.get("number") or "").strip()[:20],
                        "name": str(p.get("name") or "").strip()[:100],
                        "school": str(p.get("school") or default_school or "").strip()[:120],
                        "goals": max(0, int(p.get("goals") or 0)),
                        "assists": max(0, int(p.get("assists") or 0)),
                        "penalties": max(
                            0,
                            int(
                                p.get("penalties")
                                if p.get("penalties") is not None
                                else (p.get("penaltyCount") or 0)
                            ),
                        ),
                    }
                )

    if not rows and isinstance(m.get("players"), list):
        for p in m["players"]:
            if not isinstance(p, dict):
                continue
            side = str(p.get("side") or p.get("team") or "home").lower()
            side = "away" if side == "away" else "home"
            default_school = away_school if side == "away" else home_school
            rows.append(
                {
                    "side": side,
                    "number": str(p.get("number") or "").strip()[:20],
                    "name": str(p.get("name") or "").strip()[:100],
                    "school": str(p.get("school") or default_school or "").strip()[:120],
                    "goals": max(0, int(p.get("goals") or 0)),
                    "assists": max(0, int(p.get("assists") or 0)),
                    "penalties": max(
                        0,
                        int(
                            p.get("penalties")
                            if p.get("penalties") is not None
                            else (p.get("penaltyCount") or 0)
                        ),
                    ),
                }
            )
    return rows


def extract_logs(m):
    raw_logs = m.get("logs") if isinstance(m.get("logs"), list) else m.get("events")
    if not isinstance(raw_logs, list):
        return []
    rows = []
    for idx, item in enumerate(raw_logs, start=1):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "seq": idx,
                "period": str(item.get("period") or "1P").strip()[:16],
                "game_time": str(item.get("gameTime") or item.get("time") or "00:00").strip()[:20],
                "category": str(item.get("category") or item.get("type") or "").strip()[:60],
                "team": str(item.get("team") or "-").strip()[:120],
                "detail": str(item.get("detail") or "").strip()[:255],
                "home_score": max(0, int(item.get("homeScore") or 0)),
                "away_score": max(0, int(item.get("awayScore") or 0)),
            }
        )
    return rows


def build_sync_sql(matches, database="floorball", full_resync=False):
    lines = [
        "SET NAMES utf8mb4;",
        f"CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;",
        f"USE `{database}`;",
    ]
    if os.path.exists(SCHEMA_PATH):
        with open(SCHEMA_PATH, "r", encoding="utf-8") as sf:
            for sline in sf:
                up = sline.strip().upper()
                if up.startswith(("CREATE DATABASE", "USE ", "CHARACTER SET", "COLLATE ")):
                    continue
                lines.append(sline.rstrip("\r\n"))

    lines.append("START TRANSACTION;")

    valid_Matches = []
    for m in matches or []:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("matchId") or "").strip()
        if not mid:
            continue
        valid_Matches.append((mid, m))

    if full_resync:
        if valid_Matches:
            id_list_sql = ", ".join(sql_str(mid) for mid, _ in valid_Matches)
            lines.append(f"DELETE FROM match_players WHERE match_id NOT IN ({id_list_sql});")
            lines.append(f"DELETE FROM match_logs WHERE match_id NOT IN ({id_list_sql});")
            lines.append(f"DELETE FROM matches WHERE match_id NOT IN ({id_list_sql});")
        else:
            lines.append("DELETE FROM match_players;")
            lines.append("DELETE FROM match_logs;")
            lines.append("DELETE FROM matches;")

    for mid, m in valid_Matches:
        played_at = to_kst_datetime(m.get("playedAt") or m.get("endedAt"))
        div = m.get("division") if isinstance(m.get("division"), dict) else {}
        gender = str(div.get("gender") or m.get("gender") or "").strip()[:4] or None
        level = str(div.get("level") or m.get("level") or "").strip()[:4] or None

        home_obj = m.get("home") if isinstance(m.get("home"), dict) else {}
        away_obj = m.get("away") if isinstance(m.get("away"), dict) else {}

        home_school = str(
            m.get("homeSchool") or home_obj.get("school") or home_obj.get("name") or "HOME"
        ).strip()[:120]
        away_school = str(
            m.get("awaySchool") or away_obj.get("school") or away_obj.get("name") or "AWAY"
        ).strip()[:120]

        home_score = (
            m.get("homeScore")
            if m.get("homeScore") is not None
            else (home_obj.get("score") or 0)
        )
        away_score = (
            m.get("awayScore")
            if m.get("awayScore") is not None
            else (away_obj.get("score") or 0)
        )
        period = m.get("period") or 1
        raw_json = json.dumps(m, ensure_ascii=False)

        lines.append(
            "INSERT INTO matches "
            "(match_id, played_at, gender, level, home_school, away_school, home_score, away_score, period, raw_json) "
            f"VALUES ({sql_str(mid)}, {sql_str(played_at)}, {sql_str(gender)}, {sql_str(level)}, "
            f"{sql_str(home_school)}, {sql_str(away_school)}, {sql_int(home_score)}, {sql_int(away_score)}, "
            f"{sql_int(period, 1)}, {sql_str(raw_json)}) "
            "ON DUPLICATE KEY UPDATE "
            "played_at = VALUES(played_at), "
            "gender = VALUES(gender), "
            "level = VALUES(level), "
            "home_school = VALUES(home_school), "
            "away_school = VALUES(away_school), "
            "home_score = VALUES(home_score), "
            "away_score = VALUES(away_score), "
            "period = VALUES(period), "
            "raw_json = VALUES(raw_json);"
        )

        # match_id 기준 하위 선수/로그 멱등 교체 (중복 방지)
        lines.append(f"DELETE FROM match_players WHERE match_id = {sql_str(mid)};")
        for p in extract_players(m, home_school, away_school):
            lines.append(
                "INSERT INTO match_players "
                "(match_id, side, number, name, school, goals, assists, penalties) "
                f"VALUES ({sql_str(mid)}, {sql_str(p['side'])}, {sql_str(p['number'])}, "
                f"{sql_str(p['name'])}, {sql_str(p['school'])}, {sql_int(p['goals'])}, "
                f"{sql_int(p['assists'])}, {sql_int(p['penalties'])});"
            )

        lines.append(f"DELETE FROM match_logs WHERE match_id = {sql_str(mid)};")
        for lg in extract_logs(m):
            lines.append(
                "INSERT INTO match_logs "
                "(match_id, seq, period, game_time, category, team, detail, home_score, away_score) "
                f"VALUES ({sql_str(mid)}, {sql_int(lg['seq'], 1)}, {sql_str(lg['period'])}, "
                f"{sql_str(lg['game_time'])}, {sql_str(lg['category'])}, {sql_str(lg['team'])}, "
                f"{sql_str(lg['detail'])}, {sql_int(lg['home_score'])}, {sql_int(lg['away_score'])});"
            )

    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


def execute_sql_script(sql_text, cfg):
    # 1. pymysql이 설치되어 있으면 우선 사용
    try:
        import pymysql  # type: ignore

        conn = pymysql.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            charset="utf8mb4",
            autocommit=False,
        )
        try:
            with conn.cursor() as cur:
                for stmt in [s.strip() for s in sql_text.split(";\n") if s.strip()]:
                    cur.execute(stmt)
            conn.commit()
        finally:
            conn.close()
        return
    except ImportError:
        pass

    # 2. 표준 mysql.exe CLI 실행 (MYSQL_PWD 환경변수 사용으로 프로세스 인자에 비밀번호 미노출)
    mysql_bin = cfg["mysql_bin"]
    if not os.path.exists(mysql_bin):
        mysql_bin = "mysql"

    cmd = [
        mysql_bin,
        f"--host={cfg['host']}",
        f"--port={cfg['port']}",
        f"--user={cfg['user']}",
        "--default-character-set=utf8mb4",
    ]
    env = os.environ.copy()
    if cfg["password"]:
        env["MYSQL_PWD"] = cfg["password"]

    proc = subprocess.run(
        cmd,
        input=sql_text.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if proc.returncode != 0:
        err_msg = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"MySQL 실행 오류 (종료 코드 {proc.returncode}): {err_msg}\n"
            f"💡 .env 파일에 MYSQL_PASSWORD가 올바르게 설정되어 있는지 확인해 주세요."
        )


def run_once(full_resync=False, emit_sql_path=None):
    cfg = get_config()
    state = load_sync_state()
    since = None if full_resync else state.get("lastUpdatedAt")

    mode_str = "전체 다시 맞추기(--full)" if full_resync else (f"증분 동기화(?since={since})" if since else "초기 동기화")
    print(f"[SQL 로더] {mode_str} 요청 중... ({cfg['api_url']})")

    resp = fetch_matches_from_api(cfg["api_url"], since=since)
    matches = resp.get("matches") if isinstance(resp, dict) else []
    if not isinstance(matches, list):
        matches = []
    last_updated_at = resp.get("lastUpdatedAt") if isinstance(resp, dict) else None

    if not full_resync and len(matches) == 0:
        print(f"[SQL 로더] 새로 변경된 경기가 없습니다 (0건). lastUpdatedAt={last_updated_at or since}")
        if last_updated_at:
            save_sync_state(last_updated_at)
        return 0, last_updated_at

    sql_text = build_sync_sql(matches, database=cfg["database"], full_resync=full_resync)

    if emit_sql_path:
        with open(emit_sql_path, "w", encoding="utf-8") as f:
            f.write(sql_text)
        print(f"[SQL 로더] SQL 스크립트 출력 완료: {emit_sql_path} (대상 경기 {len(matches)}건)")
        return len(matches), last_updated_at

    execute_sql_script(sql_text, cfg)
    if last_updated_at or full_resync:
        save_sync_state(last_updated_at)

    print(
        f"[SQL 로더] 완료: 서버에서 {len(matches)}건 가져와 MySQL({cfg['database']})에 반영했습니다. "
        f"(lastUpdatedAt={last_updated_at})"
    )
    return len(matches), last_updated_at


def main():
    if sys.stdout is None:
        redirect_output_to_log()
    parser = argparse.ArgumentParser(description="플로어볼 경기 결과 MySQL 동기화 로더")
    parser.add_argument(
        "--full",
        "--resync",
        dest="full_resync",
        action="store_true",
        help="전체 다시 맞추기 (서버에서 삭제된 경기를 MySQL에서도 삭제하고 전체 재동기화)",
    )
    parser.add_argument(
        "--watch",
        type=int,
        default=0,
        metavar="SECONDS",
        help="지정한 초 간격으로 계속 증분 동기화 실행 (예: --watch 30)",
    )
    parser.add_argument(
        "--emit-sql",
        dest="emit_sql",
        default=None,
        help="MySQL에 직접 접속하는 대신 실행할 SQL을 파일로 저장",
    )
    args = parser.parse_args()

    if args.watch and args.watch > 0:
        interval = max(5, args.watch)
        print(f"[SQL 로더] {interval}초 간격 자동 동기화 모드를 시작합니다 (종료: Ctrl+C)")
        first = True
        while True:
            try:
                run_once(full_resync=(args.full_resync and first), emit_sql_path=args.emit_sql)
                first = False
            except Exception as e:
                print(f"[SQL 로더 오류] {e}", file=sys.stderr)
            time.sleep(interval)
    else:
        run_once(full_resync=args.full_resync, emit_sql_path=args.emit_sql)


if __name__ == "__main__":
    main()
