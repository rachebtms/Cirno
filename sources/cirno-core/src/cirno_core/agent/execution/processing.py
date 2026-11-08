"""TurnProcessor owns its stage of the admitted conversation lifecycle."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Awaitable, Callable, TypeVar, cast

from cirno_core.agent.execution.context import TurnContext, TurnKind
from cirno_core.agent.hook import AgentHook, AgentTurnHookFactory
from cirno_core.agent.tools.message import capture_message_deliveries
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.agent.turn_delivery import (
    TurnDelivery,
)
from cirno_core.bus.agent_events import AgentEvent, EventSink
from cirno_core.bus.events import (
    InboundMessage,
    OutboundMessage,
)
from cirno_core.bus.outbound_events import (
    StreamDeltaEvent,
    StreamedResponseEvent,
    StreamEndEvent,
)
from cirno_core.session import turn_continuation
from cirno_core.session.goal_state import (
    goal_state_raw,
    parse_goal_state,
)
from cirno_core.session.model import Session
from cirno_core.session.roles import conversation_role
from cirno_core.utils.llm_runtime import LLMRuntime
from cirno_core.utils.progress_events import output_events
from loguru import logger

from .diagnostics import content_logging_allowed

if TYPE_CHECKING:
    from cirno_core.agent.loop import AgentLoop

_T = TypeVar("_T")


class TurnProcessor:
    def __init__(self, agent: AgentLoop):
        self.agent = agent

    async def process(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[..., Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
        pending_queue: asyncio.Queue[InboundMessage] | None = None,
        ephemeral: bool = False,
        run_extra_hooks_for_ephemeral: bool = False,
        hooks: list[AgentHook] | None = None,
        hook_factories: list[AgentTurnHookFactory] | None = None,
        tools: ToolRegistry | None = None,
        runtime: LLMRuntime | None = None,
        delivery: TurnDelivery | None = None,
        on_runtime_admitted: Callable[[LLMRuntime], Awaitable[None]] | None = None,
        attributes: Mapping[str, Any] | None = None,
        session: Session | None = None,
    ) -> OutboundMessage | None:
        """Process a single inbound message and return the response."""
        kind = TurnKind.USER if msg.is_user_input else TurnKind.SYSTEM
        if kind is TurnKind.SYSTEM:
            destination = msg.chat_id.split(":", 1) if ":" in msg.chat_id else ("cli", msg.chat_id)
            key = session_key or msg.session_key_override or f"{destination[0]}:{destination[1]}"
        else:
            key = session_key or msg.session_key
        if not self.agent.subagents.accepts_result(msg, key):
            return None
        commit_session = session is None or session.policy.persist
        if delivery is None:
            delivery = (await self.agent.turn_delivery_factory.create(msg, key))
        elif delivery.session_key != key:
            raise ValueError("turn delivery session does not match the processing session")
        t0 = time.time()
        ctx = TurnContext(
            msg=msg,
            session=session,
            session_key=key,
            turn_id=f"{key}:{time.time_ns()}",
            runtime=runtime,
            kind=kind,
            delivery=delivery,
            original_user_text=(
                None
                if kind is TurnKind.SYSTEM
                or turn_continuation.internal_continuation_inbound(msg.metadata)
                else msg.content
            ),
            turn_wall_started_at=t0,
            visible_run_started_at=turn_continuation.internal_continuation_run_started_at(
                msg.metadata,
            ),
            events=output_events(
                default=delivery.events,
                on_progress=on_progress,
                on_stream=on_stream,
                on_stream_end=on_stream_end,
            ),
            streaming=on_stream is not None or delivery.streaming,
            on_runtime_admitted=on_runtime_admitted,
            pending_queue=pending_queue,
            ephemeral=ephemeral,
            commit_session=commit_session,
            run_extra_hooks_for_ephemeral=run_extra_hooks_for_ephemeral,
            hooks=list(hooks or []),
            hook_factories=list(hook_factories or []),
            tools=tools,
            attributes=dict(attributes or {}),
        )
        # A streaming callback may be present even when the final text comes from a
        # non-streaming recovery. Only the last completed segment can suppress the
        # regular outbound message.
        from cirno_core.bus.agent_events import RetryStatusEvent

        original_events = ctx.events
        segment_streamed_content = False
        retry_active = False
        retry_episode = 0

        async def track_output(event: AgentEvent) -> None:
            nonlocal segment_streamed_content, retry_active, retry_episode
            if ctx.streaming:
                if isinstance(event, StreamDeltaEvent) and event.content:
                    segment_streamed_content = True
                elif isinstance(event, StreamEndEvent):
                    ctx.streamed_content = segment_streamed_content
                    segment_streamed_content = False
            if original_events.publish is not None:
                await original_events.publish(event)
            if isinstance(event, RetryStatusEvent) and not ctx.ephemeral and ctx.commit_session:
                if event.state == "waiting" and not retry_active:
                    retry_active = True
                    retry_episode += 1
                elif event.state != "recovered" or not retry_active:
                    return
                else:
                    retry_active = False
                from cirno_core.agent.work_reports import record_retry_report

                report = await record_retry_report(
                    self.agent.sessions,
                    ctx.session_key,
                    turn_id=ctx.turn_id,
                    event=event,
                    episode=retry_episode,
                    model=ctx.runtime.model if ctx.runtime else None,
                    model_preset=ctx.runtime.model_preset if ctx.runtime else None,
                    expected_generation=ctx.session.generation
                    if ctx.session
                    else ctx.msg.session_generation,
                )
                await self.agent.reports.deliver(ctx.session_key, report)

        ctx.events = EventSink(
            track_output,
            lambda event_type: (
                event_type is RetryStatusEvent or original_events.accepts(event_type)
            ),
        )

        with logger.contextualize(turn_id=ctx.turn_id, session_key=ctx.session_key):
            await self.stage(ctx, "restore", self.agent.preparation.restore)
            await self.stage(ctx, "compact", self.agent.preparation.compact)
            if await self.stage(ctx, "command", self.agent.command_execution.dispatch):
                self.log_completion(ctx, outcome="command")
                return ctx.outbound
            await self.stage(ctx, "build", self.agent.preparation.build)
            await self.stage(ctx, "run", self.run)
            await self.stage(ctx, "save", self.agent.persistence.commit)
            await self.stage(ctx, "respond", self.prepare_outbound)
            self.log_completion(ctx)
            return ctx.outbound

    async def stage(
        self,
        ctx: TurnContext,
        name: str,
        handler: Callable[[TurnContext], Awaitable[_T]],
    ) -> _T:
        started_at = time.perf_counter()
        try:
            result = await handler(ctx)
        except Exception as error:
            await self.agent.reports.publish(ctx, stage=name, error=error)
            duration_ms = (time.perf_counter() - started_at) * 1000
            log_content = content_logging_allowed(self.agent.sessions, ctx.session_key, session=ctx.session, ephemeral=ctx.ephemeral)
            logger.opt(exception=log_content).bind(
                event="turn_stage",
                stage=name,
                outcome="error",
                duration_ms=round(duration_ms, 1),
            ).error(
                "Stage {} failed after {:.1f}ms",
                name,
                duration_ms,
            )
            raise
        duration_ms = (time.perf_counter() - started_at) * 1000
        logger.bind(
            event="turn_stage",
            stage=name,
            outcome="success",
            duration_ms=round(duration_ms, 1),
        ).debug(
            "Stage {} completed in {:.1f}ms",
            name,
            duration_ms,
        )
        return result

    def log_completion(self, ctx: TurnContext, *, outcome: str | None = None) -> None:
        if ctx.kind is TurnKind.USER:
            self.agent._last_memory_activity = time.monotonic()
        duration_ms = ctx.turn_latency_ms
        if duration_ms is None:
            duration_ms = max(0, round((time.time() - ctx.turn_wall_started_at) * 1000))
        runtime = ctx.runtime
        provider = runtime.provider.provider_name if runtime is not None else None
        model = runtime.model if runtime is not None else None
        response_preview = "[content hidden]"
        if (
            ctx.kind is TurnKind.USER
            and ctx.session is not None
            and not ctx.ephemeral
            and ctx.session.policy.persist
            and ctx.session.policy.log_content
            and ctx.final_content is not None
        ):
            response_preview = (
                f"{ctx.final_content[:120]}..."
                if len(ctx.final_content) > 120
                else ctx.final_content
            )
        final_outcome = outcome or ctx.stop_reason or "completed"
        logger.bind(
            event="turn_completed",
            outcome=final_outcome,
            duration_ms=duration_ms,
            provider=provider,
            model=model,
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
        ).info(
            "Turn completed channel={} chat_id={} outcome={} duration_ms={} "
            "provider={} model={} response={}",
            ctx.msg.channel,
            ctx.msg.chat_id,
            final_outcome,
            duration_ms,
            provider or "-",
            model or "-",
            response_preview,
        )

    def assemble_outbound(
        self,
        msg: InboundMessage,
        final_content: str,
        stop_reason: str,
        streamed_content: bool,
        *,
        turn_latency_ms: int | None = None,
    ) -> OutboundMessage | None:
        """Assemble the final outbound message from turn results."""
        event = None
        meta = dict(msg.metadata or {})
        if streamed_content and stop_reason not in {"error", "tool_error"}:
            event = StreamedResponseEvent()
        if turn_latency_ms is not None:
            meta["latency_ms"] = int(turn_latency_ms)

        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            event=event,
            metadata=meta,
        )

    async def run(self, ctx: TurnContext) -> None:
        runtime = ctx.require_runtime()
        if ctx.visible_run_started_at is None:
            ctx.visible_run_started_at = time.time()
        await ctx.delivery.running(started_at=ctx.visible_run_started_at)
        assert ctx.transcript_input is not None
        with capture_message_deliveries() as message_sends:
            result = await self.agent.model_turn.run(
                ctx.transcript_input,
                runtime=runtime,
                streaming=ctx.streaming,
                session=ctx.session,
                pending_queue=ctx.pending_queue,
                ephemeral=ctx.ephemeral,
                run_extra_hooks_for_ephemeral=ctx.run_extra_hooks_for_ephemeral,
                hooks=ctx.hooks,
                hook_factories=ctx.hook_factories,
                turn_scopes=ctx.turn_scopes,
                tools=ctx.tools,
                request_context=ctx.request_context,
                provider_state=ctx.provider_state,
                events=ctx.events,
            )
        ctx.final_content = result.final_content
        ctx.all_messages = result.messages
        ctx.summary_checkpoint = result.summary_checkpoint
        ctx.provider_compaction_applied = result.provider_compaction_applied
        ctx.stop_reason = result.stop_reason
        ctx.failure_error_kind = result.failure_error_kind
        if (
            (ctx.kind is TurnKind.USER or conversation_role(ctx.session_key).tool_replies)
            and (ctx.delivery.route.channel, ctx.delivery.route.chat_id) in message_sends
            and result.stop_reason not in {"error", "tool_error"}
        ):
            ctx.suppress_response = True
        ctx.usage = result.usage
        ctx.delivery.record_usage(result.round_usages)
        if ctx.kind is TurnKind.USER:
            current = await self.agent.sessions.state.read_metadata(ctx.session_key)
            metadata = current["metadata"] if current else {}
            goal = parse_goal_state(goal_state_raw(metadata)) or {}
            limit = int(goal.get("continuation_limit", self.agent.goal_continuation_limit))
            rounds = int(metadata.get("_sustained_goal_continuation_rounds", 0))
            if goal.get("status") == "active" and limit > 0 and rounds >= limit:
                await self.agent.sessions.state.update_metadata(
                    ctx.session_key,
                    {
                        "goal_state": {
                            **goal,
                            "status": "paused",
                            "recap": "Automatic continuation limit reached.",
                        }
                    },
                )
                current = await self.agent.sessions.state.read_metadata(ctx.session_key)
            ctx.delivery.continuation_pending = await turn_continuation.maybe_continue_turn(
                ctx,
                session_metadata=current["metadata"] if current else {},
            )

    async def prepare_outbound(self, ctx: TurnContext) -> None:
        ctx.delivery.record_stop_reason(
            ctx.stop_reason,
            failure_error_kind=ctx.failure_error_kind,
        )
        if ctx.suppress_response or (
            conversation_role(ctx.session_key).tool_replies
            and ctx.stop_reason not in {"error", "tool_error"}
        ):
            ctx.outbound = None
            return
        if ctx.kind is TurnKind.SYSTEM:
            ctx.outbound = ctx.delivery.background_response(
                ctx.final_content,
                stop_reason=ctx.stop_reason,
                streamed=ctx.streamed_content,
                latency_ms=ctx.turn_latency_ms,
            )
            return
        ctx.outbound = self.assemble_outbound(
            ctx.delivery.delivery_message,
            cast(str, ctx.final_content),
            ctx.stop_reason,
            ctx.streamed_content,
            turn_latency_ms=ctx.turn_latency_ms,
        )
        if ctx.ephemeral and ctx.outbound is not None:
            ctx.outbound.metadata["_stop_reason"] = ctx.stop_reason
