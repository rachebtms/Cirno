"""Agent runner inputs ownership."""

from __future__ import annotations

from typing import Any, cast

from cirno_core.agent.runner.contracts import AgentRunSpec
from cirno_core.agent.runner.history import (
    emit_checkpoint,
)
from cirno_core.agent.tools.context import tool_log_content_allowed
from cirno_core.agent.tools.message import (
    reset_message_delivery_segment,
)
from cirno_core.providers.conversation_state import ProviderConversationStateController
from cirno_core.session.history_visibility import is_hidden_history_message
from loguru import logger


def append_injected_messages(
    messages: list[dict[str, Any]],
    injections: list[dict[str, Any]],
) -> None:
    """Append injected messages without rewriting the raw transcript."""
    messages.extend(injections)


async def try_drain_injections(
    spec: AgentRunSpec,
    messages: list[dict[str, Any]],
    assistant_message: dict[str, Any] | None,
    injection_cycles: int,
    *,
    conversation_state: ProviderConversationStateController | None = None,
    phase: str = "after error",
    iteration: int | None = None,
    allow_continuation: bool = False,
    wait_at_terminal: bool = False,
    drain_callback: bool = True,
) -> tuple[bool, int]:
    """Append one pending-input snapshot and return whether execution continues."""
    injections = await drain_injections(spec) if drain_callback else []
    real_injection = bool(injections)
    if not injections and allow_continuation and assistant_message is not None:
        continuation = await build_continuation_message(spec)
        if continuation is not None:
            injections = [continuation]
    if (
        not injections
        and wait_at_terminal
        and drain_callback
    ):
        injections = await drain_injections(spec, terminal=True)
        real_injection = bool(injections)
    if not injections:
        return False, injection_cycles
    if real_injection:
        injection_cycles += 1
    if assistant_message is not None:
        messages.append(assistant_message)
        if iteration is not None:
            checkpoint: dict[str, Any] = {
                "phase": "final_response",
                "iteration": iteration,
                "model": spec.runtime.model,
                "assistant_message": assistant_message,
                "completed_tool_results": [],
                "pending_tool_calls": [],
            }
            if conversation_state is not None:
                checkpoint["provider_state"] = conversation_state.checkpoint(
                    messages
                )
            await emit_checkpoint(
                spec,
                checkpoint,
            )
    reset_message_delivery_segment()
    append_injected_messages(messages, injections)
    if real_injection:
        preview = "[content hidden]"
        if tool_log_content_allowed():
            preview = "\n\n".join(
                message["content"] for message in injections
                if isinstance(message.get("content"), str)
                and not is_hidden_history_message(message)
            )
            preview = preview[:80] + "..." if len(preview) > 80 else preview
        logger.info(
            "Injected {} follow-up message(s) {} (snapshot {}): {}",
            len(injections), phase, injection_cycles, preview,
        )
    else:
        logger.info("Injected caller-requested continuation {}", phase)
    return True, injection_cycles


async def build_continuation_message(spec: AgentRunSpec) -> dict[str, str] | None:
    callback = spec.continuation_callback
    if callback is None:
        return None
    try:
        content = await callback()
    except Exception:
        logger.opt(exception=tool_log_content_allowed()).error("continuation_callback failed")
        raise
    if content is None or not content.strip():
        return None
    return {"role": "user", "content": content}


async def drain_injections(
    spec: AgentRunSpec,
    *,
    terminal: bool = False,
) -> list[dict[str, Any]]:
    """Drain one pending-input snapshot via the injection callback."""
    callback = (
        spec.terminal_injection_callback
        if terminal
        else spec.injection_callback
    )
    if callback is None:
        return []
    try:
        items = await callback()
    except Exception:
        logger.opt(exception=tool_log_content_allowed()).error("injection_callback failed")
        raise
    if not items:
        return []
    injected_messages: list[dict[str, Any]] = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, dict):
            message_item = cast(dict[str, Any], item)
            if message_item.get("role") in {"user", "system"} and "content" in message_item:
                if has_injection_content(message_item.get("content")):
                    injected_messages.append(message_item)
            continue
        content = getattr(item, "content") if hasattr(item, "content") else str(item)
        if has_injection_content(content):
            injected_messages.append({"role": getattr(item, "input_role", None) or "user", "content": content})
    return injected_messages


def has_injection_content(content: Any) -> bool:
    if content is None:
        return False
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return bool(cast(list[Any], content))
    return True
