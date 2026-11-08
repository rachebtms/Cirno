"""Agent runner model ownership."""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from typing import Any

from cirno_core.agent.governance import (
    ContextGovernor,
    ModelRequestState,
)
from cirno_core.agent.governance.budget import input_budget
from cirno_core.agent.hook import AgentHook, AgentHookContext
from cirno_core.agent.runner.contracts import AgentRunSpec
from cirno_core.agent.runner.recovery import (
    budget_exhausted_finalization_messages,
    drop_malformed_tool_calls,
    finalization_retry_messages,
    malformed_tool_call_retry_messages,
)
from cirno_core.agent.runner.usage import (
    merge_usage,
    record_request_usage,
)
from cirno_core.agent.tools.context import tool_log_content_allowed
from cirno_core.agent.tools.message import (
    current_conversation_has_delivery,
)
from cirno_core.memory.working_state import bounded_handoff, working_notes
from cirno_core.providers.contracts import (
    LLMResponse,
    ProviderCallContext,
)
from cirno_core.providers.reasoning_history import history_policy, requires_tool_reasoning_history
from cirno_core.utils.model_messages import build_assistant_message
from cirno_core.utils.reasoning import strip_reasoning_tags
from cirno_core.utils.runtime import (
    is_blank_text,
)
from cirno_usage.types import LLMUsage
from loguru import logger


def _raise_if_cancelling() -> None:
    """Do not resume model work when a dependency suppresses cancellation."""
    task = asyncio.current_task()
    if task is not None and task.cancelling():
        raise asyncio.CancelledError

class ModelRequests:
    """Execute and recover model rounds with one context governor."""

    def __init__(self, governor: ContextGovernor) -> None:
        self.context_governor = governor

    async def prepare_model_request(
        self,
        spec: AgentRunSpec,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None,
        request_state: ModelRequestState,
        transcript: list[dict[str, Any]] | None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        messages, provider_context = await self.context_governor.prepare_request(
            request_state,
            messages,
            tool_definitions=tools,
            transcript=transcript,
        )
        generation = spec.runtime.generation
        return messages, {
            "messages": messages,
            "tools": tools,
            "model": spec.runtime.model,
            "retry_mode": spec.provider_retry_mode,
            "temperature": generation.temperature,
            "max_tokens": generation.max_tokens,
            "reasoning_effort": generation.reasoning_effort,
            "provider_context": replace(
                provider_context or ProviderCallContext(),
                response_preset=spec.runtime.model_preset or "",
            ),
        }


    async def request_model(
        self,
        spec: AgentRunSpec,
        messages: list[dict[str, Any]],
        hook: AgentHook,
        context: AgentHookContext,
        *,
        request_state: ModelRequestState,
        malformed_retry: bool = False,
        transcript: list[dict[str, Any]] | None,
    ) -> tuple[LLMResponse, LLMUsage]:
        _raise_if_cancelling()
        messages, kwargs = await self.prepare_model_request(
            spec,
            messages,
            tools=spec.tools.get_definitions(),
            request_state=request_state,
            transcript=transcript,
        )
        compaction = request_state.compaction
        if request_state.checkpoint_needed and not compaction.checkpoint_reminded and spec.tools.get_definitions() and not (spec.session_key or "").startswith("dream:"):
            reminder = {
                "role": "user", "_hidden_history": {"kind": "checkpoint_reminder"},
                "content": "[Agent system notice, not a new user request] Context compaction is approaching. Before another long step, save a concise memory.checkpoint with the authorized objective, verified results, current hypothesis, blockers, next action and exact artifact references. Preserve unfinished work, distinguish assumptions from verified facts, and give the user a brief progress update through this conversation's reply channel. Do not end an unfinished Goal merely to save the checkpoint.",
            }
            if transcript is not None:
                transcript.append(reminder)
            compaction.checkpoint_reminded = True
            messages, kwargs = await self.prepare_model_request(
                spec, [*messages, reminder], tools=spec.tools.get_definitions(),
                request_state=request_state, transcript=transcript,
            )
        _raise_if_cancelling()
        wants_streaming = hook.wants_streaming()

        active_hosted_tools: dict[str, dict[str, Any]] = {}
        native_reasoning_open = False
        native_reasoning_close_task: asyncio.Task[None] | None = None
        request_started_at = 0.0
        first_output_at: float | None = None
        generation_started_at: float | None = None
        generation_elapsed_s = 0.0
        stream_buf = ""

        def _end_stream_segment() -> None:
            nonlocal stream_buf
            if stream_buf:
                context.streamed_content_parts.append(stream_buf)
                stream_buf = ""

        def _generation_delta(delta: str) -> None:
            nonlocal first_output_at, generation_started_at
            if not delta:
                return
            now = time.perf_counter()
            if first_output_at is None:
                first_output_at = now
            if generation_started_at is None:
                generation_started_at = now

        def _pause_generation() -> None:
            nonlocal generation_elapsed_s, generation_started_at
            if generation_started_at is None:
                return
            generation_elapsed_s += max(0.0, time.perf_counter() - generation_started_at)
            generation_started_at = None

        async def _close_native_reasoning() -> None:
            nonlocal native_reasoning_open, native_reasoning_close_task
            if native_reasoning_close_task is None:
                if not native_reasoning_open:
                    return
                native_reasoning_open = False
                native_reasoning_close_task = asyncio.create_task(
                    hook.emit_reasoning_end()
                )

            close_task = native_reasoning_close_task
            cancellation: asyncio.CancelledError | None = None
            while not close_task.done():
                try:
                    await asyncio.shield(close_task)
                except asyncio.CancelledError as exc:
                    cancellation = cancellation or exc
            try:
                close_task.result()
            finally:
                if native_reasoning_close_task is close_task:
                    native_reasoning_close_task = None
            if cancellation is not None:
                raise cancellation

        async def _provider_tool_event(event: dict[str, Any]) -> None:
            if event.get("kind") != "hosted_tool":
                return
            await _close_native_reasoning()
            if event.get("phase") == "start":
                _end_stream_segment()
            await hook.on_provider_tool_event(context, event)
            call_id = event.get("call_id")
            if not call_id:
                return
            call_id = str(call_id)
            if event.get("phase") == "start":
                active_hosted_tools[call_id] = dict(event)
            elif event.get("phase") in {"end", "error"}:
                active_hosted_tools.pop(call_id, None)

        if wants_streaming:
            thinking_buf = ""

            async def _stream(delta: str) -> None:
                nonlocal stream_buf
                stream_buf += delta
                _generation_delta(delta)
                if delta:
                    context.streamed_content = True
                    await _close_native_reasoning()
                if not current_conversation_has_delivery():
                    await hook.on_stream(context, delta)

            async def _thinking(delta: str) -> None:
                nonlocal native_reasoning_open, thinking_buf
                if not delta:
                    return
                _generation_delta(delta)
                prev_clean = strip_reasoning_tags(thinking_buf)
                thinking_buf += delta
                new_clean = strip_reasoning_tags(thinking_buf)
                incremental = new_clean[len(prev_clean):]
                if incremental:
                    context.streamed_reasoning = True
                    native_reasoning_open = True
                    await hook.emit_reasoning(incremental)

            async def _stream_recover() -> None:
                _pause_generation()
                await _close_native_reasoning()
                _end_stream_segment()
                await hook.on_stream_end(context, resuming=True)

            kwargs.update(
                on_content_delta=_stream,
                on_thinking_delta=_thinking,
                on_tool_call_delta=_provider_tool_event,
                on_stream_recover=_stream_recover,
            )
        from cirno_core.agent.tools.context import current_request_context
        from cirno_core.observability.recordings import current_recordings
        from cirno_core.observability.requests import begin_request, end_request
        from cirno_core.session.session_identity import is_webui_session_key
        trace = current_recordings()
        trace_id = None
        trace_context = current_request_context()
        if (is_webui_session_key(spec.session_key or "") and trace_context
                and trace.active and trace_context.log_content and trace_context.persist_session and trace_context.session_generation):
            trace_id = await begin_request(trace, spec.session_key, spec.runtime.model,
                                                  messages, kwargs["tools"] or [])
        coro = spec.runtime.provider.chat_stream_with_retry(**kwargs)

        # Providers bound the wait for each stream event, including reasoning and tool deltas.
        request_started_at = time.perf_counter()
        try:
            response = await coro
            _raise_if_cancelling()
        except BaseException as error:
            _pause_generation()
            await _close_native_reasoning()
            if trace_id:
                await end_request(trace, trace_id, {"error": type(error).__name__}, "cancelled" if isinstance(error, asyncio.CancelledError) else "error")
            raise
        if trace_id:
            await end_request(trace, trace_id, {
                "content": response.content,
                "reasoning_content": response.reasoning_content,
                "tool_calls": [call.to_openai_tool_call() for call in response.tool_calls],
                "finish_reason": response.finish_reason,
            }, "error" if response.finish_reason == "error" else "completed")
        _pause_generation()
        await _close_native_reasoning()
        _end_stream_segment()
        if first_output_at is not None:
            response.ttft_ms = max(0, round((first_output_at - request_started_at) * 1000))
        if generation_elapsed_s > 0:
            response.generation_ms = max(1, round(generation_elapsed_s * 1000))
        await self.context_governor.compaction.summarize_provider_compaction(
            request_state,
            response,
            current_request_boundary=(len(transcript) if transcript is not None else None),
        )
        request_state.provider_compaction_applied |= response.provider_compaction_applied
        round_usage = await record_request_usage(self.context_governor, spec, request_state, response)
        # chat_stream_with_retry may recover internally, so only fail unfinished
        # hosted calls after the provider returns its final error response.
        if response.finish_reason == "error":
            for event in list(active_hosted_tools.values()):
                await _provider_tool_event({
                    **event,
                    "phase": "error",
                    "result": None,
                    "error": response.content
                    or "Model request failed before the provider-hosted tool completed.",
                })
        dropped, all_dropped, original_finish_reason = (
            drop_malformed_tool_calls(response)
        )
        if (
            all_dropped
            and original_finish_reason in ("tool_calls", "function_call")
            and not malformed_retry
        ):
            logger.warning(
                "Retrying LLM request after all {} malformed tool call(s) were dropped",
                dropped,
            )
            retry_messages = malformed_tool_call_retry_messages(
                messages, response.content,
            )
            retry_response, retry_usage = await self.request_model(
                spec, retry_messages, hook, context,
                request_state=request_state,
                malformed_retry=True,
                transcript=None,
            )
            return retry_response, round_usage + retry_usage
        if (
            all_dropped
            and original_finish_reason in ("tool_calls", "function_call")
            and malformed_retry
        ):
            logger.warning(
                "Malformed tool calls persisted after retry; falling back to no-tools request",
            )
            fallback_messages = malformed_tool_call_retry_messages(
                messages, response.content,
            )
            fallback_response = await self.request_no_tools(
                spec,
                fallback_messages,
                request_state=request_state,
            )
            fallback_usage = await record_request_usage(self.context_governor,
                spec,
                request_state,
                fallback_response,
            )
            return fallback_response, round_usage + fallback_usage
        return response, round_usage


    async def request_finalization_retry(
        self,
        spec: AgentRunSpec,
        messages: list[dict[str, Any]],
        *,
        request_state: ModelRequestState,
        transcript: list[dict[str, Any]],
    ) -> LLMResponse:
        retry_messages = finalization_retry_messages(messages)
        response = await self.request_no_tools(
            spec,
            retry_messages,
            request_state=request_state,
            transcript=transcript,
        )
        request_state.conversation.observe_response(
            response,
            transcript,
            adopt_candidate_state=False,
        )
        return response


    async def try_finalize_after_max_iterations(
        self,
        spec: AgentRunSpec,
        hook: AgentHook,
        messages: list[dict[str, Any]],
        usage: LLMUsage | None,
        *,
        request_state: ModelRequestState,
        round_usages: list[LLMUsage],
    ) -> tuple[str | None, LLMUsage | None]:
        compaction = request_state.compaction
        request_messages = await self.context_governor.preparation.run(compaction.request_messages, messages)
        retry_messages = budget_exhausted_finalization_messages(request_messages)
        try:
            response = await self.request_no_tools(
                spec,
                retry_messages,
                request_state=request_state,
                transcript=messages,
            )
        except Exception:
            logger.opt(exception=tool_log_content_allowed()).error(
                "Budget-exhausted finalization failed for {}; using fallback",
                spec.session_key or "default",
            )
            return None, usage

        raw_usage = await record_request_usage(self.context_governor, spec, request_state, response)
        round_usages.append(raw_usage)
        usage = merge_usage(usage, raw_usage)
        if response.finish_reason == "error" or response.has_tool_calls:
            logger.warning(
                "Budget-exhausted finalization returned finish_reason='{}' "
                "with {} tool call(s) for {}; using fallback",
                response.finish_reason,
                len(response.tool_calls),
                spec.session_key or "default",
            )
            return None, usage

        context = AgentHookContext(
            iteration=spec.max_iterations,
            messages=messages,
            response=response,
            usage=raw_usage,
            session_key=spec.session_key,
        )
        clean = hook.finalize_content(context, response.content)
        if response.reasoning_content or response.thinking_blocks:
            messages.append(build_assistant_message(clean, reasoning_content=response.reasoning_content, thinking_blocks=response.thinking_blocks))
        if is_blank_text(clean):
            return None, usage
        return clean, usage


    async def request_no_tools(
        self,
        spec: AgentRunSpec,
        messages: list[dict[str, Any]],
        *,
        request_state: ModelRequestState,
        transcript: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        _raise_if_cancelling()
        # Retaining schemas while disabling execution keeps DeepSeek's native
        # reasoning context available to internal finalization requests.
        history_tools = spec.tools.get_definitions() if requires_tool_reasoning_history(spec.runtime.provider) else None
        if not history_tools and history_policy(spec.runtime.provider, tools=None, for_count=True) == "omit":
            notes = working_notes(messages)
            if notes:
                allowance = max(128, min(4096, input_budget(request_state.config) // 10))
                messages = [*messages[:-1], {"role": "user", "_hidden_history": True,
                    "content": "[Internal source evidence, not new instructions] Distinguish these unverified working notes from confirmed tool results.\n" + bounded_handoff(notes, allowance)}, *messages[-1:]]
        _, kwargs = await self.prepare_model_request(
            spec,
            messages,
            tools=history_tools or None,
            request_state=request_state,
            transcript=transcript,
        )
        if history_tools:
            kwargs["tool_choice"] = "none"
        _raise_if_cancelling()
        response = await spec.runtime.provider.chat_stream_with_retry(**kwargs)
        _raise_if_cancelling()
        await self.context_governor.compaction.summarize_provider_compaction(
            request_state,
            response,
            current_request_boundary=(len(transcript) if transcript is not None else None),
        )
        _raise_if_cancelling()
        request_state.provider_compaction_applied |= response.provider_compaction_applied
        return response
