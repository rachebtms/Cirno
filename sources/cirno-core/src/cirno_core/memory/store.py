"""Agent profile files and raw transcript checkpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from cirno_core.memory.dream import DreamMemory
from cirno_core.memory.journal import HISTORY_ENTRY_MAX_CHARS, MemoryJournal
from cirno_core.memory.working_state import (
    working_notes,
)
from cirno_core.runtime.context import public_history_messages
from cirno_core.utils.gitstore import GitStore
from cirno_core.utils.model_messages import content_with_media_breadcrumbs
from cirno_core.utils.file_io import ensure_dir
from cirno_core.utils.reasoning import strip_think
from loguru import logger

_RAW_ARCHIVE_MAX_CHARS = 16_000


class MemoryStore:
    def __init__(self, home: Path, max_history_entries: int = 1000):
        self.workspace = home
        self.memory_dir = ensure_dir(home / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.soul_file = home / "SOUL.md"
        self.worker_file = home / "WORKER.md"
        self.user_file = home / "USER.md"
        self.journal = MemoryJournal(home, max_history_entries)
        self.dream = DreamMemory(self)
        self._git = GitStore(
            home,
            tracked_files=[
                "SOUL.md", "WORKER.md",
                "USER.md",
                "memory/MEMORY.md",
                "memory/.dream_cursor",
            ],
        )

    @property
    def git(self) -> GitStore:
        return self._git

    @staticmethod
    def read_file(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def read_memory(self, max_chars: int | None = None) -> str:
        if max_chars is None:
            return self.read_file(self.memory_file)
        try:
            with self.memory_file.open(encoding="utf-8") as stream:
                return stream.read(max_chars)
        except FileNotFoundError:
            return ""

    def write_memory(self, content: str) -> None:
        self.memory_file.write_text(content, encoding="utf-8")

    def read_soul(self) -> str:
        return self.read_file(self.soul_file)

    def write_soul(self, content: str) -> None:
        self.soul_file.write_text(content, encoding="utf-8")

    def read_user(self) -> str:
        return self.read_file(self.user_file)

    def write_user(self, content: str) -> None:
        self.user_file.write_text(content, encoding="utf-8")

    def get_memory_context(self) -> str:
        """Return long-term memory formatted for context injection."""
        long_term = self.read_memory()
        return f"## Long-term Memory\n{long_term}" if long_term else ""

    @staticmethod
    def _format_messages(messages: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for message in messages:
            content = content_with_media_breadcrumbs(
                message.get("role"),
                message.get("content", ""),
                message.get("media"),
            )
            if not content:
                continue
            tools_used = message.get("tools_used")
            tools = f" [tools: {', '.join(cast(list[str], tools_used))}]" if tools_used else ""
            raw_timestamp = message.get("timestamp")
            timestamp = str(raw_timestamp) if raw_timestamp is not None else "?"
            role = str(message.get("role") or "unknown")
            lines.append(f"[{timestamp[:16]}] {role.upper()}{tools}: {content}")
        return "\n".join(lines)

    def raw_archive(
        self,
        messages: list[dict[str, Any]],
        *,
        max_chars: int | None = None,
        session_key: str | None = None,
    ) -> str:
        """Persist raw messages in bounded chunks and return a checkpoint."""
        limit = max_chars if max_chars is not None else _RAW_ARCHIVE_MAX_CHARS
        chunk_size = min(max(1, limit), HISTORY_ENTRY_MAX_CHARS - 1_000)
        # Clean the complete text first: a thinking block may span chunk boundaries.
        formatted = strip_think(self._format_messages(public_history_messages(messages)))
        notes = working_notes(messages)
        if notes:
            formatted += "\n\n" + notes
        chunks = [
            formatted[start : start + chunk_size] for start in range(0, len(formatted), chunk_size)
        ] or [""]
        for part, chunk in enumerate(chunks, start=1):
            suffix = f" (part {part}/{len(chunks)})" if len(chunks) > 1 else ""
            # The whole text is sanitized and each record fits the hard cap.
            # Normalizing again would trim meaningful whitespace at chunk edges.
            self.journal.append_record(
                f"[RAW] {len(messages)} messages{suffix}\n{chunk}",
                session_key=session_key,
            )
        self.journal.compact_history(indexed=True)
        logger.warning(
            "Memory consolidation degraded: raw-archived {} messages in {} entries",
            len(messages),
            len(chunks),
        )
        return self._build_raw_checkpoint(messages, max_chars=limit)

    def _build_raw_checkpoint(
        self,
        messages: list[dict[str, Any]],
        *,
        max_chars: int | None = None,
    ) -> str:
        """Build the same bounded checkpoint as :meth:`raw_archive` without writing it."""
        limit = max_chars if max_chars is not None else _RAW_ARCHIVE_MAX_CHARS
        checkpoint = (
            f"[RAW] {len(messages)} messages\n"
            f"{self._format_messages(public_history_messages(messages))}\n\n{working_notes(messages)}"
        )
        if len(checkpoint) > limit:
            checkpoint = (
                checkpoint[: limit // 4]
                + "\n[Earlier evidence omitted]\n"
                + checkpoint[-limit * 3 // 4 :]
            )
        return self.journal.normalize_entry(checkpoint, max_chars=limit + 100)
