from app.db import _has_column, init_db, migrate


def test_migrate_is_idempotent_and_keeps_memory_owner_columns(tmp_path):
    db = tmp_path / "chat.db"
    conn = init_db(str(db))
    migrate(conn)
    migrate(conn)
    assert _has_column(conn, "memories", "user_id")
    assert _has_column(conn, "conversations", "user_id")
    assert _has_column(conn, "users", "role")
    assert _has_column(conn, "sessions", "remember")
    assert _has_column(conn, "sessions", "idle_ms")
    assert _has_column(conn, "memories", "source_conversation_id")
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    assert "idx_memories_slot_owner" in names
    assert "idx_memories_slot" not in names
    row = conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()
    assert row["n"] == 0
