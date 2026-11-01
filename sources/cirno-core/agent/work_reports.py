"""Latest work status and durable delivery through the existing conversation inbox."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from cirno.session.goal_state import goal_state_raw, parse_goal_state
from cirno.session.keys import CIRNO_SESSION_KEY
from cirno.session.session_handles import SessionHandleResolver

WORK_REPORT_KEY = "work_report"
REPORT_STATES = ("progress", "waiting", "ready", "blocked", "failed", "dropped")


async def save_work_report(sessions, key, *, state, summary, artifacts=(), human_action=None, expected_generation=None, expected_goal=None):
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
    if key == CIRNO_SESSION_KEY:
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
            "source_session_key": key,
            "target_session_key": goal.get("report_to") or metadata.get("delegated_by") or CIRNO_SESSION_KEY,
        }
        report["id"] = hashlib.sha256(json.dumps(
            [session.generation, report], sort_keys=True, ensure_ascii=False,
        ).encode()).hexdigest()
        if previous.get("id") == report["id"]:
            report = previous
            return
        report["created_at"] = datetime.now(timezone.utc).isoformat()
        # Routine progress and ordinary waiting are facts, not model turns.
        new_question = current_question and (current_question != previous.get("human_action") or previous.get("delivery_status") == "pending")
        report["delivery_status"] = "pending" if new_question or state in {"ready", "blocked", "failed", "dropped"} else "recorded"
        if report["delivery_status"] == "pending":
            pending = metadata.get("work_report_pending", [])
            queued = next((item for item in pending if item["id"] == report["id"]), None)
            if queued is not None:
                report = queued
            else:
                if len(pending) >= 20:
                    raise ValueError("Work report delivery queue is full; repair the reporting destination before adding more reports")
                metadata["work_report_pending"] = [*pending, report]
        metadata[WORK_REPORT_KEY] = report

    await sessions.state.mutate_metadata(key, save, expected_generation=session.generation)
    if report and state in {"ready", "blocked", "failed", "dropped"}:
        from cirno.notifications.inbox import NotificationInbox
        import asyncio
        await asyncio.to_thread(NotificationInbox().record, "report:" + report["id"],
                                "conversations", "report", status=state, session_key=key,
                                body=summary, data={"artifacts": list(artifacts), "session_generation": session.generation,
                                                    "session_title": session.metadata.get("title")})
    return report


async def deliver_work_report(sessions, sender, key, report):
    """Retry only inbox delivery, never worker execution or external side effects."""
    if report.get("delivery_status") != "pending":
        return report["delivery_status"]
    retry_at = report.get("retry_at")
    if retry_at and datetime.fromisoformat(retry_at) > datetime.now(timezone.utc):
        return "pending"
    from cirno.agent.tools.session_messages import SessionMessageError
    from cirno.webui.instance_api import ensure_global_session

    try:
        target_key = report["target_session_key"]
        if target_key == CIRNO_SESSION_KEY:
            await ensure_global_session(sessions)
        target = await SessionHandleResolver(sessions).ahandle_for_session(target_key)
        if target is None:
            raise SessionMessageError("The reporting destination no longer exists")
        # Transport timestamps and delivery attempts are not part of the semantic payload.
        payload = {name: report[name] for name in (
            "id", "state", "summary", "artifacts", "human_action", "goal_id", "source_session_key",
        )}
        await sender.enqueue(
            source_session_key=key, target_handle="@" + target.name,
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
        ]
    await sessions.state.mutate_metadata(key, settled)
    if updates.get("error"):
        raise SessionMessageError(updates["error"])
    return "queued"


async def record_goal_report(sessions, key, goal, metadata):
    """Goal lifecycle uses the same report contract as an explicit worker report."""
    state = {"completed": "ready", "blocked": "blocked", "cancelled": "dropped"}.get(goal.get("status"))
    if state is None or goal.get("report_delivered"):
        return None
    existing = metadata.get(WORK_REPORT_KEY) or {}
    if existing.get("goal_id") == goal.get("goal_id") and existing.get("state") == state:
        return existing
    return await save_work_report(
        sessions, key, state=state,
        summary=str(goal.get("recap") or goal.get("objective") or "Goal ended"),
        artifacts=existing.get("artifacts", []) if existing.get("goal_id") == goal.get("goal_id") else [],
        expected_goal=goal,
    )
