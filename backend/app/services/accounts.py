from __future__ import annotations

import hashlib
import re
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.db import get_conn

COOKIE = "kiln_session"
_USER_RE = re.compile(r"^[a-z0-9_]{3,32}$")
_HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
_DUMMY_HASH = _HASHER.hash("kiln-dummy-not-a-user")
LOCK_AFTER = 8
LOCK_MS = 15 * 60 * 1000
SESSION_DAYS_DEFAULT = 14


def _now() -> int:
    return int(time.time() * 1000)


def _id() -> str:
    return str(uuid.uuid4())


def normalize_username(raw: str) -> str:
    return (raw or "").strip().lower()


def validate_username(raw: str) -> str:
    name = normalize_username(raw)
    if not _USER_RE.match(name):
        raise ValueError("username must be 3-32 chars: a-z, 0-9, underscore")
    return name


def validate_password(raw: str) -> str:
    if raw is None or not isinstance(raw, str):
        raise ValueError("password required")
    if len(raw) < 10:
        raise ValueError("password must be at least 10 characters")
    if len(raw) > 128:
        raise ValueError("password too long")
    return raw


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def verify_password(password: str, stored: str) -> bool:
    try:
        return _HASHER.verify(stored, password)
    except (VerifyMismatchError, Exception):
        return False


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


@dataclass
class User:
    id: str
    username: str


def user_count(conn: sqlite3.Connection | None = None) -> int:
    db = conn or get_conn()
    return int(db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])


def get_user(user_id: str) -> User | None:
    row = get_conn().execute(
        "SELECT id, username FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    return User(id=row["id"], username=row["username"])


def create_user(username: str, password: str, conn: sqlite3.Connection | None = None) -> User:
    name = validate_username(username)
    pw = validate_password(password)
    db = conn or get_conn()
    uid = _id()
    ts = _now()
    db.execute(
        """
        INSERT INTO users (id, username, password_hash, failed_logins, created_at, updated_at)
        VALUES (?, ?, ?, 0, ?, ?)
        """,
        (uid, name, hash_password(pw), ts, ts),
    )
    db.commit()
    return User(id=uid, username=name)


def authenticate(username: str, password: str) -> User | None:
    name = normalize_username(username)
    db = get_conn()
    row = db.execute(
        "SELECT id, username, password_hash, failed_logins, locked_until FROM users WHERE username=?",
        (name,),
    ).fetchone()
    stored = row["password_hash"] if row is not None else _DUMMY_HASH
    ok = verify_password(password or "", stored)
    ts = _now()
    locked = bool(row and row["locked_until"] and int(row["locked_until"]) > ts)
    if locked:
        return None
    if row is None or not ok:
        if row is not None:
            fails = int(row["failed_logins"] or 0) + 1
            locked = ts + LOCK_MS if fails >= LOCK_AFTER else row["locked_until"]
            db.execute(
                "UPDATE users SET failed_logins=?, locked_until=?, updated_at=? WHERE id=?",
                (fails, locked, ts, row["id"]),
            )
            db.commit()
        return None
    db.execute(
        "UPDATE users SET failed_logins=0, locked_until=NULL, updated_at=? WHERE id=?",
        (ts, row["id"]),
    )
    db.commit()
    return User(id=row["id"], username=row["username"])


def create_session(user_id: str, days: int = SESSION_DAYS_DEFAULT) -> str:
    token = new_session_token()
    ts = _now()
    expires = ts + max(1, days) * 24 * 3600 * 1000
    get_conn().execute(
        """
        INSERT INTO sessions (id, user_id, token_hash, created_at, expires_at, last_seen_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (_id(), user_id, hash_session_token(token), ts, expires, ts),
    )
    get_conn().commit()
    return token


def resolve_session(token: str | None) -> User | None:
    if not token:
        return None
    ts = _now()
    row = get_conn().execute(
        """
        SELECT s.id AS sid, s.expires_at, u.id AS uid, u.username
        FROM sessions s JOIN users u ON u.id = s.user_id
        WHERE s.token_hash=?
        """,
        (hash_session_token(token),),
    ).fetchone()
    if row is None or int(row["expires_at"]) <= ts:
        return None
    get_conn().execute(
        "UPDATE sessions SET last_seen_at=? WHERE id=?",
        (ts, row["sid"]),
    )
    get_conn().commit()
    return User(id=row["uid"], username=row["username"])


def revoke_session(token: str | None) -> None:
    if not token:
        return
    get_conn().execute(
        "DELETE FROM sessions WHERE token_hash=?",
        (hash_session_token(token),),
    )
    get_conn().commit()


def purge_expired_sessions() -> None:
    get_conn().execute("DELETE FROM sessions WHERE expires_at<=?", (_now(),))
    get_conn().commit()


def ensure_bootstrap(username: str, password: str) -> User | None:
    db = get_conn()
    if user_count(db) > 0:
        return None
    user = create_user(username, password, db)
    db.execute(
        "UPDATE conversations SET user_id=? WHERE user_id IS NULL",
        (user.id,),
    )
    db.commit()
    return user
