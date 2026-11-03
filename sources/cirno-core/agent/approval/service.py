"""Review exactly one boundary-crossing call, then restore restricted access."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from contextlib import asynccontextmanager

from cirno_core.agent.tools.naming import NAMES
from cirno_core.config.loader import load_config
from cirno_core.bus.events import INBOUND_META_TURN_ID, InboundMessage
from cirno_core.bus.runtime_events import GoalStateChanged, RuntimeEventContext
from cirno_core.session.recovery import PENDING_FOLLOWUP_ID_KEY
from cirno_core.notifications.inbox import NotificationInbox
from cirno_core.runtime.context import public_history_message
from cirno_core.agent.approval.reviewer import operation_evidence, review_operation
from cirno_core.security.approval.store import ApprovalStore
from cirno_core.security.workspace_access import (
    bind_workspace_scope, build_workspace_scope, reset_workspace_scope,
)
from cirno_core.session.goal_state import GOAL_STATE_KEY, parse_goal_state
from cirno_core.session.recovery import REQUEST_ORIGIN_METADATA_KEY
from cirno_core.session.turn_continuation import INTERNAL_CONTINUATION_META, SKIP_USER_PERSIST_META


class OperationApproval:
    def __init__(self, sessions, bus, *, store=None, inbox=None, model_resolver=None):
        self.sessions = sessions
        self.bus = bus
        self.store = store or ApprovalStore()
        self.inbox = inbox or NotificationInbox()
        self.model_resolver = model_resolver
        self._locks = {}  # Only active review tasks retain locks.

    async def authorize(self, tool, params, request, boundary):
        if not request.persist_session or not request.session_key or not request.session_generation:
            raise PermissionError("Independent review requires a saved conversation; use Default or explicitly choose Full Access for a temporary conversation.")
        operation = await asyncio.to_thread(operation_evidence, tool.name, params, request.workspace)
        raw = json.dumps([request.session_key, request.session_generation, request.turn_id, operation], sort_keys=True, ensure_ascii=False)
        fingerprint = hashlib.sha256(raw.encode()).hexdigest()
        # Identical concurrent calls must not consume the same one-use grant.
        lock, users = self._locks.setdefault(fingerprint, (asyncio.Lock(), 0))
        self._locks[fingerprint] = (lock, users + 1)
        try:
            async with lock:
                await self._authorize(tool, params, request, boundary, operation, fingerprint)
        finally:
            lock, users = self._locks[fingerprint]
            if users == 1:
                del self._locks[fingerprint]
            else:
                self._locks[fingerprint] = (lock, users - 1)

    async def _authorize(self, tool, params, request, boundary, operation, fingerprint):
        session = await self.sessions.state.get(request.session_key)
        if session.generation != request.session_generation:
            raise PermissionError("This operation belongs to a replaced conversation.")
        prior = await asyncio.to_thread(self.store.latest, fingerprint)
        if prior and prior["status"] in {"denied", "pending"}:
            raise PermissionError(f"Operation approval {prior['status']} ({prior['id']}): {prior['reason']}. Do not retry or bypass this operation; wait for the owner.")
        if prior and prior["status"] == "approved":
            if time.time() - prior["decided_at"] > 3600:
                raise PermissionError("This operation approval expired. Ask the owner to submit a new request.")
            if await asyncio.to_thread(self.store.consume, prior["id"]):
                return
        # Find the original human request, not an internal continuation or agent report.
        human = next((public_history_message(item).get("content", "") for item in reversed(session.messages)
                      if item.get("role") == "user" and item.get(INBOUND_META_TURN_ID) == request.turn_id
                      and not item.get("input_origin") and not item.get("session_message")), "")
        human = human if isinstance(human, str) and len(human) <= 6000 else ""
        settings = (await asyncio.to_thread(load_config)).agents.defaults.approval
        runtime = request.runtime
        if not settings.enabled:
            decision, reason = "human", "AI review is disabled. The owner must approve this operation."
        else:
            try:
                if settings.model_override and settings.model_override != "default":
                    if self.model_resolver is None:
                        raise ValueError("The configured review model is unavailable")
                    runtime = self.model_resolver.resolve_preset(settings.model_override)
            except Exception as error:
                decision, reason = "human", f"The review model could not be loaded: {error}"
            else:
                decision, reason = await review_operation(runtime, human_request=human, operation=operation,
                                                         timeout_seconds=settings.timeout_seconds)
        fresh = await self.sessions.state.read_header(request.session_key)
        if fresh is None or fresh.generation != request.session_generation:
            raise PermissionError("The conversation changed during review; the operation was not executed.")
        current = await asyncio.to_thread(operation_evidence, tool.name, params, request.workspace)
        if current != operation:
            raise PermissionError("Referenced scripts or paths changed during review; request a fresh review.")
        status = {"approve": "used", "deny": "denied", "human": "pending"}[decision]
        item = await asyncio.to_thread(self.store.record, fingerprint, request, operation, status, reason)
        await asyncio.to_thread(self.inbox.record, "approval:" + item["id"], "operations", "approval",
                                status={"used": "approved", "denied": "denied", "pending": "pending"}[status],
                                session_key=request.session_key,
                                body=reason,
                                data={"approval_id": item["id"], "operation": NAMES.get(tool.name, tool.name),
                                      "arguments": params, "boundary": boundary, "reviewer": "independent"})
        if status == "used":
            return
        if status == "pending":
            def wait(metadata):
                goal = parse_goal_state(metadata.get(GOAL_STATE_KEY))
                if goal and goal["status"] == "active":
                    goal = {**goal, "status": "waiting", "approval_id": item["id"]}
                    goal.pop("wake_at", None)
                    metadata[GOAL_STATE_KEY] = goal
            _, metadata = await self.sessions.state.mutate_metadata(request.session_key, wait, expected_generation=request.session_generation)
            await self._publish_goal(request.session_key, metadata)
        raise PermissionError(f"Operation approval {status} ({item['id']}): {reason}. No effects were applied. Do not retry or bypass it; the owner can decide in Inbox.")

    async def decide(self, identifier, approved):
        if not isinstance(identifier, str) or not isinstance(approved, bool):
            raise ValueError("Provide an approval ID and a boolean approved decision")
        item = await asyncio.to_thread(self.store.get, identifier)
        session = await self.sessions.state.read_header(item["session_key"])
        item = await asyncio.to_thread(self.store.decide, identifier, approved=approved,
                                       generation=session.generation if session else None)
        await self._deliver_decision(item, publish=True)
        return {"id": identifier, "status": item["status"]}

    async def recover(self):
        """Stage accepted owner decisions before the server scans saved follow-ups."""
        while items := await asyncio.to_thread(self.store.pending_wakes):
            for item in items:
                session = await self.sessions.state.read_header(item["session_key"])
                if session is None or session.generation != item["generation"]:
                    await asyncio.to_thread(self.store.wake_queued, item["id"], stale=True)
                    await asyncio.to_thread(self.inbox.unavailable, "approval:" + item["id"])
                else:
                    await self._deliver_decision(item, publish=False)

    async def _deliver_decision(self, item, *, publish):
        identifier, approved = item["id"], item["status"] == "approved"
        await asyncio.to_thread(self.inbox.record, "approval:" + identifier, "operations", "approval",
                                status="approved" if approved else "denied", session_key=item["session_key"],
                                body=item["reason"], data={"approval_id": identifier, "operation": NAMES.get(json.loads(item["operation"])["tool"], json.loads(item["operation"])["tool"])})
        def wake(metadata):
            goal = parse_goal_state(metadata.get(GOAL_STATE_KEY))
            if goal and goal.get("approval_id") == identifier:
                goal = {**goal, "status": "active" if approved else "blocked"}
                goal.pop("approval_id", None)
                metadata[GOAL_STATE_KEY] = goal
        _, metadata = await self.sessions.state.mutate_metadata(item["session_key"], wake, expected_generation=item["generation"])
        await self._publish_goal(item["session_key"], metadata)
        # This is a decision on an exact saved operation, not fresh task authorization.
        message = InboundMessage(
            channel="websocket", sender_id="system:approval", chat_id=item["session_key"].split(":", 1)[1],
            content=f"The owner {'approved one use of' if approved else 'denied'} operation {identifier}. "
                    "Continue from saved context. An approval only covers its exact arguments and inspected scripts; do not repeat completed work.",
            session_key_override=item["session_key"], require_existing_session=True, session_generation=item["generation"],
            metadata={"webui": True, "_wants_stream": True, "_approval_decision": identifier,
                      INTERNAL_CONTINUATION_META: True, SKIP_USER_PERSIST_META: True,
                      REQUEST_ORIGIN_METADATA_KEY: {"turn_id": item["turn_id"], "message_id": None}},
        )
        message.metadata[PENDING_FOLLOWUP_ID_KEY] = "approval:" + identifier
        await self.sessions.state.queue_followup(item["session_key"], message)
        await asyncio.to_thread(self.store.wake_queued, identifier)
        if publish:
            await self.bus.publish_inbound(message)

    async def _publish_goal(self, key, metadata):
        await self.bus.publish(GoalStateChanged(
            context=RuntimeEventContext(channel="websocket", chat_id=key.split(":", 1)[1], session_key=key),
            session_metadata=metadata,
        ))


@asynccontextmanager
async def operation_access(tool, params, request):
    token = None
    if tool is not None and request and request.workspace_scope and request.workspace_scope.access_mode == "review":
        reason = tool.approval_reason(params)
        if reason:
            if request.operation_approval is None:
                raise PermissionError("Independent operation review is unavailable in this runtime.")
            await request.operation_approval.authorize(tool, params, request, reason)
            # No loopback/SSRF override and no change to the conversation's access mode.
            token = bind_workspace_scope(build_workspace_scope(request.workspace, "full", source_channel="approval"))
            from cirno_core.agent.tools.shell import ExecTool
            if isinstance(tool, ExecTool):
                # Approval of a command must not grant an interactive shell capability.
                params = dict(params)
                params["yield_time_ms"] = None
    try:
        yield params
    finally:
        if token is not None:
            reset_workspace_scope(token)
