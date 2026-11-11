CREATE DATABASE IF NOT EXISTS floorball CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE floorball;

CREATE TABLE IF NOT EXISTS matches (
  match_id    VARCHAR(80)  NOT NULL PRIMARY KEY,
  played_at   DATETIME(3)  NULL COMMENT '경기 저장 시각 (한국시간)',
  gender      VARCHAR(4)   NULL,
  level       VARCHAR(4)   NULL,
  home_school VARCHAR(120) NOT NULL,
  away_school VARCHAR(120) NOT NULL,
  home_score  INT          NOT NULL DEFAULT 0,
  away_score  INT          NOT NULL DEFAULT 0,
  period      INT          NOT NULL DEFAULT 1,
  raw_json    JSON         NOT NULL,
  INDEX idx_matches_played_at (played_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS match_players (
  match_id  VARCHAR(80)  NOT NULL,
  side      VARCHAR(10)  NOT NULL,
  number    VARCHAR(20)  NOT NULL DEFAULT '',
  name      VARCHAR(100) NOT NULL DEFAULT '',
  school    VARCHAR(120) NOT NULL DEFAULT '',
  goals     INT          NOT NULL DEFAULT 0,
  assists   INT          NOT NULL DEFAULT 0,
  penalties INT          NOT NULL DEFAULT 0,
  INDEX idx_mp_match (match_id),
  CONSTRAINT fk_mp_matches FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS match_logs (
  match_id   VARCHAR(80)  NOT NULL,
  seq        INT          NOT NULL,
  period     VARCHAR(16)  NOT NULL DEFAULT '1P',
  game_time  VARCHAR(20)  NOT NULL DEFAULT '00:00',
  category   VARCHAR(60)  NOT NULL DEFAULT '',
  team       VARCHAR(120) NOT NULL DEFAULT '-',
  detail     VARCHAR(255) NOT NULL DEFAULT '',
  home_score INT          NOT NULL DEFAULT 0,
  away_score INT          NOT NULL DEFAULT 0,
  PRIMARY KEY (match_id, seq),
  CONSTRAINT fk_ml_matches FOREIGN KEY (match_id) REFERENCES matches(match_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
