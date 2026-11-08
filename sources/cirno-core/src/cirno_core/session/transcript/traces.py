"""Traces for durable conversation presentation."""

from __future__ import annotations

import re
from typing import Any, Callable

from cirno_core.session.display_history import (
    HistoryReader,
)
from cirno_core.session.presentation_history import (
    record_from_fact,
)

from .activity import _normalize_tool_events, tool_trace_lines_from_events
from .contracts import (
    _MAX_INLINE_TRACE_DETAIL_BYTES,
    _MAX_TRANSCRIPT_PAGE_BYTES,
    _MAX_TRANSCRIPT_PAGE_RECORDS,
    WEBUI_REPLAY_IDENTITY_KEY,
    _WEBUI_TRACE_DETAIL_REF_RE,
    WEBUI_FORK_MARKER_EVENT,
    _DeferredTraceGroup,
)
from .event_projection import _client_projection_event
from .identities import client_projection_event_id, _history_generation, _record_position
from .records import _record_json_line
from .streaming import _projection_receipts


def _trace_detail_ref(
    lines: list[dict[str, Any]], group: _DeferredTraceGroup, generation: str
) -> str | None:
    first, last = _record_position(lines[group.start]), _record_position(lines[group.stop - 1])
    if first is None or last is None or first[0] != last[0]:
        return None
    return f"{first[0]}.{first[1]}.{last[1] + 1}.{generation}.{client_projection_event_id(lines[group.start])}"


def _truncate_utf8(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[: max_bytes - 3].decode("utf-8", errors="ignore") + "…"


def _trace_summary(line: str) -> str:
    if len(line.encode("utf-8")) <= 512:
        return line
    match = re.match(r"^([A-Za-z0-9_.-]+)\(", line.strip())
    return f"{_truncate_utf8(match.group(1), 240)}(…)" if match else _truncate_utf8(line, 240)


def build_webui_trace_detail_response(
    session_key: str,
    detail_ref: str,
    *,
    history: HistoryReader,
) -> dict[str, Any] | None:
    """Resolve one deferred activity group as canonical projection events."""
    match = _WEBUI_TRACE_DETAIL_REF_RE.fullmatch(detail_ref)
    if match is None:
        return None
    if match["generation"] != _history_generation(history):
        return None
    ordinal, start, stop = int(match["turn"]), int(match["start"]), int(match["stop"])
    entries = history.read_range(
        ordinal,
        start,
        stop,
        max_records=_MAX_TRANSCRIPT_PAGE_RECORDS,
        max_bytes=_MAX_TRANSCRIPT_PAGE_BYTES,
    )
    if not entries:
        return None
    lines = [
        {
            **record_from_fact(fact, session_key),
            WEBUI_REPLAY_IDENTITY_KEY: f"turn:{ordinal}:record:{position}",
        }
        for position, fact in entries
    ]
    message_id = match["message"]
    if client_projection_event_id(lines[0]) != message_id:
        return None
    if any(
        record.get("event") != "message" or record.get("kind") not in {"tool_hint", "progress"}
        for record in lines
    ):
        return None
    events = [
        _client_projection_event(
            record,
            augment_user_media=None,
            augment_assistant_media=None,
            augment_assistant_text=None,
        )
        for record in lines
    ]
    return {"message_id": message_id, "events": [event for event in events if event is not None]}


def _client_projection_deferred_trace_groups(
    lines: list[dict[str, Any]],
) -> dict[int, _DeferredTraceGroup]:
    """Group oversized consecutive activity events behind one stable detail ref."""
    groups: dict[int, _DeferredTraceGroup] = {}
    start: int | None = None
    detail_bytes = 0
    trace_count = 0

    def flush(stop: int) -> None:
        nonlocal start, detail_bytes, trace_count
        if start is not None and detail_bytes > _MAX_INLINE_TRACE_DETAIL_BYTES:
            groups[start] = _DeferredTraceGroup(
                start=start,
                stop=stop,
                detail_bytes=detail_bytes,
                trace_count=max(1, trace_count),
            )
        start = None
        detail_bytes = 0
        trace_count = 0

    for index, record in enumerate(lines):
        is_activity = record.get("event") == "message" and record.get("kind") in {
            "tool_hint",
            "progress",
        }
        if not is_activity:
            flush(index)
            continue
        event = _client_projection_event(
            record,
            augment_user_media=None,
            augment_assistant_media=None,
            augment_assistant_text=None,
        )
        if event is None:
            flush(index)
            continue
        if start is not None:
            previous, current = _record_position(lines[index - 1]), _record_position(record)
            if (
                previous is None
                or current is None
                or previous[0] != current[0]
                or previous[1] + 1 != current[1]
            ):
                flush(index)
        if start is None:
            start = index
        detail_bytes += len(_record_json_line(event).encode("utf-8"))
        tool_events = _normalize_tool_events(record.get("tool_events"))
        traces = tool_trace_lines_from_events(tool_events)
        if traces:
            trace_count += len(traces)
        elif not tool_events and isinstance(record.get("text"), str) and record["text"]:
            trace_count += 1
    flush(len(lines))
    return groups


def _client_projection_events(
    lines: list[dict[str, Any]],
    *,
    history_generation: str,
    augment_user_media: Callable[[list[str], list[str]], list[dict[str, Any]]] | None,
    augment_assistant_media: Callable[[list[str]], list[dict[str, Any]]] | None,
    augment_assistant_text: Callable[[str], str] | None,
) -> tuple[list[dict[str, Any]], int | None]:
    events: list[dict[str, Any]] = []
    fork_boundary_event_index: int | None = None
    deferred_groups = _client_projection_deferred_trace_groups(lines)
    deferred_until = 0
    for index, record in enumerate(lines):
        if index < deferred_until:
            continue
        if record.get("event") == WEBUI_FORK_MARKER_EVENT:
            if fork_boundary_event_index is None:
                fork_boundary_event_index = len(events)
            continue
        event = _client_projection_event(
            record,
            augment_user_media=augment_user_media,
            augment_assistant_media=augment_assistant_media,
            augment_assistant_text=augment_assistant_text,
        )
        if event is None:
            continue
        group = deferred_groups.get(index)
        if group is not None:
            detail_ref = _trace_detail_ref(lines, group, history_generation)
            last_text = next(
                (
                    text
                    for grouped in reversed(lines[group.start : group.stop])
                    if isinstance((text := grouped.get("text")), str) and text
                ),
                "",
            )
            if not last_text:
                last_text = next(
                    (
                        traces[-1]
                        for grouped in reversed(lines[group.start : group.stop])
                        if (traces := tool_trace_lines_from_events(grouped.get("tool_events")))
                    ),
                    "",
                )
            event["text"] = _trace_summary(last_text)
            event.pop("tool_events", None)
            receipts = _projection_receipts(lines[group.start : group.stop])
            if receipts:
                event["projection_receipts"] = receipts
            if detail_ref is not None:
                event["trace_detail"] = {
                    "ref": detail_ref,
                    "bytes": group.detail_bytes,
                    "traceCount": group.trace_count,
                }
            deferred_until = group.stop
        events.append(event)
    return events, fork_boundary_event_index
