"""Wake durable Goals through the normal per-session execution queue."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from loguru import logger

from cirno_core.bus.events import InboundMessage
from cirno_core.notifications.service_errors import report_service_error
from cirno_core.runtime.admission import RuntimeMaintenanceError
from cirno_core.session.goal_state import goal_state_raw, parse_goal_state, pause_goal_at_limit
from cirno_core.session.recovery.state import goal_recovery_pending
from cirno_core.session.sqlite_store import SessionConflictError
from cirno_core.session.turn_continuation import _goal_continuation_prompt
from cirno_core.utils.cancellation import shield_and_drain


async def wake_due_goals(loop) -> None:
    now = datetime.now(timezone.utc)
    rows = await loop.sessions.state.list_metadata()
    for row in rows:
        try:
            await _wake_goal(loop, row["key"], now)
        except SessionConflictError:
            # Deleting/replacing one conversation must not delay other Goals.
            logger.debug("Goal scheduler skipped a changed conversation: {}", row["key"])
        except RuntimeMaintenanceError:
            return  # Closing/maintenance is not a failed user task.
        except Exception as error:
            logger.exception("Goal processing failed for {}; other conversations will continue", row["key"])
            await asyncio.to_thread(report_service_error, None, "Goal scheduler", error, session_key=row["key"])


async def _wake_goal(loop, key, now):
    if key in loop._discarding_sessions:
        return
    session = await loop.sessions.state.read_header(key)
    if session is None:
        return
    metadata = session.metadata
    goal = parse_goal_state(goal_state_raw(metadata)) or {}
    from cirno_core.agent.tools.session_messages import SessionMessageError
    from cirno_core.agent.work_reports import deliver_work_report, record_goal_report

    report = metadata.get("work_report")
    report_error = None
    # The executing turn owns its detailed failure/result report. Its Goal may
    # already be blocked while persistence is still settling that same turn.
    if goal.get("report_to") and key not in loop._pending_queues:
        try:
            report = await record_goal_report(loop.sessions, key, goal, metadata) or report
        except ValueError as error:
            # Drain already saved reports even when a new report cannot be queued.
            report_error = error
    sender = getattr(loop, "tools", None)
    sender = sender.get("send_session_message") if sender is not None else None
    if report and sender is not None:
        try:
            pending_reports = list(metadata.get("work_report_pending", []))
            if not any(item["id"] == report["id"] for item in pending_reports):
                pending_reports.append(report)
            status = None
            for pending_report in pending_reports:
                delivered = await deliver_work_report(loop.sessions, sender, key, pending_report)
                if delivered == "pending":
                    break  # Keep delivery order while an earlier report is backing off.
                if pending_report["id"] == report["id"]:
                    status = delivered
        except SessionMessageError as error:
            logger.warning("Work report deferred for {}: {}", key, error)
        else:
            if (
                status == "queued" and report_error is None
                and report.get("goal_id") == goal.get("goal_id")
                and goal.get("status") == "completed" and not goal.get("report_delivered")
            ):
                def reported(current):
                    if parse_goal_state(goal_state_raw(current)) == goal:
                        current["goal_state"] = {**goal, "report_delivered": True}
                await loop.sessions.state.mutate_metadata(key, reported, expected_generation=session.generation)
    if report_error:
        raise report_error
    if key in loop._pending_queues:
        return
    # Restart recovery owns admission until an explicit Continue is committed.
    # Do not wake, pause at a round limit, or consume a continuation meanwhile.
    if goal_recovery_pending(metadata):
        return
    if goal.get("status") not in {"active", "waiting"}:
        return
    if goal.get("status") == "waiting":
        wake_at = goal.get("wake_at")
        if not wake_at or datetime.fromisoformat(wake_at).timestamp() > now.timestamp():
            return
    admitted = False
    previous_goal = goal
    reserved_rounds = 0

    def wake(current):
        nonlocal admitted, goal, reserved_rounds
        if (
            parse_goal_state(goal_state_raw(current)) != goal
            or key in loop._pending_queues
            or key in loop._discarding_sessions
            or goal_recovery_pending(current)
        ):
            return
        rounds = current.get("_sustained_goal_continuation_rounds", 0)
        limit = goal.get("continuation_limit", loop.goal_continuation_limit)
        if limit > 0 and rounds >= limit:
            current["goal_state"] = pause_goal_at_limit(goal)
            return
        goal = {**goal, "status": "active"}
        goal.pop("wake_at", None)
        current["goal_state"] = goal
        current["_sustained_goal_continuation_rounds"] = rounds + 1
        reserved_rounds = rounds
        admitted = True

    try:
        await loop.sessions.state.mutate_metadata(key, wake, expected_generation=session.generation)
        if not admitted:
            return
        channel, chat_id = key.split(":", 1)
        await loop.dispatch.enqueue(
            InboundMessage(
                channel=channel,
                chat_id=chat_id,
                sender_id="system:goal",
                content=_goal_continuation_prompt({"goal_state": goal}),
                session_key_override=key,
                require_existing_session=True,
                session_generation=session.generation,
                input_role="user",
                metadata={
                    "_internal_continuation": True,
                    "_internal_continuation_kind": "sustained_goal",
                    "_skip_user_persist": True,
                    "_goal_id": goal.get("goal_id"),
                },
            )
        )
    except BaseException:
        if not admitted:
            raise
        async def release_reservation():
            def restore(current):
                if (
                    key not in loop._pending_queues
                    and parse_goal_state(goal_state_raw(current)) == goal
                    and current.get("_sustained_goal_continuation_rounds", 0) == reserved_rounds + 1
                ):
                    current["goal_state"] = previous_goal
                    current["_sustained_goal_continuation_rounds"] = reserved_rounds
            await loop.sessions.state.mutate_metadata(
                key, restore, expected_generation=session.generation,
            )
        try:
            await shield_and_drain(release_reservation())
        except BaseException as cleanup_error:
            logger.warning("Goal admission rollback for {} failed ({})", key, type(cleanup_error).__name__)
        raise
