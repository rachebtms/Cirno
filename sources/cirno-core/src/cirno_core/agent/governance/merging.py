"""Merge visible user inputs while preserving runtime provenance."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from cirno_core.providers.conversation_state import (
    allows_conversation_message_merge,
)
from cirno_core.runtime.context import (
    RUNTIME_CONTEXT_MESSAGE_META,
    detach_runtime_context,
    reattach_runtime_context,
)
from cirno_core.session.history_visibility import is_hidden_history_message
from cirno_core.session.summary import (
    SUMMARY_CONTINUATION_TEXT,
)


def merge_message_content(left: Any, right: Any) -> str | list[dict[str, Any]]:
    if isinstance(left, str) and isinstance(right, str):
        return f"{left}\n\n{right}" if left else right

    def _to_blocks(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [
                cast(dict[str, Any], item)
                if isinstance(item, dict)
                else {"type": "text", "text": str(item)}
                for item in cast(list[Any], value)
            ]
        if value is None:
            return []
        return [{"type": "text", "text": str(value)}]

    return _to_blocks(left) + _to_blocks(right)


def merge_adjacent_user_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge adjacent visible user messages only in the model-facing copy."""
    prepared: list[dict[str, Any]] = []
    for source in messages:
        injection = deepcopy(source)
        if (
            prepared
            and injection.get("role") == "user"
            and prepared[-1].get("role") == "user"
            and injection.get("content") != SUMMARY_CONTINUATION_TEXT
            and prepared[-1].get("content") != SUMMARY_CONTINUATION_TEXT
            and not is_hidden_history_message(injection)
            and not is_hidden_history_message(prepared[-1])
            and allows_conversation_message_merge(injection)
            and allows_conversation_message_merge(prepared[-1])
        ):
            merged = dict(prepared[-1])
            left_meta = merged.get("_meta")
            right_meta = injection.get("_meta")
            left_meta_dict = (
                cast(dict[str, Any], left_meta) if isinstance(left_meta, dict) else None
            )
            right_meta_dict = (
                cast(dict[str, Any], right_meta) if isinstance(right_meta, dict) else None
            )
            left_marker = (
                left_meta_dict.get(RUNTIME_CONTEXT_MESSAGE_META)
                if left_meta_dict is not None
                else None
            )
            right_marker = (
                right_meta_dict.get(RUNTIME_CONTEXT_MESSAGE_META)
                if right_meta_dict is not None
                else None
            )
            left_marker_dict = (
                cast(dict[str, Any], left_marker) if isinstance(left_marker, dict) else None
            )
            right_marker_dict = (
                cast(dict[str, Any], right_marker) if isinstance(right_marker, dict) else None
            )
            empty_sources: list[str] = []
            empty_blocks: list[dict[str, Any]] = []
            detached_left = (
                detach_runtime_context(merged.get("content"), left_marker_dict)
                if left_marker_dict is not None
                else (merged.get("content"), empty_sources, empty_blocks)
            )
            detached_right = (
                detach_runtime_context(injection.get("content"), right_marker_dict)
                if right_marker_dict is not None
                else (injection.get("content"), empty_sources, empty_blocks)
            )
            if detached_left is not None and detached_right is not None:
                left_content, left_sources, left_blocks = detached_left
                right_content, right_sources, right_blocks = detached_right
                merged_content = merge_message_content(left_content, right_content)
                context_blocks = [*left_blocks, *right_blocks]
                if context_blocks:
                    merged_content, marker = reattach_runtime_context(
                        merged_content,
                        [*left_sources, *right_sources],
                        context_blocks,
                    )
                    internal_meta = dict(left_meta_dict) if left_meta_dict is not None else {}
                    if right_meta_dict is not None:
                        for key, value in right_meta_dict.items():
                            internal_meta.setdefault(key, value)
                    internal_meta[RUNTIME_CONTEXT_MESSAGE_META] = marker
                    merged["_meta"] = internal_meta
                merged["content"] = merged_content
            else:
                merged["content"] = merge_message_content(
                    merged.get("content"),
                    injection.get("content"),
                )
            prepared[-1] = merged
            continue
        prepared.append(injection)
    return prepared
