"""Durable display facts, separate from provider/model messages and transports."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

MAX_HISTORY_FACT_BYTES = 8 * 1024 * 1024
HISTORY_GENERATION_METADATA_KEY = "_history_generation"


class HistoryKind(StrEnum):
    INPUT = "input"
    ANSWER = "answer"
    ANSWER_SEGMENT = "answer_segment"
    REASONING = "reasoning"
    REASONING_SEGMENT = "reasoning_segment"
    PROGRESS = "progress"
    TOOL_ACTIVITY = "tool_activity"
    FILE_ACTIVITY = "file_activity"
    COMPLETION = "completion"
    FORK_BOUNDARY = "fork_boundary"
    COMPACTION = "compaction"
    # Only old transcripts can contain unfinished transport fragments.
    ANSWER_FRAGMENT = "answer_fragment"
    REASONING_FRAGMENT = "reasoning_fragment"


@dataclass(frozen=True)
class HistoryFact:
    kind: HistoryKind
    content: Mapping[str, Any] = field(default_factory=lambda: cast(dict[str, Any], {}))
    turn_id: str | None = None
    phase: str | None = None
    sequence: int | None = None
    created_at_ms: int = 0

    def encode(self) -> str:
        record = json.dumps({
            "kind": self.kind.value, "content": dict(self.content),
            "turn_id": self.turn_id, "phase": self.phase,
            "sequence": self.sequence, "created_at_ms": self.created_at_ms,
        }, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(record.encode("utf-8")) > MAX_HISTORY_FACT_BYTES:
            raise ValueError("history fact exceeds the 8 MiB storage limit")
        return record

    @classmethod
    def decode(cls, record: str) -> HistoryFact:
        value = cast(dict[str, Any], json.loads(record))
        return cls(
            HistoryKind(value["kind"]), value["content"], value["turn_id"],
            value["phase"], value["sequence"], value["created_at_ms"],
        )


def is_model_input_fact(fact: HistoryFact) -> bool:
    """Display-only control, subagent and continuation rows do not index prompts."""
    return (fact.kind is HistoryKind.INPUT
            and (fact.content.get("input_origin") or {}).get("kind")
            not in {"supervision", "subagent", "continuation"})


@dataclass(frozen=True)
class HistoryTurn:
    ordinal: int
    record_count: int
    byte_count: int
    user_count: int


class HistoryReader:
    """A single-session view valid only inside its owner's read transaction."""

    def __init__(self, db: sqlite3.Connection, key: str, storage_path: Path) -> None:
        self._db = db
        self.key = key
        self.storage_path = storage_path

    @property
    def revision(self) -> tuple[str, int] | None:
        row = self._db.execute(
            """SELECT sessions.generation, coalesce(history_heads.revision, -1) FROM sessions
               LEFT JOIN history_heads ON history_heads.session_key=sessions.key WHERE sessions.key=?""",
            (self.key,),
        ).fetchone()
        return (str(row[0]), int(row[1])) if row is not None else None

    @property
    def turn_count(self) -> int:
        return int(self._db.execute(
            "SELECT coalesce(max(ordinal)+1, 0) FROM history_turns WHERE session_key=?",
            (self.key,),
        ).fetchone()[0])

    def turns(
        self, *, before: int | None = None, after: int = 0, reverse: bool = False,
    ) -> Iterator[HistoryTurn]:
        upper = self.turn_count if before is None else before
        order = "DESC" if reverse else "ASC"
        for row in self._db.execute(
            f"""SELECT ordinal, record_count, byte_count, user_count FROM history_turns
                WHERE session_key=? AND ordinal>=? AND ordinal<? ORDER BY ordinal {order}""",
            (self.key, after, upper),
        ):
            yield HistoryTurn(*row)

    def read_entries(self, ordinal: int) -> list[tuple[int, HistoryFact]]:
        """Read one turn whose caller has already checked its stored size."""
        return [(int(row[0]), HistoryFact.decode(row[1])) for row in self._db.execute(
            """SELECT position,record FROM history_entries
               WHERE session_key=? AND turn_ordinal=? ORDER BY position""", (self.key, ordinal),
        )]

    def read_window(
        self, ordinal: int, *, start: int = 0, stop: int | None = None,
        reverse: bool = True, max_records: int, max_bytes: int,
    ) -> tuple[list[tuple[int, HistoryFact]], int, int]:
        """Read a contiguous bounded slice, with the original input as its anchor."""
        params: tuple[object, ...] = (self.key, ordinal)
        anchor = self._db.execute(
            """SELECT position,record,length(CAST(record AS BLOB)) FROM history_entries
               WHERE session_key=? AND turn_ordinal=? AND kind=? ORDER BY position LIMIT 1""",
            (*params, HistoryKind.INPUT),
        ).fetchone()
        clause = "session_key=? AND turn_ordinal=? AND position>=?"
        params += (start,)
        if stop is not None:
            clause += " AND position<?"
            params += (stop,)
        order = "DESC" if reverse else "ASC"
        sizes = self._db.execute(
            f"SELECT position,length(CAST(record AS BLOB)) FROM history_entries WHERE {clause} "
            f"ORDER BY position {order} LIMIT ?", (*params, max_records),
        )
        selected: list[int] = []
        used = int(anchor[2]) if anchor else 0
        for position, size in sizes:
            is_anchor = anchor is not None and position == anchor[0]
            if len(selected) >= max_records - bool(anchor) or used + (0 if is_anchor else size) > max_bytes:
                break
            selected.append(int(position))
            used += 0 if is_anchor else size
        if not selected:
            return [], start, start
        first, last = min(selected), max(selected) + 1
        if anchor is not None and anchor[0] not in selected:
            selected.append(int(anchor[0]))
        placeholders = ','.join('?' for _ in selected)
        entries = [(int(row[0]), HistoryFact.decode(row[1])) for row in self._db.execute(
            f"SELECT position,record FROM history_entries WHERE session_key=? AND turn_ordinal=? "
            f"AND position IN ({placeholders}) ORDER BY position", (self.key, ordinal, *selected),
        )]
        return entries, first, last

    def user_count_before(self, ordinal: int) -> int:
        return int(self._db.execute(
            "SELECT coalesce(sum(user_count), 0) FROM history_turns WHERE session_key=? AND ordinal<?",
            (self.key, ordinal),
        ).fetchone()[0])

    def read_range(
        self, ordinal: int, start: int, stop: int, *, max_records: int, max_bytes: int,
    ) -> list[tuple[int, HistoryFact]] | None:
        """Resolve a bounded trace range before decoding any stored bodies."""
        if start < 0 or stop <= start or stop - start > max_records:
            return None
        params = (self.key, ordinal, start, stop)
        clause = "session_key=? AND turn_ordinal=? AND position>=? AND position<?"
        count, size = self._db.execute(
            f"SELECT count(*), coalesce(sum(length(CAST(record AS BLOB))),0) FROM history_entries WHERE {clause}",
            params,
        ).fetchone()
        if count != stop - start or size > max_bytes:
            return None
        return [(row[0], HistoryFact.decode(row[1])) for row in self._db.execute(
            f"SELECT position,record FROM history_entries WHERE {clause} ORDER BY position", params,
        )]

    def navigation(self) -> Iterator[tuple[int, int, HistoryFact]]:
        """Read input/answer records only, never file diffs or tool result bodies."""
        kinds = (HistoryKind.INPUT, HistoryKind.ANSWER, HistoryKind.ANSWER_SEGMENT,
                 HistoryKind.ANSWER_FRAGMENT, HistoryKind.COMPLETION)
        for row in self._db.execute(
            """SELECT turn_ordinal, position, record FROM history_entries
               WHERE session_key=? AND kind IN (?, ?, ?, ?, ?) ORDER BY turn_ordinal, position""",
            (self.key, *kinds),
        ):
            yield int(row[0]), int(row[1]), HistoryFact.decode(row[2])

    def pending_tail_facts(self) -> list[HistoryFact]:
        """Inspect interruption state without materializing a long-running turn."""
        ordinal = self.turn_count - 1
        if ordinal < 0:
            return []
        params = (self.key, ordinal)
        incomplete = self._db.execute(
            """SELECT 1 FROM history_entries WHERE session_key=? AND turn_ordinal=?
               AND json_extract(record,'$.content.transcript_incomplete')=1 LIMIT 1""", params,
        ).fetchone()
        if incomplete:
            return [HistoryFact(HistoryKind.COMPLETION, {"transcript_incomplete": True})]
        row = self._db.execute(
            """SELECT record FROM history_entries WHERE session_key=? AND turn_ordinal=?
               AND kind NOT IN (?,?) ORDER BY position DESC LIMIT 1""",
            (*params, HistoryKind.FORK_BOUNDARY, HistoryKind.COMPACTION),
        ).fetchone()
        return [HistoryFact.decode(row[0])] if row is not None else []

    def all_facts(self) -> list[HistoryFact]:
        return [HistoryFact.decode(row[0]) for row in self._db.execute(
            "SELECT record FROM history_entries WHERE session_key=? ORDER BY turn_ordinal, position",
            (self.key,),
        )]
