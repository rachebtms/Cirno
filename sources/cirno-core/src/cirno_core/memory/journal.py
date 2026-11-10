"""Append-only memory journal, monotonic cursors, and streaming retention."""

from __future__ import annotations

import json
from contextlib import nullcontext, suppress
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, cast

from filelock import FileLock
from loguru import logger

from cirno_core.storage.records import decode_record
from cirno_core.utils.atomic_file import atomic_write_lines, atomic_write_text
from cirno_core.utils.file_io import ensure_dir
from cirno_core.utils.reasoning import strip_think
from cirno_core.utils.text import truncate_text

HISTORY_ENTRY_MAX_CHARS = 64_000


class MemoryJournal:
    def __init__(self, home: Path, max_history_entries: int = 1000):
        self.workspace = home
        self.memory_dir = ensure_dir(home / "memory")
        self.max_history_entries = max_history_entries
        self.history_file = self.memory_dir / "history.jsonl"
        self._cursor_file = self.memory_dir / ".cursor"
        self._dream_cursor_file = self.memory_dir / ".dream_cursor"
        self._oversize_logged = False
        self._append_lock = FileLock(str(self.memory_dir / ".history.lock"))
        with self._append_lock:
            for path in (self._cursor_file, self._dream_cursor_file):
                if not path.exists():
                    atomic_write_text(path, "0")

    def normalize_entry(
        self,
        entry: str,
        *,
        max_chars: int | None = None,
    ) -> str:
        """Return the exact bounded, model-safe text accepted by the journal."""
        limit = max_chars if max_chars is not None else HISTORY_ENTRY_MAX_CHARS
        raw = entry.rstrip()
        content = strip_think(raw)
        if len(content) > limit:
            if not self._oversize_logged:
                self._oversize_logged = True
                logger.warning(
                    "history entry exceeds {} chars ({}); truncating. "
                    "Usually means a caller forgot its own cap; "
                    "further occurrences suppressed.",
                    limit,
                    len(content),
                )
            content = truncate_text(content, limit)
        return content

    def append_history(
        self,
        entry: str,
        *,
        max_chars: int | None = None,
        session_key: str | None = None,
        source_refs: list[dict[str, Any]] | None = None,
        archive_id: str | None = None,
    ) -> int:
        """Append *entry* to history.jsonl and return its auto-incrementing cursor.

        Entries are passed through `strip_think` to drop template-level leaks
        (e.g. unclosed `<think` prefixes, `<channel|>` markers) before being
        persisted. If the cleaned content is empty but the raw entry wasn't,
        the record is persisted with an empty string rather than falling back
        to the raw leak — otherwise `strip_think`'s guarantees would be
        undone when Dream consumes the journal entry.

        Journal text is capped at *max_chars* (default
        ``HISTORY_ENTRY_MAX_CHARS``). Callers may select a smaller summary budget.
        Original conversation evidence is stored separately.
        """
        content = self.normalize_entry(entry, max_chars=max_chars)
        if entry.rstrip() and not content:
            logger.debug(
                "history entry stripped to empty (likely template leak); "
                "persisting empty content to avoid re-polluting Dream input",
            )
        return self.append_record(content, session_key=session_key, source_refs=source_refs, archive_id=archive_id)

    def append_record(
        self,
        content: str,
        *,
        session_key: str | None = None,
        source_refs: list[dict[str, Any]] | None = None,
        archive_id: str | None = None,
    ) -> int:
        """Persist already sanitized, bounded content without rewriting chunk edges."""
        from cirno_memory.repository import MemoryRepository
        from cirno_core.memory.journal_checkpoints import checkpoint_entry, index_checkpoint

        repository = MemoryRepository(self.workspace)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        # Cursor allocation and the append must be atomic: concurrent writers
        # could otherwise read the same current cursor and emit duplicates.
        with self._append_lock:
            existing = None
            if archive_id:
                existing = checkpoint_entry(repository, session_key, archive_id, content) or next(
                    (entry for entry, _ in self.iter_valid_entries()
                     if entry.get("archive_id") == archive_id
                     and entry.get("session_key") == session_key),
                    None,
                )
            if existing is not None:
                if existing["content"] != content:
                    raise ValueError("Archived checkpoint already exists with different content")
                cursor, ts = existing["cursor"], existing["timestamp"]
                source_refs = existing.get("source_refs")
            else:
                cursor = self._next_cursor()
                record: dict[str, Any] = {"cursor": cursor, "timestamp": ts, "content": content}
                if session_key:
                    record["session_key"] = session_key
                if source_refs:
                    record["source_refs"] = source_refs
                if archive_id:
                    record["archive_id"] = archive_id
                with open(self.history_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                atomic_write_text(self._cursor_file, str(cursor))
            if archive_id:
                # Publish identity before ingestion can make this entry eligible
                # for retention. A failed ingestion is resumed from this identity.
                index_checkpoint(repository, session_key, archive_id, cursor, ts, content, source_refs)
        repository.ingest_history(
            cursor, content, session_key, source_refs, timestamp=ts
        )
        if archive_id:
            self.compact_history(indexed=True)
        return cursor

    @staticmethod
    def _valid_cursor(value: Any) -> int | None:
        """Non-negative int cursors only; reject bool (``isinstance(True, int)`` is True)."""
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return value

    def iter_valid_entries(self) -> Iterator[tuple[dict[str, Any], int]]:
        """Yield validated entries and stop at corrupt evidence."""
        for entry in self._stream_entries():
            yield entry, cast(int, entry["cursor"])

    @staticmethod
    def _valid_history_payload(entry: dict[str, Any]) -> bool:
        if not isinstance(entry.get("timestamp"), str):
            return False
        if not isinstance(entry.get("content"), str):
            return False
        session_key = entry.get("session_key")
        return session_key is None or isinstance(session_key, str)

    @staticmethod
    def _read_counter(path: Path) -> int | None:
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        try:
            cursor = int(content.strip())
        except ValueError as error:
            raise ValueError(f"Invalid memory cursor at {path}") from error
        if cursor < 0:
            raise ValueError(f"Invalid negative memory cursor at {path}")
        return cursor

    def _next_cursor(self) -> int:
        """Allocate above the durable counter and the validated journal tail."""
        counter = self._read_counter(self._cursor_file)
        last = self._read_last_entry()
        tail_cursor = cast(int, last["cursor"]) if last is not None else 0
        return max(counter if counter is not None else 0, tail_cursor) + 1

    def read_unprocessed_history(self, since_cursor: int) -> list[dict[str, Any]]:
        """Return history entries with a valid cursor > *since_cursor*."""
        return [e for e, c in self.iter_valid_entries() if c > since_cursor]

    def compact_history(self, *, indexed: bool = False) -> None:
        """Stream journal retention without loading the long-term corpus into RAM."""
        if self.max_history_entries <= 0:
            return
        from cirno_memory.repository import MemoryRepository
        repository = MemoryRepository(self.workspace) if indexed else None
        with self._append_lock:
            count, first_pending = 0, None
            last = self.get_last_dream_cursor() if not indexed else 0
            # Consolidation keeps every event in the immutable memory catalog;
            # retention no longer depends on the retired idle Dream cursor.
            with repository.connect() if repository else nullcontext(None) as db:
                for entry in self._stream_entries():
                    cursor = cast(int, entry["cursor"])
                    pending = (db.execute("SELECT 1 FROM memories WHERE id=?", (f"history-{cursor}",)).fetchone() is None) if db else cursor > last
                    if pending and first_pending is None:
                        first_pending = count
                    count += 1
            keep_from = min(
                max(0, count - self.max_history_entries),
                first_pending if first_pending is not None else count,
            )
            if keep_from:
                atomic_write_lines(
                    self.history_file,
                    (
                        json.dumps(entry, ensure_ascii=False)
                        for index, entry in enumerate(self._stream_entries())
                        if index >= keep_from
                    ),
                )

    def _decode_entry(self, line: str | bytes, *, line_number: int | None = None) -> dict[str, Any]:
        try:
            entry = decode_record(line)
            if self._valid_cursor(entry.get("cursor")) is None:
                raise ValueError("cursor must be a non-negative integer")
            if not self._valid_history_payload(entry):
                raise ValueError("timestamp/content must be strings and session_key must be text")
            return entry
        except ValueError as error:
            location = f":{line_number}" if line_number is not None else " (last record)"
            raise ValueError(
                f"Invalid memory history at {self.history_file}{location}: {error}"
            ) from error

    def _stream_entries(self) -> Iterator[dict[str, Any]]:
        with suppress(FileNotFoundError):
            with self.history_file.open(encoding="utf-8") as stream:
                for number, line in enumerate(stream, 1):
                    if line.strip():
                        yield self._decode_entry(line, line_number=number)

    def _read_last_entry(self) -> dict[str, Any] | None:
        """Read the last entry from the JSONL file efficiently."""
        try:
            with open(self.history_file, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                if size == 0:
                    return None
                position = size
                tail = b""
                while position:
                    count = min(position, 4096)
                    position -= count
                    f.seek(position)
                    tail = f.read(count) + tail
                    content = tail.rstrip(b"\r\n \t")
                    boundary = content.rfind(b"\n")
                    if boundary >= 0 or position == 0:
                        if not content:
                            return None
                        return self._decode_entry(content[boundary + 1 :])
                return None
        except FileNotFoundError:
            return None

    def get_last_dream_cursor(self) -> int:
        cursor = self._read_counter(self._dream_cursor_file)
        return cursor if cursor is not None else 0

    def set_last_dream_cursor(self, cursor: int) -> None:
        if self._valid_cursor(cursor) is None:
            raise ValueError("Dream cursor must be a non-negative integer")
        atomic_write_text(self._dream_cursor_file, str(cursor))

    def get_latest_cursor(self) -> int:
        return max(self._next_cursor() - 1, 0)
