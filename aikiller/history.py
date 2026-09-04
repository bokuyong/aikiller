"""로컬 분석 기록 — 개인용. SQLite(표준 라이브러리)로 홈 디렉터리에 저장한다.

    ~/.aikiller/history.db

왜 로컬인가
-----------
많이 쓰게 되면 "아까 그 글 점수가 몇이었지"를 계속 다시 찾게 된다. 그래서
기록을 남긴다. 다만 이건 **내 컴퓨터 안에만** 있다 — 서버로 나가지 않고,
`AIKILLER_NO_HISTORY=1`로 끄거나 CLI/웹에서 통째로 지울 수 있다.

배포용으로 전환할 때는 이 모듈을 꺼야 한다(남의 글을 저장하게 된다).
`enabled()`가 그 스위치다.
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass

HOME = os.path.expanduser("~")
DEFAULT_DIR = os.path.join(HOME, ".aikiller")
DB_NAME = "history.db"

MAX_ROWS = 500        # 이보다 오래된 건 자동으로 지운다
PREVIEW_CHARS = 90


def enabled() -> bool:
    return os.environ.get("AIKILLER_NO_HISTORY", "") not in ("1", "true", "yes")


def db_path() -> str:
    d = os.environ.get("AIKILLER_HOME", DEFAULT_DIR)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, DB_NAME)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL    NOT NULL,
    kind      TEXT    NOT NULL,          -- 'detect' | 'humanize'
    genre     TEXT    NOT NULL,
    level     TEXT,                      -- humanize 만
    score     REAL,
    after_score REAL,
    band      TEXT,
    n_chars   INTEGER NOT NULL,
    preview   TEXT    NOT NULL,
    text      TEXT    NOT NULL,
    result    TEXT                       -- humanize 결과문
);
CREATE INDEX IF NOT EXISTS runs_ts ON runs(ts DESC);
"""


@dataclass
class Row:
    id: int
    ts: float
    kind: str
    genre: str
    level: str | None
    score: float | None
    after_score: float | None
    band: str | None
    n_chars: int
    preview: str

    def to_dict(self) -> dict:
        return {
            "id": self.id, "ts": self.ts, "kind": self.kind,
            "genre": self.genre, "level": self.level, "score": self.score,
            "after_score": self.after_score, "band": self.band,
            "n_chars": self.n_chars, "preview": self.preview,
        }


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=5.0)
    conn.executescript(_SCHEMA)
    return conn


def preview_of(text: str) -> str:
    flat = " ".join(text.split())
    return flat[:PREVIEW_CHARS] + ("…" if len(flat) > PREVIEW_CHARS else "")


def add(
    kind: str,
    text: str,
    genre: str,
    *,
    level: str | None = None,
    score: float | None = None,
    after_score: float | None = None,
    band: str | None = None,
    result: str | None = None,
) -> int | None:
    """기록 한 건 추가. 비활성이거나 실패하면 None (호출자는 무시해도 된다)."""
    if not enabled() or not text.strip():
        return None
    try:
        with _connect() as conn:
            # 직전 기록과 완전히 같으면 중복 저장하지 않는다 — 자동 탐지가
            # 켜져 있으면 같은 글이 여러 번 들어온다.
            last = conn.execute(
                "SELECT text, kind FROM runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if last and last[0] == text and last[1] == kind:
                return None
            cur = conn.execute(
                "INSERT INTO runs (ts,kind,genre,level,score,after_score,band,"
                "n_chars,preview,text,result) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (time.time(), kind, genre, level, score, after_score, band,
                 len(text.strip()), preview_of(text), text, result),
            )
            conn.execute(
                "DELETE FROM runs WHERE id NOT IN "
                "(SELECT id FROM runs ORDER BY id DESC LIMIT ?)", (MAX_ROWS,)
            )
            return cur.lastrowid
    except sqlite3.Error:
        return None


def recent(limit: int = 60) -> list[Row]:
    if not enabled():
        return []
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT id,ts,kind,genre,level,score,after_score,band,n_chars,"
                "preview FROM runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [Row(*r) for r in rows]
    except sqlite3.Error:
        return []


def get(run_id: int) -> dict | None:
    if not enabled():
        return None
    try:
        with _connect() as conn:
            r = conn.execute(
                "SELECT id,ts,kind,genre,level,score,after_score,band,n_chars,"
                "preview,text,result FROM runs WHERE id=?", (run_id,)
            ).fetchone()
    except sqlite3.Error:
        return None
    if not r:
        return None
    d = Row(*r[:10]).to_dict()
    d["text"] = r[10]
    d["result"] = r[11]
    return d


def delete(run_id: int) -> bool:
    try:
        with _connect() as conn:
            return conn.execute("DELETE FROM runs WHERE id=?", (run_id,)).rowcount > 0
    except sqlite3.Error:
        return False


def clear() -> int:
    try:
        with _connect() as conn:
            n = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            conn.execute("DELETE FROM runs")
            return n
    except sqlite3.Error:
        return 0


def stats() -> dict:
    if not enabled():
        return {"enabled": False, "count": 0, "path": db_path()}
    try:
        with _connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            avg = conn.execute(
                "SELECT AVG(score) FROM runs WHERE kind='detect' AND score IS NOT NULL"
            ).fetchone()[0]
    except sqlite3.Error:
        return {"enabled": True, "count": 0, "path": db_path()}
    return {
        "enabled": True, "count": count, "path": db_path(),
        "avg_score": round(avg, 1) if avg is not None else None,
    }
