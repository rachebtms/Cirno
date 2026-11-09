"""TurnPreparation owns its stage of the admitted conversation lifecycle."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any, cast

from cirno_core.agent.execution.context import TurnContext, TurnKind
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.bus.events import (
    INBOUND_META_TURN_ID,
)
from cirno_core.bus.input_origin import origin_context
from cirno_core.session.recovery.contracts import RECOVERY_INBOUND_METADATA_KEY
from cirno_core.session.recovery.interruption import restore_pending_interruption
from cirno_core.session.recovery.checkpoints import restore_runtime_checkpoint
from cirno_core.utils.document import reference_non_image_attachments
from loguru import logger

if TYPE_CHECKING:
    from cirno_core.agent.loop import AgentLoop

_SUBAGENT_PROVIDER_TASK_META = "subagent_provider_task_id"


class TurnPreparation:
    def __init__(self, agent: AgentLoop):
        self.agent = agent

    async def restore(self, ctx: TurnContext) -> None:
        """Restore checkpoint / pending user turn; reference non-image attachments."""
        msg = ctx.msg

        if ctx.kind is TurnKind.USER and msg.media:
            new_content, image_paths = reference_non_image_attachments(
                msg.content,
                msg.media,
            )
            ctx.msg = dataclasses.replace(msg, content=new_content, media=image_paths)
            msg = ctx.msg

        if ctx.session is None and not ctx.ephemeral:
            await self.agent.persistence.release_archive(ctx.session_key)
        if ctx.session is None:
            ctx.session = (
                await self.agent.sessions.state.read(ctx.session_key)
                if msg.require_existing_session or msg.session_generation is not None
                else await self.agent.sessions.state.get(ctx.session_key)
            )
        session = ctx.session
        if session is None:
            raise RuntimeError("required session is not active")
        if msg.session_generation is not None and session.generation != msg.session_generation:
            raise RuntimeError("required session generation was replaced")
        ctx.ephemeral = ctx.ephemeral or not session.policy.persist
        await ctx.delivery.bind_session_generation(session.generation)
        tools = ctx.tools if ctx.tools is not None else self.agent.tools
        if session.policy.disabled_tools:
            restricted = ToolRegistry()
            for name in tools.tool_names:
                tool = tools.get(name)
                if name not in session.policy.disabled_tools and tool:
                    restricted.register(tool)
            tools = restricted
        ctx.tools = tools

        if ctx.kind is TurnKind.SYSTEM:
            logger.info("Processing system message from {}", msg.sender_id)
        elif session.policy.log_content and not ctx.ephemeral:
            preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
            logger.info("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)
        else:
            logger.info(
                "Processing message from {}:{}: [content hidden]", msg.channel, msg.sender_id
            )

        self.agent.inputs.remember_route(
            session,
            msg,
            delivery=ctx.delivery,
            is_user_turn=ctx.original_user_text is not None,
        )
        await ctx.delivery.started()
        if ctx.kind is TurnKind.USER:
            self.agent.workspace_scopes.persist_message_scope(session, msg)

        if restore_runtime_checkpoint(session) and ctx.commit_session:
            await self.agent.sessions.state.restore_interruption(session)
        if (
            RECOVERY_INBOUND_METADATA_KEY not in msg.metadata
            and restore_pending_interruption(session)
            and ctx.commit_session
        ):
            await self.agent.sessions.state.restore_interruption(session)

    async def compact(self, ctx: TurnContext) -> None:
        if not ctx.commit_session:
            return
        session = ctx.require_session()
        ctx.session, pending = await self.agent.auto_compact.prepare_session(
            session,
            ctx.session_key,
        )
        ctx.pending_summary = pending

    async def build(self, ctx: TurnContext) -> None:
        session = ctx.require_session()
        runtime = ctx.runtime
        if runtime is None:
            runtime = await self.agent.runtime_for_session(session)
            ctx.runtime = runtime
        if ctx.session_key.startswith("dream:"):
            logger.info(
                "Dream run using model={} (preset={})",
                runtime.model,
                runtime.model_preset or "default",
            )
        if ctx.on_runtime_admitted is not None:
            await ctx.on_runtime_admitted(runtime)
        is_subagent = ctx.kind is TurnKind.SYSTEM and ctx.msg.sender_id == "subagent"

        ctx.history = await self.agent.runner.prepare_prompt(
            session.get_history,
            extend_to_user=is_subagent,
        )
        stored_state = session.provider_state
        subagent_followup_persisted = False
        if is_subagent:
            # Keep the durable internal delivery as an assistant record, but
            # present this completion to the model as fresh follow-up input.
            # Providers without assistant-prefill support drop trailing
            # assistant messages, so using the persisted record as the current
            # prompt would hide an independently dispatched subagent result.
            subagent_followup_persisted = self.agent.persistence.persist_subagent(
                session,
                ctx.msg,
            )
            if subagent_followup_persisted:
                logger.debug("Subagent result persisted for session {}", ctx.session_key)
                # Establish a durable, replay-safe baseline before any fallible
                # provider compatibility or prompt assembly work. A compatible
                # staged state replaces this in a second atomic save below.
                session.provider_state = None
                await self.agent.sessions.state.prepare_input(session)
            ctx.input_persisted_early = True
        await ctx.delivery.runtime_admitted(runtime)

        ctx.request_context = await self.agent.inputs.request_context(ctx)
        if ctx.kind is TurnKind.USER:
            ctx.runtime_context_blocks = await self.agent.inputs.resolve_context(ctx)
        if source_block := origin_context(ctx.msg):
            ctx.runtime_context_blocks = [source_block, *ctx.runtime_context_blocks]
        if session.policy.persist:
            memory = await self.agent.runner.prepare_prompt(
                self.agent.context.build_memory_context, session.messages[session.last_archived :]
            )
            if memory is not None:
                ctx.runtime_context_blocks.append(memory)
        if session.policy.persist and not ctx.ephemeral:
            checkpoint = await self.agent.runner.prepare_prompt(
                self.agent.context.build_task_context,
                ctx.session_key,
                project_id=session.metadata.get("project_id"),
                include_automatic=not bool(ctx.pending_summary),
            )
            if checkpoint is not None:
                ctx.runtime_context_blocks.append(checkpoint)
        staged_provider_state = False
        if stored_state is not None and runtime.provider.can_resume_conversation_state(
            stored_state,
            runtime.model,
        ):
            current_provider_message = self.agent.context.build_current_message(
                ctx.msg.content,
                media=ctx.msg.media if ctx.kind is TurnKind.USER and ctx.msg.media else None,
                current_role=ctx.msg.input_role or "user",
                runtime_context_blocks=ctx.runtime_context_blocks,
            )
            task_id = ctx.msg.metadata.get("subagent_task_id") if is_subagent else None
            already_staged = False
            if isinstance(task_id, str) and task_id:
                internal_meta = current_provider_message.get("_meta")
                current_provider_message["_meta"] = {
                    **(
                        cast(dict[str, Any], internal_meta)
                        if isinstance(internal_meta, dict)
                        else {}
                    ),
                    _SUBAGENT_PROVIDER_TASK_META: task_id,
                }
                already_staged = any(
                    isinstance(message.get("_meta"), dict)
                    and cast(dict[str, Any], message["_meta"]).get(_SUBAGENT_PROVIDER_TASK_META)
                    == task_id
                    for message in stored_state.pending_messages
                )
            ctx.provider_state = (
                stored_state
                if already_staged
                else stored_state.with_pending_messages(
                    [
                        *stored_state.pending_messages,
                        current_provider_message,
                    ]
                )
            )
            if not ctx.ephemeral and (ctx.kind is TurnKind.USER or subagent_followup_persisted):
                session.provider_state = ctx.provider_state
                staged_provider_state = True
        elif stored_state is not None:
            session.provider_state = None
        if (
            ctx.kind is TurnKind.USER or ctx.msg.metadata.get("_work_report")
        ) and ctx.commit_session:
            if (
                ctx.delivery.route.channel == "websocket"
                and ctx.turn_id
                and INBOUND_META_TURN_ID not in ctx.msg.metadata
            ):
                ctx.msg.metadata[INBOUND_META_TURN_ID] = ctx.turn_id
            ctx.input_persisted_early = await self.agent.inputs.persist_early(
                ctx.msg,
                session,
                runtime_context_blocks=ctx.runtime_context_blocks,
            )
            if staged_provider_state and not ctx.input_persisted_early:
                session.provider_state = stored_state
        elif subagent_followup_persisted and staged_provider_state:
            # Upgrade the replay-safe baseline to the resumable state before
            # prompt assembly and the first model checkpoint.
            await self.agent.sessions.state.prepare_input(session)
        if not session.persisted and ctx.commit_session:
            await self.agent.sessions.state.prepare_input(session)
        ctx.transcript_input = self.agent.inputs.transcript(ctx)
