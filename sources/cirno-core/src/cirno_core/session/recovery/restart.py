"""Conversation recovery restart ownership."""

from __future__ import annotations

import dataclasses
from typing import Any, cast
from uuid import uuid4

from loguru import logger

from cirno_core.session.manager import SessionManager
from cirno_core.session.model import Session

from .checkpoints import (
    discard_runtime_checkpoint,
    restore_runtime_checkpoint,
    runtime_checkpoint_is_well_formed,
)
from .contracts import (
    KNOWN_CHECKPOINT_PHASES,
    PENDING_USER_TURN_KEY,
    RUNTIME_CHECKPOINT_KEY,
    UNCERTAIN_TOOL_PHASES,
)
from .delivery import RecoveryDelivery
from .interruption import restore_pending_interruption
from .state import (
    has_saved_continuation_context,
    has_unfinished_transcript,
    needs_recovery,
    recovery_state_from_metadata,
    resume_message_count,
    set_recovery_state,
    webui_route,
)


@dataclasses.dataclass(slots=True)
class RecoveryRestart:
    sessions: SessionManager
    delivery: RecoveryDelivery

    async def scan(self) -> None:
        """Recover every interrupted WebUI session once at gateway startup."""

        for key in await self._recovery_candidates():
            metadata_payload = await self.sessions.state.read_metadata(key)
            raw_metadata = metadata_payload.get("metadata") if metadata_payload else None
            metadata = cast(dict[str, Any], raw_metadata) if isinstance(raw_metadata, dict) else {}
            route = webui_route(key)
            if route is None:
                continue
            unfinished = await has_unfinished_transcript(self.sessions, key)
            if not needs_recovery(metadata) and not unfinished:
                continue
            session = await self.sessions.state.get(key)
            try:
                await self.recover(session, route[1])
                await self.delivery.requeue_pending_followups(session)
            except Exception as error:
                logger.opt(exception=session.policy.log_content).error(
                    "Recovery {} failed: {}",
                    session.key,
                    type(error).__name__,
                )
                state = recovery_state_from_metadata(session.metadata)
                failed = set_recovery_state(
                    session,
                    status="failed",
                    recovery_id=cast(str, state["recovery_id"]) if state else uuid4().hex,
                    attempts=cast(int, state.get("attempts", 0)) if state else 0,
                    reason="recovery_failed",
                    can_continue=False,
                )
                await self.sessions.state.restore_interruption(session)
                await self.delivery.publish(route[1], failed, generation=session.generation)

    async def _recovery_candidates(self) -> list[str]:
        """Return conversation keys owned by the current session store."""
        return [item["key"] for item in await self.sessions.state.list_sessions()]

    async def recover(self, session: Session, chat_id: str) -> None:
        checkpoint_value = cast(object, session.metadata.get(RUNTIME_CHECKPOINT_KEY))
        checkpoint = (
            cast(dict[str, Any], checkpoint_value) if isinstance(checkpoint_value, dict) else None
        )
        pending = session.metadata.get(PENDING_USER_TURN_KEY) is True
        state = recovery_state_from_metadata(session.metadata)
        if not pending and checkpoint is None:
            if state and state["status"] == "resuming":
                resume_count = resume_message_count(session)
                if resume_count is not None and len(session.messages) > resume_count:
                    next_state = set_recovery_state(
                        session,
                        status="recovered",
                        recovery_id=cast(str, state["recovery_id"]),
                        attempts=cast(int, state.get("attempts", 0)),
                        reason="committed",
                    )
                else:
                    next_state = set_recovery_state(
                        session,
                        status="awaiting_user",
                        recovery_id=cast(str, state["recovery_id"]),
                        attempts=cast(int, state.get("attempts", 1)),
                        reason="loop_guard",
                    )
                await self.sessions.state.restore_interruption(session)
                await self.delivery.publish(chat_id, next_state, generation=session.generation)
            elif await has_unfinished_transcript(self.sessions, session.key):
                # A normal last-client shutdown can materialize the checkpoint
                # before the process exits.  In that path there is no pending
                # marker left to classify, but the append-only transcript still
                # contains an activity row without a turn_end.  Treat it as an
                # interrupted turn instead of letting the UI resurrect it as a
                # forever-running spinner.
                can_continue = has_saved_continuation_context(session)
                waiting = set_recovery_state(
                    session,
                    status="awaiting_user",
                    recovery_id=uuid4().hex,
                    attempts=0,
                    reason=(
                        "interrupted_with_saved_context"
                        if can_continue
                        else "interrupted_without_checkpoint"
                    ),
                    can_continue=can_continue,
                )
                await self.sessions.state.restore_interruption(session)
                await self.delivery.publish(chat_id, waiting, generation=session.generation)
            return
        if state and state["status"] in {"awaiting_user", "failed"}:
            await self.delivery.publish(chat_id, state, generation=session.generation)
            return
        if state and state["status"] == "resuming":
            restore_runtime_checkpoint(session)
            restore_pending_interruption(session)
            waiting = set_recovery_state(
                session,
                status="awaiting_user",
                recovery_id=cast(str, state["recovery_id"]),
                attempts=cast(int, state.get("attempts", 1)),
                reason="loop_guard",
            )
            await self.sessions.state.restore_interruption(session)
            await self.delivery.publish(chat_id, waiting, generation=session.generation)
            return

        recovery_id = uuid4().hex
        phase = checkpoint.get("phase") if checkpoint is not None else None
        pending_calls = checkpoint.get("pending_tool_calls") if checkpoint is not None else None
        if checkpoint is not None and phase not in KNOWN_CHECKPOINT_PHASES:
            discard_runtime_checkpoint(session)
            restore_pending_interruption(session)
            waiting = set_recovery_state(
                session,
                status="awaiting_user",
                recovery_id=recovery_id,
                attempts=0,
                reason="checkpoint_unknown",
                can_continue=False,
            )
            await self.sessions.state.restore_interruption(session)
            await self.delivery.publish(chat_id, waiting, generation=session.generation)
            return
        if checkpoint is not None and not runtime_checkpoint_is_well_formed(checkpoint):
            discard_runtime_checkpoint(session)
            restore_pending_interruption(session)
            waiting = set_recovery_state(
                session,
                status="awaiting_user",
                recovery_id=recovery_id,
                attempts=0,
                reason="checkpoint_invalid",
                can_continue=False,
            )
            await self.sessions.state.restore_interruption(session)
            await self.delivery.publish(chat_id, waiting, generation=session.generation)
            return
        if phase == "final_response":
            restore_runtime_checkpoint(session)
            recovered = set_recovery_state(
                session,
                status="recovered",
                recovery_id=recovery_id,
                attempts=0,
                reason="answer_restored",
            )
            await self.sessions.state.restore_interruption(session)
            await self.delivery.publish(chat_id, recovered, generation=session.generation)
            return
        if phase in UNCERTAIN_TOOL_PHASES or pending_calls:
            restore_runtime_checkpoint(session)
            waiting = set_recovery_state(
                session,
                status="awaiting_user",
                recovery_id=recovery_id,
                attempts=0,
                reason="tool_state_unknown",
            )
            await self.sessions.state.restore_interruption(session)
            await self.delivery.publish(chat_id, waiting, generation=session.generation)
            return
        # A gateway restart is a lifecycle boundary.  Never enqueue model work
        # implicitly: even a synchronized checkpoint may sit next to an
        # external side effect that the user should review first.  The final
        # answer path above only restores persisted output; it never executes.
        restore_runtime_checkpoint(session)
        waiting = set_recovery_state(
            session,
            status="awaiting_user",
            recovery_id=recovery_id,
            attempts=0,
            reason="restart_requires_confirmation",
        )
        await self.sessions.state.restore_interruption(session)
        await self.delivery.publish(chat_id, waiting, generation=session.generation)
