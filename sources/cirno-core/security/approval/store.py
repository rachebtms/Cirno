"""One-use operation decisions, isolated from transcripts and Agent memory."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from cirno_core.config.paths import get_data_dir


class ApprovalStore:
    def __init__(self, path: Path | None = None):
        self.path = path or get_data_dir() / "security" / "approvals.sqlite3"

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.touch(mode=0o600, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("""CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, session_key TEXT NOT NULL,
                    generation TEXT NOT NULL, turn_id TEXT NOT NULL, operation TEXT NOT NULL,
                    status TEXT NOT NULL, reason TEXT NOT NULL, created_at REAL NOT NULL,
                    decided_at REAL, wake_pending INTEGER NOT NULL DEFAULT 0
                )""")
                db.execute("CREATE INDEX IF NOT EXISTS approval_lookup ON approvals(fingerprint,created_at)")
                yield db
        finally:
            db.close()

    def latest(self, fingerprint):
        with self.connect() as db:
            row = db.execute("SELECT * FROM approvals WHERE fingerprint=? ORDER BY created_at DESC LIMIT 1", (fingerprint,)).fetchone()
        return dict(row) if row else None

    def record(self, fingerprint, request, operation, status, reason):
        item = dict(id=uuid4().hex, fingerprint=fingerprint, session_key=request.session_key,
                    generation=request.session_generation, turn_id=request.turn_id or "",
                    operation=json.dumps(operation, ensure_ascii=False), status=status,
                    reason=reason[:2000], created_at=time.time())
        with self.connect() as db:
            db.execute("INSERT INTO approvals (id,fingerprint,session_key,generation,turn_id,operation,status,reason,created_at) VALUES(:id,:fingerprint,:session_key,:generation,:turn_id,:operation,:status,:reason,:created_at)", item)
        return item

    def decide(self, identifier, *, approved, generation):
        with self.connect() as db:
            row = db.execute("SELECT * FROM approvals WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise ValueError("Approval request does not exist")
            status = "approved" if approved else "denied"
            if row["status"] == status and row["wake_pending"]:
                return dict(row)  # Retry settlement after an observable delivery error.
            if row["status"] != "pending":
                raise ValueError("This approval request has already been resolved")
            if generation != row["generation"]:
                raise ValueError("The conversation was replaced; this approval is no longer valid")
            decided_at = time.time()
            changed = db.execute("UPDATE approvals SET status=?,decided_at=?,wake_pending=1 WHERE id=? AND status='pending'", (status, decided_at, identifier)).rowcount
            if not changed:
                raise ValueError("This approval request has already been resolved")
            return {**dict(row), "status": status, "decided_at": decided_at, "wake_pending": 1}

    def get(self, identifier):
        with self.connect() as db:
            row = db.execute("SELECT * FROM approvals WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ValueError("Approval request does not exist")
        return dict(row)

    def pending_wakes(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM approvals WHERE wake_pending=1 ORDER BY decided_at LIMIT 100")]

    def wake_queued(self, identifier, *, stale=False):
        with self.connect() as db:
            if stale:
                db.execute("UPDATE approvals SET wake_pending=0,status='stale' WHERE id=?", (identifier,))
            else:
                db.execute("UPDATE approvals SET wake_pending=0 WHERE id=?", (identifier,))

    def consume(self, identifier):
        with self.connect() as db:
            return db.execute("UPDATE approvals SET status='used' WHERE id=? AND status='approved'", (identifier,)).rowcount == 1
