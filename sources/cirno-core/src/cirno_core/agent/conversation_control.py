"""Router supervisory operations over the existing conversation runtime."""

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
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.model_selection import SESSION_MODEL_PRESET_METADATA_KEY, model_preset_from_metadata
from cirno_core.security.workspace_access import WORKSPACE_SCOPE_METADATA_KEY, validate_workspace_scope_payload
from cirno_core.session.session_identity import is_webui_session_key
from cirno_core.session.session_handles import SessionHandleResolver
from cirno_core.session.sqlite_store import SessionConflictError
from cirno_core.session.recovery.state import recovery_state_from_metadata
from cirno_core.session.transcript import append_session_message_input
from cirno_core.session.turn_continuation import INTERNAL_CONTINUATION_META, SKIP_USER_PERSIST_META
from cirno_core.utils.cancellation import shield_and_drain

if TYPE_CHECKING:
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.session.model import Session
    from cirno_core.session.session_handles import SessionHandle


class ConversationControl:
    """Only the Router may control another persistent Web conversation.

    The intake lock prevents a new worker from starting between cancellation and
    a Goal change. The execution lock also serializes direct SDK turns. Neither
    lock is held while waiting for a future model response.
    """

    def __init__(self, loop: AgentLoop):
        self.loop = loop

    async def execute(self, to: str, action: str, *, goal: bool = False, **values: Any) -> str:
        request = current_request_context()
        if request is None or request.session_key != ROUTER_SESSION_KEY or not request.persist_session:
            return ToolResult.error("Only the Router conversation may supervise other conversations.")
        source = await self.loop.sessions.state.read_header(ROUTER_SESSION_KEY)
        if source is None or request.session_generation is not None and source.generation != request.session_generation:
            return ToolResult.error("The Router request belongs to a cleared or replaced conversation.")
        if not goal and action == "list":
            if to is not None or values:
                return ToolResult.error("list does not accept a target or configuration fields.")
            return await self._list_execution()
        if not isinstance(to, str) or not to.strip():
            return ToolResult.error("A target conversation id or current @name is required.")
        target = await SessionHandleResolver(self.loop.sessions).aresolve(to)
        if target is None:
            return ToolResult.error("Target conversation was not found. Use conversations__search to find its stable id.")
        if target.session_key == ROUTER_SESSION_KEY or not is_webui_session_key(target.session_key):
            return ToolResult.error("Supervisory controls require another Web conversation; the Router cannot stop itself.")
        if action not in ({"get", "create", "set", "update", "stop", "pause", "resume", "delete", "wait"} if goal else {"get", "configure", "stop", "continue"}):
            return ToolResult.error("Unsupported supervisory action.")
        if not goal and action != "configure" and values:
            return ToolResult.error("Configuration fields require action=configure.")
        return await shield_and_drain(self._apply(target, action, goal, values, request))

    async def _apply(self, target, action, goal, values, request):
        key = target.session_key
        async with self.loop.session_intake_lock(key):
            session = await self.loop.sessions.state.read_header(key)
            if session is None or not session.policy.persist:
                return ToolResult.error("The target conversation no longer exists or is temporary.")
            if not goal and action == "get":
                return json.dumps({"to": "@" + target.name, **self._configuration(session),
                                   **self._execution(session)}, ensure_ascii=False)
            if not goal and action == "configure":
                return await self._configure(session, target, values)
            if goal and action == "get":
                with request_context(dataclasses.replace(request, session_key=key, session_generation=session.generation)):
                    return await GetGoalTool(self.loop.sessions).execute()
            if not goal and action == "continue" and self.loop.dispatch.is_running(key):
                return json.dumps({"to": "@" + target.name, "status": "already_running",
                                   **self._execution(session)})
            recovery = recovery_state_from_metadata(session.metadata)
            if not goal and action == "continue" and recovery and recovery["status"] in {"awaiting_user", "failed"}:
                coordinator = self.loop.recovery_admission
                if coordinator is None:
                    return ToolResult.error("Recovery is unavailable; inspect the saved interruption before continuing.")
                # Share the owner's Continue path, including checkpoint safety,
                # pending input restoration and duplicate/stale action checks.
                await coordinator.resume_session(key)
                await self._audit(session, target, "continue", {}, uuid4().hex)
                return json.dumps({"to": "@" + target.name, "action": "continue",
                                   "continuation_queued": True, "recovery_id": recovery["recovery_id"]})
            prior = parse_goal_state(goal_state_raw(session.metadata))
            if goal:
                error = self._validate_goal(action, prior, values)
                if error:
                    return ToolResult.error(error)
            # Stop only the target's workers, child agents and owned shell sessions.
            cancelled = await self.loop.cancel_session_work(key, stop_goal=not goal and action == "stop")
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
                source = await SessionHandleResolver(self.loop.sessions).ahandle_for_session(ROUTER_SESSION_KEY)
                await self.loop.dispatch.enqueue_locked(InboundMessage(
                    channel="websocket", sender_id="system:supervisor", chat_id=key.split(":", 1)[1],
                    content="Continue the authorized task from the saved context and current Goal. Check completed work before acting; do not repeat completed operations.",
                    session_key_override=key, require_existing_session=True,
                    session_generation=session.generation,
                    metadata={"webui": True, "_wants_stream": True,
                              "_supervisor_control": {"source_session_key": ROUTER_SESSION_KEY, "source_name": "@" + source.name, "id": event_id, "action": action},
                              INTERNAL_CONTINUATION_META: True, SKIP_USER_PERSIST_META: True},
                ))
            return json.dumps({"to": "@" + target.name, "action": ("goal." if goal else "") + action,
                               "result": str(result), "cancelled_tasks": cancelled,
                               "continuation_queued": should_continue}, ensure_ascii=False)

    def _execution(self, session: Session) -> dict[str, Any]:
        key = session.key
        recovery = recovery_state_from_metadata(session.metadata)
        state = ("running" if key in self.loop._executing_sessions else
                 "queued" if self.loop.dispatch.is_running(key) else
                 "interrupted" if recovery and recovery["status"] in {"awaiting_user", "failed"} else "idle")
        return {"execution_status": state, "recovery": recovery,
                "goal": parse_goal_state(goal_state_raw(session.metadata))}

    async def _list_execution(self) -> str:
        resolver = SessionHandleResolver(self.loop.sessions)
        rows = []
        for item in await self.loop.sessions.state.list_metadata():
            key = item["key"]
            if not is_webui_session_key(key):
                continue
            recovery = recovery_state_from_metadata(item["metadata"])
            if key not in self.loop._executing_sessions and not self.loop.dispatch.is_running(key) and not (
                recovery and recovery["status"] in {"awaiting_user", "failed"}
            ):
                continue
            session = await self.loop.sessions.state.read_header(key)
            if session is None or not session.policy.persist:
                continue
            status = self._execution(session)
            if status["execution_status"] == "idle":
                continue
            handle = await resolver.ahandle_for_session(key)
            rows.append({"id": handle.id if handle else None, "session_key": key, "handle": "@" + handle.name if handle else None,
                         "title": session.metadata.get("title"), **status})
        return json.dumps({"worker_concurrency_limit": self.loop.max_concurrent_requests,
                           "subagent_concurrency_limit": self.loop.subagents.max_concurrent_subagents,
                           "unlimited": self.loop.max_concurrent_requests == 0,
                           "router_has_reserved_slot": True, "conversations": rows}, ensure_ascii=False)

    def _configuration(self, session: Session) -> dict[str, Any]:
        scope = self.loop.workspace_scopes.for_turn(channel="websocket", message_metadata={}, session_metadata=session.metadata)
        return {
            "workspace_scope": scope.payload(), "ptc_mode": session.metadata.get("ptc_mode") is True,
            "model_preset": model_preset_from_metadata(session.metadata) or "default",
            "available_model_presets": sorted({"default", *self.loop.runtime_resolver.model_presets}),
        }

    async def _configure(self, session: Session, target: SessionHandle, values: dict[str, Any]) -> str:
        key = session.key
        lock = self.loop._get_session_lock(key)
        if self.loop.dispatch.is_running(key) or lock.locked() or any(not task.done() for task in self.loop._active_tasks.get(key, ())):
            return ToolResult.error("The target conversation is running. Use stop, configure, then continue when ready.")
        if not values or values.keys() - {"workspace", "ptc_mode", "model_preset"}:
            return ToolResult.error("configure requires workspace, ptc_mode or model_preset; other settings are not supported.")
        async with lock:
            fresh = await self.loop.sessions.state.read_header(key)
            if fresh is None or fresh.generation != session.generation:
                raise SessionConflictError("The target was deleted or replaced during configuration.")
            updates, remove, applied = {}, [], {}
            try:
                if "workspace" in values:
                    path = values["workspace"]
                    if not isinstance(path, str) or not path.strip():
                        raise ValueError("workspace must be an existing absolute directory")
                    current = self.loop.workspace_scopes.for_turn(channel="websocket", message_metadata={}, session_metadata=fresh.metadata)
                    changed = validate_workspace_scope_payload(
                        {"project_path": path, "access_mode": current.access_mode},
                        default_workspace=self.loop.workspace,
                        default_restrict_to_workspace=current.restrict_to_workspace, source_channel="websocket",
                    )
                    updates[WORKSPACE_SCOPE_METADATA_KEY] = changed.payload()
                    applied["workspace"] = str(changed.project_path)
                if "ptc_mode" in values:
                    if not isinstance(values["ptc_mode"], bool):
                        raise ValueError("ptc_mode must be a boolean")
                    updates["ptc_mode"] = applied["ptc_mode"] = values["ptc_mode"]
                if "model_preset" in values:
                    name = values["model_preset"]
                    if not isinstance(name, str) or not name.strip():
                        raise ValueError("model_preset must be a configured model ID or default")
                    if name.strip().casefold() == "default":
                        remove.append(SESSION_MODEL_PRESET_METADATA_KEY)
                        applied["model_preset"] = "default"
                    else:
                        runtime = self.loop.runtime_resolver.resolve_preset(name)
                        updates[SESSION_MODEL_PRESET_METADATA_KEY] = applied["model_preset"] = runtime.model_preset
            except (KeyError, ValueError) as error:
                return ToolResult.error(str(error))
            await self.loop.sessions.state.update_metadata(key, updates, remove=remove, expected_generation=fresh.generation)
            fresh.metadata.update(updates)
            for name in remove:
                fresh.metadata.pop(name, None)
            await self._audit(fresh, target, "configure", applied, uuid4().hex,
                              workspace_scope=updates.get(WORKSPACE_SCOPE_METADATA_KEY))
            return json.dumps({"to": "@" + target.name, "action": "configure", "continuation_queued": False,
                               **self._configuration(fresh)}, ensure_ascii=False)

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
            def report_to_router(metadata):
                if metadata.get("goal_state"):
                    metadata["goal_state"]["report_to"] = ROUTER_SESSION_KEY
            await self.loop.sessions.state.mutate_metadata(session.key, report_to_router, expected_generation=session.generation)
        return result

    async def _audit(self, session: Session, target: SessionHandle, action: str, values: dict, event_id: str, *, workspace_scope=None) -> None:
        source = await SessionHandleResolver(self.loop.sessions).ahandle_for_session(ROUTER_SESSION_KEY)
        assert source is not None
        text = "Router supervisory operation: " + json.dumps({"action": action, **values}, ensure_ascii=False)
        created = int(time.time() * 1000)
        provenance = {"message_id": event_id, "session": source.public_payload()}
        origin = {"kind": "supervision", "label": "@" + source.name, "id": event_id, "action": action, "values": values}
        await append_session_message_input(session.key, sessions=self.loop.sessions, content=text, created_at_ms=created,
                                           session_message=provenance, expected_generation=session.generation, input_origin=origin)
        def record(metadata):
            events = list(metadata.get("supervision_events", []))
            events.append({"id": event_id, "action": action, "values": values, "source": "@" + source.name, "created_at_ms": created})
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
            channel="websocket", chat_id=session.key.split(":", 1)[1], event=SessionUpdatedEvent(scope="metadata", workspace_scope=workspace_scope), metadata={}))
