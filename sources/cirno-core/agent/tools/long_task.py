"""Sustained-goal tools with explicit user opt-in at the execution boundary."""

# pyright: reportIncompatibleMethodOverride=false

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import TYPE_CHECKING, Any

from cirno.agent.goals.permission import (
    goal_mutation_allowed,
    revoke_goal_mutation_permission,
)
from cirno.agent.tools.base import Tool, ToolResult, tool_parameters
from cirno.agent.tools.context import RequestContext, ToolContext, current_request_context
from cirno.agent.tools.schema import IntegerSchema, StringSchema, tool_parameters_schema
from cirno.bus.queue import MessageBus
from cirno.bus.runtime_events import GoalStateChanged, RuntimeEventContext
from cirno.runtime.context import RuntimeContextBlock, wrap_runtime_context_lines
from cirno.session.goal_state import (
    GOAL_STATE_KEY,
    MAX_GOAL_OBJECTIVE_CHARS,
    discard_legacy_goal_state_key,
    explicit_goal_requested,
    goal_state_raw,
    goal_state_runtime_lines,
    parse_goal_state,
    sustained_goal_active,
)
from cirno.session.turn_continuation import reset_goal_continuation_rounds
from cirno.utils.cancellation import shield_and_drain
from cirno.utils.prompt_templates import render_template

if TYPE_CHECKING:
    from cirno.session.manager import Session, SessionManager


_GOAL_ACTIONS = ("complete", "cancel", "block", "replace", "pause", "resume", "stop", "wait", "continue", "delete")
_CREATE_UNAVAILABLE_ERROR = (
    "Error: creating a goal requires a current user request."
)
_REPLACE_UNAVAILABLE_ERROR = (
    "Error: changing the objective requires a current user request."
)


def _iso_now() -> str:
    return datetime.now().isoformat()


class _GoalToolsMixin:
    """Shared routing context and session lookup."""

    def __init__(
        self,
        sessions: SessionManager,
        bus: MessageBus | None = None,
        continuation_limit: int = 0,
    ) -> None:
        self._sessions = sessions
        self._bus = bus
        self._continuation_limit = continuation_limit

    async def _session(self) -> Session | None:
        request_ctx = current_request_context()
        if request_ctx is None:
            return None
        key = request_ctx.session_key
        if not key:
            return None
        return await self._sessions.state.get_header(key)

    def _goal_mutation_allowed(self) -> bool:
        return current_request_context() is not None and goal_mutation_allowed()

    async def _save_goal_state(
        self,
        sess: Session,
        blob: dict[str, Any] | None,
        *,
        reset_continuation: bool = False,
        revoke_permission: bool = False,
    ) -> None:
        saved = False

        async def save_and_publish() -> None:
            nonlocal saved
            def change(metadata: dict[str, Any]) -> None:
                if blob is None:
                    metadata.pop(GOAL_STATE_KEY, None)
                else:
                    metadata[GOAL_STATE_KEY] = deepcopy(blob)
                discard_legacy_goal_state_key(metadata)
                if reset_continuation:
                    reset_goal_continuation_rounds(metadata)
            _, sess.metadata = await self._sessions.state.mutate_metadata(
                sess.key, change, expected_generation=sess.generation,
            )
            saved = True
            await self._publish_goal_state_changed(sess.metadata)

        try:
            await shield_and_drain(save_and_publish())
        finally:
            # This ContextVar belongs to the caller task, not the settlement task.
            if revoke_permission and saved:
                revoke_goal_mutation_permission()

    async def _publish_goal_state_changed(self, metadata: dict[str, Any]) -> None:
        bus = self._bus
        rc = current_request_context()
        if bus is None or rc is None:
            return
        cid = (rc.chat_id or "").strip()
        if not cid:
            return
        await bus.publish(
            GoalStateChanged(
                context=RuntimeEventContext(
                    channel=rc.channel,
                    chat_id=cid,
                    session_key=rc.session_key or f"{rc.channel}:{cid}",
                    metadata=dict(rc.metadata or {}),
                ),
                session_metadata=dict(metadata),
            )
        )


@tool_parameters(
    tool_parameters_schema(
        objective=StringSchema(
            "Self-contained goal with explicit completion criteria, bounded and safe to repeat. "
            "May incorporate prior discussion.",
            min_length=1,
            max_length=MAX_GOAL_OBJECTIVE_CHARS,
        ),
        ui_summary=StringSchema(
            "One-line display label for session lists and logs; objective defines the goal.",
            max_length=120,
            nullable=True,
        ),
        continuation_limit=IntegerSchema(description="Maximum automatic continuation rounds; 0 is unlimited. Omit to use the instance default.", minimum=0, nullable=True),
        required=["objective"],
    )
)
class CreateGoalTool(Tool, _GoalToolsMixin):
    """Create one explicit sustained objective for the current session."""

    def __init__(
        self,
        sessions: SessionManager,
        bus: MessageBus | None = None,
        continuation_limit: int = 0,
    ) -> None:
        _GoalToolsMixin.__init__(self, sessions, bus, continuation_limit)

    @classmethod
    def create(cls, ctx: ToolContext) -> Tool:
        sess = ctx.sessions
        if sess is None:
            raise RuntimeError("CreateGoalTool requires an initialized session manager")
        return cls(
            sessions=sess,
            bus=ctx.bus,
            continuation_limit=ctx.goal_continuation_limit,
        )

    @classmethod
    def enabled(cls, ctx: ToolContext) -> bool:
        return ctx.sessions is not None

    @property
    def name(self) -> str:
        return "create_goal"

    @property
    def description(self) -> str:
        return (
            "Create one sustained goal for the current session when the user requests ongoing work. "
            "Record the requested objective; do not create unrelated goals or retry after success. Uses the configured continuation limit by default; do not ask the user to specify one."
        )

    def runtime_context_provider(self):
        return self._provide_runtime_context

    async def _provide_runtime_context(
        self,
        request: RequestContext,
    ) -> RuntimeContextBlock | None:
        if not request.session_key or not request.persist_session:
            return None
        payload = await self._sessions.state.read_metadata(request.session_key)
        if payload is None:
            return None
        metadata = payload["metadata"]
        goal_start_requested = explicit_goal_requested(request.metadata)
        goal_active = sustained_goal_active(metadata)
        if not goal_start_requested and not goal_active:
            return None

        guidance = render_template(
            "agent/goal_runtime.md",
            strip=True,
            goal_start_requested=goal_start_requested,
            goal_active=goal_active,
        )
        state = wrap_runtime_context_lines(goal_state_runtime_lines(metadata))
        content = "\n\n".join(part for part in (guidance, state) if part)
        return RuntimeContextBlock(source="goal", content=content)

    async def execute(
        self,
        objective: str,
        ui_summary: str | None = None,
        continuation_limit: int | None = None,
        **kwargs: Any,
    ) -> str:
        sess = await self._session()
        if sess is None:
            return ToolResult.error(
                "Error: create_goal requires an active chat session (missing routing context)."
            )
        if not self._goal_mutation_allowed():
            return ToolResult.error(_CREATE_UNAVAILABLE_ERROR)
        prior = parse_goal_state(goal_state_raw(sess.metadata))
        if isinstance(prior, dict) and prior.get("status") in {"active", "paused", "blocked", "waiting", "stopped"}:
            return ToolResult.error(
                "Error: a sustained goal is already active. Use update_goal with "
                "action='replace' only if the user explicitly changes the objective."
            )

        objective_text = objective.strip()
        if not objective_text:
            return ToolResult.error("Error: objective must not be empty.")
        if len(objective_text) > MAX_GOAL_OBJECTIVE_CHARS:
            return ToolResult.error(
                f"Error: objective must not exceed {MAX_GOAL_OBJECTIVE_CHARS} characters."
            )
        summary = (ui_summary or "").strip()[:120]
        blob = {
            "status": "active",
            "goal_id": uuid4().hex,
            "continuation_limit": self._continuation_limit if continuation_limit is None else continuation_limit,
            "objective": objective_text,
            "ui_summary": summary,
            "started_at": _iso_now(),
        }
        await self._save_goal_state(sess, blob, reset_continuation=True)
        extra = f"\nSummary line: {summary}" if summary else ""
        return (
            "Goal recorded. Keep working toward the objective using ordinary tools. "
            "When fully done and verified, call goals__update with action='complete'."
            f"{extra}"
        )


@tool_parameters(
    tool_parameters_schema(
        action=StringSchema(
            "How to update the active goal.",
            enum=_GOAL_ACTIONS,
        ),
        recap=StringSchema(
            "Brief honest recap for the user. Required in practice for complete, cancel, and block.",
            max_length=8000,
            nullable=True,
        ),
        objective=StringSchema(
            "Replacement objective. Required only when action is 'replace'; make it durable, "
            "self-contained, bounded, and explicit about done-ness.",
            max_length=MAX_GOAL_OBJECTIVE_CHARS,
            nullable=True,
        ),
        ui_summary=StringSchema(
            "Optional one-line display label for a replacement goal.",
            max_length=120,
            nullable=True,
        ),
        wake_after_seconds=IntegerSchema(description="Delay before resuming a waiting Goal. Required for action=wait.", minimum=1, nullable=True),
        continuation_limit=IntegerSchema(description="Override the continuation limit; 0 is unlimited. Counts survive restart and resume.", minimum=0, nullable=True),
        required=["action"],
    )
)
class UpdateGoalTool(Tool, _GoalToolsMixin):
    """Complete, cancel, block, or replace the active sustained goal."""

    def __init__(
        self,
        sessions: SessionManager,
        bus: MessageBus | None = None,
        continuation_limit: int = 0,
    ) -> None:
        _GoalToolsMixin.__init__(self, sessions, bus, continuation_limit)

    @classmethod
    def create(cls, ctx: ToolContext) -> Tool:
        sess = ctx.sessions
        if sess is None:
            raise RuntimeError("UpdateGoalTool requires an initialized session manager")
        return cls(
            sessions=sess,
            bus=ctx.bus,
            continuation_limit=ctx.goal_continuation_limit,
        )

    @classmethod
    def enabled(cls, ctx: ToolContext) -> bool:
        return ctx.sessions is not None

    @property
    def name(self) -> str:
        return "update_goal"

    @property
    def description(self) -> str:
        return (
            "Update the active sustained goal. Use action='complete' only after the objective "
            "is actually achieved and verified. Use action='cancel' when the user cancels, "
            "action='block' when progress is genuinely blocked, and action='replace' only when "
            "the requested objective changes. Use pause, resume, or delete when the user requests "
            "those changes. Pausing prevents further automatic continuation; it does not interrupt "
            "the current tool call. Use wait with wake_after_seconds to persist a timed wait; use stop to stop the Goal without deleting it."
        )

    async def execute(
        self,
        action: str,
        recap: str | None = None,
        objective: str | None = None,
        ui_summary: str | None = None,
        wake_after_seconds: int | None = None,
        continuation_limit: int | None = None,
        **kwargs: Any,
    ) -> str:
        sess = await self._session()
        if sess is None:
            return ToolResult.error("Error: update_goal requires an active chat session.")
        prior = parse_goal_state(goal_state_raw(sess.metadata))
        if not isinstance(prior, dict):
            return "No goal to update."

        normalized = (action or "").strip().lower()
        if normalized not in _GOAL_ACTIONS:
            return ToolResult.error(
                "Error: action must be complete, cancel, block, replace, pause, resume, stop, wait, continue, delete."
            )

        if continuation_limit is not None and continuation_limit != prior.get("continuation_limit") and not self._goal_mutation_allowed():
            return ToolResult.error("Changing the continuation limit requires a current user request.")
        if continuation_limit is not None:
            prior = {**prior, "continuation_limit": continuation_limit}
        if normalized == "wait":
            if wake_after_seconds is None or wake_after_seconds < 1:
                return ToolResult.error("wait requires a positive wake_after_seconds")
            if prior.get("status") != "active":
                return ToolResult.error("Only an active goal can wait.")
            blob = {**prior, "status": "waiting", "wake_at": (datetime.now(timezone.utc) + timedelta(seconds=wake_after_seconds)).isoformat(), "recap": (recap or "").strip()}
            await self._save_goal_state(sess, blob)
            return "Goal waiting; the gateway will wake it at " + blob["wake_at"]
        if normalized == "continue":
            if prior.get("status") != "active":
                return ToolResult.error("Only an active goal can continue.")
            await self._save_goal_state(sess, {**prior, "recap": (recap or "").strip()})
            return "Progress saved; continue working."
        if normalized in {"pause", "resume", "stop", "delete"}:
            if not self._goal_mutation_allowed():
                return ToolResult.error("Error: this goal change requires a current user request.")
            status = prior.get("status")
            if normalized == "delete":
                await self._save_goal_state(sess, None, reset_continuation=True)
                return "Goal deleted."
            if normalized in {"pause", "stop"}:
                if status not in {"active", "waiting"}:
                    return ToolResult.error("Only an active goal can be paused.")
                blob = {**prior, "status": "stopped" if normalized == "stop" else "paused", "paused_at": _iso_now()}
            else:
                if status not in {"paused", "blocked", "stopped", "waiting"}:
                    return ToolResult.error("Only a paused or blocked goal can be resumed.")
                blob = {**prior, "status": "active", "resumed_at": _iso_now()}
                blob.pop("ended_at", None)
            blob.pop("wake_at", None)
            await self._save_goal_state(sess, blob)
            return "Goal resumed." if normalized == "resume" else "Goal stopped." if normalized == "stop" else "Goal paused."

        if normalized == "replace":
            if not self._goal_mutation_allowed():
                return ToolResult.error(_REPLACE_UNAVAILABLE_ERROR)
            objective_text = (objective or "").strip()
            if not objective_text:
                return ToolResult.error(
                    "Error: update_goal action='replace' requires a replacement objective."
                )
            if len(objective_text) > MAX_GOAL_OBJECTIVE_CHARS:
                return ToolResult.error(
                    f"Error: objective must not exceed {MAX_GOAL_OBJECTIVE_CHARS} characters."
                )
            summary = (ui_summary or "").strip()[:120]
            blob = {
                "status": "active",
                "goal_id": uuid4().hex,
                "continuation_limit": prior.get("continuation_limit", self._continuation_limit),
                "objective": objective_text,
                "ui_summary": summary,
                "started_at": _iso_now(),
                "replaced_at": _iso_now(),
                "previous_objective": str(prior.get("objective") or ""),
                **({"report_to": prior["report_to"]} if prior.get("report_to") else {}),
                "recap": (recap or "").strip(),
            }
            await self._save_goal_state(sess, blob, reset_continuation=True)
            extra = f"\nSummary line: {summary}" if summary else ""
            return "Goal replaced. Continue toward the new objective using ordinary tools." + extra

        if prior.get("status") not in {"active", "waiting"}:
            return ToolResult.error("This Goal is not running; resume it before completing it.")
        ended = _iso_now()
        status = {
            "complete": "completed",
            "cancel": "cancelled",
            "block": "blocked",
        }[normalized]
        blob = {
            **prior,
            "status": status,
            "ended_at": ended,
            "recap": (recap or "").strip(),
        }
        if normalized == "complete":
            blob["completed_at"] = ended
        await self._save_goal_state(sess, blob, revoke_permission=True)

        tail = (recap or "").strip()
        label = {
            "complete": "complete",
            "cancel": "cancelled",
            "block": "blocked",
        }[normalized]
        if tail:
            return f"Goal marked {label} ({ended}). Recap:\n{tail}"
        return f"Goal marked {label} ({ended})."


@tool_parameters(tool_parameters_schema())
class GetGoalTool(CreateGoalTool):
    """Read the current conversation's persisted goal."""

    @property
    def name(self) -> str:
        return "get_goal"

    @property
    def description(self) -> str:
        return "Read the current session's goal, including its objective and paused or active status."

    def runtime_context_provider(self):
        return None

    async def execute(self, **kwargs: Any) -> str:
        session = await self._session()
        if session is None:
            return ToolResult.error("Error: get_goal requires an active chat session.")
        goal = parse_goal_state(goal_state_raw(session.metadata))
        return json.dumps({**goal, "continuation_rounds": session.metadata.get("_sustained_goal_continuation_rounds", 0)} if goal else None, ensure_ascii=False)
