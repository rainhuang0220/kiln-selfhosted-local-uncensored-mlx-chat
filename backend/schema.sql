-- Kiln chat.db v1
-- Timestamps: INTEGER Unix milliseconds UTC
-- IDs: TEXT UUID

BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version     INTEGER PRIMARY KEY,
  name        TEXT    NOT NULL UNIQUE,
  applied_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
  id                      TEXT PRIMARY KEY,
  title                   TEXT,
  title_source            TEXT NOT NULL DEFAULT 'auto'
                          CHECK (title_source IN ('auto', 'user')),
  model                   TEXT NOT NULL,
  system_prompt           TEXT,
  settings_json           TEXT NOT NULL DEFAULT '{}',
  message_count           INTEGER NOT NULL DEFAULT 0,
  prompt_tokens_total     INTEGER NOT NULL DEFAULT 0,
  completion_tokens_total INTEGER NOT NULL DEFAULT 0,
  total_tokens            INTEGER NOT NULL DEFAULT 0,
  last_message_preview    TEXT,
  pinned                  INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0, 1)),
  deleted_at              INTEGER,
  created_at              INTEGER NOT NULL,
  updated_at              INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  id                TEXT PRIMARY KEY,
  conversation_id   TEXT NOT NULL
                    REFERENCES conversations(id) ON DELETE CASCADE,
  seq               INTEGER NOT NULL,
  role              TEXT NOT NULL
                    CHECK (role IN ('system', 'user', 'assistant', 'tool')),
  content           TEXT NOT NULL DEFAULT '',
  reasoning         TEXT,
  status            TEXT NOT NULL DEFAULT 'complete'
                    CHECK (status IN ('pending', 'streaming', 'complete', 'error', 'cancelled')),
  prompt_tokens     INTEGER,
  completion_tokens INTEGER,
  cached_tokens     INTEGER,
  total_tokens      INTEGER,
  finish_reason     TEXT,
  error             TEXT,
  tool_call_id      TEXT,
  tool_name         TEXT,
  tool_calls_json   TEXT,
  metadata_json     TEXT NOT NULL DEFAULT '{}',
  created_at        INTEGER NOT NULL,
  updated_at        INTEGER NOT NULL,
  UNIQUE (conversation_id, seq)
);

CREATE TABLE IF NOT EXISTS generation_runs (
  id                   TEXT PRIMARY KEY,
  conversation_id      TEXT NOT NULL
                       REFERENCES conversations(id) ON DELETE CASCADE,
  message_id           TEXT NOT NULL
                       REFERENCES messages(id) ON DELETE CASCADE,
  snapshot_id          TEXT,
  model                TEXT NOT NULL,
  params_json          TEXT NOT NULL DEFAULT '{}',
  prompt_tokens        INTEGER,
  completion_tokens    INTEGER,
  cached_tokens        INTEGER,
  total_tokens         INTEGER,
  finish_reason        TEXT,
  latency_ms           INTEGER,
  error                TEXT,
  created_at           INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS context_snapshots (
  id                      TEXT PRIMARY KEY,
  conversation_id         TEXT NOT NULL
                          REFERENCES conversations(id) ON DELETE CASCADE,
  generation_run_id       TEXT,
  payload_json            TEXT NOT NULL,
  effective_system_prompt TEXT,
  tokens_json             TEXT NOT NULL DEFAULT '{}',
  truncated               INTEGER NOT NULL DEFAULT 0 CHECK (truncated IN (0, 1)),
  dropped_message_ids_json TEXT NOT NULL DEFAULT '[]',
  memory_ids_json         TEXT NOT NULL DEFAULT '[]',
  created_at              INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS memories (
  id                      TEXT PRIMARY KEY,
  memory_type             TEXT NOT NULL
                          CHECK (memory_type IN (
                            'fact', 'preference', 'user_profile',
                            'episode', 'tool_result'
                          )),
  key                     TEXT,
  content                 TEXT NOT NULL,
  structured_json         TEXT,
  importance              REAL NOT NULL DEFAULT 0.5
                          CHECK (importance >= 0.0 AND importance <= 1.0),
  confidence              REAL NOT NULL DEFAULT 0.5
                          CHECK (confidence >= 0.0 AND confidence <= 1.0),
  status                  TEXT NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active', 'superseded', 'deleted')),
  superseded_by_id        TEXT REFERENCES memories(id) ON DELETE SET NULL,
  source_conversation_id  TEXT REFERENCES conversations(id) ON DELETE SET NULL,
  source_message_id       TEXT REFERENCES messages(id) ON DELETE SET NULL,
  valid_from              INTEGER,
  valid_until             INTEGER,
  last_accessed_at        INTEGER,
  access_count            INTEGER NOT NULL DEFAULT 0,
  deleted_at              INTEGER,
  created_at              INTEGER NOT NULL,
  updated_at              INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_evidence (
  memory_id         TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  message_id        TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  conversation_id   TEXT REFERENCES conversations(id) ON DELETE SET NULL,
  excerpt           TEXT,
  created_at        INTEGER NOT NULL,
  PRIMARY KEY (memory_id, message_id)
);

CREATE TABLE IF NOT EXISTS embeddings (
  id           TEXT PRIMARY KEY,
  source_type  TEXT NOT NULL
               CHECK (source_type IN ('message', 'memory', 'snapshot')),
  source_id    TEXT NOT NULL,
  model        TEXT NOT NULL,
  dim          INTEGER NOT NULL,
  dtype        TEXT NOT NULL DEFAULT 'f32'
               CHECK (dtype IN ('f32', 'f16')),
  vector       BLOB,
  path         TEXT,
  created_at   INTEGER NOT NULL,
  UNIQUE (source_type, source_id, model),
  CHECK ((vector IS NOT NULL AND path IS NULL) OR
         (vector IS NULL     AND path IS NOT NULL) OR
         (vector IS NULL     AND path IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_conversations_list
  ON conversations(pinned DESC, updated_at DESC)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_messages_conv_seq
  ON messages(conversation_id, seq);

CREATE INDEX IF NOT EXISTS idx_generation_runs_conv
  ON generation_runs(conversation_id, created_at);

CREATE INDEX IF NOT EXISTS idx_snapshots_conv
  ON context_snapshots(conversation_id, created_at);

CREATE INDEX IF NOT EXISTS idx_memories_active
  ON memories(memory_type, importance DESC, updated_at DESC)
  WHERE status = 'active' AND deleted_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_slot
  ON memories(memory_type, key)
  WHERE key IS NOT NULL AND status = 'active' AND deleted_at IS NULL;

INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
VALUES (1, '0001_init', CAST(strftime('%s','now') AS INTEGER) * 1000);

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

INSERT OR IGNORE INTO schema_migrations(version, name, applied_at)
VALUES (2, '0002_users_sessions', CAST(strftime('%s','now') AS INTEGER) * 1000);

COMMIT;
