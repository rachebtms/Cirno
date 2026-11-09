"""TurnInputs owns its stage of the admitted conversation lifecycle."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from cirno_core.agent import context as agent_context
from cirno_core.agent.context import TranscriptInput
from cirno_core.agent.execution.context import TurnContext, TurnKind
from cirno_core.agent.execution.scope import _prompt_scope_metadata
from cirno_core.agent.tools.context import (
    RequestContext,
)
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.agent.turn_delivery import (
    TurnDelivery,
)
from cirno_core.bus.events import (
    INBOUND_META_LOCAL_MEDIA,
    INBOUND_META_TURN_ID,
    InboundMessage,
)
from cirno_core.bus.input_origin import input_origin
from cirno_core.runtime.context import (
    RUNTIME_CONTEXT_HISTORY_META,
    RuntimeContextBlock,
    append_runtime_context,
    resolve_runtime_context,
    runtime_context_blocks_from_metadata,
)
from cirno_core.session import turn_continuation
from cirno_core.session.automation_turns import automation_history_overrides
from cirno_core.session.history_visibility import HIDDEN_HISTORY_META
from cirno_core.session.model import Session
from cirno_core.session.recovery.contracts import PENDING_FOLLOWUP_ID_KEY, REQUEST_ORIGIN_METADATA_KEY, RequestOrigin, request_origin_from_metadata

if TYPE_CHECKING:
    from cirno_core.agent.loop import AgentLoop


class TurnInputs:
    def __init__(self, agent: AgentLoop):
        self.agent = agent

    @staticmethod
    def history_extra(msg: InboundMessage) -> dict[str, Any]:
        """Keep input admission separate from the run that eventually consumes it."""
        extra: dict[str, Any] = {"timestamp": msg.timestamp.isoformat()}
        if origin := input_origin(msg):
            extra["input_origin"] = origin
        turn_id = msg.metadata.get(INBOUND_META_TURN_ID)
        if isinstance(turn_id, str) and turn_id:
            extra[INBOUND_META_TURN_ID] = turn_id
        local_media = msg.metadata.get(INBOUND_META_LOCAL_MEDIA)
        if isinstance(local_media, list) and local_media:
            extra[INBOUND_META_LOCAL_MEDIA] = [
                path for path in cast(list[object], local_media) if isinstance(path, str)
            ]
        return extra

    async def persist_early(
        self,
        msg: InboundMessage,
        session: Session,
        runtime_context_blocks: list[RuntimeContextBlock] | None = None,
        **kwargs: Any,
    ) -> bool:
        """Persist the triggering user message and recovery markers before running the turn."""
        if not turn_continuation.should_persist_user_message(msg.metadata):
            return False
        media_paths = [
            path for path in (msg.media or []) if isinstance(cast(object, path), str) and path
        ]
        content_value = cast(object, msg.content)
        has_text = isinstance(content_value, str) and content_value.strip()
        if has_text or media_paths or runtime_context_blocks:
            extra = (
                self.history_extra(msg)
                | ({"media": list(media_paths)} if media_paths else {})
                | agent_context.session_extra(msg.metadata)
            )
            extra.update(kwargs)
            if HIDDEN_HISTORY_META in msg.metadata:
                extra[HIDDEN_HISTORY_META] = msg.metadata[HIDDEN_HISTORY_META]
            text = content_value if isinstance(content_value, str) else ""
            text_override, automation_extra = automation_history_overrides(msg.metadata)
            if text_override is not None:
                text = text_override
            extra.update(automation_extra)
            text, runtime_context_meta = append_runtime_context(
                text,
                runtime_context_blocks or (),
            )
            if runtime_context_meta is not None:
                extra[RUNTIME_CONTEXT_HISTORY_META] = runtime_context_meta
            session.add_message(msg.input_role or "user", text, **extra)
            self.agent.persistence.mark_pending(session)
            followup_id = msg.metadata.get(PENDING_FOLLOWUP_ID_KEY)
            if isinstance(followup_id, str) and followup_id:
                session.consumed_followup_ids |= {followup_id}
            await self.agent.sessions.state.prepare_input(session)
            return True
        return False

    def transcript(self, ctx: TurnContext) -> TranscriptInput:
        """Capture the persisted history and fresh input as separate transcript parts."""
        assert ctx.session is not None
        return TranscriptInput(
            history=ctx.history,
            current_message=ctx.msg.content,
            current_role=ctx.msg.input_role or "user",
            media=ctx.msg.media if ctx.kind is TurnKind.USER and ctx.msg.media else None,
            session_summary=ctx.pending_summary,
            runtime_context_blocks=ctx.runtime_context_blocks,
        )

    async def request_context(self, ctx: TurnContext) -> RequestContext:
        assert ctx.session is not None
        origin: RequestOrigin = {
            "message_id": ctx.msg.metadata.get("message_id"),
            "turn_id": ctx.delivery.route.turn_id or ctx.turn_id,
        }
        if turn_continuation.internal_continuation_inbound(ctx.msg.metadata):
            origin = request_origin_from_metadata(ctx.msg.metadata) or origin
        if origin != request_origin_from_metadata(ctx.session.metadata):
            ctx.session.metadata[REQUEST_ORIGIN_METADATA_KEY] = origin
            if ctx.original_user_text is None:
                # No new user row will persist this turn's owner before execution.
                await self.agent.sessions.state.update_metadata(
                    ctx.session.key,
                    {REQUEST_ORIGIN_METADATA_KEY: origin},
                    expected_generation=ctx.session.generation,
                )
        scope = await self.agent.runner.prepare_prompt(
            self.agent.workspace_scopes.for_turn,
            channel=ctx.delivery.route.channel,
            message_metadata=_prompt_scope_metadata(ctx.msg.metadata),
            session_metadata=_prompt_scope_metadata(ctx.session.metadata),
        )
        return RequestContext(
            channel=ctx.delivery.route.channel,
            chat_id=ctx.delivery.route.chat_id,
            message_id=origin["message_id"],
            session_key=ctx.session_key,
            session_generation=ctx.session.generation,
            original_user_text=ctx.original_user_text,
            runtime=ctx.runtime,
            metadata={
                **(ctx.msg.metadata or {}),
                **(
                    ctx.delivery.route.metadata if ctx.delivery.route.channel == "websocket" else {}
                ),
            },
            attributes=dict(ctx.attributes),
            sender_id=ctx.msg.sender_id,
            turn_id=origin["turn_id"],
            workspace=scope.project_path,
            workspace_scope=scope,
            operation_approval=self.agent.operation_approval,
            log_content=ctx.session.policy.log_content and not ctx.ephemeral,
            persist_session=ctx.session.policy.persist and not ctx.ephemeral,
            can_receive_background_results=self.agent._running,
        )

    async def resolve_context(
        self,
        ctx: TurnContext,
    ) -> list[RuntimeContextBlock]:
        assert ctx.request_context is not None
        return await self.resolve_request_context(
            ctx.request_context,
            ctx.tools if ctx.tools is not None else self.agent.tools,
        )

    async def resolve_request_context(
        self,
        request: RequestContext,
        tools: ToolRegistry,
    ) -> list[RuntimeContextBlock]:
        providers = [
            *tools.get_runtime_context_providers(),
            *self.agent._runtime_context_providers,
        ]
        blocks = runtime_context_blocks_from_metadata(request.metadata)
        blocks.extend(await resolve_runtime_context(providers, request))
        text = request.original_user_text or ""
        skill_context = (
            await self.agent.runner.prepare_prompt(
                self.agent.context.skill_context.build_explicit_skill_runtime_context, text
            )
            if "$" in text
            else None
        )
        if skill_context is not None and skill_context not in blocks:
            blocks.append(skill_context)
        return blocks

    def remember_route(
        self,
        session: Session,
        msg: InboundMessage,
        *,
        delivery: TurnDelivery,
        is_user_turn: bool,
    ) -> None:
        """Remember the latest user-facing destination, including channel threads."""
        if not is_user_turn or msg.channel in {"cli", "system"} or msg.sender_id == "subagent":
            return
        _, automation_metadata = automation_history_overrides(msg.metadata)
        if automation_metadata:
            return
        delivery.remember_session_route(session.metadata)
