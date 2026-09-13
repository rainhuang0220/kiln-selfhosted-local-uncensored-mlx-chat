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
from app.security import HOST_SESSION_COOKIE, SESSION_COOKIE

COOKIE = SESSION_COOKIE
_USER_RE = re.compile(r"^[a-z0-9_]{3,32}$")
_HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
_DUMMY_HASH = _HASHER.hash("kiln-dummy-not-a-user")
LOCK_AFTER = 8
LOCK_MS = 2 * 60 * 1000
SESSION_DAYS_DEFAULT = 7
API_TOKEN_PREFIX = "kiln_live_"


def cookie_name(*, secure: bool) -> str:
    return HOST_SESSION_COOKIE if secure else SESSION_COOKIE


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
    role: str = "user"


def user_count(conn: sqlite3.Connection | None = None) -> int:
    db = conn or get_conn()
    return int(db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])


def get_user(user_id: str) -> User | None:
    row = get_conn().execute(
        "SELECT id, username, role FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    return User(id=row["id"], username=row["username"], role=row["role"] or "user")


def create_user(username: str, password: str, conn: sqlite3.Connection | None = None) -> User:
    name = validate_username(username)
    pw = validate_password(password)
    db = conn or get_conn()
    uid = _id()
    ts = _now()
    role = "owner" if user_count(db) == 0 else "user"
    db.execute(
        """
        INSERT INTO users (id, username, password_hash, failed_logins, created_at, updated_at, role)
        VALUES (?, ?, ?, 0, ?, ?, ?)
        """,
        (uid, name, hash_password(pw), ts, ts, role),
    )
    db.commit()
    return User(id=uid, username=name, role=role)


def authenticate(username: str, password: str) -> User | None:
    name = normalize_username(username)
    db = get_conn()
    row = db.execute(
        "SELECT id, username, password_hash, failed_logins, locked_until, role FROM users WHERE username=?",
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
            locked_until = ts + LOCK_MS if fails >= LOCK_AFTER else row["locked_until"]
            if fails > LOCK_AFTER:
                locked_until = row["locked_until"]
                fails = LOCK_AFTER
            db.execute(
                "UPDATE users SET failed_logins=?, locked_until=?, updated_at=? WHERE id=?",
                (fails, locked_until, ts, row["id"]),
            )
            db.commit()
        return None
    db.execute(
        "UPDATE users SET failed_logins=0, locked_until=NULL, updated_at=? WHERE id=?",
        (ts, row["id"]),
    )
    db.commit()
    return User(id=row["id"], username=row["username"], role=row["role"] or "user")


def change_password(username: str, current: str, new: str) -> User:
    user = authenticate(username, current)
    if user is None:
        raise ValueError("invalid username or password")
    pw = validate_password(new)
    ts = _now()
    get_conn().execute(
        "UPDATE users SET password_hash=?, failed_logins=0, locked_until=NULL, updated_at=? WHERE id=?",
        (hash_password(pw), ts, user.id),
    )
    get_conn().commit()
    revoke_all_sessions(user.id)
    return user


def create_session(
    user_id: str,
    days: int = SESSION_DAYS_DEFAULT,
    *,
    remember: bool = False,
    idle_minutes: int = 45,
    absolute_hours: int = 12,
    remember_days: int = 7,
) -> str:
    token = new_session_token()
    ts = _now()
    if remember:
        expires = ts + max(1, remember_days) * 24 * 3600 * 1000
    else:
        expires = ts + max(1, absolute_hours) * 3600 * 1000
        if days and days * 24 < absolute_hours:
            expires = ts + max(1, days) * 24 * 3600 * 1000
    get_conn().execute(
        """
        INSERT INTO sessions (
          id, user_id, token_hash, created_at, expires_at, last_seen_at, remember, idle_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _id(),
            user_id,
            hash_session_token(token),
            ts,
            expires,
            ts,
            1 if remember else 0,
            max(1, idle_minutes) * 60 * 1000,
        ),
    )
    get_conn().commit()
    return token


def resolve_session(token: str | None) -> User | None:
    if not token:
        return None
    ts = _now()
    row = get_conn().execute(
        """
        SELECT s.id AS sid, s.expires_at, s.last_seen_at, s.remember, s.idle_ms,
               u.id AS uid, u.username, u.role
        FROM sessions s JOIN users u ON u.id = s.user_id
        WHERE s.token_hash=?
        """,
        (hash_session_token(token),),
    ).fetchone()
    if row is None or int(row["expires_at"]) <= ts:
        return None
    remember = bool(row["remember"])
    idle_ms = int(row["idle_ms"] or 0)
    if not remember and idle_ms and int(row["last_seen_at"]) + idle_ms <= ts:
        get_conn().execute("DELETE FROM sessions WHERE id=?", (row["sid"],))
        get_conn().commit()
        return None
    get_conn().execute(
        "UPDATE sessions SET last_seen_at=? WHERE id=?",
        (ts, row["sid"]),
    )
    get_conn().commit()
    return User(id=row["uid"], username=row["username"], role=row["role"] or "user")


def session_row_for_token(token: str | None) -> sqlite3.Row | None:
    if not token:
        return None
    return get_conn().execute(
        """
        SELECT id, user_id, created_at, expires_at, last_seen_at, remember
        FROM sessions WHERE token_hash=?
        """,
        (hash_session_token(token),),
    ).fetchone()


def list_sessions(user_id: str, current_token: str | None = None) -> list[dict]:
    current_hash = hash_session_token(current_token) if current_token else ""
    rows = get_conn().execute(
        """
        SELECT id, created_at, expires_at, last_seen_at, remember, token_hash
        FROM sessions WHERE user_id=? ORDER BY last_seen_at DESC
        """,
        (user_id,),
    ).fetchall()
    out = []
    for row in rows:
        out.append(
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
                "last_seen_at": row["last_seen_at"],
                "remember": bool(row["remember"]),
                "current": bool(current_hash and row["token_hash"] == current_hash),
            }
        )
    return out


def revoke_session(token: str | None) -> None:
    if not token:
        return
    get_conn().execute(
        "DELETE FROM sessions WHERE token_hash=?",
        (hash_session_token(token),),
    )
    get_conn().commit()


def revoke_session_id(user_id: str, session_id: str, current_token: str | None = None) -> bool:
    row = get_conn().execute(
        "SELECT id, token_hash FROM sessions WHERE id=? AND user_id=?",
        (session_id, user_id),
    ).fetchone()
    if row is None:
        return False
    get_conn().execute("DELETE FROM sessions WHERE id=?", (session_id,))
    get_conn().commit()
    return True


def revoke_other_sessions(user_id: str, current_token: str | None) -> int:
    if not current_token:
        cur = get_conn().execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        get_conn().commit()
        return cur.rowcount
    cur = get_conn().execute(
        "DELETE FROM sessions WHERE user_id=? AND token_hash!=?",
        (user_id, hash_session_token(current_token)),
    )
    get_conn().commit()
    return cur.rowcount


def revoke_all_sessions(user_id: str) -> int:
    cur = get_conn().execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    get_conn().commit()
    return cur.rowcount


def purge_expired_sessions() -> None:
    get_conn().execute("DELETE FROM sessions WHERE expires_at<=?", (_now(),))
    get_conn().commit()


def create_api_token(user_id: str, name: str = "cli") -> str:
    raw = API_TOKEN_PREFIX + secrets.token_urlsafe(32)
    ts = _now()
    get_conn().execute(
        """
        INSERT INTO api_tokens (id, user_id, token_hash, name, created_at, last_used_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (_id(), user_id, hash_session_token(raw), name[:64], ts, ts),
    )
    get_conn().commit()
    return raw


def resolve_api_token(token: str | None) -> User | None:
    if not token or not token.startswith(API_TOKEN_PREFIX):
        return None
    ts = _now()
    row = get_conn().execute(
        """
        SELECT t.id AS tid, u.id AS uid, u.username, u.role
        FROM api_tokens t JOIN users u ON u.id = t.user_id
        WHERE t.token_hash=? AND t.revoked_at IS NULL
        """,
        (hash_session_token(token),),
    ).fetchone()
    if row is None:
        return None
    get_conn().execute(
        "UPDATE api_tokens SET last_used_at=? WHERE id=?",
        (ts, row["tid"]),
    )
    get_conn().commit()
    return User(id=row["uid"], username=row["username"], role=row["role"] or "user")


def assign_legacy_owner(user_id: str, conn: sqlite3.Connection | None = None) -> None:
    db = conn or get_conn()
    db.execute("UPDATE conversations SET user_id=? WHERE user_id IS NULL", (user_id,))
    db.execute("UPDATE memories SET user_id=? WHERE user_id IS NULL", (user_id,))
    db.execute("UPDATE media_jobs SET user_id=? WHERE user_id IS NULL", (user_id,))
    db.commit()


def ensure_bootstrap(username: str, password: str) -> User | None:
    db = get_conn()
    if user_count(db) > 0:
        return None
    user = create_user(username, password, db)
    assign_legacy_owner(user.id, db)
    return user
