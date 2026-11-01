"""Wake durable Goals through the normal per-session execution queue."""

from __future__ import annotations

from datetime import datetime, timezone

from cirno.bus.events import InboundMessage
from cirno.session.goal_state import goal_state_raw, parse_goal_state
from cirno.session.sqlite_store import SessionConflictError
from cirno.session.turn_continuation import _goal_continuation_prompt
from loguru import logger


async def wake_due_goals(loop) -> None:
    now = datetime.now(timezone.utc)
    rows = await loop.sessions.state.list_metadata()
    for row in rows:
        try:
            await _wake_goal(loop, row["key"], now)
        except SessionConflictError:
            # Deleting/replacing one conversation must not delay other Goals.
            logger.debug("Goal scheduler skipped a changed conversation: {}", row["key"])


async def _wake_goal(loop, key, now):
    if key in loop._discarding_sessions:
        return
    session = await loop.sessions.state.read_header(key)
    if session is None:
        return
    metadata = session.metadata
    goal = parse_goal_state(goal_state_raw(metadata)) or {}
    from cirno.agent.work_reports import deliver_work_report, record_goal_report
    from cirno.agent.tools.session_messages import SessionMessageError

    report = metadata.get("work_report")
    if goal.get("report_to"):
        report = await record_goal_report(loop.sessions, key, goal, metadata) or report
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
            if status == "queued" and goal.get("status") == "completed" and not goal.get("report_delivered"):
                def reported(current):
                    if parse_goal_state(goal_state_raw(current)) == goal:
                        current["goal_state"] = {**goal, "report_delivered": True}
                await loop.sessions.state.mutate_metadata(key, reported, expected_generation=session.generation)
    if key in loop._pending_queues:
        return
    if goal.get("status") not in {"active", "waiting"}:
        return
    if goal.get("status") == "waiting":
        wake_at = goal.get("wake_at")
        if not wake_at or datetime.fromisoformat(wake_at).timestamp() > now.timestamp():
            return
    limit = goal.get("continuation_limit", loop.goal_continuation_limit)
    rounds = metadata.get("_sustained_goal_continuation_rounds", 0)
    if limit > 0 and rounds >= limit:

        def pause_at_limit(current):
            if parse_goal_state(goal_state_raw(current)) == goal:
                current["goal_state"] = {
                    **goal,
                    "status": "paused",
                    "recap": "Automatic continuation limit reached.",
                }

        await loop.sessions.state.mutate_metadata(key, pause_at_limit, expected_generation=session.generation)
        return
    # Uncertain side effects are recovered by the existing recovery flow.
    if metadata.get("runtime_checkpoint") or metadata.get("pending_user_turn"):
        return
    admitted = False

    def wake(current):
        nonlocal admitted, goal
        if (
            parse_goal_state(goal_state_raw(current)) != goal
            or key in loop._pending_queues
            or key in loop._discarding_sessions
        ):
            return
        goal = {**goal, "status": "active"}
        goal.pop("wake_at", None)
        current["goal_state"] = goal
        current["_sustained_goal_continuation_rounds"] = rounds + 1
        admitted = True

    await loop.sessions.state.mutate_metadata(key, wake, expected_generation=session.generation)
    if not admitted:
        return
    channel, chat_id = key.split(":", 1)
    await loop._enqueue_session_message(
        InboundMessage(
            channel=channel,
            chat_id=chat_id,
            sender_id="system:goal",
            content=_goal_continuation_prompt({"goal_state": goal}),
            session_key_override=key,
            require_existing_session=True,
            input_role="user",
            metadata={
                "_internal_continuation": True,
                "_internal_continuation_kind": "sustained_goal",
                "_skip_user_persist": True,
                "_goal_id": goal.get("goal_id"),
            },
        )
    )
