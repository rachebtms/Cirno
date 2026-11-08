"""Execution lifetime for one accepted input, including pre-model failures."""
from __future__ import annotations

import asyncio
from contextlib import nullcontext
from typing import TYPE_CHECKING

from cirno_core.command.router import command_text
from cirno_core.session import turn_continuation
from cirno_core.session.goal_state import goal_state_raw, parse_goal_state, sustained_goal_active
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.recovery.contracts import RECOVERY_INBOUND_METADATA_KEY
from cirno_core.session.recovery.checkpoints import restore_runtime_checkpoint
from loguru import logger

from .diagnostics import content_logging_allowed

if TYPE_CHECKING:
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.agent.turn_delivery import TurnDelivery
    from cirno_core.bus.events import InboundMessage


class SessionTurn:
    def __init__(self, agent: AgentLoop):
        self.agent = agent

    async def execute(self, msg: InboundMessage, pending: asyncio.Queue[InboundMessage]) -> None:
        key = self.agent.dispatch.session_key(msg)
        delivery = self.agent.turn_delivery_factory.unrouted(msg, key)
        recovery = self.agent.recovery_admission
        recovery_task = None
        executing = False
        lifecycle_active = False
        completion_published = False
        stage = "admission"
        log_content = False
        try:
            log_content = content_logging_allowed(self.agent.sessions, key)
            if recovery is not None:
                identifier = msg.metadata.get(RECOVERY_INBOUND_METADATA_KEY)
                if isinstance(identifier, str) and identifier:
                    recovery_task = asyncio.current_task()
                    if recovery_task is not None:
                        recovery.register_recovery_task(key, recovery_task)
                if not await recovery.admit(msg):
                    logger.info("Skipped stale recovery for session {}", key)
                    return
            lock = self.agent._get_session_lock(key)
            gate = (self.agent._concurrency_gate if key != ROUTER_SESSION_KEY else None) or nullcontext()
            async with lock, gate:
                executing = True
                self.agent._executing_sessions.add(key)
                stage = "guard"
                if not await self.current_goal(msg, key):
                    return
                lifecycle_active = True
                stage = "route"
                delivery = (await self.agent.turn_delivery_factory.create(msg, key, enable_stream=True))
                stage = "process"
                response = await self.agent.processing.process(msg, pending_queue=pending, delivery=delivery)
                stage = "delivery"
                await delivery.complete(response, publish_completion=not delivery.continuation_pending)
                completion_published = not delivery.continuation_pending
                for coordinator in self.agent._automation_turn_coordinators:
                    coordinator.complete(msg, response=response)
        except asyncio.CancelledError:
            logger.info("Task cancelled for session {}", key)
            if executing:
                delivery.continuation_pending = False
                await self.cancel(key, delivery)
            if not completion_published and self.agent.commands.requires_session_queue(command_text(msg)):
                await delivery.complete(None, publish_completion=True)
            raise
        except Exception as error:
            delivery.continuation_pending = False
            lifecycle_active = False
            await self.agent.dispatch.failed(msg, error, stage=stage, delivery=delivery, log_content=log_content)
        finally:
            if executing:
                self.agent._executing_sessions.discard(key)
            if recovery_task is not None and recovery is not None:
                recovery.unregister_recovery_task(key, recovery_task)
            if lifecycle_active and not delivery.continuation_pending:
                await delivery.idle()

    async def current_goal(self, msg: InboundMessage, key: str) -> bool:
        if turn_continuation.sustained_goal_continuation_inbound(msg.metadata) and not sustained_goal_active(
            (await self.agent.sessions.state.get(key)).metadata
        ):
            return False
        goal_id = msg.metadata.get("_goal_id")
        return not goal_id or (parse_goal_state(goal_state_raw(
            (await self.agent.sessions.state.get_header(key)).metadata
        )) or {}).get("goal_id") == goal_id

    async def cancel(self, key: str, delivery: TurnDelivery) -> None:
        log_content = content_logging_allowed(self.agent.sessions, key)
        try:
            await delivery.abort_stream()
        except Exception:
            logger.opt(exception=log_content).error("Could not close cancelled stream for {}", key)
        # Stop materializes completed side effects; shutdown retains the checkpoint
        # so recovery continues from the last durable boundary instead of replaying it.
        if key in self.agent._discarding_sessions or self.agent._preserve_inflight_turns_on_shutdown:
            return
        try:
            session = await self.agent.sessions.state.get(key)
            restore_runtime_checkpoint(session)
            await self.agent.sessions.state.finish_turn(session)
        except Exception:
            logger.opt(exception=log_content).error("Could not finalize cancelled turn for {}", key)
