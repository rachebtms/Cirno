-- Conversation schema from the published v0.1.6 tag.
CREATE TABLE IF NOT EXISTS sessions (
            key TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            metadata TEXT NOT NULL, provider_state TEXT, last_archived INTEGER NOT NULL,
            revision INTEGER NOT NULL, generation TEXT NOT NULL,
            title TEXT NOT NULL, preview TEXT NOT NULL, visible_updated_at TEXT
        );
CREATE TABLE IF NOT EXISTS messages (
            session_key TEXT NOT NULL REFERENCES sessions(key) ON DELETE CASCADE,
            position INTEGER NOT NULL, record TEXT NOT NULL,
            PRIMARY KEY (session_key, position)
        );
CREATE TABLE IF NOT EXISTS checkpoints (
            session_key TEXT PRIMARY KEY REFERENCES sessions(key) ON DELETE CASCADE,
            record TEXT NOT NULL
        );
CREATE TABLE IF NOT EXISTS pending_inputs (
            session_key TEXT NOT NULL REFERENCES sessions(key) ON DELETE CASCADE,
            kind TEXT NOT NULL, position INTEGER NOT NULL, record TEXT NOT NULL,
            PRIMARY KEY (session_key, kind, position)
        );
CREATE INDEX IF NOT EXISTS sessions_updated ON sessions(updated_at DESC);
CREATE TABLE IF NOT EXISTS history_heads (
            session_key TEXT PRIMARY KEY REFERENCES sessions(key) ON DELETE CASCADE,
            revision INTEGER NOT NULL DEFAULT 0,
            updated_at_ms INTEGER NOT NULL DEFAULT 0,
            preview TEXT NOT NULL DEFAULT '', user_preview TEXT NOT NULL DEFAULT ''
        );
CREATE TABLE IF NOT EXISTS history_turns (
            session_key TEXT NOT NULL REFERENCES sessions(key) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL, record_count INTEGER NOT NULL,
            byte_count INTEGER NOT NULL, user_count INTEGER NOT NULL,
            completed INTEGER NOT NULL,
            PRIMARY KEY (session_key, ordinal)
        );
CREATE TABLE IF NOT EXISTS history_entries (
            session_key TEXT NOT NULL, turn_ordinal INTEGER NOT NULL,
            position INTEGER NOT NULL, kind TEXT NOT NULL, record TEXT NOT NULL,
            PRIMARY KEY (session_key, turn_ordinal, position),
            FOREIGN KEY (session_key, turn_ordinal)
                REFERENCES history_turns(session_key, ordinal) ON DELETE CASCADE
        );
CREATE TABLE IF NOT EXISTS inbox_receipts (
        session_key TEXT NOT NULL REFERENCES sessions(key) ON DELETE CASCADE,
        generation TEXT NOT NULL, input_id TEXT NOT NULL, journal_id TEXT NOT NULL, digest TEXT NOT NULL,
        read INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (session_key, generation, input_id)
    );
CREATE INDEX IF NOT EXISTS inbox_journal ON inbox_receipts(session_key,generation,journal_id);
PRAGMA user_version=3;
