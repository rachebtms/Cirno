"""Encrypted personal records. Values never appear in list responses."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet
from filelock import FileLock

_INIT_LOCK = threading.Lock()


class CredentialVault:
    def __init__(self, directory: Path):
        self.directory = directory

    def _open(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with _INIT_LOCK:
            with FileLock(self.directory / "vault.lock", timeout=10, mode=0o600):
                return self._open_locked()

    def _open_locked(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        key_path = self.directory / "vault.key"
        try:
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "wb") as file:
                file.write(Fernet.generate_key())
                file.flush()
                os.fsync(file.fileno())
        cipher = Fernet(key_path.read_bytes())
        path = self.directory / "vault.sqlite3"
        db = sqlite3.connect(path)
        path.chmod(0o600)
        db.execute(
            "CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, label TEXT NOT NULL, kind TEXT NOT NULL, encrypted BLOB NOT NULL, agent_visible INTEGER NOT NULL DEFAULT 0)"
        )
        if "agent_visible" not in {row[1] for row in db.execute("PRAGMA table_info(records)")}:
            db.execute("ALTER TABLE records ADD COLUMN agent_visible INTEGER NOT NULL DEFAULT 0")
            db.commit()
        return db, cipher

    def list(self) -> dict:
        db, _ = self._open()
        try:
            return {
                "records": [
                    {"id": row[0], "label": row[1], "kind": row[2], "agent_visible": bool(row[3])}
                    for row in db.execute("SELECT id,label,kind,agent_visible FROM records ORDER BY label,id")
                ]
            }
        finally:
            db.close()

    def read_record(self, identifier: str) -> dict:
        db, cipher = self._open()
        try:
            row = db.execute("SELECT id,label,kind,encrypted,agent_visible FROM records WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise KeyError("Credential no longer exists")
            return {"id": row[0], "label": row[1], "kind": row[2], "agent_visible": bool(row[4]), **json.loads(cipher.decrypt(row[3]))}
        finally:
            db.close()

    def metadata(self, identifier: str) -> dict:
        db, _ = self._open()
        try:
            row = db.execute("SELECT id,label,kind,agent_visible FROM records WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise KeyError("Credential no longer exists")
            return {"id": row[0], "label": row[1], "kind": row[2], "agent_visible": bool(row[3])}
        finally:
            db.close()

    def decrypted_records(self, kind: str) -> list[dict]:
        """Internal consumers resolve one consistent snapshot; never expose this as a tool."""
        db, cipher = self._open()
        try:
            rows = db.execute("SELECT id,label,kind,encrypted,agent_visible FROM records WHERE kind=? ORDER BY label,id", (kind,)).fetchall()
            return [{"id": row[0], "label": row[1], "kind": row[2], "agent_visible": bool(row[4]),
                     **json.loads(cipher.decrypt(row[3]))} for row in rows]
        finally:
            db.close()

    def save(
        self,
        *,
        label: str,
        value: str,
        kind: str = "text",
        id: str | None = None,
        username: str = "",
        create_id: str | None = None,
        agent_visible: bool = False,
    ) -> dict:
        if not isinstance(agent_visible, bool):
            raise ValueError("Agent visibility must be a boolean")
        if not isinstance(label, str):
            raise ValueError("Choose a label (1–120 characters)")
        label = label.strip()
        if not label or len(label) > 120 or not isinstance(kind, str) or kind not in {"password", "text", "identity", "token", "ssh"}:
            raise ValueError("Choose a label (1–120 characters) and a supported record type")
        if not isinstance(username, str) or len(username) > 4096:
            raise ValueError("Account username must contain at most 4096 characters")
        if not isinstance(value, str) or not value or len(value.encode()) > 1024 * 1024:
            raise ValueError("The encrypted value must contain 1 byte–1 MiB")
        if create_id is not None and (id is not None or re.fullmatch(r"[a-f0-9]{32}", create_id) is None):
            raise ValueError("Invalid imported credential ID")
        db, cipher = self._open()
        try:
            db.execute("BEGIN IMMEDIATE")
            if create_id is not None and db.execute("SELECT 1 FROM records WHERE id=?", (create_id,)).fetchone():
                raise ValueError("Imported credential ID already exists")
            if (
                id is not None
                and db.execute("SELECT 1 FROM records WHERE id=?", (id,)).fetchone() is None
            ):
                raise KeyError("Credential no longer exists")
            identifier = id or create_id or uuid4().hex
            with db:
                db.execute(
                    "INSERT INTO records(id,label,kind,encrypted,agent_visible) VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET label=excluded.label,kind=excluded.kind,encrypted=excluded.encrypted,agent_visible=excluded.agent_visible",
                    (
                        identifier,
                        label,
                        kind,
                        cipher.encrypt(
                            json.dumps(
                                {"value": value, **({"username": username} if username else {})},
                                ensure_ascii=False,
                            ).encode()
                        ),
                        int(agent_visible),
                    ),
                )
            return {"id": identifier, "label": label, "kind": kind, "agent_visible": agent_visible}
        finally:
            db.close()

    def reveal(self, identifier: str) -> dict:
        db, cipher = self._open()
        try:
            row = db.execute("SELECT encrypted FROM records WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise KeyError("Credential no longer exists")
            return json.loads(cipher.decrypt(row[0]))
        finally:
            db.close()

    def delete(self, identifier: str) -> dict:
        db, _ = self._open()
        try:
            with db:
                if db.execute("DELETE FROM records WHERE id=?", (identifier,)).rowcount != 1:
                    raise KeyError("Credential no longer exists")
            return {"ok": True}
        finally:
            db.close()
