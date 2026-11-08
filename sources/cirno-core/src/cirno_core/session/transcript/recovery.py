"""Recovery for durable conversation presentation."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from cirno_core.bus.events import INBOUND_META_LOCAL_MEDIA

from .answers import visit_transcript_answers
from .contracts import _TURN_DISPLAY_EVENTS, WEBUI_TRANSCRIPT_INCOMPLETE_KEY, SessionBackfillTurn
from .identities import _split_transcript_turns
from .inputs import _assistant_text_signature
from .records import valid_created_at_ms


def transcript_turn_signature(records: Iterable[dict[str, Any]]) -> tuple[str, ...]:
    """Return durable assistant answer texts used only for backfill matching."""
    texts: list[str] = []
    stream_parts: list[str] = []

    def replace(text: str) -> None:
        stream_parts[:] = [text]

    def finish() -> None:
        if signature := _assistant_text_signature("".join(stream_parts)):
            texts.append(signature)
        stream_parts.clear()

    visit_transcript_answers(records, stream_parts.append, replace, finish)
    return tuple(texts)


def _user_recovery_signature(event: dict[str, Any]) -> str:
    fields = {
        key: event[key]
        for key in (
            "text",
            "media_paths",
            INBOUND_META_LOCAL_MEDIA,
            "cli_apps",
            "mcp_presets",
            "session_mentions",
            "session_message",
            "input_origin",
        )
        if key in event
    }
    return json.dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _find_unique_session_turn_by_user(
    session_turns: list[SessionBackfillTurn],
    user_event: dict[str, Any],
) -> SessionBackfillTurn | None:
    signature = _user_recovery_signature(user_event)
    matches = [
        turn for turn in session_turns if _user_recovery_signature(turn.user_event) == signature
    ]
    return matches[0] if len(matches) == 1 else None


def _is_recoverable_answer_record(record: dict[str, Any]) -> bool:
    event = record.get("event")
    if event in {"delta", "stream_end"}:
        return True
    return event == "message" and record.get("kind") not in {
        "tool_hint",
        "progress",
        "reasoning",
    }


def _needs_incomplete_turn_recovery(lines: list[dict[str, Any]]) -> bool:
    return any(
        record.get("event") == "turn_end" and record.get(WEBUI_TRANSCRIPT_INCOMPLETE_KEY) is True
        for record in lines
    )


def _recover_incomplete_turns(
    lines: list[dict[str, Any]],
    session_turns: list[SessionBackfillTurn],
) -> list[dict[str, Any]]:
    recovered: list[dict[str, Any]] = []
    for turn in _split_transcript_turns(lines):
        turn_end = turn[-1] if turn else None
        if (
            not isinstance(turn_end, dict)
            or turn_end.get("event") != "turn_end"
            or turn_end.get(WEBUI_TRANSCRIPT_INCOMPLETE_KEY) is not True
        ):
            recovered.extend(turn)
            continue

        user_events = [record for record in turn if record.get("event") == "user"]
        if len(user_events) != 1:
            recovered.extend(turn)
            continue
        session_turn = _find_unique_session_turn_by_user(session_turns, user_events[0])
        if session_turn is None or not session_turn.assistant_records:
            recovered.extend(turn)
            continue

        stable_end_ms = valid_created_at_ms(turn_end.get("created_at_ms"))
        turn_id = turn_end.get("turn_id")
        answer_records: list[dict[str, Any]] = []
        for index, source in enumerate(session_turn.assistant_records):
            answer = dict(source)
            if isinstance(turn_id, str) and turn_id:
                answer["turn_id"] = turn_id
                answer["turn_phase"] = "answer"
            if stable_end_ms is not None:
                answer["created_at_ms"] = max(
                    0,
                    stable_end_ms - len(session_turn.assistant_records) + index,
                )
            answer_records.append(answer)

        # Session history is the durable source of the completed answer. Keep
        # traces/reasoning/file edits, but replace any partial answer fragments.
        recovered.extend(
            record for record in turn[:-1] if not _is_recoverable_answer_record(record)
        )
        recovered.extend(answer_records)
        completed_end = dict(turn_end)
        completed_end.pop(WEBUI_TRANSCRIPT_INCOMPLETE_KEY, None)
        recovered.append(completed_end)
    return recovered


def _needs_user_event_backfill(lines: list[dict[str, Any]]) -> bool:
    return any(
        not any(record.get("event") == "user" for record in turn)
        and transcript_turn_signature(turn)
        for turn in _split_transcript_turns(lines)
    )


def _with_backfilled_user(
    records: list[dict[str, Any]],
    user_event: dict[str, Any],
) -> list[dict[str, Any]]:
    for index, rec in enumerate(records):
        if rec.get("event") in _TURN_DISPLAY_EVENTS:
            return [*records[:index], dict(user_event), *records[index:]]
    return records
