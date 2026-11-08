"""Conversation recovery checkpoints ownership."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast

from cirno_core.session.model import Session

from .contracts import (
    PENDING_USER_TURN_KEY,
    PROVIDER_STATE_CHECKPOINT_VERSION,
    PROVIDER_STATE_CHECKPOINT_VERSION_KEY,
    RUNTIME_CHECKPOINT_KEY,
)


def _checkpoint_message_key(message: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        message.get("role"),
        message.get("content"),
        message.get("tool_call_id"),
        message.get("name"),
        message.get("tool_calls"),
        message.get("reasoning_content"),
        message.get("thinking_blocks"),
    )


def _checkpoint_tool_call_ids(
    value: object,
    *,
    result_rows: bool = False,
) -> list[str] | None:
    """Validate checkpoint tool rows and return their stable IDs."""
    if not isinstance(value, list):
        return None
    ids: list[str] = []
    for raw in cast(list[object], value):
        if not isinstance(raw, dict):
            return None
        row = cast(dict[str, Any], raw)
        id_key = "tool_call_id" if result_rows else "id"
        call_id = cast(object, row.get(id_key))
        if not isinstance(call_id, str) or not call_id:
            return None
        if result_rows:
            if row.get("role") != "tool":
                return None
        else:
            function_value = cast(object, row.get("function"))
            if not isinstance(function_value, dict):
                return None
            function = cast(dict[str, Any], function_value)
            name = cast(object, function.get("name"))
            if not isinstance(name, str) or not name:
                return None
        ids.append(call_id)
    return ids if len(ids) == len(set(ids)) else None


def runtime_checkpoint_is_well_formed(checkpoint: Mapping[str, Any]) -> bool:
    """Return whether a checkpoint is safe to offer for continuation.

    Restoration stays tolerant so Dismiss can always clear corrupt state.
    Continue is stricter: silently dropping a malformed tool result could make
    the model repeat an external side effect.
    """
    assistant_value = cast(object, checkpoint.get("assistant_message"))
    if not isinstance(assistant_value, dict):
        return False
    assistant = cast(dict[str, Any], assistant_value)
    if assistant.get("role") != "assistant":
        return False

    completed_ids = _checkpoint_tool_call_ids(
        cast(object, checkpoint.get("completed_tool_results")),
        result_rows=True,
    )
    pending_ids = _checkpoint_tool_call_ids(
        cast(object, checkpoint.get("pending_tool_calls")),
    )
    if completed_ids is None or pending_ids is None:
        return False
    assistant_calls_value = cast(object, assistant.get("tool_calls"))
    assistant_call_ids = (
        [] if assistant_calls_value is None else _checkpoint_tool_call_ids(assistant_calls_value)
    )
    if assistant_call_ids is None:
        return False

    phase = checkpoint.get("phase")
    if phase == "final_response":
        content = cast(object, assistant.get("content"))
        return (
            isinstance(content, str)
            and bool(content.strip())
            and not assistant_call_ids
            and not completed_ids
            and not pending_ids
        )
    if phase == "awaiting_tools":
        return (
            bool(assistant_call_ids)
            and not completed_ids
            and len(assistant_call_ids) == len(pending_ids)
            and set(assistant_call_ids) == set(pending_ids)
        )
    if phase == "tools_completed":
        return (
            bool(assistant_call_ids)
            and not pending_ids
            and len(assistant_call_ids) == len(completed_ids)
            and set(assistant_call_ids) == set(completed_ids)
        )
    # Error checkpoints have no current producer contract. Treat legacy or
    # future instances as review-only until their exact persisted shape is
    # specified; guessing here could make a partial side effect repeat.
    return False


def restore_runtime_checkpoint(session: Session) -> bool:
    """Materialize the durable checkpoint exactly once and clear it.

    Pending tool calls become explicit interrupted tool results.  They are
    never executed here.  Provider-native state is retained only for the two
    checkpoint shapes known to be synchronized with persisted history.
    """
    checkpoint = cast(object, session.metadata.get(RUNTIME_CHECKPOINT_KEY))
    if not isinstance(checkpoint, dict):
        return False
    data = cast(dict[str, Any], checkpoint)
    assistant = cast(object, data.get("assistant_message"))
    completed_value = cast(object, data.get("completed_tool_results"))
    pending_value = cast(object, data.get("pending_tool_calls"))
    completed = cast(list[object], completed_value) if isinstance(completed_value, list) else []
    pending = cast(list[object], pending_value) if isinstance(pending_value, list) else []

    restored: list[dict[str, Any]] = []
    if isinstance(assistant, dict):
        assistant_row = cast(dict[str, Any], assistant)
    else:
        assistant_row = {}
    if assistant_row.get("role") == "assistant":
        row = dict(assistant_row)
        row.setdefault("timestamp", datetime.now().isoformat())
        restored.append(row)
    for value in completed:
        if not isinstance(value, dict):
            continue
        tool_result = cast(dict[str, Any], value)
        if tool_result.get("role") != "tool":
            continue
        row = dict(tool_result)
        row.setdefault("timestamp", datetime.now().isoformat())
        restored.append(row)
    for value in pending:
        if not isinstance(value, dict):
            continue
        tool_call = cast(dict[str, Any], value)
        tool_call_id = tool_call.get("id")
        function_value = cast(object, tool_call.get("function"))
        if not isinstance(tool_call_id, str) or not tool_call_id:
            continue
        function = cast(dict[str, Any], function_value) if isinstance(function_value, dict) else {}
        name = function.get("name")
        restored.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": name if isinstance(name, str) and name else "tool",
                "content": "Error: Task interrupted before this tool finished.",
                "timestamp": datetime.now().isoformat(),
                "_recovery_interrupted": True,
            }
        )

    overlap = 0
    for size in range(min(len(session.messages), len(restored)), 0, -1):
        if all(
            _checkpoint_message_key(left) == _checkpoint_message_key(right)
            for left, right in zip(session.messages[-size:], restored[:size])
        ):
            overlap = size
            break
    session.messages.extend(restored[overlap:])

    assistant_data = cast(dict[str, Any], assistant) if isinstance(assistant, dict) else None
    synchronized = (
        data.get(PROVIDER_STATE_CHECKPOINT_VERSION_KEY) == PROVIDER_STATE_CHECKPOINT_VERSION
    )
    phase = data.get("phase")
    exact_final = (
        phase == "final_response"
        and assistant_data is not None
        and assistant_data.get("role") == "assistant"
        and not data.get("completed_tool_results")
        and not data.get("pending_tool_calls")
    )
    exact_tools = (
        phase == "tools_completed"
        and assistant_data is not None
        and assistant_data.get("role") == "assistant"
        and not data.get("pending_tool_calls")
    )
    if not (synchronized and (exact_final or exact_tools)):
        session.provider_state = None

    session.metadata.pop(PENDING_USER_TURN_KEY, None)
    session.metadata.pop(RUNTIME_CHECKPOINT_KEY, None)
    session.updated_at = datetime.now()
    return True


def discard_runtime_checkpoint(session: Session) -> bool:
    """Drop checkpoint state that cannot be projected into valid history."""
    if RUNTIME_CHECKPOINT_KEY not in session.metadata:
        return False
    session.metadata.pop(RUNTIME_CHECKPOINT_KEY, None)
    session.provider_state = None
    session.updated_at = datetime.now()
    return True
