"""Built-in control commands."""

from __future__ import annotations

import time
from dataclasses import replace

from cirno_core.bus.events import INBOUND_META_USER_SHELL, InboundMessage, OutboundMessage
from cirno_core.command.router import CommandContext
from cirno_core.session.history_visibility import HIDDEN_HISTORY_META
from cirno_core.utils.cancellation import shield_and_drain


async def cmd_stop(ctx: CommandContext) -> OutboundMessage:
    """Cancel all active tasks and subagents for the session."""
    loop = ctx.loop
    msg = ctx.msg
    total = await loop.cancel_session_work(ctx.key)
    content = f"Stopped {total} task(s)." if total else "No active task to stop."
    return OutboundMessage(
        channel=msg.channel, chat_id=msg.chat_id, content=content, metadata=dict(msg.metadata or {})
    )


def _human_control_required(ctx: CommandContext) -> OutboundMessage | None:
    if ctx.is_user_turn:
        return None
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content="This control requires a direct user request; agent and system inputs cannot change it.",
        metadata={**ctx.msg.metadata, "render_as": "text"},
    )


async def cmd_access(ctx: CommandContext) -> OutboundMessage:
    from cirno_core.bus.outbound_events import SessionUpdatedEvent, outbound_message_for_event
    from cirno_core.security.workspace_access import (
        WORKSPACE_SCOPE_METADATA_KEY,
        build_workspace_scope,
    )

    denied = _human_control_required(ctx)
    if denied is not None:
        return denied
    mode = {
        "default": "restricted",
        "restricted": "restricted",
        "review": "review",
        "full": "full",
    }.get(ctx.args.strip().lower())
    text = "Usage: /access default|review|full"
    if mode is not None:
        session = ctx.session or await ctx.loop.sessions.state.get(ctx.key)
        scope = ctx.loop.workspace_scopes.for_turn(
            channel="websocket", message_metadata={}, session_metadata=session.metadata
        )
        changed = build_workspace_scope(scope.project_path, mode, source_channel="websocket")
        await ctx.loop.sessions.state.update_metadata(
            ctx.key,
            {WORKSPACE_SCOPE_METADATA_KEY: changed.payload()},
            expected_generation=session.generation,
        )
        await ctx.loop.bus.publish_outbound(
            outbound_message_for_event(
                channel="websocket",
                chat_id=ctx.key.split(":", 1)[1],
                event=SessionUpdatedEvent(scope="metadata", workspace_scope=changed.payload()),
                metadata={},
            )
        )
        text = {
            "restricted": "Default access selected.",
            "review": "Independent AI review selected. AI decisions can be wrong; uncertain cases require owner approval in Inbox.",
            "full": "Full Access selected. Commands and files are not restricted to the workspace; mistakes can expose or damage data.",
        }[mode]
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=text,
        metadata={**ctx.msg.metadata, "render_as": "text"},
    )


async def cmd_draft_mode(ctx: CommandContext) -> OutboundMessage:
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content="Use /temporary on|off or /ptc on|off in the new-conversation composer before sending its first message.",
        metadata={**ctx.msg.metadata, "render_as": "text"},
    )


async def cmd_resume(ctx: CommandContext) -> OutboundMessage:
    """Resume the saved request through the same mechanism as the UI button."""
    from cirno_core.session.recovery.contracts import RecoveryActionError

    denied = _human_control_required(ctx)
    if denied is not None:
        return denied
    recovery = ctx.loop.recovery_admission
    if ctx.loop.dispatch.is_running(ctx.key):
        text = "This conversation is already running."
    elif recovery is None:
        text = "Continuation is unavailable in this runtime."
    else:
        try:
            await recovery.resume_session(ctx.key)
        except RecoveryActionError as error:
            text = str(error)
        else:
            text = "Continuing from saved context."
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=text,
        metadata={**ctx.msg.metadata, "render_as": "text"},
    )


async def cmd_clear(ctx: CommandContext) -> OutboundMessage:
    """Only the fixed personal conversation needs a dedicated clear command."""
    from cirno_core.session.keys import ROUTER_SESSION_KEY

    if ctx.key != ROUTER_SESSION_KEY:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="/clear is available only in the Router conversation.",
            metadata=dict(ctx.msg.metadata),
        )
    return await cmd_new(ctx)


async def cmd_new(ctx: CommandContext) -> OutboundMessage:
    """Stop active task and start a fresh session."""
    denied = _human_control_required(ctx)
    if denied is not None:
        return denied
    loop = ctx.loop
    await loop.cancel_session_work(ctx.key)
    loop.discard_session_file_state(ctx.key)
    session = ctx.session or await loop.sessions.state.get(ctx.key)
    snapshot = list(session.messages)
    archive_snapshot = None
    runtime = None
    if session.last_archived < len(snapshot):
        runtime = ctx.runtime or await loop.runtime_for_session(session)
        archive_snapshot = replace(
            session,
            messages=snapshot,
            metadata=dict(session.metadata),
            provider_state=None,
        )

    async def reset_and_schedule_archive() -> None:
        await loop.sessions.state.reset(session.key)
        if archive_snapshot is not None and runtime is not None:
            loop.schedule_background(
                loop.consolidator.archive_session(  # pyright: ignore[reportUnknownMemberType]
                    archive_snapshot,
                    archive_end=len(snapshot),
                    runtime=runtime,
                )
            )

    await shield_and_drain(reset_and_schedule_archive())
    from cirno_core.bus.outbound_events import SessionUpdatedEvent, outbound_message_for_event
    from cirno_core.session.session_identity import webui_chat_id

    chat_id = webui_chat_id(ctx.key)
    if chat_id is not None:
        await loop.bus.publish_outbound(
            outbound_message_for_event(
                channel="websocket",
                chat_id=chat_id,
                event=SessionUpdatedEvent(scope="reset"),
                metadata={},
            )
        )
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content="New session started.",
        metadata=dict(ctx.msg.metadata or {}),
    )


async def cmd_compact(ctx: CommandContext) -> OutboundMessage | None:
    """Compact the current session without resetting the conversation."""
    loop = ctx.loop
    session = ctx.session or await loop.sessions.state.get(ctx.key)
    runtime = ctx.runtime or await loop.runtime_for_session(session)
    if ctx.args.strip():
        from cirno_core.memory.consolidation_recovery import retry_session_learning
        parts = ctx.args.split()
        if parts[0] != "retry" or len(parts) > 2:
            raise ValueError("Usage: /consolidate retry [source-id]")
        async with loop.consolidator.get_lock(ctx.key):
            result = await retry_session_learning(loop.consolidator.archiver, session, runtime, parts[1] if len(parts) == 2 else None)
        failure = result.get("learning_failure")
        text = (f"Learning retry incomplete. Source: {failure['source']}. Pending: "
                + "; ".join(item["label"] or item["kind"] for item in failure["pending"])
                + f". Error: {failure['error']}" if failure else
                f"Learning retry completed: {result['retried']} batch. Existing task checkpoint retained.")
        return OutboundMessage(channel=ctx.msg.channel, chat_id=ctx.msg.chat_id, content=text, metadata=dict(ctx.msg.metadata or {}))
    delivery = (await loop.turn_delivery_factory.create(ctx.msg, ctx.key))

    await loop.consolidator.compact_idle_session(
        ctx.key,
        runtime=runtime,
        events=delivery.events,
        notify=True,
        reason="manual",
    )


async def cmd_goal(ctx: CommandContext) -> InboundMessage | OutboundMessage:
    """Expand an explicit goal command into model-only input."""
    goal = ctx.args.strip()
    if not goal:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Usage: /goal <long-running task description>",
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )
    if not ctx.is_user_turn:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Goal mode can only be started by a user `/goal <task>` command.",
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    session = ctx.session or await ctx.loop.sessions.state.get(ctx.key)
    session.add_message("user", ctx.msg.content, _command=True, media=list(ctx.msg.media))
    await ctx.loop.sessions.state.prepare_input(session)
    return replace(
        ctx.msg,
        content=goal,
        metadata={
            **ctx.msg.metadata,
            "original_command": "/goal",
            "original_content": ctx.msg.content,
            "goal_requested": True,
            "goal_started_at": time.time(),
            HIDDEN_HISTORY_META: {"kind": "goal_request"},
        },
    )


async def cmd_user_shell(ctx: CommandContext) -> OutboundMessage:
    """Run a trusted local ``!command`` through cirno's exec policy."""
    metadata = dict(ctx.msg.metadata or {})
    if (
        ctx.msg.channel != "websocket"
        or metadata.get("webui") is not True
        or metadata.get(INBOUND_META_USER_SHELL) is not True
    ):
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Shell commands are only available from a trusted local client.",
            metadata={**metadata, "render_as": "text"},
        )
    if not ctx.args.strip():
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Type a command after `!`, for example `!pwd`.",
            metadata={**metadata, "render_as": "text"},
        )
    return await ctx.loop.command_execution.user_shell(ctx)
