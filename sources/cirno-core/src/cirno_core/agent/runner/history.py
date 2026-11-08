"""Agent runner history ownership."""

from __future__ import annotations

from typing import Any

from cirno_core.agent.governance import (
    ContextCompactionState,
)
from cirno_core.agent.runner.contracts import AgentRunSpec
from cirno_core.utils.model_messages import build_assistant_message
from cirno_core.utils.runtime import (
    is_blank_text,
)


def restore_outer_whitespace(content: str, original: str | None) -> str:
    """Restore boundary whitespace stripped while cleaning one recovered segment."""
    if not original:
        return content
    leading_size = len(original) - len(original.lstrip())
    trailing_size = len(original) - len(original.rstrip())
    leading = original[:leading_size]
    trailing = original[-trailing_size:] if trailing_size else ""
    return f"{leading}{content}{trailing}"

_PERSISTED_MODEL_ERROR_PLACEHOLDER = "[Assistant reply unavailable due to model error.]"
def initial_transcript_and_compaction(
    spec: AgentRunSpec,
) -> tuple[list[dict[str, Any]], ContextCompactionState]:
    """Build the initial transcript and its compaction state."""
    consolidate_history = spec.consolidate_history
    if consolidate_history is None:
        raise ValueError("consolidate_history is required")
    transcript_input = spec.transcript_input
    if transcript_input is not None:
        if spec.initial_messages is not None:
            raise ValueError("provide either transcript_input or initial_messages, not both")
        transcript_builder = spec.transcript_builder
        if transcript_builder is None:
            raise ValueError("transcript_builder is required with transcript_input")
        return ContextCompactionState.from_transcript(
            transcript_input,
            transcript_builder,
            consolidate_history,
            spec.consolidate_provider_compaction,
        )
    if spec.initial_messages is None:
        raise ValueError("initial_messages is required without transcript_input")
    messages = list(spec.initial_messages)
    return messages, ContextCompactionState.from_messages(
        messages,
        consolidate_history,
        spec.consolidate_provider_compaction,
    )


async def emit_checkpoint(
    spec: AgentRunSpec,
    payload: dict[str, Any],
) -> None:
    callback = spec.checkpoint_callback
    if callback is not None:
        await callback(payload)


def append_final_message(messages: list[dict[str, Any]], content: str | None) -> None:
    if not content:
        return
    if (
        messages
        and messages[-1].get("role") == "assistant"
        and not messages[-1].get("tool_calls")
        and not (is_blank_text(messages[-1].get("content")) and (messages[-1].get("reasoning_content") or messages[-1].get("thinking_blocks")))
    ):
        if messages[-1].get("content") == content:
            return
        messages[-1] = build_assistant_message(content)
        return
    messages.append(build_assistant_message(content))


def append_model_error_placeholder(messages: list[dict[str, Any]]) -> None:
    if messages and messages[-1].get("role") == "assistant" and not messages[-1].get("tool_calls"):
        return
    messages.append(build_assistant_message(_PERSISTED_MODEL_ERROR_PLACEHOLDER))
