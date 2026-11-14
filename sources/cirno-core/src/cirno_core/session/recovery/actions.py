"""Conversation recovery actions ownership."""

from __future__ import annotations

import asyncio
import dataclasses
from typing import Any, cast
from weakref import WeakValueDictionary

from cirno_core.bus.queue import MessageBus
from cirno_core.session.goal_state import goal_state_raw, parse_goal_state, resume_goal_state
from cirno_core.session.manager import SessionManager
from cirno_core.session.session_identity import webui_session_key
from cirno_core.utils.cancellation import shield_and_drain

from .checkpoints import restore_runtime_checkpoint
from .contracts import RecoveryActionError
from .delivery import RecoveryDelivery
from .interruption import restore_pending_interruption
from .state import recovery_state_from_metadata, set_recovery_state


@dataclasses.dataclass(slots=True)
class RecoveryActions:
    sessions: SessionManager
    bus: MessageBus
    delivery: RecoveryDelivery
    _action_locks: WeakValueDictionary[str, asyncio.Lock] = dataclasses.field(
        default_factory=WeakValueDictionary,
        init=False,
        repr=False,
    )

    async def resume_session(self, session_key: str) -> dict[str, Any]:
        """Use the same recovery action for a slash command and the Continue UI."""
        session = await self.sessions.state.read_header(session_key)
        state = recovery_state_from_metadata(session.metadata) if session else None
        if not state:
            raise RecoveryActionError("No stopped or interrupted request to continue.", status=409)
        return await self.execute(
            "continue",
            {"chat_id": session_key.split(":", 1)[1], "recovery_id": state["recovery_id"]},
        )

    async def execute(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Settle one accepted control before releasing its admission and session lock."""
        chat_id = payload.get("chat_id")
        if not isinstance(chat_id, str) or not chat_id:
            raise RecoveryActionError("missing chat_id")
        with self.bus.admission.activity():
            lock = self._action_locks.setdefault(webui_session_key(chat_id), asyncio.Lock())
            async with lock:
                return await shield_and_drain(
                    self._apply_action(action, chat_id, payload.get("recovery_id"))
                )

    async def _apply_action(self, action: str, chat_id: str, recovery_id: object) -> dict[str, Any]:
        """Validate committed recovery state and perform its single queue handoff."""
        if not isinstance(recovery_id, str) or not recovery_id:
            raise RecoveryActionError("missing recovery_id")
        session = await self.sessions.state.read(webui_session_key(chat_id))
        if session is None:
            raise RecoveryActionError("conversation no longer exists", status=409)
        state = recovery_state_from_metadata(session.metadata)
        if not state or state["recovery_id"] != recovery_id:
            raise RecoveryActionError("recovery state is stale", status=409)
        if action not in {"continue", "dismiss"}:
            raise RecoveryActionError("unknown recovery action")
        if state["status"] not in {"awaiting_user", "failed"}:
            raise RecoveryActionError("recovery is not waiting for confirmation", status=409)

        if action == "dismiss":
            restore_runtime_checkpoint(session)
            restore_pending_interruption(session)
            next_state = set_recovery_state(
                session,
                status="recovered",
                recovery_id=recovery_id,
                attempts=cast(int, state.get("attempts", 0)),
                reason="dismissed",
            )
            await self.sessions.state.restore_interruption(session)
            await self.delivery.publish(chat_id, next_state, generation=session.generation)
            return next_state
        if state.get("can_continue") is False:
            raise RecoveryActionError("recovery context is unavailable", status=409)
        goal = parse_goal_state(goal_state_raw(session.metadata))
        if goal and goal.get("status") in {"stopped", "paused", "blocked", "waiting"}:
            session.metadata["goal_state"] = resume_goal_state(goal)
        next_state = set_recovery_state(
            session,
            status="resuming",
            recovery_id=recovery_id,
            attempts=cast(int, state.get("attempts", 0)) + 1,
            reason="user_confirmed",
            resume_message_count=len(session.messages),
        )
        await self.sessions.state.restore_interruption(session)
        await self.delivery.publish(chat_id, next_state, generation=session.generation)
        await self.delivery.queue_continuation(session, chat_id, next_state)
        return next_state
