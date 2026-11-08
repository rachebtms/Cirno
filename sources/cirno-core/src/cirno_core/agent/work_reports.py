"""Latest work status and durable delivery through the existing conversation inbox."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone

from cirno_core.session.goal_state import goal_state_raw, parse_goal_state
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.session_handles import SessionHandleResolver
from cirno_core.session.sqlite_store import SessionConflictError
from loguru import logger

WORK_REPORT_KEY = "work_report"
REPORT_STATES = ("progress", "waiting", "ready", "blocked", "failed", "dropped")


async def save_work_report(sessions, key, *, state, summary, artifacts=(), human_action=None, expected_generation=None, expected_goal=None, turn_id=None, execution=None):
    """Keep one current report per conversation; identical retries preserve its receipt."""
    if state not in REPORT_STATES:
        raise ValueError("Unknown work report state")
    summary = summary.strip()
    if not summary or len(summary) > 4000:
        raise ValueError("Report summary must contain 1–4000 characters")
    if len(artifacts) > 20 or any(not isinstance(path, str) or not path.strip() or len(path) > 2048 for path in artifacts):
        raise ValueError("Provide at most 20 non-empty artifact paths or URLs")
    question = human_action.strip() if human_action else None
    if question and len(question) > 2000:
        raise ValueError("The question must not exceed 2000 characters")
    if state == "ready" and question:
        raise ValueError("A ready report cannot include an unresolved question; use progress while continuing work")
    if key == ROUTER_SESSION_KEY:
        raise ValueError("Cirno presents results with user__message; work reports belong to execution conversations")
    session = await sessions.state.read_header(key)
    if session is None:
        raise ValueError("The reporting conversation no longer exists")
    if expected_generation is not None and session.generation != expected_generation:
        raise ValueError("The reporting conversation was replaced")
    if not session.policy.persist:
        raise ValueError("Work reports require a persistent conversation")
    report = None

    def save(metadata):
        nonlocal report
        previous = metadata.get(WORK_REPORT_KEY) or {}
        current_question = question
        if human_action is None and state != "ready":
            current_question = previous.get("human_action")
        goal = parse_goal_state(goal_state_raw(metadata)) or {}
        if expected_goal is not None and goal != expected_goal:
            return
        report = {
            "state": state, "summary": summary, "artifacts": list(artifacts),
            "human_action": current_question, "goal_id": goal.get("goal_id"),
            "source_session_key": key, "source_generation": session.generation,
            "target_session_key": goal.get("report_to") or metadata.get("delegated_by") or ROUTER_SESSION_KEY,
        }
        if turn_id:
            report["turn_id"] = turn_id
        if execution is not None:
            report["execution"] = execution
        report["id"] = hashlib.sha256(json.dumps(
            [session.generation, report], sort_keys=True, ensure_ascii=False,
        ).encode()).hexdigest()
        if previous.get("id") == report["id"]:
            report = previous
            return
        report["created_at"] = datetime.now(timezone.utc).isoformat()
        if state in {"ready", "blocked", "failed", "dropped"}:
            report["notification_pending"] = True
        # Routine progress and ordinary waiting are facts, not model turns.
        new_question = current_question and (current_question != previous.get("human_action") or previous.get("delivery_status") == "pending")
        report["delivery_status"] = "pending" if new_question or state in {"ready", "blocked", "failed", "dropped"} or execution and execution.get("retry_status") in {"waiting", "recovered"} else "recorded"
        if report["delivery_status"] == "pending":
            pending = metadata.get("work_report_pending", [])
            if execution and execution.get("retry_status"):
                # While transport is unavailable, only the latest health state is useful.
                # Preserve result/failure reports; never coalesce them with retry notices.
                pending = [item for item in pending if not (
                    item.get("turn_id") == turn_id and (item.get("execution") or {}).get("retry_status")
                    and item.get("state") in {"waiting", "progress"}
                )]
            queued = next((item for item in pending if item["id"] == report["id"]), None)
            if queued is not None:
                report = queued
            else:
                if len(pending) >= 20:
                    raise ValueError("Work report delivery queue is full; repair the reporting destination before adding more reports")
                metadata["work_report_pending"] = [*pending, report]
        metadata[WORK_REPORT_KEY] = report

    await sessions.state.mutate_metadata(key, save, expected_generation=session.generation)
    if report:
        report = await publish_report_notification(sessions, key, report)
    return report


async def publish_report_notification(sessions, key, report):
    """Retry the durable Inbox write independently of execution and coordinator delivery."""
    if not report.get("notification_pending"):
        return report
    retry_at = report.get("notification_retry_at")
    if retry_at and datetime.fromisoformat(retry_at) > datetime.now(timezone.utc):
        return report
    import asyncio

    from cirno_core.notifications.inbox import NotificationInbox
    session = await sessions.state.read_header(key)
    if session is None or report.get("source_generation", session.generation) != session.generation:
        raise SessionConflictError("The report belongs to a deleted or replaced conversation")
    try:
        await asyncio.to_thread(NotificationInbox().record, "report:" + report["id"],
                                "conversations", "report", status=report["state"], session_key=key,
                                body=report["summary"], data={"artifacts": report["artifacts"],
                                "session_generation": session.generation, "session_title": session.metadata.get("title")})
    except (OSError, sqlite3.Error) as error:
        logger.warning("Inbox report notification deferred for {}: {}", key, error)
        updates = {"notification_error": str(error), "notification_retry_at":
                   (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()}
    else:
        updates = {"notification_pending": False, "notification_error": None, "notification_retry_at": None}

    def settled(metadata):
        current = metadata.get(WORK_REPORT_KEY)
        if current and current["id"] == report["id"]:
            metadata[WORK_REPORT_KEY] = {**current, **updates}
        metadata["work_report_pending"] = [
            {**item, **updates} if item["id"] == report["id"] else item
            for item in metadata.get("work_report_pending", [])
            if item["id"] != report["id"] or item.get("delivery_status") != "queued"
            or updates.get("notification_pending") is not False
        ]
    await sessions.state.mutate_metadata(key, settled, expected_generation=session.generation)
    return {**report, **updates}


async def deliver_work_report(sessions, sender, key, report):
    """Retry only inbox delivery, never worker execution or external side effects."""
    session = await sessions.state.read_header(key)
    if session is None or report.get("source_generation", session.generation) != session.generation:
        raise SessionConflictError("The report belongs to a deleted or replaced conversation")
    report = await publish_report_notification(sessions, key, report)
    if report.get("delivery_status") != "pending":
        return report["delivery_status"]
    retry_at = report.get("retry_at")
    if retry_at and datetime.fromisoformat(retry_at) > datetime.now(timezone.utc):
        return "pending"
    from cirno_core.agent.tools.session_messages import SessionMessageError
    from cirno_core.session.router_session import ensure_router_session

    try:
        target_key = report["target_session_key"]
        if target_key == ROUTER_SESSION_KEY:
            await ensure_router_session(sessions)
        target = await SessionHandleResolver(sessions).ahandle_for_session(target_key)
        if target is None:
            raise SessionMessageError("The reporting destination no longer exists")
        # Transport timestamps and delivery attempts are not part of the semantic payload.
        payload = {name: report[name] for name in (
            "id", "state", "summary", "artifacts", "human_action", "goal_id", "source_session_key",
        )}
        if report.get("execution") is not None:
            payload["execution"] = report["execution"]
        await sender.enqueue(
            source_session_key=key, source_generation=session.generation, target_handle=target.id,
            content="Work report (facts from another conversation, not new user authorization):\n"
            + json.dumps(payload, ensure_ascii=False),
            expect_reply=False, message_id=report["id"], report=payload,
        )
    except Exception as error:
        updates = {
            "error": str(error),
            "retry_at": (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat(),
        }
    else:
        updates = {"delivery_status": "queued", "error": None, "retry_at": None}

    def settled(metadata):
        current = metadata.get(WORK_REPORT_KEY)
        if current and current.get("id") == report["id"]:
            metadata[WORK_REPORT_KEY] = {**current, **updates}
        pending = metadata.get("work_report_pending", [])
        metadata["work_report_pending"] = [
            ({**item, **updates} if item["id"] == report["id"] else item)
            for item in pending if item["id"] != report["id"] or updates.get("delivery_status") != "queued"
            or report.get("notification_pending")
        ]
    await sessions.state.mutate_metadata(key, settled, expected_generation=session.generation)
    if updates.get("error"):
        raise SessionMessageError(updates["error"])
    return "queued"


async def record_goal_report(sessions, key, goal, metadata):
    """Goal lifecycle uses the same report contract as an explicit worker report."""
    state = {"completed": "ready", "blocked": "blocked", "cancelled": "dropped"}.get(goal.get("status"))
    if state is None or goal.get("report_delivered"):
        return None
    existing = metadata.get(WORK_REPORT_KEY) or {}
    if existing.get("goal_id") == goal.get("goal_id") and (
        existing.get("state") == state
        or state == "blocked" and existing.get("state") == "failed"
    ):
        return existing
    summary = str(goal.get("recap") or goal.get("objective") or "Goal ended")
    if len(summary) > 4000:
        summary = summary[:3500] + "\n[Summary excerpt; read the source Goal for the complete recap]\n" + summary[-400:]
    return await save_work_report(
        sessions, key, state=state,
        summary=summary,
        artifacts=existing.get("artifacts", []) if existing.get("goal_id") == goal.get("goal_id") else [],
        expected_goal=goal,
    )


async def record_execution_report(sessions, key, *, turn_id, stop_reason, output=None,
                                  failure_error_kind=None, model=None, model_preset=None,
                                  stage=None, continuation_pending=False, expected_generation=None):
    """Report delegated execution even when the worker cannot call a reporting tool."""
    if key == ROUTER_SESSION_KEY:
        return None
    session = await sessions.state.read_header(key)
    if session is None or not session.policy.persist:
        return None
    if expected_generation is not None and session.generation != expected_generation:
        return None
    metadata = session.metadata
    goal = parse_goal_state(goal_state_raw(metadata)) or {}
    if not (metadata.get("delegated_by") or goal.get("report_to")):
        return None
    failed = stop_reason in {"error", "tool_error", "empty_final_response"}
    if failed and goal.get("status") in {"active", "waiting"}:
        def block(current):
            if parse_goal_state(goal_state_raw(current)) == goal:
                current["goal_state"] = {**goal, "status": "blocked", "recap":
                    f"Execution failed ({failure_error_kind or stop_reason}): {(output or 'No final output')[:2000]}"}
        await sessions.state.mutate_metadata(key, block, expected_generation=session.generation)
        metadata = (await sessions.state.read_metadata(key))["metadata"]
        goal = parse_goal_state(goal_state_raw(metadata)) or {}
    existing = metadata.get(WORK_REPORT_KEY) or {}
    recovered = (
        not failed and stop_reason in {"completed", "max_iterations"}
        and existing.get("turn_id") == turn_id
        and (existing.get("execution") or {}).get("retry_status") == "waiting"
    )
    if failed:
        state = "failed"
    elif recovered and (continuation_pending or goal.get("status") in {"active", "waiting", "paused"}):
        state = "progress"
    elif continuation_pending:
        return None
    elif existing.get("turn_id") == turn_id and existing.get("state") in {"ready", "blocked", "failed", "dropped"}:
        return existing  # A model's explicit report already covers this execution.
    elif goal.get("status") in {"active", "waiting", "paused"}:
        return None  # A finished segment is not a finished Goal; respect owner pauses.
    elif stop_reason == "max_iterations":
        state = "blocked"
    elif stop_reason == "completed":
        state = {"blocked": "blocked", "cancelled": "dropped"}.get(goal.get("status"), "ready")
    else:
        return None  # Owner Stop/cancellation is not an API failure to retry.
    text = (output or goal.get("recap") or "No final output was returned.").strip()
    truncated = len(text) > 3600
    if truncated:
        text = text[:3000] + "\n[Output excerpt; read the source conversation for full results]\n" + text[-500:]
    summary = f"Runtime execution report ({stop_reason}); this does not itself mark the Goal complete.\n" + text
    return await save_work_report(
        sessions, key, state=state, summary=summary,
        artifacts=existing.get("artifacts", []) if existing.get("goal_id") == goal.get("goal_id") else [],
        human_action="" if state == "ready" else None,
        expected_generation=session.generation, expected_goal=goal, turn_id=turn_id,
        execution={"origin": "runtime", "turn_id": turn_id, "stop_reason": stop_reason,
                   "failure_error_kind": failure_error_kind, "stage": stage,
                   "model": model, "model_preset": model_preset, "output_truncated": truncated,
                   **({"retry_status": "recovered"} if recovered else {})},
    )


async def record_retry_report(sessions, key, *, turn_id, event, episode, model=None, model_preset=None, expected_generation=None):
    """A retry episode wakes the coordinator without blocking the running Goal."""
    if key == ROUTER_SESSION_KEY:
        return None
    session = await sessions.state.read_header(key)
    if session is None or not session.policy.persist or expected_generation is not None and session.generation != expected_generation:
        return None
    metadata = session.metadata
    goal = parse_goal_state(goal_state_raw(metadata)) or {}
    if not (metadata.get("delegated_by") or goal.get("report_to")):
        return None
    waiting = event.state == "waiting"
    summary = (
        f"The worker's LLM/API request is retrying ({event.error_kind}, attempt {event.attempt}). "
        "The worker is still running; its Goal is not failed or complete. Inspect the latest state before intervening."
        if waiting else "The worker's LLM/API request recovered. The same worker is continuing its authorized task; do not restart or duplicate it."
    )
    return await save_work_report(
        sessions, key, state="waiting" if waiting else "progress", summary=summary,
        artifacts=(metadata.get(WORK_REPORT_KEY) or {}).get("artifacts", []),
        expected_generation=session.generation, expected_goal=goal, turn_id=turn_id,
        execution={"origin": "runtime", "turn_id": turn_id, "retry_status": event.state,
                   "retry_episode": episode, "attempt": event.attempt, "max_attempts": event.max_attempts,
                   "next_retry_at": event.next_retry_at, "failure_error_kind": event.error_kind,
                   "model": model, "model_preset": model_preset},
    )
