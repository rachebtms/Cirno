"""TurnCommands owns its stage of the admitted conversation lifecycle."""

from __future__ import annotations

from contextlib import ExitStack
from typing import TYPE_CHECKING, Awaitable, Callable

from cirno_core.agent.execution.context import TurnContext, TurnKind
from cirno_core.agent.goals.permission import GoalInputScope
from cirno_core.agent.tools.context import (
    RequestContext,
    bind_request_context,
    reset_request_context,
)
from cirno_core.agent.tools.shell import ExecTool
from cirno_core.bus.events import (
    INBOUND_META_USER_SHELL,
    InboundMessage,
    OutboundMessage,
)
from cirno_core.command import CommandContext
from cirno_core.command.router import command_text
from cirno_core.security.workspace_access import bind_workspace_scope, reset_workspace_scope
from cirno_core.session import turn_continuation
from cirno_core.session.automation_turns import automation_history_overrides

if TYPE_CHECKING:
    from cirno_core.agent.loop import AgentLoop


class TurnCommands:
    def __init__(self, agent: AgentLoop):
        self.agent = agent

    async def dispatch_inline(
        self,
        msg: InboundMessage,
        key: str,
        raw: str,
        dispatch_fn: Callable[[CommandContext], Awaitable[InboundMessage | OutboundMessage | None]],
    ) -> None:
        """Dispatch a command directly from the run() loop and publish the result."""
        if self.agent.commands.requires_session_queue(raw):
            await self.agent.dispatch.enqueue(msg)
            return

        async def dispatch_and_publish() -> None:
            _, automation_metadata = automation_history_overrides(msg.metadata)
            ctx = CommandContext(
                msg=msg,
                session=None,
                key=key,
                raw=raw,
                loop=self.agent,
                is_user_turn=(
                    msg.is_user_input
                    and msg.channel != "system"
                    and msg.sender_id != "subagent"
                    and not automation_metadata
                    and not turn_continuation.internal_continuation_inbound(msg.metadata)
                ),
            )
            result = await dispatch_fn(ctx)
            if isinstance(result, InboundMessage):
                await self.agent.dispatch.enqueue(result)
            elif result is not None:
                await self.agent.bus.publish_outbound(result)

        # A shell command may run for up to the configured exec timeout. Keep
        # the inbound consumer responsive when it runs beside an active turn.
        if (msg.metadata or {}).get(INBOUND_META_USER_SHELL) is True:
            self.agent.schedule_background(dispatch_and_publish())
            return
        await dispatch_and_publish()

    async def dispatch(self, ctx: TurnContext) -> bool:
        if ctx.kind is TurnKind.SYSTEM or ctx.msg.channel == "system":
            return False
        session = ctx.require_session()
        raw = command_text(ctx.msg)
        _, automation_metadata = automation_history_overrides(ctx.msg.metadata)
        is_user_turn = (
            ctx.original_user_text is not None
            and not automation_metadata
            and ctx.msg.channel != "system"
            and ctx.msg.sender_id != "subagent"
        )
        cmd_ctx = CommandContext(
            msg=ctx.msg,
            session=session,
            key=ctx.session_key,
            raw=raw,
            loop=self.agent,
            runtime=ctx.runtime,
            is_user_turn=is_user_turn,
            turn_scopes=ctx.turn_scopes,
        )
        command_matched = self.agent.commands.command_name(raw) is not None
        result = await self.agent.commands.dispatch(cmd_ctx)
        if isinstance(result, InboundMessage):
            ctx.msg = result
            result = None
            command_matched = False
        ctx.turn_scopes.append(GoalInputScope(ctx.msg))
        if result is not None:
            ctx.outbound = result
            if cmd_ctx.raw.lower() == "/new":
                current = await self.agent.sessions.state.get_header(ctx.session_key)
                await ctx.delivery.bind_session_generation(current.generation)
            # Shortcut commands skip BUILD and SAVE, so we must persist the
            # turn here so WebUI history hydration after turn_end sees the
            # message.  Mark messages with _command so get_history can filter
            # them out of LLM context.  /new is excluded because it
            # intentionally clears the session.
            if cmd_ctx.raw.lower() not in {"/new", "/clear"} and ctx.commit_session:
                ctx.input_persisted_early = await self.agent.inputs.persist_early(
                    ctx.msg, session, _command=True
                )
                session.add_message("assistant", result.content, _command=True)
                self.agent.persistence.clear_pending(session)
                await self.agent.sessions.state.prepare_input(session)
                if not ctx.ephemeral:
                    await self.agent.runtime_event_publisher.session_turn_persisted(
                        ctx.msg,
                        ctx.session_key,
                        turn_id=ctx.turn_id,
                        attributes=ctx.attributes,
                    )
            return True
        return command_matched

    async def user_shell(self, ctx: CommandContext) -> OutboundMessage:
        """Execute one trusted user command with the active workspace policy."""
        metadata = dict(ctx.msg.metadata or {})
        tool = self.agent.tools.get("exec")
        if not isinstance(tool, ExecTool):
            content = "Shell execution is disabled in this Cirno configuration."
        else:
            session = ctx.session or await self.agent.sessions.state.get(ctx.key)
            scope = self.agent.workspace_scopes.for_turn(
                channel=ctx.msg.channel,
                message_metadata=metadata,
                session_metadata=session.metadata,
            )
            request_token = bind_request_context(
                RequestContext(
                    channel=ctx.msg.channel,
                    chat_id=ctx.msg.chat_id,
                    message_id=metadata.get("message_id"),
                    session_key=ctx.key,
                    session_generation=session.generation,
                    original_user_text=f"!{ctx.args.strip()}",
                    runtime=ctx.runtime,
                    metadata=metadata,
                    sender_id=ctx.msg.sender_id,
                    turn_id=metadata.get("webui_turn_id"),
                    workspace=scope.project_path,
                    log_content=session.policy.log_content,
                )
            )
            workspace_token = bind_workspace_scope(scope)
            turn_scope_stack = ExitStack()
            try:
                for turn_scope in ctx.turn_scopes:
                    turn_scope_stack.enter_context(turn_scope)
                result = await tool.execute_to_completion(
                    command=ctx.args.strip(),
                    working_dir=str(scope.project_path),
                )
                content = str(result)
            finally:
                turn_scope_stack.close()
                reset_workspace_scope(workspace_token)
                reset_request_context(request_token)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=content,
            metadata={**metadata, "render_as": "text"},
        )
