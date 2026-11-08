"""Agent runner recovery ownership."""

from __future__ import annotations

from typing import Any

from cirno_core.agent.runner.contracts import AgentRunSpec
from cirno_core.providers.contracts import (
    LLMResponse,
)
from cirno_core.utils.prompt_templates import render_template
from cirno_core.utils.runtime import (
    build_budget_exhausted_finalization_message,
    build_finalization_retry_message,
)
from loguru import logger


def drop_malformed_tool_calls(
    response: LLMResponse,
) -> tuple[int, bool, str | None]:
    """Strip tool calls whose name is missing/non-string from the response.

    Returns (dropped_count, all_dropped, original_finish_reason).

    A degenerate call (name=None or "") cannot be executed, and if it were
    persisted into the assistant message it would be replayed on every
    subsequent turn, causing upstream validation errors
    (``tool_use.name: Input should be a valid string``) that permanently
    wedge the session. Dropping it here keeps it out of execution, the
    assistant message, and the saved history in one place.
    """
    calls = getattr(response, "tool_calls", None)
    if not calls:
        return (0, False, getattr(response, "finish_reason", None))
    valid = [tc for tc in calls if tc.has_valid_name()]
    if len(valid) == len(calls):
        return (0, False, getattr(response, "finish_reason", None))
    dropped = len(calls) - len(valid)
    original_finish_reason = getattr(response, "finish_reason", None)
    logger.warning(
        "Dropped {} malformed tool call(s) with missing/non-string name "
        "from LLM response (finish_reason={!r})",
        dropped,
        original_finish_reason,
    )
    response.tool_calls = valid
    # The opaque candidate still contains every raw function_call item.
    # Advancing it after dropping even one call would replay an unmatched
    # call without a corresponding tool output on the next request.
    response.provider_state = None
    if not valid:
        response.finish_reason = "stop"
    return (dropped, not valid, original_finish_reason)


def malformed_tool_call_retry_messages(
    messages: list[dict[str, Any]],
    assistant_text: str | None,
) -> list[dict[str, Any]]:
    retry_messages = list(messages)
    note = (
        "The previous model response attempted to call tools, but every tool call "
        "was malformed: the tool_use blocks had missing or non-string tool names. "
        "Do not answer with a promise to use tools. Either call the required tools again "
        "using valid tool names from the provided tool list and JSON object inputs, or give "
        "a final answer only if no tool is required."
    )
    if assistant_text:
        note += (
            f"\n\nPrevious assistant text before the malformed calls:\n"
            f"{assistant_text}"
        )
    retry_messages.append({"role": "user", "content": note})
    return retry_messages


def finalization_retry_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    retry_messages = list(messages)
    retry_messages.append(build_finalization_retry_message())
    return retry_messages


def budget_exhausted_finalization_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    retry_messages = list(messages)
    retry_messages.append(build_budget_exhausted_finalization_message())
    return retry_messages


def max_iterations_fallback(spec: AgentRunSpec) -> str:
    if spec.max_iterations_message:
        return spec.max_iterations_message.format(
            max_iterations=spec.max_iterations,
        )
    return render_template(
        "agent/max_iterations_message.md",
        strip=True,
        max_iterations=spec.max_iterations,
    )
