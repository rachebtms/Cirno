"""Cirno's supervisory operations over the existing conversation runtime."""

from __future__ import annotations

import dataclasses
import json
import time
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from cirno_core.agent.goals.permission import goal_mutation_permission
from cirno_core.agent.tools.base import ToolResult
from cirno_core.agent.tools.context import current_request_context, request_context
from cirno_core.agent.tools.long_task import CreateGoalTool, GetGoalTool, UpdateGoalTool
from cirno_core.bus.events import InboundMessage
from cirno_core.bus.outbound_events import (
    SessionUpdatedEvent,
    UserInputEvent,
    outbound_message_for_event,
)
from cirno_core.bus.runtime_events import GoalStateChanged, RuntimeEventContext
from cirno_core.session.goal_state import goal_state_raw, parse_goal_state
from cirno_core.session.keys import CIRNO_SESSION_KEY
from cirno_core.session.session_identity import is_webui_session_key
from cirno_core.session.session_handles import SessionHandleResolver
from cirno_core.session.sqlite_store import SessionConflictError
from cirno_core.session.transcript import append_session_message_input
from cirno_core.session.turn_continuation import INTERNAL_CONTINUATION_META, SKIP_USER_PERSIST_META
from cirno_core.utils.cancellation import shield_and_drain

if TYPE_CHECKING:
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.session.manager import Session
    from cirno_core.session.session_handles import SessionHandle


class ConversationControl:
    """Only Cirno may control another persistent Web conversation.

    The intake lock prevents a new worker from starting between cancellation and
    a Goal change. The execution lock also serializes direct SDK turns. Neither
    lock is held while waiting for a future model response.
    """

    def __init__(self, loop: AgentLoop):
        self.loop = loop

    async def execute(self, to: str, action: str, *, goal: bool = False, **values: Any) -> str:
        request = current_request_context()
        if request is None or request.session_key != CIRNO_SESSION_KEY or not request.persist_session:
            return ToolResult.error("Only the personal Cirno conversation may supervise other conversations.")
        source = await self.loop.sessions.state.read_header(CIRNO_SESSION_KEY)
        if source is None or request.session_generation is not None and source.generation != request.session_generation:
            return ToolResult.error("The Cirno request belongs to a cleared or replaced conversation.")
        target = await SessionHandleResolver(self.loop.sessions).aresolve(to)
        if target is None:
            return ToolResult.error("Target conversation was not found. Use conversations__search to find its @handle.")
        if target.session_key == CIRNO_SESSION_KEY or not is_webui_session_key(target.session_key):
            return ToolResult.error("Supervisory controls require another Web conversation; Cirno cannot stop itself.")
        if action not in ({"get", "create", "set", "update", "stop", "pause", "resume", "delete", "wait"} if goal else {"stop", "continue"}):
            return ToolResult.error("Unsupported supervisory action.")
        return await shield_and_drain(self._apply(target, action, goal, values, request))

    async def _apply(self, target, action, goal, values, request):
        key = target.session_key
        async with self.loop.session_intake_lock(key):
            session = await self.loop.sessions.state.read_header(key)
            if session is None or not session.policy.persist:
                return ToolResult.error("The target conversation no longer exists or is temporary.")
            if goal and action == "get":
                with request_context(dataclasses.replace(request, session_key=key, session_generation=session.generation)):
                    return await GetGoalTool(self.loop.sessions).execute()
            if not goal and action == "continue" and key in self.loop._pending_queues:
                return json.dumps({"to": "@" + target.name, "status": "already_running"})
            prior = parse_goal_state(goal_state_raw(session.metadata))
            if goal:
                error = self._validate_goal(action, prior, values)
                if error:
                    return ToolResult.error(error)
            # Stop only the target's workers, child agents and owned shell sessions.
            cancelled = await self.loop._cancel_active_tasks(key, stop_goal=not goal and action == "stop")
            async with self.loop._get_session_lock(key):
                fresh = await self.loop.sessions.state.read_header(key)
                if fresh is None or fresh.generation != session.generation:
                    raise SessionConflictError("The target was deleted or replaced during the control operation.")
                session = fresh
                if goal:
                    result = await self._goal_action(session, action, values, request)
                    if isinstance(result, ToolResult) and result.is_error:
                        return result
                else:
                    result = "Conversation stopped." if action == "stop" else "Continuation queued from saved context."
                    if action == "continue":
                        prior = parse_goal_state(goal_state_raw(session.metadata))
                        if prior and prior.get("status") in {"stopped", "paused", "waiting", "blocked"}:
                            with request_context(dataclasses.replace(request, channel="websocket", chat_id=key.split(":", 1)[1], session_key=key, session_generation=session.generation)), goal_mutation_permission(True):
                                await UpdateGoalTool(self.loop.sessions, self.loop.bus).execute(action="resume")
                event_id = uuid4().hex
                await self._audit(session, target, ("goal." if goal else "") + action, values, event_id)
            should_continue = (not goal and action == "continue" or goal and (action in {"create", "set", "resume"} or action == "update" and (prior or {}).get("status") == "active"))
            if should_continue:
                # Use normal admission/checkpoint restoration, without replaying the
                # original user request or any previous tool calls.
                await self.loop._enqueue_session_message_unlocked(InboundMessage(
                    channel="websocket", sender_id="system:supervisor", chat_id=key.split(":", 1)[1],
                    content="Continue the authorized task from the saved context and current Goal. Check completed work before acting; do not repeat completed operations.",
                    session_key_override=key, require_existing_session=True,
                    metadata={"webui": True, "_wants_stream": True,
                              "_supervisor_control": {"source_session_key": CIRNO_SESSION_KEY, "id": event_id, "action": action},
                              INTERNAL_CONTINUATION_META: True, SKIP_USER_PERSIST_META: True},
                ))
            return json.dumps({"to": "@" + target.name, "action": ("goal." if goal else "") + action,
                               "result": str(result), "cancelled_tasks": cancelled,
                               "continuation_queued": should_continue}, ensure_ascii=False)

    @staticmethod
    def _validate_goal(action: str, prior: dict | None, values: dict) -> str | None:
        if values.get("objective") and len(values["objective"]) > 4000:
            return "Goal objective must not exceed 4000 characters."
        if action in {"create", "set"} and not str(values.get("objective") or "").strip():
            return "A Goal objective with completion criteria is required."
        if action == "create" and prior and prior.get("status") in {"active", "waiting", "stopped", "paused", "blocked"}:
            return "A Goal already exists; use set to replace it explicitly."
        if action not in {"create", "set"} and not prior:
            return "The target has no Goal."
        if action not in {"create", "set"} and "objective" in values:
            return "Use set to change the objective; update preserves it."
        status = (prior or {}).get("status")
        if action in {"stop", "pause", "wait"} and status not in {"active", "waiting"}:
            return "Only an active or waiting Goal can be stopped, paused or put to sleep."
        if action == "resume" and status not in {"paused", "stopped", "waiting", "blocked"}:
            return "Only a paused, stopped, waiting or blocked Goal can be resumed."
        if action == "wait" and status != "active":
            return "Only an active Goal can wait."
        if action == "wait" and (values.get("wake_after_seconds") or 0) < 1:
            return "wait requires a positive wake_after_seconds."
        return None

    async def _goal_action(self, session: Session, action: str, values: dict, request) -> str:
        goal = parse_goal_state(goal_state_raw(session.metadata))
        target_request = dataclasses.replace(request, channel="websocket", chat_id=session.key.split(":", 1)[1],
                                             session_key=session.key, session_generation=session.generation)
        with request_context(target_request), goal_mutation_permission(True):
            if action == "create" or action == "set" and not goal:
                result = await CreateGoalTool(self.loop.sessions, self.loop.bus, self.loop.goal_continuation_limit).execute(
                    objective=values["objective"], ui_summary=values.get("ui_summary"), continuation_limit=values.get("continuation_limit"))
            else:
                result = await UpdateGoalTool(self.loop.sessions, self.loop.bus, self.loop.goal_continuation_limit).execute(
                    action="replace" if action == "set" else action, **values)
        if not isinstance(result, ToolResult) or not result.is_error:
            # A delegated Goal always reports back to its personal coordinator.
            def report_to_cirno(metadata):
                if metadata.get("goal_state"):
                    metadata["goal_state"]["report_to"] = CIRNO_SESSION_KEY
            await self.loop.sessions.state.mutate_metadata(session.key, report_to_cirno, expected_generation=session.generation)
        return result

    async def _audit(self, session: Session, target: SessionHandle, action: str, values: dict, event_id: str) -> None:
        source = await SessionHandleResolver(self.loop.sessions).ahandle_for_session(CIRNO_SESSION_KEY)
        assert source is not None
        text = "Cirno supervisory operation: " + json.dumps({"action": action, **values}, ensure_ascii=False)
        created = int(time.time() * 1000)
        provenance = {"message_id": event_id, "session": source.public_payload()}
        origin = {"kind": "supervision", "label": "@cirno", "id": event_id, "action": action, "values": values}
        await append_session_message_input(session.key, sessions=self.loop.sessions, content=text, created_at_ms=created,
                                           session_message=provenance, expected_generation=session.generation, input_origin=origin)
        def record(metadata):
            events = list(metadata.get("supervision_events", []))
            events.append({"id": event_id, "action": action, "values": values, "source": "@cirno", "created_at_ms": created})
            metadata["supervision_events"] = events[-8:]
        await self.loop.sessions.state.mutate_metadata(session.key, record, expected_generation=session.generation)
        await self.loop.bus.publish_outbound(outbound_message_for_event(
            channel="websocket", chat_id=session.key.split(":", 1)[1],
            event=UserInputEvent(content=text, created_at_ms=created, provenance={"session_message": provenance, "input_origin": origin}), metadata={}))
        current = await self.loop.sessions.state.read_metadata(session.key)
        await self.loop.bus.publish(GoalStateChanged(
            context=RuntimeEventContext(channel="websocket", chat_id=session.key.split(":", 1)[1], session_key=session.key, metadata={}, session_generation=session.generation),
            session_metadata=current["metadata"],
        ))
        await self.loop.bus.publish_outbound(outbound_message_for_event(
            channel="websocket", chat_id=session.key.split(":", 1)[1], event=SessionUpdatedEvent(scope="metadata"), metadata={}))
