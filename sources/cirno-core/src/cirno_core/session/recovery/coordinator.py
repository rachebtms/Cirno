"""Conversation recovery coordinator ownership."""

from __future__ import annotations

import asyncio
import dataclasses
from typing import Any, cast
from uuid import uuid4

from cirno_core.bus.events import InboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_core.config.agents import ResumeConfig
from cirno_core.session.manager import SessionManager
from cirno_core.session.session_identity import webui_chat_id

from .actions import RecoveryActions
from .checkpoints import restore_runtime_checkpoint
from .contracts import RECOVERY_INBOUND_METADATA_KEY
from .delivery import RecoveryDelivery
from .interruption import append_recovery_interruption, restore_pending_interruption
from .restart import RecoveryRestart
from .state import recovery_state_from_metadata, set_recovery_state, webui_route


@dataclasses.dataclass(slots=True)
class RecoveryCoordinator:
    """Own admission and completed-turn recovery; compose actions and restart scanning."""

    sessions: SessionManager
    bus: MessageBus
    resume_settings: ResumeConfig = dataclasses.field(default_factory=ResumeConfig)
    _active_recovery_tasks: dict[str, asyncio.Task[Any]] = dataclasses.field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _delivery: RecoveryDelivery = dataclasses.field(init=False, repr=False)
    _actions: RecoveryActions = dataclasses.field(init=False, repr=False)
    _restart: RecoveryRestart = dataclasses.field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._delivery = RecoveryDelivery(self.sessions, self.bus, self.resume_settings)
        self._actions = RecoveryActions(self.sessions, self.bus, self._delivery)
        self._restart = RecoveryRestart(self.sessions, self._delivery)

    async def scan(self) -> None:
        await self._restart.scan()

    async def resume_session(self, session_key: str) -> dict[str, Any]:
        return await self._actions.resume_session(session_key)

    async def handle_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._actions.execute(action, payload)

    def register_recovery_task(self, session_key: str, task: asyncio.Task[Any]) -> None:
        """Track the task that owns an explicit recovery continuation."""
        self._active_recovery_tasks[session_key] = task

    def unregister_recovery_task(self, session_key: str, task: asyncio.Task[Any]) -> None:
        """Drop a recovery task without removing a newer task for the same session."""
        if self._active_recovery_tasks.get(session_key) is task:
            self._active_recovery_tasks.pop(session_key, None)

    async def _cancel_active_recovery(self, session_key: str) -> None:
        """Stop an explicit continuation before accepting newer user input."""
        task = self._active_recovery_tasks.get(session_key)
        if task is None or task is asyncio.current_task() or task.done():
            return
        task.cancel()
        # AgentLoop's cancellation path materializes any partial checkpoint and
        # releases its pending queue. Wait for that ownership to be released
        # before the newer message is routed.
        await asyncio.gather(task, return_exceptions=True)

    async def admit(self, message: InboundMessage) -> bool:
        """Reject stale queued recoveries and let new user input supersede them."""
        recovery_id = message.metadata.get(RECOVERY_INBOUND_METADATA_KEY)
        if isinstance(recovery_id, str):
            session = await self.sessions.state.read(message.session_key)
            if (
                session is None
                or message.session_generation is not None
                and session.generation != message.session_generation
            ):
                return False
            state = recovery_state_from_metadata(session.metadata)
            return bool(
                state and state["status"] == "resuming" and state["recovery_id"] == recovery_id
            )
        # Coordination, heartbeat and scheduled input can reach a Web chat
        # through the internal channel. The destination owns recovery state.
        chat_id = webui_chat_id(message.session_key)
        if chat_id is None:
            return True
        session = await self.sessions.state.read(message.session_key)
        if session is None:
            return not message.require_existing_session and message.session_generation is None
        if (
            message.session_generation is not None
            and session.generation != message.session_generation
        ):
            return False
        state = recovery_state_from_metadata(session.metadata)
        if state and state["status"] in {"resuming", "awaiting_user", "failed"}:
            await self._cancel_active_recovery(message.session_key)
            # Cancellation can materialize the latest checkpoint. Classify its
            # committed result, never append an older draft of those tool rows.
            fresh = await self.sessions.state.read(message.session_key)
            if fresh is None or fresh.generation != session.generation:
                return False
            session = fresh
            state = recovery_state_from_metadata(session.metadata)
            if not state or state["status"] not in {"resuming", "awaiting_user", "failed"}:
                return True
            if state.get("reason") != "model_request_failed":
                restore_runtime_checkpoint(session)
                if not restore_pending_interruption(session, superseded=True):
                    append_recovery_interruption(session, superseded=True)
            recovered = set_recovery_state(
                session,
                status="recovered",
                recovery_id=cast(str, state["recovery_id"]),
                attempts=cast(int, state.get("attempts", 0)),
                reason="superseded",
            )
            await self.sessions.state.restore_interruption(session)
            await self._delivery.publish(chat_id, recovered, generation=session.generation)
        return True

    async def turn_stopped(self, session_key: str) -> None:
        """Offer continuation after cancellation has saved the partial turn."""
        session = await self.sessions.state.read(session_key)
        if session is None or not session.policy.persist:
            return
        route = webui_route(session.key)
        if route is None or not any(message.get("role") == "user" for message in session.messages):
            return
        waiting = set_recovery_state(
            session,
            status="awaiting_user",
            recovery_id=uuid4().hex,
            attempts=0,
            reason="user_stopped",
            can_continue=True,
        )
        await self.sessions.state.restore_interruption(session)
        await self._delivery.publish(route[1], waiting, generation=session.generation)

    async def turn_completed(
        self,
        session_key: str,
        *,
        failure_kind: str | None = None,
        failure_error_kind: str | None = None,
        expected_generation: str | None = None,
    ) -> None:
        """Offer explicit continuation of committed model failures or resolve recovery."""
        session = await self.sessions.state.read(session_key)
        if (
            session is None
            or expected_generation is not None
            and session.generation != expected_generation
        ):
            return
        state = recovery_state_from_metadata(session.metadata)
        route = webui_route(session.key)
        if route is None:
            return
        if failure_kind == "model":
            # The turn has already saved its transcript and tool results. Use
            # that context, never resend the user's message or replay tools.
            waiting = set_recovery_state(
                session,
                status="awaiting_user",
                recovery_id=uuid4().hex,
                attempts=cast(int, state.get("attempts", 0)) if state else 0,
                reason="model_request_failed",
                can_continue=any(message.get("role") == "user" for message in session.messages),
            )
            waiting["failure_error_kind"] = failure_error_kind or "unknown"
            if session.messages and session.messages[-1].get("_interrupted") is True:
                waiting["reply_preserved"] = True
            await self.sessions.state.restore_interruption(session)
            await self._delivery.publish(route[1], waiting, generation=session.generation)
            return
        if not state or state["status"] != "resuming":
            return
        recovered = set_recovery_state(
            session,
            status="recovered",
            recovery_id=cast(str, state["recovery_id"]),
            attempts=cast(int, state.get("attempts", 0)),
            reason="continued",
        )
        await self.sessions.state.restore_interruption(session)
        await self._delivery.publish(route[1], recovered, generation=session.generation)
