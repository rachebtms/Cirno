"""Memory databases separated by lifetime and rebuildability.

The catalog and Dream state are authoritative; search and vectors are caches.
Attached rollback-journal databases keep catalog/index/queue writes atomic.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock


@contextmanager
def connect(root: Path, *, vectors=False):
    db = sqlite3.connect(root / "catalog.sqlite3", timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("ATTACH DATABASE ? AS search", (str(root / "search.sqlite3"),))
        db.execute("ATTACH DATABASE ? AS dream", (str(root / "dream.sqlite3"),))
        if vectors:
            db.execute("ATTACH DATABASE ? AS vectors", (str(root / "vectors.sqlite3"),))
            (root / "vectors.sqlite3").chmod(0o600)
        for schema in ("main", "search", "dream", *(('vectors',) if vectors else ())):
            db.execute(f"PRAGMA {schema}.cache_size=-512")
            db.execute(f"PRAGMA {schema}.journal_mode=DELETE")
            db.execute(f"PRAGMA {schema}.synchronous=FULL")
        db.execute("PRAGMA temp_store=FILE")
        with db:
            yield db
    finally:
        db.close()


def initialize(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    with FileLock(str(root / ".storage.lock")):
        with connect(root) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY, body TEXT NOT NULL, path TEXT NOT NULL,
                    scope TEXT NOT NULL, project_id TEXT, session_key TEXT,
                    layer TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL,
                    content_hash TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS memory_scope ON memories(scope,project_id,session_key,status);
                CREATE TABLE IF NOT EXISTS revisions (
                    memory_id TEXT, revision INTEGER, body TEXT NOT NULL, path TEXT NOT NULL,
                    PRIMARY KEY(memory_id,revision)
                );
                CREATE TABLE IF NOT EXISTS links (
                    source TEXT,target TEXT,relation TEXT,evidence TEXT NOT NULL,
                    PRIMARY KEY(source,target,relation)
                );
                CREATE TABLE IF NOT EXISTS maintenance (key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS search.chunks (
                    id INTEGER PRIMARY KEY,memory_id TEXT NOT NULL,start_line INTEGER,end_line INTEGER,text TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS search.chunk_memory ON chunks(memory_id);
                CREATE VIRTUAL TABLE IF NOT EXISTS search.memory_fts USING fts5(title,tokens);
                CREATE TABLE IF NOT EXISTS dream.dream_queue (
                    memory_id TEXT PRIMARY KEY,revision INTEGER NOT NULL,queued_at REAL NOT NULL,
                    lease TEXT,lease_until REAL NOT NULL DEFAULT 0,claimed_revision INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,error TEXT,retry_after REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS dream.dream_state (key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS dream.dream_receipts (
                    token TEXT,memory_id TEXT,input_revision INTEGER,outcome TEXT NOT NULL,
                    targets TEXT NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL,
                    PRIMARY KEY(token,memory_id)
                );
            """)
        for name in ("catalog", "search", "dream"):
            (root / f"{name}.sqlite3").chmod(0o600)
