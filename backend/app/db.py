from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path

from app.config import settings

_SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"
_local = threading.local()


def _connect(path: str | None = None) -> sqlite3.Connection:
    db_path = Path(path or settings.sqlite_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    try:
        os.chmod(db_path, 0o600)
    except OSError:
        pass
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _connect()
        _local.conn = conn
    return conn


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
          id             TEXT PRIMARY KEY,
          username       TEXT NOT NULL UNIQUE,
          password_hash  TEXT NOT NULL,
          failed_logins  INTEGER NOT NULL DEFAULT 0,
          locked_until   INTEGER,
          created_at     INTEGER NOT NULL,
          updated_at     INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
          id            TEXT PRIMARY KEY,
          user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          token_hash    TEXT NOT NULL UNIQUE,
          created_at    INTEGER NOT NULL,
          expires_at    INTEGER NOT NULL,
          last_seen_at  INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, expires_at);
        """
    )
    if not _has_column(conn, "conversations", "user_id"):
        conn.execute("ALTER TABLE conversations ADD COLUMN user_id TEXT")
    if not _has_column(conn, "memories", "user_id"):
        conn.execute("ALTER TABLE memories ADD COLUMN user_id TEXT")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_conversations_user
          ON conversations(user_id, pinned DESC, updated_at DESC)
          WHERE deleted_at IS NULL
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
        VALUES (2, '0002_users_sessions', CAST(strftime('%s','now') AS INTEGER) * 1000)
        """
    )
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS media_jobs (
          id TEXT PRIMARY KEY, user_id TEXT, kind TEXT NOT NULL CHECK (kind IN ('image', 'video')),
          backend TEXT NOT NULL, status TEXT NOT NULL, prompt TEXT NOT NULL,
          params_json TEXT NOT NULL DEFAULT '{}', output_path TEXT, error TEXT,
          metrics_json TEXT NOT NULL DEFAULT '{}', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
          started_at INTEGER, finished_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_media_jobs_user ON media_jobs(user_id, created_at DESC);
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
        VALUES (3, '0003_media_jobs', CAST(strftime('%s','now') AS INTEGER) * 1000)
        """
    )


def init_db(path: str | None = None) -> sqlite3.Connection:
    conn = _connect(path)
    sql = _SCHEMA.read_text(encoding="utf-8")
    conn.executescript(sql)
    migrate(conn)
    conn.execute(
        """
        UPDATE messages
        SET status='cancelled', error='orphan', updated_at=?
        WHERE status IN ('streaming', 'pending')
        """,
        (int(time.time() * 1000),),
    )
    conn.commit()
    _local.conn = conn
    return conn


def close_thread_conn() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None
