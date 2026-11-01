"""Durable notification history, separate from memory and session transcripts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager

from cirno.config.home import get_home_path
from cirno.session.keys import CIRNO_SESSION_KEY

CATEGORIES = ("operations", "conversations", "system")


class NotificationInbox:
    def __init__(self, home=None):
        self.path = (home or get_home_path()) / "notifications" / "inbox.sqlite3"

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("""CREATE TABLE IF NOT EXISTS notices (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL,
                    session_key TEXT, body TEXT NOT NULL, data TEXT NOT NULL,
                    created_at INTEGER NOT NULL, read_at INTEGER
                )""")
                db.execute("CREATE INDEX IF NOT EXISTS notice_category ON notices(category,seq)")
                yield db
        finally:
            db.close()

    def record(self, identifier, category, kind, *, status="info", session_key=None, body="", data=None):
        if category not in CATEGORIES:
            raise ValueError("Unknown notification category")
        now = int(time.time() * 1000)
        encoded = json.dumps(data or {}, ensure_ascii=False)
        with self.connect() as db:
            db.execute("""INSERT INTO notices(id,category,kind,status,session_key,body,data,created_at)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                status=excluded.status, body=excluded.body, data=excluded.data,
                read_at=CASE WHEN notices.status<>excluded.status THEN NULL ELSE notices.read_at END
                WHERE notices.status<>excluded.status OR notices.body<>excluded.body OR notices.data<>excluded.data""",
                (identifier, category, kind, status, session_key, body[:8000], encoded, now))
            # Pending actions remain until their original workflow resolves them.
            db.execute("""DELETE FROM notices WHERE status<>'pending' AND seq NOT IN
                (SELECT seq FROM notices ORDER BY seq DESC LIMIT 10000)""")

    def list(self, *, category=None, before=None, after=None, limit=50):
        if category is not None and category not in CATEGORIES:
            raise ValueError("Unknown notification category")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("Notification page size must be between 1 and 100")
        for value in (before, after):
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise ValueError("Notification cursor must be a non-negative integer")
        clauses, values = [], []
        for name, operator, value in (("category", "=", category), ("seq", "<", before), ("seq", ">", after)):
            if value is not None:
                clauses.append(f"{name}{operator}?")
                values.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connect() as db:
            rows = db.execute("SELECT * FROM notices" + where + " ORDER BY seq DESC LIMIT ?", (*values, limit + 1)).fetchall()
            unread = {name: 0 for name in CATEGORIES}
            unread.update({row[0]: row[1] for row in db.execute("SELECT category,count(*) FROM notices WHERE read_at IS NULL GROUP BY category")})
            latest = db.execute("SELECT coalesce(max(seq),0) FROM notices").fetchone()[0]
        items = [{**dict(row), "data": json.loads(row["data"])} for row in rows[:limit]]
        return {"items": items, "unread": unread, "latest_seq": latest,
                "next_before": items[-1]["seq"] if len(rows) > limit else None}

    def read(self, *, identifiers=None, category=None):
        if category is not None and category not in CATEGORIES:
            raise ValueError("Unknown notification category")
        if identifiers is not None and (not isinstance(identifiers, list) or not 1 <= len(identifiers) <= 100
                                       or any(not isinstance(value, str) for value in identifiers)):
            raise ValueError("Provide 1–100 notification IDs")
        where, values = "read_at IS NULL", []
        if identifiers is not None:
            where += " AND id IN (" + ",".join("?" for _ in identifiers) + ")"
            values.extend(identifiers)
        if category:
            where += " AND category=?"
            values.append(category)
        with self.connect() as db:
            db.execute("UPDATE notices SET read_at=? WHERE " + where, (int(time.time() * 1000), *values))

    def get(self, identifier):
        with self.connect() as db:
            row = db.execute("SELECT * FROM notices WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise KeyError("Notification not found")
        return {**dict(row), "data": json.loads(row["data"])}

    def unavailable(self, identifier):
        with self.connect() as db:
            db.execute("UPDATE notices SET status='unavailable' WHERE id=?", (identifier,))

    def answer(self, session_key, content):
        # This is the existing quoted-answer protocol; it marks no other session's question.
        match = re.match(r"> \[!QUOTE\]\n> <!-- cirno-question:([a-f0-9]{32}) -->\n", content)
        if match is None:
            return
        with self.connect() as db:
            db.execute("UPDATE notices SET status='answered',read_at=? WHERE id=? AND session_key=?",
                       (int(time.time() * 1000), "question:" + match[1], session_key))

    def sync_pairing(self):
        from cirno.pairing.store import list_pending
        pending = list_pending(strict=True)
        identifiers = []
        for item in pending:
            identifier = "pairing:" + item["code"]
            identifiers.append(identifier)
            self.record(identifier, "operations", "pairing", status="pending",
                        body=str(item.get("channel", "")), data={"code": item["code"], "expires_at": item.get("expires_at")})
        with self.connect() as db:
            unmatched = " AND id NOT IN (" + ",".join("?" for _ in identifiers) + ")" if identifiers else ""
            db.execute("UPDATE notices SET status='resolved' WHERE kind='pairing' AND status='pending'" + unmatched, identifiers)

    def capture(self, message):
        notice = self.prepare(message)
        if notice is not None:
            self.record(**notice)

    @staticmethod
    def prepare(message):
        from cirno.bus.events import OUTBOUND_META_AGENT_UI
        from cirno.bus.outbound_events import StreamedResponseEvent, TurnEndEvent
        from cirno.bus.agent_events import ContextCompactionEvent, RecoveryStateEvent
        if message.metadata.get("_temporary_chat") or message.metadata.get("_persist_transcript") is False:
            return
        key = message.metadata.get("_session_key") or f"{message.channel}:{message.chat_id}"
        if key.startswith(("dream:", "temporary:")):
            return
        ui = message.metadata.get(OUTBOUND_META_AGENT_UI) or {}
        event = message.event
        if ui.get("kind") == "user_question":
            question = ui["data"]
            return dict(identifier="question:" + question["id"], category="operations", kind="question", status="pending",
                        session_key=key, body=question["question"],
                        data={**question, "session_generation": message.metadata.get("_session_generation")})
        elif isinstance(event, ContextCompactionEvent) and event.phase in {"succeeded", "failed"}:
            return dict(identifier="compact:" + event.compaction_id, category="system", kind="compaction", status=event.phase,
                        session_key=key, body=event.error or "", data={"reason": event.reason, "context_tokens": event.context_tokens})
        elif isinstance(event, RecoveryStateEvent) and event.status in {"awaiting_user", "failed", "recovered"}:
            return dict(identifier="recovery:" + event.recovery_id, category="operations", kind="recovery",
                        status="resolved" if event.status == "recovered" else "pending", session_key=key, body=event.reason or "")
        elif isinstance(event, TurnEndEvent) and event.outcome != "cancelled" and (key != CIRNO_SESSION_KEY or event.outcome != "completed"):
            turn = message.metadata.get("webui_turn_id")
            if turn:
                return dict(identifier=f"turn:{key}:{turn}", category="conversations", kind="turn", status=event.outcome,
                            session_key=key, body=event.failure_message or "")
        elif not ui and (message.content or message.media) and (event is None or message.metadata.get("_record_channel_delivery") and isinstance(event, StreamedResponseEvent)):
            identity = hashlib.sha256(json.dumps([key, message.metadata.get("webui_turn_id"), message.content, message.media], ensure_ascii=False).encode()).hexdigest()
            return dict(identifier="message:" + identity, category="conversations", kind="message", session_key=key,
                        body=message.content, data={"media": message.media})
