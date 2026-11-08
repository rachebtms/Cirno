"""Paging for durable conversation presentation."""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any, cast

from cirno_core.session.display_history import (
    HistoryReader,
)
from cirno_core.session.presentation_history import (
    record_from_fact,
    turn_records,
)

from .contracts import (
    _DEFAULT_TRANSCRIPT_PAGE_LIMIT,
    _MAX_TRANSCRIPT_PAGE_BYTES,
    _MAX_TRANSCRIPT_PAGE_LIMIT,
    _MAX_TRANSCRIPT_PAGE_RECORDS,
    TranscriptReplayStats,
    _TranscriptTurnRef,
)
from .identities import _records_with_replay_identity
from .records import _records_bytes
from .streaming import _compact_completed_stream_deltas


def encode_page_cursor(before_turn_ordinal: int, position: int | None = None) -> str:
    raw = json.dumps(
        {"before_turn": before_turn_ordinal, **({"position": position} if position is not None else {})},
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_page_cursor(value: str | None) -> tuple[int, int | None] | None:
    if not value:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    cursor_data = cast(dict[str, Any], data)
    before_turn = cursor_data.get("before_turn")
    if isinstance(before_turn, bool) or not isinstance(before_turn, int) or before_turn < 0:
        return None
    position = cursor_data.get("position")
    if position is not None and (isinstance(position, bool) or not isinstance(position, int) or position < 0):
        return None
    return before_turn, position


def decode_transcript_cursor(value: str | None) -> int | None:
    cursor = _decode_page_cursor(value)
    return cursor[0] if cursor is not None else None


def _coerce_page_limit(limit: int | None) -> int:
    if limit is None:
        return _DEFAULT_TRANSCRIPT_PAGE_LIMIT
    return max(1, min(_MAX_TRANSCRIPT_PAGE_LIMIT, int(limit)))


def _select_transcript_page(
    *,
    history: HistoryReader,
    limit: int | None,
    before: str | None,
    after: str | None = None,
    stats: TranscriptReplayStats | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stats = stats or TranscriptReplayStats()
    page_limit = _coerce_page_limit(limit)
    stats.effective_limit = page_limit
    total_turns = history.turn_count
    before_cursor = _decode_page_cursor(before)
    before_ordinal, before_position = before_cursor or (None, None)
    upper = total_turns if before_ordinal is None else min(before_ordinal + (before_position is not None), total_turns)
    after_cursor = _decode_page_cursor(after)
    after_ordinal, after_position = after_cursor or (None, None)
    selected: list[_TranscriptTurnRef] = []
    event_count = record_count = byte_count = 0
    for ref in history.turns(before=upper, after=after_ordinal or 0, reverse=after_ordinal is None):
        exceeds_records = record_count + ref.record_count > _MAX_TRANSCRIPT_PAGE_RECORDS
        exceeds_bytes = byte_count + ref.byte_count > _MAX_TRANSCRIPT_PAGE_BYTES
        stats.capped_by_records |= exceeds_records
        stats.capped_by_bytes |= exceeds_bytes
        if selected and (exceeds_records or exceeds_bytes):
            break
        window_before = before_position if ref.ordinal == before_ordinal else None
        window_after = after_position if ref.ordinal == after_ordinal else None
        safe = not (exceeds_records or exceeds_bytes or window_before is not None or window_after is not None)
        start, stop = 0, ref.record_count
        if safe:
            turn = turn_records(history, ref.ordinal)
        else:
            entries, start, stop = history.read_window(
                ref.ordinal, start=window_after or 0, stop=window_before,
                reverse=after_ordinal is None,
                max_records=_MAX_TRANSCRIPT_PAGE_RECORDS, max_bytes=_MAX_TRANSCRIPT_PAGE_BYTES,
            )
            turn = [{**record_from_fact(fact, history.key),
                     "_webui_replay_identity": f"turn:{ref.ordinal}:record:{position}"}
                    for position, fact in entries]
        stats.parsed_records += len(turn)
        stats.source_bytes += ref.byte_count if safe else _records_bytes(turn)
        turn, dropped = _compact_completed_stream_deltas(turn, include_projection_receipts=True)
        stats.compacted_delta_records += dropped
        if not safe:
            stats.truncated_oversized_turn = True
        selected.append(_TranscriptTurnRef(ref.ordinal, turn, start, stop, ref.record_count))
        record_count += len(turn)
        byte_count += _records_bytes(turn)
        event_count += _client_projection_page_event_count(turn)
        if not safe or event_count >= page_limit:
            break
    chronological = selected if after_ordinal is not None else list(reversed(selected))
    records = [
        record
        for ref in chronological
        for record in _records_with_replay_identity(
            ref.records,
            turn_ordinal=ref.ordinal,
        )
    ]
    stats.selected_records, stats.selected_bytes = len(records), byte_count
    if not chronological:
        return [], {
            "before_cursor": None,
            "has_more_before": False,
            "after_cursor": None,
            "has_more_after": False,
            "loaded_event_count": 0,
            "user_message_offset": 0,
        }
    first_ref, last_ref = chronological[0], chronological[-1]
    first, last = first_ref.ordinal, last_ref.ordinal
    has_before = first > 0 or first_ref.start > 0
    has_after = last + 1 < total_turns or last_ref.stop < last_ref.total
    page: dict[str, Any] = {
        "before_cursor": encode_page_cursor(first, first_ref.start) if first_ref.start > 0 else encode_page_cursor(first) if first else None,
        "has_more_before": has_before,
        "after_cursor": encode_page_cursor(last, last_ref.stop) if last_ref.stop < last_ref.total else encode_page_cursor(last + 1) if has_after else None,
        "has_more_after": has_after,
        "loaded_event_count": 0,
        "user_message_offset": history.user_count_before(first),
    }
    if stats.truncated_oversized_turn:
        page["truncated_oversized_turn"] = True
    return records, page


def read_transcript_lines(session_key: str, *, history: HistoryReader) -> list[dict[str, Any]]:
    return [record_from_fact(fact, session_key) for fact in history.all_facts()]


def _client_projection_page_event_count(turn: list[dict[str, Any]]) -> int:
    """Apply the soft page limit in canonical protocol events, not UI rows."""
    supported = {
        "user",
        "delta",
        "stream_end",
        "reasoning_delta",
        "reasoning_end",
        "message",
        "file_edit",
        "context_compaction",
        "turn_end",
    }
    return max(1, sum(record.get("event") in supported for record in turn))
