"""Build scoped hooks, tools and checkpoints for one model run."""

from __future__ import annotations

import asyncio
import dataclasses
from contextlib import AbstractContextManager, ExitStack
from functools import partial
from typing import TYPE_CHECKING, Any

from cirno_core.agent.context import TranscriptInput
from cirno_core.agent.goals.permission import GoalInputScope
from cirno_core.agent.hook import AgentHook, AgentTurnHookFactory
from cirno_core.agent.runner.contracts import AgentRunResult, AgentRunSpec
from cirno_core.agent.tools.context import (
    RequestContext,
    bind_request_context,
    reset_request_context,
)
from cirno_core.agent.tools.file_state import bind_file_states, reset_file_states
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.agent.tools.selection import conversation_tools
from cirno_core.agent.turn_hooks import AgentTurnHookSpec, build_agent_turn_hook
from cirno_core.bus.agent_events import NO_EVENTS, EventSink
from cirno_core.bus.events import (
    InboundMessage,
)
from cirno_core.bus.outbound_events import (
    StreamDeltaEvent,
    StreamEndEvent,
)
from cirno_core.providers.contracts import ProviderConversationState
from cirno_core.security.workspace_access import (
    bind_workspace_scope,
    reset_workspace_scope,
)
from cirno_core.session import turn_continuation
from cirno_core.session.model import Session
from cirno_core.session.request_usage import append_request_usage
from cirno_core.session.recovery.contracts import PROVIDER_STATE_CHECKPOINT_VERSION, PROVIDER_STATE_CHECKPOINT_VERSION_KEY
from cirno_core.utils.llm_runtime import LLMRuntime
from cirno_usage.context import source_from_request
from cirno_usage.types import LLMUsage
from loguru import logger

from .injection import PendingInputInjector
from .scope import _prompt_scope_metadata

if TYPE_CHECKING:
    from cirno_core.agent.loop import AgentLoop


class ModelTurnExecutor:
    def __init__(self, agent: AgentLoop):
        self.agent = agent

    async def run(
        self,
        transcript_input: TranscriptInput,
        events: EventSink = NO_EVENTS,
        streaming: bool = False,
        *,
        runtime: LLMRuntime,
        session: Session | None = None,
        pending_queue: asyncio.Queue[InboundMessage] | None = None,
        ephemeral: bool = False,
        run_extra_hooks_for_ephemeral: bool = False,
        hooks: list[AgentHook] | None = None,
        hook_factories: list[AgentTurnHookFactory] | None = None,
        turn_scopes: list[AbstractContextManager[Any]] | None = None,
        tools: ToolRegistry | None = None,
        request_context: RequestContext | None = None,
        provider_state: ProviderConversationState | None = None,
        require_visible_reply: bool = False,
    ) -> AgentRunResult:
        """Run the agent iteration loop.

        *events*: scoped operation and output events.
        *streaming*: request incremental output from the runner.
        ``resuming=True`` means the active turn continues. ``merge_next=True`` means
        the next text segment belongs to the same user-visible assistant message.

        Returns the complete result produced by ``AgentRunner``.
        """
        self.agent._sync_subagent_runtime_limits()

        ephemeral = ephemeral or (session is not None and not session.policy.persist)

        async def _request_usage(usage: LLMUsage) -> None:
            if session is None or ephemeral:
                return
            await self.agent.sessions.state.mutate_metadata(
                session.key,
                partial(append_request_usage, usage=usage),
                expected_generation=session.generation,
            )

        async def _checkpoint(payload: dict[str, Any]) -> None:
            if session is None or ephemeral:
                return
            public_payload = dict(payload)
            private_state = public_payload.pop("provider_state", None)
            public_payload.pop(PROVIDER_STATE_CHECKPOINT_VERSION_KEY, None)
            if "provider_state" in payload and (
                private_state is None or isinstance(private_state, ProviderConversationState)
            ):
                session.provider_state = private_state
                public_payload[PROVIDER_STATE_CHECKPOINT_VERSION_KEY] = (
                    PROVIDER_STATE_CHECKPOINT_VERSION
                )
            await self.agent.persistence.checkpoint(session, public_payload)

        request_ctx = request_context or RequestContext(
            channel="cli",
            chat_id="direct",
            session_key=session.key if session is not None else None,
            runtime=runtime,
            can_receive_background_results=self.agent._running,
        )
        active_session_key = session.key if session else request_ctx.session_key
        consolidation_session_key = active_session_key or "agent:transient"
        request_metadata = request_ctx.metadata
        effective_scope = await self.agent.runner.prepare_prompt(
            self.agent.workspace_scopes.for_turn,
            channel=request_ctx.channel,
            message_metadata=_prompt_scope_metadata(request_metadata),
            session_metadata=_prompt_scope_metadata(session.metadata)
            if session is not None
            else None,
        )
        transcript_builder = partial(
            self.agent.context.build_transcript,
            channel=request_ctx.channel,
            session_key=active_session_key,
            workspace=effective_scope.project_path,
            include_memory=session.policy.persist if session is not None else True,
            include_task_context=False,
            include_memory_context=False,
            system_prompts=await self.agent.runner.prepare_prompt(self.agent.context.current_system_prompts),
            project_id=session.metadata.get("project_id") if session else None,
        )
        if request_context is None:
            request_ctx = dataclasses.replace(
                request_ctx,
                workspace=effective_scope.project_path,
            )
        request_ctx = dataclasses.replace(
            request_ctx,
            workspace_scope=effective_scope,
            session_generation=(
                session.generation if session is not None else request_ctx.session_generation
            ),
            log_content=(
                request_ctx.log_content
                and not ephemeral
                and (session is None or session.policy.log_content)
            ),
            persist_session=(
                request_ctx.persist_session
                and not ephemeral
                and (session is None or session.policy.persist)
            ),
        )
        effective_tools = conversation_tools(
            tools if tools is not None else self.agent.tools,
            active_session_key,
            ptc_mode=session is not None and session.metadata.get("ptc_mode") is True,
        )
        tool_instructions = effective_tools.model_instructions()
        if tool_instructions:
            native_builder = transcript_builder

            def transcript_builder(*args, **kwargs):
                assembled = native_builder(*args, **kwargs)
                assembled[0] = {
                    **assembled[0],
                    "content": assembled[0]["content"] + "\n\n" + tool_instructions,
                }
                return assembled

        file_state_token = bind_file_states(
            self.agent._file_state_store.for_session(active_session_key)
        )
        request_token = bind_request_context(request_ctx)
        workspace_token = bind_workspace_scope(effective_scope)
        turn_scope_stack = ExitStack()

        from cirno_core.agent.goals.continuation import GoalContinuation

        goal_continuation = GoalContinuation()
        # Compute lazily because create_goal may create goal metadata during this run.
        async def _goal_continue() -> str | None:
            current = (
                await self.agent.sessions.state.read_metadata(session.key) if session else None
            )
            return goal_continuation.message(current["metadata"] if current else None)

        session_metadata = session.metadata if session is not None else None
        try:
            goal_inputs = turn_scope_stack.enter_context(GoalInputScope())
            injection = PendingInputInjector(
                self.agent,
                session=session,
                queue=pending_queue,
                runtime=runtime,
                request=request_ctx,
                scope=effective_scope,
                tools=effective_tools,
                goal_inputs=goal_inputs,
            )
            for scope in turn_scopes or ():
                turn_scope_stack.enter_context(scope)
            hook = build_agent_turn_hook(
                AgentTurnHookSpec(
                    events=events,
                    streaming=streaming,
                    channel=request_ctx.channel,
                    chat_id=request_ctx.chat_id,
                    message_id=request_ctx.message_id,
                    metadata=request_metadata,
                    attributes=dict(request_ctx.attributes),
                    session_key=active_session_key,
                    workspace=effective_scope.project_path,
                    registered_hook_factories=self.agent._hook_factories,
                    turn_hook_factories=list(hook_factories or []),
                    registered_hooks=self.agent._extra_hooks,
                    turn_hooks=list(hooks or []),
                    ephemeral=ephemeral,
                    run_extra_hooks_for_ephemeral=run_extra_hooks_for_ephemeral,
                    log_content=request_ctx.log_content,
                )
            )
            result = await self.agent.runner.run(
                AgentRunSpec(
                    initial_messages=None,
                    tools=effective_tools,
                    runtime=runtime,
                    max_iterations=min(self.agent.max_iterations, self.agent.dream_max_iterations)
                    if ephemeral and (active_session_key or "").startswith("dream:")
                    else self.agent.max_iterations,
                    max_tool_result_chars=self.agent.max_tool_result_chars,
                    transcript_input=transcript_input,
                    transcript_builder=transcript_builder,
                    hook=hook,
                    concurrent_tools=True,
                    # Temporary turns use the governor's bounded in-memory results;
                    # never create durable spill files, even before discard/cancellation.
                    workspace=None if ephemeral else effective_scope.project_path,
                    session_key=session.key if session else None,
                    require_visible_reply=require_visible_reply,
                    provider_retry_mode=self.agent.provider_retry_mode,
                    checkpoint_callback=_checkpoint,
                    request_usage_callback=_request_usage,
                    consolidate_history=partial(
                        self.agent.consolidator.summarize_transcript,
                        runtime=runtime,
                        session_key=consolidation_session_key,
                        tools=effective_tools.get_definitions(),
                        persist=session is not None and not ephemeral,
                    ),
                    consolidate_provider_compaction=partial(
                        self.agent.consolidator.summarize_provider_compaction,
                        runtime=runtime,
                        session_key=consolidation_session_key,
                        tools=effective_tools.get_definitions(),
                        persist=session is not None and not ephemeral,
                    ),
                    injection_callback=injection.drain,
                    terminal_injection_callback=injection.wait,
                    continuation_callback=_goal_continue,
                    finalize_on_max_iterations=turn_continuation.should_finalize_on_max_iterations(
                        pending_queue_available=pending_queue is not None and session is not None,
                        session_metadata=session_metadata,
                        message_metadata=request_metadata,
                    ),
                    provider_state=provider_state,
                    llm_usage_source=source_from_request(
                        active_session_key,
                        channel=request_ctx.channel,
                        metadata=request_metadata,
                    ),
                    events=events,
                )
            )
        finally:
            turn_scope_stack.close()
            reset_workspace_scope(workspace_token)
            reset_request_context(request_token)
            reset_file_states(file_state_token)
        if session is not None and not ephemeral:
            session.provider_state = result.provider_state
        if result.stop_reason == "max_iterations":
            logger.warning("Max iterations ({}) reached", self.agent.max_iterations)
            should_stream = turn_continuation.should_stream_budget_response(
                stop_reason=result.stop_reason,
                pending_queue_available=pending_queue is not None and session is not None,
                session_metadata=session_metadata,
                message_metadata=request_metadata,
            )
            # Push final content through stream so streaming channels (e.g. Feishu)
            # update the card instead of leaving it empty.
            if events.publish is not None and streaming and should_stream:
                stream_content = (
                    result.pending_stream_content
                    if result.pending_stream_content is not None
                    else result.final_content or ""
                )
                await events.publish(StreamDeltaEvent(content=stream_content))
                await events.publish(StreamEndEvent())
        elif result.stop_reason == "error":
            logger.error(
                "LLM returned error: {}",
                (result.final_content or "")[:200]
                if request_ctx.log_content
                else "[content hidden]",
            )
        return result
