"""Stream current and released canonical messages from one session snapshot."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from cirno_core.session.contracts import CanonicalMessage
from cirno_core.storage.records import decode_record


def initialize_archive_index(db: sqlite3.Connection) -> None:
    db.execute("""CREATE TABLE IF NOT EXISTS runtime_archives (
        session_key TEXT NOT NULL REFERENCES sessions(key) ON DELETE CASCADE,
        generation TEXT NOT NULL, start_position INTEGER NOT NULL,
        message_count INTEGER NOT NULL, path TEXT NOT NULL,
        PRIMARY KEY(session_key,generation,start_position)
    )""")


def reverse_json_lines(path: Path) -> Iterator[dict[str, Any]]:
    """Read immutable archive lines newest first without loading the corpus."""
    with path.open("rb") as stream:
        remaining = stream.seek(0, 2)
        pending = b""
        while remaining:
            size = min(64 * 1024, remaining)
            remaining -= size
            stream.seek(remaining)
            parts = (stream.read(size) + pending).split(b"\n")
            pending = parts[0]
            for line in reversed(parts[1:]):
                if line:
                    yield decode_record(line)
        if pending:
            yield decode_record(pending)


def reverse_messages(db: sqlite3.Connection, key: str, generation: str, released: int, base: Path) -> Iterator[CanonicalMessage]:
    for position, record in db.execute(
        "SELECT position,record FROM messages WHERE session_key=? ORDER BY position DESC", (key,)
    ):
        yield released + position, decode_record(record)
    for start, count, path in db.execute(
        """SELECT start_position,message_count,path FROM runtime_archives
           WHERE session_key=? AND generation=? ORDER BY start_position DESC""",
        (key, generation),
    ):
        for offset, message in enumerate(reverse_json_lines(base / path)):
            yield start + count - offset - 1, message
