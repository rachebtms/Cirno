"""Repair model-facing history without editing the saved transcript."""

from __future__ import annotations

from typing import Any, cast

from cirno_core.agent.governance.contracts import ContextGovernanceConfig
from cirno_core.agent.governance.merging import merge_adjacent_user_messages
from cirno_core.agent.governance.results import apply_tool_result_budget
from cirno_core.providers.tool_calls import valid_tool_name
from loguru import logger

BACKFILL_CONTENT = "[Tool result unavailable — call was interrupted or lost]"
PLACEHOLDER_TEXTS = frozenset({"[Previous assistant message omitted.]"})


def _tool_call_name_is_valid(tool_call: Any) -> bool:
    """Whether a persisted OpenAI-style tool_call carries a usable name.

    Mirrors ``ToolCallRequest.has_valid_name`` for the dict shape stored in
    message history: a degenerate call with ``name=None`` / ``""`` cannot be
    executed and is rejected by upstream APIs if replayed.
    """
    if not isinstance(tool_call, dict):
        return False
    tool_call_data = cast(dict[str, Any], tool_call)
    fn = tool_call_data.get("function")
    name = (
        cast(dict[str, Any], fn).get("name") if isinstance(fn, dict) else tool_call_data.get("name")
    )
    return valid_tool_name(name)


def strip_placeholder_assistant_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove assistant messages that are compaction placeholders.

    Messages like ``[Previous assistant message omitted.]`` carry no useful
    context for the model and can cause it to repeatedly attempt tool calls
    that previously failed, producing malformed responses in a loop.
    Consecutive same-role messages that result from removal are handled
    downstream by the provider's merge-consecutive logic. Only the
    model-facing copy is repaired; the persisted transcript is untouched
    (a copy is returned, or the same list object when nothing changes).
    """
    updated: list[dict[str, Any]] | None = None
    for idx, msg in enumerate(messages):
        if msg.get("role") != "assistant":
            if updated is not None:
                updated.append(msg)
            continue
        content = msg.get("content", "")
        text = content if isinstance(content, str) else ""
        is_placeholder = text.strip() in PLACEHOLDER_TEXTS
        has_tool_calls = bool(msg.get("tool_calls"))
        if is_placeholder and not has_tool_calls:
            if updated is None:
                updated = list(messages[:idx])
            logger.debug(
                "Stripping placeholder assistant message from history: {!r}",
                text[:60],
            )
            continue
        if updated is not None:
            updated.append(msg)
    if updated is None:
        return messages
    return updated


def strip_malformed_tool_calls(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove invalid calls from the model-facing copy, preserving saved history."""
    updated: list[dict[str, Any]] | None = None
    for idx, msg in enumerate(messages):
        if msg.get("role") != "assistant":
            if updated is not None:
                updated.append(msg)
            continue
        calls = msg.get("tool_calls")
        if not calls:
            if updated is not None:
                updated.append(msg)
            continue
        kept = [tc for tc in cast(list[Any], calls) if _tool_call_name_is_valid(tc)]
        if len(kept) == len(calls):
            if updated is not None:
                updated.append(msg)
            continue
        if updated is None:
            updated = [dict(m) for m in messages[:idx]]
        logger.warning(
            "Stripping {} malformed tool_call(s) with missing/non-string "
            "name from assistant history before request",
            len(calls) - len(kept),
        )
        repaired = dict(msg)
        if kept:
            repaired["tool_calls"] = kept
        else:
            repaired.pop("tool_calls", None)
        # An assistant turn with neither content nor any valid tool call is
        # itself invalid upstream; drop it entirely in that case.
        has_content = bool(repaired.get("content"))
        if not kept and not has_content:
            continue
        updated.append(repaired)

    if updated is None:
        return messages
    return updated


def drop_orphan_tool_results(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop invalid tool results before history is sent back to providers."""
    declared: set[str] = set()
    fulfilled: set[str] = set()
    updated: list[dict[str, Any]] | None = None
    for idx, msg in enumerate(messages):
        role = msg.get("role")
        if role == "assistant":
            for tc in cast(list[Any], msg.get("tool_calls") or []):
                if isinstance(tc, dict):
                    tool_call = cast(dict[str, Any], tc)
                    if tool_call.get("id"):
                        declared.add(str(tool_call["id"]))
        if role == "tool":
            tid = msg.get("tool_call_id")
            tid_str = str(tid) if tid else ""
            if not tid_str or tid_str not in declared or tid_str in fulfilled:
                if updated is None:
                    updated = [dict(m) for m in messages[:idx]]
                continue
            fulfilled.add(tid_str)
        if updated is not None:
            updated.append(dict(msg))

    if updated is None:
        return messages
    return updated


def backfill_missing_tool_results(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Insert synthetic error results for assistant tool_calls with missing tool outputs."""
    declared: list[tuple[int, str, str]] = []
    fulfilled: set[str] = set()
    for idx, msg in enumerate(messages):
        role = msg.get("role")
        if role == "assistant":
            for tc in cast(list[Any], msg.get("tool_calls") or []):
                if isinstance(tc, dict):
                    name = ""
                    tool_call = cast(dict[str, Any], tc)
                    if tool_call.get("id"):
                        func = tool_call.get("function")
                        if isinstance(func, dict):
                            func_data = cast(dict[str, Any], func)
                            raw_name = func_data.get("name", "")
                            name = raw_name if isinstance(raw_name, str) else str(raw_name)
                        declared.append((idx, str(tool_call["id"]), name))
        elif role == "tool":
            tid = msg.get("tool_call_id")
            if tid:
                fulfilled.add(str(tid))

    missing = [(ai, cid, name) for ai, cid, name in declared if cid not in fulfilled]
    if not missing:
        return messages

    updated = list(messages)
    offset = 0
    for assistant_idx, call_id, name in missing:
        insert_at = assistant_idx + 1 + offset
        while insert_at < len(updated) and updated[insert_at].get("role") == "tool":
            insert_at += 1
        updated.insert(
            insert_at,
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": BACKFILL_CONTENT,
            },
        )
        offset += 1
    return updated


def prepare_history(
    config: ContextGovernanceConfig,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    updated = strip_placeholder_assistant_messages(messages)
    updated = strip_malformed_tool_calls(updated)
    updated = drop_orphan_tool_results(updated)
    updated = backfill_missing_tool_results(updated)
    return apply_tool_result_budget(config, updated)


def prepare_messages(
    config: ContextGovernanceConfig,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build the normalized model-facing copy of a raw transcript."""
    governed = prepare_history(config, messages)
    return merge_adjacent_user_messages(governed)
