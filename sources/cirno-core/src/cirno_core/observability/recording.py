"""One tab's disposable SQLite recording and request snapshots."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from cirno_core.observability.request_snapshots import RequestSnapshots
from cirno_core.session.display_history import HistoryFact, HistoryKind

MAX_BYTES = 64 * 1024 * 1024
MAX_EVENTS = 50_000


class Recording:
    def __init__(self, identifier: str) -> None:
        self.id = identifier
        self.temp = tempfile.TemporaryDirectory(prefix="cirno-trace-")
        self.path = Path(self.temp.name) / "recording.sqlite3"
        self.requests = RequestSnapshots(self.path)
        self.epoch = uuid4().hex
        self.running = True
        self.reason: str | None = None
        self.created_ms = int(time.time() * 1000)
        self.count = 0
        with self.open() as db:
            db.execute("""CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT NOT NULL, kind TEXT NOT NULL,
                created_ms INTEGER NOT NULL, summary TEXT NOT NULL, status TEXT NOT NULL,
                turn_id TEXT, origin TEXT, bytes INTEGER NOT NULL, body TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX source_events ON events(session,id DESC)")
            db.execute("CREATE INDEX type_events ON events(kind,id DESC)")

    @contextmanager
    def open(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path)
        try:
            with db:
                yield db
        finally:
            db.close()

    def info(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "epoch": self.epoch,
            "running": self.running,
            "reason": self.reason,
            "count": self.count,
            "created_ms": self.created_ms,
        }

    def append(
        self,
        session: str,
        kind: str,
        summary: str,
        status: str,
        body: dict[str, Any],
        *,
        turn_id: str | None = None,
        origin: str | None = None,
        created_ms: int | None = None,
    ) -> int:
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        size = len(encoded.encode())
        with self.open() as db:
            cursor = db.execute(
                "INSERT INTO events(session,kind,created_ms,summary,status,turn_id,origin,bytes,body) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    session,
                    kind,
                    created_ms or int(time.time() * 1000),
                    summary[:240],
                    status,
                    turn_id,
                    origin,
                    size,
                    encoded,
                ),
            )
            self.count += 1
        self.check_capacity()
        return cast(int, cursor.lastrowid)

    def check_capacity(self) -> None:
        if self.count >= MAX_EVENTS or self.path.stat().st_size >= MAX_BYTES:
            self.running, self.reason = False, "capacity"

    def fact(self, session: str, fact: HistoryFact) -> None:
        content = fact.content
        origin = content.get("input_origin") or {}
        tools = content.get("tool_events") or []
        summary = str(
            (tools[0].get("name") if tools else None)
            or content.get("text")
            or content.get("reason")
            or fact.kind
        )
        if origin.get("label"):
            summary = f"{origin['label']}: {summary}"
        status = str(
            (tools[0].get("phase") if tools else None)
            or content.get("outcome")
            or content.get("phase")
            or fact.phase
            or ""
        )
        kind = "system_input" if fact.kind == HistoryKind.INPUT and origin else fact.kind.value
        self.append(
            session,
            kind,
            summary,
            status,
            json.loads(fact.encode()),
            turn_id=fact.turn_id,
            origin=origin.get("kind"),
            created_ms=fact.created_at_ms,
        )

    def page(
        self,
        *,
        before: int | None = None,
        kind: list[str] | None = None,
        session: str | None = None,
    ) -> dict[str, Any]:
        conditions, params = [], []
        if before is not None:
            if type(before) is not int or before < 1:
                raise ValueError("Invalid recording cursor")
            conditions.append("id<?")
            params.append(before)
        if kind:
            conditions.append("kind IN (" + ",".join("?" for _ in kind) + ")")
            params.extend(kind)
        if session:
            conditions.append("session=?")
            params.append(session)
        clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        with self.open() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT id,session AS session_key,kind,created_ms,summary,status,turn_id,origin,bytes FROM events"
                + clause
                + " ORDER BY id DESC LIMIT 101",
                params,
            ).fetchall()
            sources = [
                row[0] for row in db.execute("SELECT DISTINCT session FROM events ORDER BY session")
            ]
        return {
            **self.info(),
            "events": [dict(row) for row in rows[:100]],
            "before": rows[99]["id"] if len(rows) > 100 else None,
            "sources": sources,
        }

    def detail(self, identifier: int, offset: int = 0) -> dict[str, Any]:
        with self.open() as db:
            row = db.execute("SELECT kind,body FROM events WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise KeyError("Recorded event was cleared")
        body = json.loads(row[1])
        if row[0] == "request":
            return self.requests.detail(self.id, body["request_id"], offset=offset)
        return {"event": body}

    def close(self) -> None:
        self.temp.cleanup()
