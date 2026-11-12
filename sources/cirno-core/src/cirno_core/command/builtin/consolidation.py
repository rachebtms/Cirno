"""Deliver manual learning recovery through persisted consolidation reports."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from cirno_core.bus.agent_events import ContextCompactionEvent
from cirno_core.command.router import CommandContext
from cirno_core.memory.consolidation_recovery import retry_session_learning
from cirno_core.memory.consolidation_retry_report import empty_report
from cirno_core.session.model import Session
from cirno_core.utils.llm_runtime import LLMRuntime


async def retry_consolidation(ctx: CommandContext, session: Session, runtime: LLMRuntime) -> None:
    parts = ctx.args.split()
    source = parts[1] if len(parts) == 2 else None
    delivery = await ctx.loop.turn_delivery_factory.create(ctx.msg, ctx.key)
    report = empty_report(source)
    identifier = uuid4().hex

    async def emit(phase, *, error=None):
        await delivery.events.emit(
            ContextCompactionEvent(
                compaction_id=identifier,
                phase=phase,
                reason="manual",
                notify=True,
                learning_retry=report,
                error=error,
            )
        )

    await emit("started")
    try:
        if not parts or parts[0].lower() != "retry" or len(parts) > 2:
            raise ValueError("Usage: /consolidate retry [source-id]")
        async with ctx.loop.consolidator.get_lock(ctx.key):
            result = await retry_session_learning(
                ctx.loop.consolidator.archiver, session, runtime, source
            )
        report = result["learning_retry"]
        failure = result.get("learning_failure")
        if failure:
            await emit("failed", error=failure["error"])
        elif report["outcome"] == "incomplete":
            await emit("failed", error="Learning recovery has no completed save receipt.")
        else:
            await emit("succeeded")
    except asyncio.CancelledError:
        report = {**report, "outcome": "incomplete"}
        await emit("cancelled")
        raise
    except Exception as error:
        report = {**report, "outcome": "incomplete"}
        await emit("failed", error=f"{type(error).__name__}: {error}"[:1000])
