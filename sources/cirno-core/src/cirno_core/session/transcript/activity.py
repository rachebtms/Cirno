"""Activity for durable conversation presentation."""

from __future__ import annotations

import json
from typing import Any, cast


def _format_tool_call_trace(call: Any) -> str | None:
    if not call or not isinstance(call, dict):
        return None
    call_data = cast(dict[str, Any], call)
    fn = call_data.get("function")
    function_data = cast(dict[str, Any], fn) if isinstance(fn, dict) else None
    name = function_data.get("name") if function_data is not None else None
    if not isinstance(name, str) or not name:
        raw_name = call_data.get("name")
        name = raw_name if isinstance(raw_name, str) else ""
    if not name:
        return None
    args = (function_data.get("arguments") if function_data is not None else None) or call_data.get(
        "arguments"
    )
    if isinstance(args, str) and args.strip():
        return f"{name}({args})"
    if args and isinstance(args, dict):
        return f"{name}({json.dumps(args, ensure_ascii=False)})"
    return f"{name}()"


def tool_trace_lines_from_events(events: Any) -> list[str]:
    if not isinstance(events, list):
        return []
    lines: list[str] = []
    seen: set[str] = set()
    for event in cast(list[Any], events):
        if not event or not isinstance(event, dict):
            continue
        tool_event = cast(dict[str, Any], event)
        if tool_event.get("phase") not in {"start", "end", "error"}:
            continue
        call_id = tool_event.get("call_id")
        if isinstance(call_id, str) and call_id:
            if call_id in seen:
                continue
            seen.add(call_id)
        t = _format_tool_call_trace(tool_event)
        if t:
            lines.append(t)
    return lines


def _normalize_tool_events(events: Any) -> list[dict[str, Any]]:
    if not isinstance(events, list):
        return []
    normalized: list[dict[str, Any]] = []
    for event in cast(list[Any], events):
        if not event or not isinstance(event, dict):
            continue
        tool_event = cast(dict[str, Any], event)
        if tool_event.get("phase") not in {"start", "end", "error"}:
            continue
        if not isinstance(tool_event.get("name"), str):
            function = tool_event.get("function")
            if not isinstance(function, dict):
                continue
            typed_function = cast(dict[str, Any], function)
            if not isinstance(typed_function.get("name"), str):
                continue
        normalized.append(tool_event)
    return normalized
