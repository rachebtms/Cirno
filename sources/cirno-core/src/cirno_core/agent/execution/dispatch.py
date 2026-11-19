"""SessionDispatcher for conversation admission and resource lifetime."""

from __future__ import annotations

import asyncio
import dataclasses
from typing import TYPE_CHECKING

from loguru import logger

from cirno_core.bus.events import (
    INBOUND_META_RUNTIME_CONTROL,
    RUNTIME_CONTROL_SESSION_DISCARD,
    InboundMessage,
)
from cirno_core.command.router import command_text
from cirno_core.session import turn_continuation
from cirno_core.session.goal_state import goal_state_raw, parse_goal_state
from cirno_core.session.keys import session_key_for_channel
from cirno_core.session.recovery.contracts import PENDING_FOLLOWUP_ID_KEY
from cirno_core.session.transport_metadata import WEBSOCKET_TURN_OWNER_METADATA_KEY

from .diagnostics import content_logging_allowed

if TYPE_CHECKING:
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.agent.turn_delivery import TurnDelivery


class SessionDispatcher:
    def __init__(self, agent: AgentLoop):
        self.agent = agent
        from .session_turn import SessionTurn
        self.turn = SessionTurn(agent)

    def is_running(self, session_key: str) -> bool:
        """Whether this session owns an admitted worker and its pending queue."""
        return session_key in self.agent._pending_queues

    def session_key(self, msg: InboundMessage) -> str:
        """Return the session key used for task routing and mid-turn injections."""
        if not msg.session_key_override:
            return session_key_for_channel(
                msg.channel,
                msg.chat_id,
            )
        return msg.session_key

    def can_inject(self, msg: InboundMessage) -> bool:
        """Keep independent turns and controls out of user-input batches."""
        if turn_continuation.internal_continuation_inbound(msg.metadata) or any(
            coordinator.owns_turn(msg) for coordinator in self.agent._automation_turn_coordinators
        ):
            return False
        return msg.channel == "system" or not self.agent.commands.is_dispatchable_command(
            command_text(msg)
        )

    async def receive(self, msg: InboundMessage) -> None:
        """Route one input through command and session admission."""
        self.agent.lifecycle.check_admission()
        from cirno_core.runtime.heartbeat import discard_paused_heartbeat
        if await discard_paused_heartbeat(self.agent.sessions, msg):
            return
        raw = command_text(msg)
        effective_key = self.session_key(msg)
        if msg.metadata.get(INBOUND_META_RUNTIME_CONTROL) == RUNTIME_CONTROL_SESSION_DISCARD:
            await self.agent.discard_session(msg.session_key)
            return
        if msg.require_existing_session or msg.session_generation is not None:
            current = await self.agent.sessions.state.read_header(effective_key)
            if current is None or (
                msg.session_generation is not None and current.generation != msg.session_generation
            ):
                return
        if msg.is_user_input and not msg.metadata.get("_session_message"):
            await self.agent.runtime_event_publisher.user_input_accepted(msg, effective_key)
        if msg.channel != "system" and self.agent.commands.is_priority(raw):
            await self.agent.command_execution.dispatch_inline(
                msg,
                effective_key,
                raw,
                self.agent.commands.dispatch_priority,
            )
            return
        routed_msg = msg
        if effective_key != msg.session_key:
            routed_msg = dataclasses.replace(
                msg,
                session_key_override=effective_key,
            )
        # A newer WebUI message must supersede an explicit recovery
        # before it is injected into that recovery's pending queue.
        # Without this admission point, a recovered turn could finish
        # first and only then observe the user's newer request.
        if (
            effective_key in self.agent._pending_queues
            and msg.channel == "websocket"
            and self.agent.recovery_admission is not None
            and not await self.agent.recovery_admission.admit(routed_msg)
        ):
            return
        # If this session already has an active pending queue (i.e. a task
        # is processing this session), route the message there for mid-turn
        # injection instead of creating a competing task.
        if effective_key in self.agent._pending_queues:
            if msg.channel != "system" and self.agent.commands.is_dispatchable_command(raw):
                await self.agent.command_execution.dispatch_inline(
                    msg,
                    effective_key,
                    raw,
                    self.agent.commands.dispatch,
                )
                return
        await self.enqueue(routed_msg)

    async def journal(
        self,
        session_key: str,
        msg: InboundMessage,
    ) -> InboundMessage:
        """Persist a recoverable WebUI follow-up before adding it to the inbox."""
        if not self.can_inject(msg):
            return msg
        followup_id = await self.agent.sessions.state.queue_followup(session_key, msg)
        if followup_id is None:
            return msg
        pending_msg = dataclasses.replace(
            msg,
            metadata={
                **msg.metadata,
                PENDING_FOLLOWUP_ID_KEY: followup_id,
            },
        )
        return pending_msg

    async def enqueue(self, msg: InboundMessage) -> None:
        """Admit work after any in-progress control operation has settled."""
        async with self.agent.session_intake_lock(self.session_key(msg)):
            await self.enqueue_locked(msg)

    async def enqueue_locked(self, msg: InboundMessage) -> None:
        """Admit session work while the caller owns its intake lock."""
        self.agent.lifecycle.check_admission()
        self.agent.bus.admission.check()
        session_key = self.session_key(msg)
        receipted_input = bool(msg.metadata.get("_session_message")) or (
            msg.input_role == "system" and bool(msg.metadata.get(PENDING_FOLLOWUP_ID_KEY))
        )
        if receipted_input:
            identifier = await self.agent.sessions.state.queue_followup(session_key, msg)
            if identifier is None:
                return
            accepted = self.agent._journaled_input_ids.setdefault(session_key, set())
            if identifier in accepted:
                return
            msg = dataclasses.replace(
                msg, metadata={**msg.metadata, PENDING_FOLLOWUP_ID_KEY: identifier}
            )
            current = await self.agent.sessions.state.read_metadata(session_key)
            accepted.intersection_update(
                record["id"]
                for record in (current or {}).get("metadata", {}).get("pending_user_followups", [])
            )
            goal = parse_goal_state(goal_state_raw((current or {}).get("metadata"))) or {}
            if msg.metadata.get("_session_message") and goal.get("status") == "waiting":
                resumed = {**goal, "status": "active"}
                resumed.pop("wake_at", None)
                await self.agent.sessions.state.update_metadata(
                    session_key, {"goal_state": resumed}
                )
        if not self.agent.subagents.accepts_result(msg, session_key):
            return
        if session_key != msg.session_key:
            msg = dataclasses.replace(msg, session_key_override=session_key)

        for coordinator in self.agent._automation_turn_coordinators:
            if coordinator.defer_if_active(
                msg,
                session_key=session_key,
                active_session_keys=self.agent._pending_queues.keys(),
            ):
                return

        if session_key in self.agent._pending_queues and not receipted_input:
            msg = await self.journal(session_key, msg)
        if receipted_input:
            self.agent._journaled_input_ids.setdefault(session_key, set()).add(
                msg.metadata[PENDING_FOLLOWUP_ID_KEY]
            )
            if msg.is_user_input:
                await self.agent.runtime_event_publisher.user_input_accepted(msg, session_key)
        # Receipt/journal persistence above can yield while shutdown begins.
        # No worker may be created after the close owner captured its task set.
        self.agent.lifecycle.check_admission()
        pending = self.agent._pending_queues.get(session_key)
        if pending is not None:
            pending.put_nowait(msg)
            return

        new_pending: asyncio.Queue[InboundMessage] = asyncio.Queue()
        new_pending.put_nowait(msg)
        self.agent._pending_queues[session_key] = new_pending
        task = asyncio.create_task(self.run_queue(session_key, new_pending))
        self.agent._track_active_task(session_key, task)

    async def run_queue(
        self,
        session_key: str,
        pending: asyncio.Queue[InboundMessage],
    ) -> None:
        """Run the sole worker for a session until its inbox is empty."""
        settled_owner: str | None = None
        try:
            while self.agent._pending_queues.get(session_key) is pending:
                try:
                    msg = pending.get_nowait()
                except asyncio.QueueEmpty:
                    # Idle-only automation follows all accepted user input on
                    # this same worker, including before the bus loop starts.
                    deferred = self.agent._deferred_automation_turns.get(session_key)
                    if not deferred:
                        break
                    msg = deferred.pop(0)
                    if not deferred:
                        self.agent._deferred_automation_turns.pop(session_key)
                log_content = False
                try:
                    log_content = content_logging_allowed(self.agent.sessions, session_key)
                    await self.execute(msg, pending)
                except asyncio.CancelledError as exc:
                    owner = msg.metadata.get(WEBSOCKET_TURN_OWNER_METADATA_KEY)
                    if isinstance(owner, str):
                        settled_owner = owner
                    for coordinator in self.agent._automation_turn_coordinators:
                        coordinator.complete(msg, error=exc)
                    raise
                except Exception as error:
                    logger.opt(exception=log_content).error(
                        "Session worker finalization failed for {} ({}); continuing FIFO",
                        session_key, type(error).__name__,
                    )
        except asyncio.CancelledError as exc:
            await self.cancel_pending(session_key, pending, exc, settled_owner=settled_owner)
            raise
        finally:
            owns_queue = self.agent._pending_queues.get(session_key) is pending
            if owns_queue:
                self.agent._pending_queues.pop(session_key, None)
                self.agent._journaled_input_ids.pop(session_key, None)

    async def cancel_pending(
        self,
        session_key: str,
        pending: asyncio.Queue[InboundMessage],
        error: asyncio.CancelledError,
        *,
        settled_owner: str | None = None,
    ) -> None:
        """Complete queued independent turns after their session worker stops."""
        settled: set[str] = {settled_owner} if settled_owner is not None else set()
        for msg in self.agent._deferred_automation_turns.pop(session_key, []):
            pending.put_nowait(msg)
        while not pending.empty():
            msg = pending.get_nowait()
            for coordinator in self.agent._automation_turn_coordinators:
                coordinator.complete(msg, error=error)
            owner = msg.metadata.get(WEBSOCKET_TURN_OWNER_METADATA_KEY)
            if isinstance(owner, str) and owner in settled:
                continue  # An automatic handoff shares its parent's visible turn.
            if msg.channel != "system":
                delivery = self.agent.turn_delivery_factory.unrouted(msg, session_key)
                try:
                    await delivery.complete(None, publish_completion=True)
                finally:
                    await delivery.idle()
                if isinstance(owner, str):
                    settled.add(owner)

    async def execute(self, msg: InboundMessage, pending: asyncio.Queue[InboundMessage]) -> None:
        return await self.turn.execute(msg, pending)

    async def failed(
        self, msg: InboundMessage, error: Exception, *, stage: str,
        delivery: TurnDelivery | None = None, publish_completion: bool = True, log_content: bool | None = None,
    ) -> None:
        """Settle an accepted input and report failures outside processing stages."""
        key = self.session_key(msg)
        if log_content is None:
            log_content = content_logging_allowed(self.agent.sessions, key)
        logger.opt(exception=log_content).error("Conversation {} failed at {}: {}", key, stage, type(error).__name__)
        for coordinator in self.agent._automation_turn_coordinators:
            coordinator.complete(msg, error=error)
        delivery = delivery or self.agent.turn_delivery_factory.unrouted(msg, key)
        if stage != "process":
            await self.agent.reports.unstarted(msg, key, delivery, stage=stage, error=error)
        await delivery.fail(publish_completion=publish_completion)
        if publish_completion:
            await delivery.idle()
