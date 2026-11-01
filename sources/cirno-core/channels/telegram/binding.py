"""One private Telegram owner, verified from the authenticated Web UI."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from cirno.config.home import get_home_path

NOTIFICATIONS = ("cirno", "operations", "conversations", "system")
PIN_TTL = 120


class TelegramBinding:
    def __init__(self, home: Path | None = None):
        self.path = (home or get_home_path()) / "telegram.sqlite3"

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS binding (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)")
                db.execute("CREATE TABLE IF NOT EXISTS pin (id INTEGER PRIMARY KEY CHECK(id=1), digest TEXT NOT NULL, expires REAL NOT NULL, attempts INTEGER NOT NULL)")
                yield db
        finally:
            db.close()

    @staticmethod
    def _load(db):
        row = db.execute("SELECT body FROM binding WHERE id=1").fetchone()
        return json.loads(row[0]) if row else {"enabled": True, "notifications": list(NOTIFICATIONS), "webui_url": ""}

    @staticmethod
    def _save(db, state):
        db.execute("INSERT INTO binding VALUES(1,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body", (json.dumps(state),))

    def status(self):
        with self.connect() as db:
            state = self._load(db)
        return {**state, "bound": bool(state.get("chat_id"))}

    def issue_pin(self):
        code = f"{secrets.randbelow(100_000_000):08d}"
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            state = self._load(db)
            state["requires_pin"] = True
            self._save(db, state)
            db.execute("INSERT INTO pin VALUES(1,?,?,0) ON CONFLICT(id) DO UPDATE SET digest=excluded.digest,expires=excluded.expires,attempts=0",
                       (hashlib.sha256(code.encode()).hexdigest(), now + PIN_TTL))
        return {"pin": code, "expires_at": int((now + PIN_TTL) * 1000), "ttl_seconds": PIN_TTL}

    def verify(self, code, *, user_id, chat_id, username="", language="en"):
        if not str(user_id).isdigit() or int(user_id) <= 0 or str(user_id) != str(chat_id):
            return False
        digest = hashlib.sha256(code.strip().encode()).hexdigest()
        with self.connect() as db:
            # Reserve before reading so two attempts cannot consume the same PIN.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM pin WHERE id=1").fetchone()
            if row is None or row["expires"] <= time.time() or row["attempts"] >= 10:
                return False
            db.execute("UPDATE pin SET attempts=attempts+1 WHERE id=1")
            if not secrets.compare_digest(row["digest"], digest):
                return False
            state = self._load(db)
            state.update(id=uuid4().hex, user_id=str(user_id), chat_id=str(chat_id), username=username,
                         language=language, bound_at=int(time.time() * 1000))
            self._save(db, state)
            db.execute("DELETE FROM pin")
        return True

    def update(self, values):
        if set(values) - {"enabled", "notifications", "webui_url"}:
            raise ValueError("Unknown Telegram binding setting")
        if "enabled" in values and not isinstance(values["enabled"], bool):
            raise ValueError("enabled must be a boolean")
        if "notifications" in values and (not isinstance(values["notifications"], list)
                or any(item not in NOTIFICATIONS for item in values["notifications"])):
            raise ValueError("Unknown Telegram notification category")
        if "webui_url" in values:
            value = values["webui_url"]
            if not isinstance(value, str) or len(value) > 2048:
                raise ValueError("Enter a Web UI URL")
            parsed = urlparse(value)
            if value and (parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment):
                raise ValueError("Use an HTTP(S) Web UI URL without credentials, query or fragment")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            state = {**self._load(db), **values}
            self._save(db, state)
        return self.status()

    def unbind(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            state = self._load(db)
            self._save(db, {**{key: state[key] for key in ("enabled", "notifications", "webui_url")}, "requires_pin": True})
            db.execute("DELETE FROM pin")
        return self.status()

    def destination(self, category):
        state = self.status()
        return state if state["bound"] and state["enabled"] and category in state["notifications"] else None
