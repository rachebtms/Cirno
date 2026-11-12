"""Execute checkpoint/learning generation with sequential provider recovery only."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any, Callable

from cirno_usage.context import llm_usage_source
from loguru import logger
from cirno_core.providers.contracts import LLMResponse, ProviderCallContext
from cirno_core.providers.context_budget import ContextBudget
from cirno_core.providers.conversation_state import ProviderConversationStateController
from cirno_core.utils.llm_runtime import LLMRuntime
from cirno_core.utils.model_messages import build_assistant_message
from cirno_core.utils.token_estimation import estimate_prompt_tokens_chain

_ARCHIVE_TOOL_RESULT = (
    "Context consolidation does not execute tools. Return the requested task checkpoint "
    "and grounded learning now using only the supplied evidence. Do not call another tool."
)


async def generate_checkpoint(
    *,
    runtime: LLMRuntime,
    history: list[dict[str, Any]],
    request_messages: list[dict[str, Any]],
    call_tools: list[dict[str, Any]],
    provider_context: ProviderCallContext | None,
    state_controller: ProviderConversationStateController | None,
    state_messages: list[dict[str, Any]],
    on_model_request: Callable[[], None] | None = None,
) -> LLMResponse | None:
    response = None
    for attempt in range(runtime.compaction_max_retries + 1):
        try:
            measured = (
                state_controller.estimate_request_context_tokens(
                    state_messages, tool_definitions=call_tools
                )
                if state_controller is not None
                else None
            )
            if measured is None:
                measured, _ = await asyncio.to_thread(
                    estimate_prompt_tokens_chain,
                    runtime.provider,
                    runtime.model,
                    [*history, *request_messages]
                    if state_controller is not None
                    else request_messages,
                    call_tools,
                )
            max_output = ContextBudget(
                runtime.context_window_tokens, runtime.generation.max_tokens
            ).output_limit(measured)
            provider_context = replace(
                provider_context or ProviderCallContext(),
                context_window_tokens=runtime.context_window_tokens,
                input_tokens=measured,
            )
            with llm_usage_source("consolidation"):
                if on_model_request is not None:
                    on_model_request()
                response = await runtime.provider.chat_stream_with_retry(
                    model=runtime.model,
                    messages=request_messages,
                    tools=call_tools,
                    temperature=runtime.generation.temperature,
                    max_tokens=max_output,
                    reasoning_effort=runtime.generation.reasoning_effort,
                    provider_context=provider_context,
                )
        except Exception:
            phase = "provider call" if attempt == 0 else "tool-call recovery"
            logger.opt(exception=True).warning(
                "Memory archive {} failed; using raw checkpoint",
                phase,
            )
            if attempt < runtime.compaction_max_retries:
                continue
            return None
        if response.finish_reason in {"error", "length"} or not response.content and not response.should_execute_tools:
            if attempt < runtime.compaction_max_retries:
                continue
            return response
        if response.should_execute_tools is not True or attempt == runtime.compaction_max_retries:
            break

        logger.info(
            "Memory archive provider returned {} tool call(s); requesting checkpoint",
            len(response.tool_calls),
        )
        assistant_message = build_assistant_message(
            response.content,
            tool_calls=[call.to_openai_tool_call() for call in response.tool_calls],
            reasoning_content=response.reasoning_content,
            thinking_blocks=response.thinking_blocks,
        )
        tool_messages = [
            {
                "role": "tool",
                "tool_call_id": call.id,
                "name": call.name,
                "content": _ARCHIVE_TOOL_RESULT,
            }
            for call in response.tool_calls
        ]
        request_messages = [
            *request_messages,
            assistant_message,
            *tool_messages,
        ]
        if state_controller is not None:
            state_controller.observe_response(
                response,
                state_messages,
            )
            state_messages.extend(
                [
                    state_controller.project_response_message(
                        dict(assistant_message),
                        response,
                    ),
                    *[dict(message) for message in tool_messages],
                ]
            )
            provider_context = state_controller.prepare_request(
                state_messages,
                context_window_tokens=runtime.context_window_tokens,
            )
            if provider_context is None or provider_context.conversation_state is None:
                return None
    assert response is not None
    return response
