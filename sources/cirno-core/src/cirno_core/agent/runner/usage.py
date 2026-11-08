"""Agent runner usage ownership."""

from __future__ import annotations

from typing import Any

from cirno_core.agent.governance import (
    ContextGovernor,
    ModelRequestState,
)
from cirno_core.agent.runner.contracts import AgentRunSpec
from cirno_core.providers.contracts import (
    LLMResponse,
)
from cirno_core.utils.model_messages import build_assistant_message
from cirno_core.utils.token_estimation import estimate_message_tokens, estimate_prompt_tokens_chain
from cirno_usage.types import LLMUsage


def usage_or_estimate(
    spec: AgentRunSpec,
    messages: list[dict[str, Any]],
    response: LLMResponse,
    *,
    tool_definitions: list[dict[str, Any]] | None,
) -> LLMUsage:
    usage = response.usage
    if response.finish_reason == "error":
        if usage is None or usage.total_tokens == 0:
            usage = LLMUsage.empty_request()
    elif usage is None or usage.total_tokens == 0:
        usage = estimate_response_usage(
            spec,
            messages,
            response,
            tool_definitions=tool_definitions,
        )
    return usage.with_timing(
        generation_ms=response.generation_ms,
        ttft_ms=response.ttft_ms,
    )


async def record_request_usage(
    governor: ContextGovernor,
    spec: AgentRunSpec,
    state: ModelRequestState,
    response: LLMResponse,
) -> LLMUsage:
    assert state.messages is not None
    if response.finish_reason != "error" and (
        response.usage is None or response.usage.total_tokens == 0
    ):
        usage = await governor.preparation.run(
            usage_or_estimate, spec, state.messages, response,
            tool_definitions=state.tool_definitions,
        )
    else:
        usage = usage_or_estimate(
            spec, state.messages, response, tool_definitions=state.tool_definitions,
        )
    # A rewritten input or another model's count cannot bound the next request.
    state.usage = None if response.provider_compaction_applied or response.is_fallback else usage
    return usage


def estimate_response_usage(
    spec: AgentRunSpec,
    messages: list[dict[str, Any]],
    response: LLMResponse,
    *,
    tool_definitions: list[dict[str, Any]] | None,
) -> LLMUsage:
    prompt_tokens, _ = estimate_prompt_tokens_chain(
        spec.runtime.provider,
        spec.runtime.model,
        messages,
        tool_definitions,
    )
    assistant_message = build_assistant_message(
        response.content or "",
        tool_calls=[tc.to_openai_tool_call() for tc in response.tool_calls],
        reasoning_content=response.reasoning_content,
        thinking_blocks=response.thinking_blocks,
    )
    completion_tokens = estimate_message_tokens(assistant_message)
    return LLMUsage.estimated(
        input_tokens=max(0, prompt_tokens),
        output_tokens=max(0, completion_tokens),
    )


def merge_usage(
    left: LLMUsage | None,
    right: LLMUsage | None,
) -> LLMUsage | None:
    if left is None:
        return right
    if right is None:
        return left
    return left + right
