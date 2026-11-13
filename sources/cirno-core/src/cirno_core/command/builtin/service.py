"""Built-in service commands."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from typing import Any

from cirno_usage.types import LLMUsage

from cirno_core import __version__
from cirno_core.agent.context_usage import measure_context_usage
from cirno_core.bus.events import OutboundMessage
from cirno_core.command.router import CommandContext
from cirno_core.utils.restart import set_restart_notice_to_env
from cirno_core.utils.runtime_status import build_status_content
from cirno_core.utils.searchusage import fetch_search_usage


async def cmd_restart(ctx: CommandContext) -> OutboundMessage:
    """Restart the process."""
    from .control import _human_control_required

    denied = _human_control_required(ctx)
    if denied is not None:
        return denied
    msg = ctx.msg
    set_restart_notice_to_env(
        channel=msg.channel,
        chat_id=msg.chat_id,
        metadata=dict(msg.metadata or {}),
    )

    async def _do_restart():
        await asyncio.sleep(1)
        argv = [sys.executable, "-m", "cirno"] + sys.argv[1:]
        mode = ctx.loop.restart_mode or "auto"
        if mode == "auto":
            mode = "spawn" if sys.platform == "win32" else "exec"
        if mode == "exec":
            os.execv(sys.executable, argv)
            return
        if mode == "spawn":
            kwargs: dict[str, Any] = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(argv, **kwargs)
        os._exit(0)

    asyncio.create_task(_do_restart())
    return OutboundMessage(
        channel=msg.channel,
        chat_id=msg.chat_id,
        content="Restarting...",
        metadata=dict(msg.metadata or {}),
    )


async def cmd_status(ctx: CommandContext) -> OutboundMessage:
    """Build an outbound status message for a session."""
    loop = ctx.loop
    session = ctx.session or await loop.sessions.state.get(ctx.key)
    runtime = ctx.runtime or await loop.runtime_for_session(session)
    ctx_est, _ = await measure_context_usage(
        session, runtime,
        consolidator=loop.consolidator, workspace_scopes=loop.workspace_scopes,
    )
    message_count = await asyncio.to_thread(lambda: len(session.get_history(max_messages=0)))
    last_usage = LLMUsage.from_dict(session.metadata.get("_last_usage"))
    if ctx_est <= 0:
        ctx_est = last_usage.input_tokens if last_usage is not None else 0

    # Await web search provider usage; network requests have a bounded timeout.
    search_cfg = loop.web_config.search
    usage = await fetch_search_usage(
        provider=search_cfg.provider,
        api_key=search_cfg.api_key or None,
    )
    search_usage_text = usage.format()
    active_tasks = loop._active_tasks.get(ctx.key, [])  # pyright: ignore[reportPrivateUsage]
    task_count = sum(1 for t in active_tasks if not t.done())
    task_count += loop.subagents.get_running_count_by_session(ctx.key)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=build_status_content(
            version=__version__,
            model=runtime.model,
            start_time=loop._start_time,  # pyright: ignore[reportPrivateUsage]
            last_usage=last_usage,
            context_window_tokens=runtime.context_window_tokens,
            session_msg_count=message_count,
            context_tokens_estimate=ctx_est,
            search_usage_text=search_usage_text,
            active_task_count=task_count,
            max_completion_tokens=runtime.generation.max_tokens,
            output_reserve_percent=runtime.output_reserve_percent,
            active_compact_percent=runtime.active_compact_percent,
        ),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )
