"""Shared execution loop for tool-using agents."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from copy import deepcopy
from typing import Any, ParamSpec, TypeVar

from cirno_core.agent.governance import (
    ContextCompactionState,
    ContextGovernanceConfig,
    ContextGovernor,
    ModelRequestState,
)
from cirno_core.agent.hook import AgentHook, AgentHookContext, AgentRunHookContext
from cirno_core.agent.runner.contracts import DEFAULT_ERROR_MESSAGE, AgentRunResult, AgentRunSpec
from cirno_core.agent.runner.history import (
    append_final_message,
    append_model_error_placeholder,
    emit_checkpoint,
    initial_transcript_and_compaction,
    restore_outer_whitespace,
)
from cirno_core.agent.runner.inputs import (
    try_drain_injections,
)
from cirno_core.agent.runner.model import ModelRequests
from cirno_core.agent.runner.reply_contract import ToolReplyContract
from cirno_core.agent.runner.recovery import (
    max_iterations_fallback,
)
from cirno_core.agent.runner.tool_results import commit_completed_tools
from cirno_core.agent.runner.usage import (
    merge_usage,
    record_request_usage,
)
from cirno_core.agent.tools.context import tool_log_content_allowed
from cirno_core.agent.tools.execution import execute_tool_calls
from cirno_core.agent.tools.role_policy import RoleToolPolicy
from cirno_core.session.roles import conversation_role
from cirno_core.agent.tools.message import (
    current_conversation_has_delivery,
)
from cirno_core.providers.conversation_state import ProviderConversationStateController
from cirno_core.providers.errors import is_billing_error, public_error_kind
from cirno_core.utils.cancellation import shield_and_drain
from cirno_core.utils.model_messages import build_assistant_message
from cirno_core.utils.reasoning import extract_reasoning
from cirno_core.utils.runtime import (
    EMPTY_FINAL_RESPONSE_MESSAGE,
    build_length_recovery_message,
    is_blank_text,
)
from cirno_usage.context import (
    bind_llm_usage_source,
    reset_llm_usage_source,
    source_from_session_key,
)
from cirno_usage.types import LLMUsage
from loguru import logger

_ARREARAGE_ERROR_MESSAGE = (
    "The AI provider rejected the request because the API key is out of quota or the "
    "account is in arrears. Please top up / check the billing status of your API key and try again."
)
_MAX_EMPTY_RETRIES = 2
_MAX_LENGTH_RECOVERIES = 3
_PromptArgs = ParamSpec("_PromptArgs")
_PromptResult = TypeVar("_PromptResult")


class AgentRunner:
    """Run a tool-capable LLM loop without product-layer concerns."""

    def __init__(self) -> None:
        self.context_governor = ContextGovernor()
        self.model_requests = ModelRequests(self.context_governor)

    async def prepare_prompt(
        self, operation: Callable[_PromptArgs, _PromptResult],
        *args: _PromptArgs.args, **kwargs: _PromptArgs.kwargs,
    ) -> _PromptResult:
        """Share the bounded context worker for prompt filesystem preparation."""
        return await self.context_governor.preparation.run(operation, *args, **kwargs)

    async def _run_context_snapshot(
        self, hook: AgentHook, messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not messages or not hook.has_run_hooks():
            return []
        return await asyncio.to_thread(deepcopy, messages)


    async def run(self, spec: AgentRunSpec) -> AgentRunResult:
        hook = spec.hook or AgentHook()
        has_run_hooks = hook.has_run_hooks()
        messages: list[dict[str, Any]] = []
        context = AgentRunHookContext(messages=[])
        llm_usage_source_token = bind_llm_usage_source(
            spec.llm_usage_source or source_from_session_key(spec.session_key)
        )

        try:
            try:
                try:
                    messages, compaction = await self.prepare_prompt(initial_transcript_and_compaction, spec)
                    context.messages = await self._run_context_snapshot(hook, messages) if has_run_hooks else []
                    await hook.before_run(context)
                    result = await self._run_core(spec, hook, messages, compaction)
                except Exception as exc:
                    context.messages = await self._run_context_snapshot(hook, messages) if has_run_hooks else []
                    context.stop_reason = "error"
                    context.error = f"Error: {type(exc).__name__}: {exc}"
                    context.exception = exc
                    await hook.on_error(context)
                    raise
                else:
                    context.messages = await self._run_context_snapshot(hook, result.messages) if has_run_hooks else []
                    context.final_content = result.final_content
                    context.tools_used = list(result.tools_used)
                    context.usage = result.usage
                    context.stop_reason = result.stop_reason
                    context.error = result.error
                    context.tool_events = deepcopy(result.tool_events)
                    context.had_injections = result.had_injections
                    context.exception = None
                    if context.error is not None:
                        await hook.on_error(context)
                    await hook.after_run(context)
                    return result
            except asyncio.CancelledError as exc:
                context.stop_reason = "cancelled"
                context.error = None
                context.exception = exc
                raise
            finally:
                if has_run_hooks:
                    try:
                        context.messages = await self._run_context_snapshot(hook, messages)
                    except asyncio.CancelledError as exc:
                        context.stop_reason = "cancelled"
                        context.error = None
                        context.exception = exc
                        context.messages = await self._run_context_snapshot(hook, messages)
                        raise
        finally:
            try:
                if context.exception is None:
                    await hook.on_finally(context)
                else:
                    try:
                        await hook.on_finally(context)
                    except Exception:
                        logger.opt(exception=tool_log_content_allowed()).error(
                            "AgentHook.on_finally error after {}",
                            context.stop_reason or "run exception",
                        )
            finally:
                reset_llm_usage_source(llm_usage_source_token)


    async def _run_core(
        self,
        spec: AgentRunSpec,
        hook: AgentHook,
        messages: list[dict[str, Any]],
        compaction: ContextCompactionState,
    ) -> AgentRunResult:
        final_content: str | None = None
        tools_used: list[str] = []
        usage: LLMUsage | None = None
        round_usages: list[LLMUsage] = []
        error: str | None = None
        failure_error_kind: str | None = None
        stop_reason = "completed"
        tool_events: list[dict[str, str]] = []
        external_lookup_counts: dict[str, int] = {}
        # Per-turn throttle for repeated attempts against the same outside target.
        workspace_violation_counts: dict[str, int] = {}
        empty_content_retries = 0
        # Segments from one uninterrupted length-recovery chain. Tool work or
        # injected user input starts a new logical answer and clears the chain.
        length_recovery_parts: list[str] = []
        pending_length_segment: tuple[AgentHookContext, str] | None = None
        had_injections = False
        injection_cycles = 0
        reply_contract = ToolReplyContract(spec.require_visible_reply)
        role_policy = RoleToolPolicy(conversation_role(spec.session_key)) if spec.session_key else None
        pending_stream_content: str | None = None
        conversation_state = ProviderConversationStateController(
            provider=spec.runtime.provider,
            model=spec.runtime.model,
            messages=messages,
            state=spec.provider_state,
            session_id=spec.session_key,
        )
        governance_config = ContextGovernanceConfig(
            provider=spec.runtime.provider,
            model=spec.runtime.model,
            tools=spec.tools,
            workspace=spec.workspace,
            session_key=spec.session_key,
            max_tool_result_chars=spec.max_tool_result_chars,
            context_window_tokens=spec.runtime.context_window_tokens,
            max_tokens=spec.runtime.generation.max_tokens,
            active_compact_percent=spec.runtime.active_compact_percent,
            checkpoint_reminder_percent=spec.runtime.checkpoint_reminder_percent,
            output_reserve_percent=spec.runtime.output_reserve_percent,
        )
        request_state = ModelRequestState(
            config=governance_config,
            conversation=conversation_state,
            compaction=compaction,
            events=spec.events,
        )

        async def end_length_segment(*, interrupted: bool) -> None:
            nonlocal pending_length_segment
            if pending_length_segment is None:
                return
            segment_context, segment_content = pending_length_segment
            pending_length_segment = None
            if interrupted:
                length_recovery_parts.clear()
            else:
                messages.append(build_length_recovery_message(
                    segment_content,
                    tool_replies=bool(role_policy and role_policy.role.tool_replies) or spec.require_visible_reply,
                    discarded_tool_calls=bool(segment_context.response and segment_context.response.has_tool_calls),
                ))
            if hook.wants_streaming():
                segment_context.stream_continues_current_message = not interrupted
                await hook.on_stream_end(segment_context, resuming=True)

        for iteration in range(spec.max_iterations):
            # A resumed iteration must not inherit a previous iteration's failure.
            stop_reason = "completed"
            error = None
            # The session inbox cuts a finite snapshot before every model call.
            # This includes follow-ups that arrived before the first request and
            # messages received while the previous request or tools were running.
            drained_before_request, injection_cycles = await try_drain_injections(
                spec,
                messages,
                None,
                injection_cycles,
                phase="before model call",
            )
            if drained_before_request:
                had_injections = True
            await end_length_segment(interrupted=drained_before_request)
            context = AgentHookContext(
                iteration=iteration,
                messages=messages,
                session_key=spec.session_key,
            )
            await hook.before_iteration(context)
            request_messages = await self.prepare_prompt(
                request_state.compaction.request_messages, messages,
            )
            response, raw_usage = await self.model_requests.request_model(
                spec,
                request_messages,
                hook,
                context,
                request_state=request_state,
                transcript=messages,
            )
            assert request_state.messages is not None
            messages_for_model = request_state.messages
            conversation_state.observe_response(response, messages)
            await self.context_governor.accept_request(
                request_state, messages_for_model,
                raw_boundary=len(messages),
            )
            context.response = response
            context.tool_calls = list(response.tool_calls)

            original_content = response.content
            reasoning_text, cleaned_content = extract_reasoning(
                response.reasoning_content,
                response.thinking_blocks,
                response.content,
            )
            response.content = cleaned_content
            round_usages.append(raw_usage)
            context.usage = raw_usage
            usage = merge_usage(usage, raw_usage)
            if reasoning_text and not context.streamed_reasoning:
                await hook.emit_reasoning(reasoning_text)
                await hook.emit_reasoning_end()
                context.streamed_reasoning = True

            if response.should_execute_tools:
                context.tool_calls = list(response.tool_calls)
                if hook.wants_streaming():
                    # A provider/fallback may return complete prose without
                    # invoking content deltas. Deliver it before its tools;
                    # this branch never reaches the terminal reply delivery.
                    if (
                        not context.streamed_content
                        and not is_blank_text(response.content)
                        and not current_conversation_has_delivery()
                    ):
                        await hook.on_stream(context, response.content or "")
                        context.streamed_content = True
                    await hook.on_stream_end(context, resuming=True)

                assistant_message = build_assistant_message(
                    response.content or "",
                    tool_calls=[tc.to_openai_tool_call() for tc in response.tool_calls],
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )
                assistant_message = conversation_state.project_response_message(
                    assistant_message,
                    response,
                )
                messages.append(assistant_message)
                await emit_checkpoint(
                    spec,
                    {
                        "phase": "awaiting_tools",
                        "iteration": iteration,
                        "model": spec.runtime.model,
                        "assistant_message": assistant_message,
                        "completed_tool_results": [],
                        "pending_tool_calls": [tc.to_openai_tool_call() for tc in response.tool_calls],
                    },
                )

                await hook.before_execute_tools(context)

                results, new_events = await execute_tool_calls(
                    spec.tools,
                    response.tool_calls,
                    concurrent=spec.concurrent_tools,
                    external_lookup_counts=external_lookup_counts,
                    workspace_violation_counts=workspace_violation_counts,
                    hook=hook,
                    context=context,
                    model_messages=messages_for_model,
                    compacted_tool_results=request_state.compacted_tool_results,
                    role_policy=role_policy,
                )
                tool_events.extend(new_events)
                tools_used.extend(
                    tool_call.name
                    for tool_call, event in zip(response.tool_calls, new_events)
                    if event.get("status") == "ok"
                )
                context.tool_results = list(results)
                context.tool_events = list(new_events)
                await shield_and_drain(commit_completed_tools(
                    spec, request_state, messages, response, assistant_message,
                    results, iteration, self.context_governor.preparation,
                ))
                empty_content_retries = 0
                length_recovery_parts.clear()
                await hook.after_iteration(context)
                continue

            if response.has_tool_calls:
                logger.warning(
                    "Ignoring tool calls under finish_reason='{}' for {}",
                    response.finish_reason,
                    spec.session_key or "default",
                )

            delivered_reply = current_conversation_has_delivery()
            clean = hook.finalize_content(context, response.content)
            if delivered_reply and response.finish_reason != "error":
                # message() already published the answer. Do not persist or stream
                # the model's redundant terminal acknowledgment as another reply.
                clean = ""
            if (
                not delivered_reply
                and response.finish_reason
                not in {"error", "length", "refusal", "content_filter"}
                and is_blank_text(clean)
            ):
                if reasoning_text:
                    messages.append(conversation_state.project_response_message(
                        build_assistant_message("", reasoning_content=response.reasoning_content, thinking_blocks=response.thinking_blocks), response,
                    ))
                empty_content_retries += 1
                if empty_content_retries < _MAX_EMPTY_RETRIES:
                    logger.warning(
                        "Empty response on turn {} for {} ({}/{}); retrying",
                        iteration,
                        spec.session_key or "default",
                        empty_content_retries,
                        _MAX_EMPTY_RETRIES,
                    )
                    if hook.wants_streaming():
                        await hook.on_stream_end(context, resuming=False)
                    await hook.after_iteration(context)
                    continue
                logger.warning(
                    "Empty response on turn {} for {} after {} retries; attempting finalization",
                    iteration,
                    spec.session_key or "default",
                    empty_content_retries,
                )
                if hook.wants_streaming():
                    await hook.on_stream_end(context, resuming=False)
                response = await self.model_requests.request_finalization_retry(
                    spec,
                    messages_for_model,
                    request_state=request_state,
                    transcript=messages,
                )
                retry_usage = await record_request_usage(self.context_governor, spec, request_state, response)
                round_usages.append(retry_usage)
                usage = merge_usage(usage, retry_usage)
                raw_usage = merge_usage(raw_usage, retry_usage)
                context.response = response
                context.usage = raw_usage
                context.tool_calls = list(response.tool_calls)
                original_content = response.content
                reasoning_text, cleaned_retry = extract_reasoning(response.reasoning_content, response.thinking_blocks, response.content)
                clean = hook.finalize_content(context, cleaned_retry)
                if reasoning_text:
                    await hook.emit_reasoning(reasoning_text)
                    await hook.emit_reasoning_end()

            if response.finish_reason == "length":
                if len(length_recovery_parts) < _MAX_LENGTH_RECOVERIES:
                    length_recovery_parts.append(
                        restore_outer_whitespace(clean or "", original_content)
                    )
                    logger.info(
                        "Output truncated on turn {} for {} ({}/{}); continuing",
                        iteration,
                        spec.session_key or "default",
                        len(length_recovery_parts),
                        _MAX_LENGTH_RECOVERIES,
                    )
                    messages.append(conversation_state.project_response_message(
                        build_assistant_message(
                            clean,
                            reasoning_content=response.reasoning_content,
                            thinking_blocks=response.thinking_blocks,
                        ),
                        response,
                    ))
                    # The next input snapshot decides whether to continue this
                    # answer or close its stream before answering a new question.
                    pending_length_segment = (context, clean or "")
                    await hook.after_iteration(context)
                    continue

            # Some streaming providers recover with a complete response but no
            # content deltas. When an earlier length segment is already visible,
            # emit this terminal segment into the same stream; otherwise the
            # regular full response would duplicate the visible prefix.
            if (
                length_recovery_parts
                and hook.wants_streaming()
                and not context.streamed_content
                and response.finish_reason != "error"
                and not is_blank_text(clean)
            ):
                await hook.on_stream(
                    context,
                    restore_outer_whitespace(clean or "", original_content),
                )
                context.streamed_content = True

            if response.finish_reason not in {"error", "length"} and not is_blank_text(clean):
                reminder = reply_contract.reminder(delivered=delivered_reply, segment=injection_cycles, remaining=iteration + 1 < spec.max_iterations)
                if reminder is not None:
                    messages.append(conversation_state.project_response_message(
                        build_assistant_message(clean, reasoning_content=response.reasoning_content, thinking_blocks=response.thinking_blocks), response,
                    ))
                    messages.append(reminder)
                    if hook.wants_streaming():
                        await hook.on_stream_end(context, resuming=True)
                    await hook.after_iteration(context)
                    continue

            assistant_message: dict[str, Any] | None = None
            if response.finish_reason != "error" and (not is_blank_text(clean) or reasoning_text):
                assistant_message = build_assistant_message(
                    clean,
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )
                assistant_message = conversation_state.project_response_message(
                    assistant_message,
                    response,
                )

            if response.finish_reason == "error":
                interrupted_parts = [
                    content
                    for part in context.streamed_content_parts
                    if (content := extract_reasoning(None, None, part)[1])
                ]
                interrupted_content = hook.finalize_content(
                    context, "\n\n".join(interrupted_parts),
                )
                if not is_blank_text(interrupted_content) or reasoning_text:
                    # This is unsynchronized output, not a completed response or
                    # provider-owned projection. Keep it in the next native delta.
                    messages.append({
                        **build_assistant_message(interrupted_content, reasoning_content=response.reasoning_content, thinking_blocks=response.thinking_blocks),
                        "_interrupted": True,
                    })

            # Check for mid-turn injections BEFORE signaling stream end.
            # If injections are found we keep the stream alive (resuming=True)
            # so streaming channels don't prematurely finalize the card.
            can_make_followup_request = iteration + 1 < spec.max_iterations
            should_continue, injection_cycles = await try_drain_injections(
                spec, messages, assistant_message, injection_cycles,
                conversation_state=conversation_state,
                phase="after final response",
                iteration=iteration,
                allow_continuation=(
                    response.finish_reason not in {"refusal", "content_filter"}
                ),
                wait_at_terminal=(
                    assistant_message is not None
                    and response.finish_reason
                    not in {"error", "length", "refusal", "content_filter"}
                ),
                drain_callback=can_make_followup_request,
            )
            if should_continue:
                had_injections = True

            if hook.wants_streaming():
                await hook.on_stream_end(context, resuming=should_continue)

            if should_continue:
                length_recovery_parts.clear()
                await hook.after_iteration(context)
                continue

            if response.finish_reason == "error":
                if is_billing_error(response):
                    final_content = _ARREARAGE_ERROR_MESSAGE
                else:
                    final_content = clean or spec.error_message or DEFAULT_ERROR_MESSAGE
                stop_reason = "error"
                error = final_content
                append_model_error_placeholder(messages)
                context.final_content = final_content
                context.error = error
                context.stop_reason = stop_reason
                await hook.after_iteration(context)
                should_continue, injection_cycles = await try_drain_injections(
                    spec, messages, None, injection_cycles,
                    phase="after LLM error",
                    drain_callback=can_make_followup_request,
                )
                if should_continue:
                    had_injections = True
                    length_recovery_parts.clear()
                    continue
                failure_error_kind = public_error_kind(response)
                break
            if is_blank_text(clean) and assistant_message is not None:
                messages.append(assistant_message)
            if is_blank_text(clean) and delivered_reply:
                final_content = ""
                context.final_content = final_content
                await hook.after_iteration(context)
                break
            if is_blank_text(clean):
                final_content = EMPTY_FINAL_RESPONSE_MESSAGE
                stop_reason = "empty_final_response"
                error = final_content
                append_final_message(messages, final_content)
                context.final_content = final_content
                context.error = error
                context.stop_reason = stop_reason
                await hook.after_iteration(context)
                should_continue, injection_cycles = await try_drain_injections(
                    spec, messages, None, injection_cycles,
                    phase="after empty response",
                    drain_callback=can_make_followup_request,
                )
                if should_continue:
                    had_injections = True
                    length_recovery_parts.clear()
                    continue
                break

            messages.append(
                assistant_message
                or conversation_state.project_response_message(
                    build_assistant_message(
                        clean,
                        reasoning_content=response.reasoning_content,
                        thinking_blocks=response.thinking_blocks,
                    ),
                    response,
                )
            )
            await emit_checkpoint(
                spec,
                {
                    "phase": "final_response",
                    "iteration": iteration,
                    "model": spec.runtime.model,
                    "assistant_message": messages[-1],
                    "completed_tool_results": [],
                    "pending_tool_calls": [],
                    "provider_state": conversation_state.checkpoint(messages),
                },
            )
            if length_recovery_parts:
                final_content = (
                    "".join(length_recovery_parts)
                    + restore_outer_whitespace(clean or "", original_content)
                ).strip()
            else:
                final_content = clean
            context.final_content = final_content
            context.stop_reason = stop_reason
            await hook.after_iteration(context)
            break
        else:
            stop_reason = "max_iterations"
            terminal_content = None
            await end_length_segment(interrupted=False)
            if spec.finalize_on_max_iterations:
                terminal_content, usage = await self.model_requests.try_finalize_after_max_iterations(
                    spec,
                    hook,
                    messages,
                    usage,
                    request_state=request_state,
                    round_usages=round_usages,
                )
            if terminal_content is None:
                terminal_content = max_iterations_fallback(spec)
            if length_recovery_parts:
                terminal_tail = f"\n\n{terminal_content.lstrip()}"
                final_content = (
                    "".join(length_recovery_parts).rstrip() + terminal_tail
                ).strip()
                pending_stream_content = terminal_tail
            else:
                final_content = terminal_content
            append_final_message(messages, terminal_content)

        return AgentRunResult(
            final_content=final_content,
            messages=messages,
            tools_used=tools_used,
            usage=usage,
            round_usages=round_usages,
            stop_reason=stop_reason,
            error=error,
            failure_error_kind=failure_error_kind,
            tool_events=tool_events,
            had_injections=had_injections,
            pending_stream_content=pending_stream_content,
            provider_state=conversation_state.finish(messages),
            summary_checkpoint=request_state.compaction.summary_checkpoint,
            provider_compaction_applied=request_state.provider_compaction_applied,
        )
