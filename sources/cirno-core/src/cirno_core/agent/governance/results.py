"""Normalize oversized tool output into workspace-backed references."""

from __future__ import annotations

from typing import Any, cast

from cirno_core.agent.governance.contracts import ContextGovernanceConfig
from cirno_core.agent.tools.naming import implementation_name
from cirno_core.utils.runtime import ensure_nonempty_tool_result
from cirno_core.utils.text import truncate_text
from cirno_core.utils.tool_results import maybe_persist_tool_result

TOOL_RESULT_OFFLOAD_EXEMPT_TOOLS = frozenset({"read_file"})


def normalize_tool_result(
    config: ContextGovernanceConfig,
    tool_call_id: str,
    tool_name: str,
    result: Any,
) -> Any:
    result = ensure_nonempty_tool_result(tool_name, result)
    if implementation_name(tool_name) in TOOL_RESULT_OFFLOAD_EXEMPT_TOOLS:
        return result

    def persist_text(text: str, call_id: str) -> str:
        content = maybe_persist_tool_result(
            config.workspace,
            config.session_key,
            call_id,
            text,
            max_chars=config.max_tool_result_chars,
        )
        # Persisted references must retain their complete paths.
        return (
            truncate_text(content, config.max_tool_result_chars)
            if config.workspace is None
            else content
        )

    if isinstance(result, str):
        return persist_text(result, tool_call_id)
    if isinstance(result, list):
        result = cast(list[object], result)
        blocks: list[dict[str, Any]] = []
        for raw_block in result:
            if not isinstance(raw_block, dict):
                return result
            block = cast(dict[str, Any], raw_block)
            if not isinstance(block.get("type"), str):
                return result
            if block["type"] == "text" and not isinstance(block.get("text"), str):
                return result
            blocks.append(block)
        # Image redaction must not change how neighboring text is normalized.
        return [
            {**block, "text": persist_text(block["text"], f"{tool_call_id}_text_{index}")}
            if block["type"] == "text"
            else block
            for index, block in enumerate(blocks)
        ]
    return result


def apply_tool_result_budget(
    config: ContextGovernanceConfig,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    updated = messages
    for idx, message in enumerate(messages):
        if message.get("role") != "tool":
            continue
        normalized = normalize_tool_result(
            config,
            str(message.get("tool_call_id") or f"tool_{idx}"),
            str(message.get("name") or "tool"),
            message.get("content"),
        )
        if normalized != message.get("content"):
            if updated is messages:
                updated = [dict(m) for m in messages]
            updated[idx]["content"] = normalized
    return updated
