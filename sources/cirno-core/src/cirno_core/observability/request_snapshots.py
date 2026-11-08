"""Content-addressed API snapshots owned by one disposable recording."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from uuid import uuid4


class RequestSnapshots:
    def __init__(self, path: Path):
        self.path = path

    def _open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(mode=0o600, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("CREATE TABLE IF NOT EXISTS blobs (digest TEXT PRIMARY KEY, body TEXT NOT NULL)")
        db.execute(
            "CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, owner TEXT NOT NULL, inputs TEXT NOT NULL, tools TEXT NOT NULL, response TEXT, status TEXT NOT NULL)"
        )
        return db

    @staticmethod
    def _blob(db, value):
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
        digest = hashlib.sha256(body.encode()).hexdigest()
        db.execute("INSERT OR IGNORE INTO blobs VALUES (?,?)", (digest, body))
        return digest

    def start(self, owner: str, messages: list, tools: list) -> str:
        db = self._open()
        try:
            identifier = uuid4().hex
            with db:
                inputs = [self._blob(db, message) for message in messages]
                tool_id = self._blob(db, tools)
                db.execute(
                    "INSERT INTO requests VALUES (?,?,?,?,NULL,'running')",
                    (identifier, owner, json.dumps(inputs), tool_id),
                )
            return identifier
        finally:
            db.close()

    def finish(self, identifier: str, response: dict, status: str):
        db = self._open()
        try:
            with db:
                result = self._blob(db, response)
                db.execute(
                    "UPDATE requests SET response=?,status=? WHERE id=?",
                    (result, status, identifier),
                )
        finally:
            db.close()

    def detail(self, owner: str, identifier: str, *, offset: int = 0, limit: int = 10) -> dict:
        db = self._open()
        try:
            row = db.execute(
                "SELECT inputs,tools,response,status FROM requests WHERE id=? AND owner=?",
                (identifier, owner),
            ).fetchone()
            if row is None:
                raise KeyError("Request not found")

            def body(digest):
                return (
                    json.loads(
                        db.execute("SELECT body FROM blobs WHERE digest=?", (digest,)).fetchone()[0]
                    )
                    if digest
                    else None
                )

            inputs = json.loads(row[0])
            offset, limit = max(0, int(offset)), max(1, min(20, int(limit)))
            return {
                "messages": [body(digest) for digest in inputs[offset : offset + limit]],
                "offset": offset,
                "total": len(inputs),
                "tools": body(row[1]) if offset == 0 else None,
                "response": body(row[2]) if offset == 0 else None,
                "status": row[3],
            }
        finally:
            db.close()
