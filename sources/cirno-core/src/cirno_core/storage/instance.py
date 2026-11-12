"""Small durable instance records, separate from project working files."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from cirno_core.config.paths import get_data_dir

KINDS = {"projects", "nodes", "node_jobs", "node_settings", "memories"}


class InstanceData:
    def __init__(self, state_dir: Path | None = None):
        self.state_dir = state_dir or get_data_dir()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.state_dir / "instance.sqlite3"
        self.path.touch(mode=0o600, exist_ok=True)
        self.path.chmod(0o600)
        with self.connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(kind,id))"
            )

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def list(self, kind: str) -> list[dict]:
        if kind not in KINDS:
            raise ValueError("Unknown record kind")
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT body FROM records WHERE kind=? ORDER BY rowid", (kind,)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def iterate(self, kind: str):
        if kind not in KINDS:
            raise ValueError("Unknown record kind")
        with self.connect() as connection:
            for row in connection.execute("SELECT body FROM records WHERE kind=? ORDER BY rowid", (kind,)):
                yield json.loads(row[0])

    def get(self, kind: str, record_id: str) -> dict:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT body FROM records WHERE kind=? AND id=?", (kind, record_id)
            ).fetchone()
        if row is None:
            raise KeyError(f"{kind} record not found: {record_id}")
        return json.loads(row[0])

    def save(self, kind: str, body: dict) -> dict:
        if kind not in KINDS:
            raise ValueError("Unknown record kind")
        record = {**body, "id": body.get("id") or uuid4().hex}
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO records(kind,id,body) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body",
                (kind, record["id"], json.dumps(record, ensure_ascii=False)),
            )
        return record

    def delete(self, kind: str, record_id: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM records WHERE kind=? AND id=?", (kind, record_id))

    def update(self, kind: str, record_id: str, change: Callable[[dict], dict], *, initial: dict | None = None) -> dict:
        """Mutate atomically; create only when the caller explicitly supplies initial data."""
        if kind not in KINDS:
            raise ValueError("Unknown record kind")
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT body FROM records WHERE kind=? AND id=?", (kind, record_id)).fetchone()
            if row is None and initial is None:
                raise KeyError(f"{kind} record not found: {record_id}")
            record = {**change(json.loads(row[0]) if row is not None else dict(initial)), "id": record_id}
            connection.execute("INSERT INTO records(kind,id,body) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body", (kind, record_id, json.dumps(record, ensure_ascii=False)))
        return record
