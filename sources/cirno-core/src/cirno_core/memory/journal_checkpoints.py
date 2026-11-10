"""Durable checkpoint identities survive bounded journal retention."""

from __future__ import annotations

import hashlib
import json

from cirno_memory.repository import MemoryRepository


def _key(session_key: str | None, archive_id: str) -> str:
    identity = json.dumps([session_key, archive_id], ensure_ascii=False).encode()
    return "journal:" + hashlib.sha256(identity).hexdigest()


def checkpoint_entry(
    repo: MemoryRepository, session_key: str | None, archive_id: str, content: str
) -> dict | None:
    with repo.connect() as db:
        row = db.execute(
            "SELECT value FROM maintenance WHERE key=?", (_key(session_key, archive_id),)
        ).fetchone()
    if row is None:
        return None
    entry = json.loads(row[0])
    if entry.pop("content_hash") != hashlib.sha256(content.encode()).hexdigest():
        raise ValueError("Archived checkpoint already exists with different content")
    return {**entry, "content": content}


def index_checkpoint(
    repo: MemoryRepository,
    session_key: str | None,
    archive_id: str,
    cursor: int,
    timestamp: str,
    content: str,
    source_refs: list | None,
) -> None:
    entry = {
        "cursor": cursor,
        "timestamp": timestamp,
        "content_hash": hashlib.sha256(content.encode()).hexdigest(),
        "source_refs": source_refs,
    }
    with repo.connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO maintenance VALUES(?,?)",
            (_key(session_key, archive_id), json.dumps(entry)),
        )
