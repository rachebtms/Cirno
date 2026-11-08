"""WorkerReports owns its stage of the admitted conversation lifecycle."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cirno_core.agent.execution.context import TurnContext, TurnKind
from loguru import logger

from .diagnostics import content_logging_allowed

if TYPE_CHECKING:
    from cirno_core.agent.loop import AgentLoop


class WorkerReports:
    def __init__(self, agent: AgentLoop):
        self.agent = agent

    async def publish(self, ctx: TurnContext, *, stage=None, error=None) -> None:
        try:
            await self.record(ctx, stage=stage, error=error)
        except Exception as error:
            # Reporting is auxiliary: a completed turn must never become a failed task.
            # Existing durable reports are retried by the Goal scheduler.
            log_content = content_logging_allowed(self.agent.sessions, ctx.session_key, session=ctx.session, ephemeral=ctx.ephemeral)
            logger.opt(exception=log_content).error(
                "Worker outcome reporting deferred for {} ({})", ctx.session_key, type(error).__name__,
            )

    async def unstarted(self, msg, key, delivery, *, stage, error) -> None:
        """Use the same durable report path when execution fails before a turn context."""
        from time import time_ns

        from cirno_core.bus.events import INBOUND_META_TURN_ID
        context = TurnContext(
            msg=msg, session_key=key, delivery=delivery, runtime=None,
            kind=TurnKind.USER if msg.is_user_input else TurnKind.SYSTEM,
            turn_id=msg.metadata.get(INBOUND_META_TURN_ID) or f"{key}:{time_ns()}",
        )
        await self.publish(context, stage=stage, error=error)

    async def record(self, ctx: TurnContext, *, stage=None, error=None) -> None:
        if ctx.ephemeral or not ctx.commit_session:
            return
        from cirno_core.agent.work_reports import record_execution_report

        runtime = ctx.runtime
        report = await record_execution_report(
            self.agent.sessions,
            ctx.session_key,
            turn_id=ctx.turn_id,
            stop_reason="error" if error is not None else ctx.stop_reason,
            output=f"{type(error).__name__}: {error}" if error is not None else ctx.final_content,
            failure_error_kind=ctx.failure_error_kind,
            model=runtime.model if runtime else None,
            model_preset=runtime.model_preset if runtime else None,
            stage=stage,
            continuation_pending=ctx.delivery.continuation_pending,
            expected_generation=ctx.session.generation
            if ctx.session
            else ctx.msg.session_generation,
        )
        await self.deliver(ctx.session_key, report)

    async def deliver(self, key, report) -> None:
        from cirno_core.agent.tools.session_messages import SessionMessageError
        from cirno_core.agent.work_reports import deliver_work_report

        sender = self.agent.tools.get("send_session_message")
        if report is not None and sender is not None:
            try:
                await deliver_work_report(self.agent.sessions, sender, key, report)
            except SessionMessageError as delivery_error:
                logger.warning("Execution report delivery deferred for {}: {}", key, delivery_error)
