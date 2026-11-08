"""Shared stop settlement for commands, supervisory controls and session removal."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from cirno_core.bus.events import InboundMessage
from cirno_core.processes.sessions import ExecSessionManager
from cirno_core.session.goal_state import goal_state_raw, parse_goal_state
from cirno_core.session.manager import SessionManager
from cirno_core.session.recovery.contracts import PENDING_FOLLOWUP_ID_KEY, RecoveryAdmission
from cirno_core.session.recovery.pending import pending_followups

_Result = TypeVar("_Result")


async def _settle(
    operation: Awaitable[_Result], failures: list[BaseException], failed_result: _Result
) -> _Result:
    """Finish independent stop steps, then report every failed operation."""
    try:
        return await operation
    except BaseException as error:
        failures.append(error)
        return failed_result


async def cancel_session_work(
    key: str,
    *,
    sessions: SessionManager,
    active_tasks: dict[str, set[asyncio.Task[Any]]],
    pending_queues: dict[str, asyncio.Queue[InboundMessage]],
    cancel_pending: Callable[
        [str, asyncio.Queue[InboundMessage], asyncio.CancelledError], Awaitable[None]
    ],
    cancel_children: Callable[[str], Awaitable[int]],
    processes: ExecSessionManager,
    recovery: RecoveryAdmission | None,
    stop_goal: bool = True,
) -> int:
    """Settle owned work before reporting cancellation or a worker cleanup error."""
    failures: list[BaseException] = []
    journal_session = None
    journaled_followup_ids: tuple[str, ...] = ()
    try:
        journal_session = await sessions.state.read(key)
        if journal_session is not None:
            journaled_followup_ids = tuple(
                followup_id
                for followup in pending_followups(journal_session)
                if isinstance(followup_id := followup.metadata.get(PENDING_FOLLOWUP_ID_KEY), str)
            )
            goal = parse_goal_state(goal_state_raw(journal_session.metadata)) or {}
            if stop_goal and goal.get("status") in {"active", "waiting"}:
                await sessions.state.update_metadata(
                    key, {"goal_state": {**goal, "status": "stopped"}}
                )
    except BaseException as error:
        failures.append(error)
    pending = pending_queues.get(key)
    tasks = tuple(active_tasks.pop(key, set()))
    cancelled = sum(1 for t in tasks if not t.done() and t.cancel())
    outcomes = await asyncio.gather(*tasks, return_exceptions=True)
    failures.extend(
        result
        for result in outcomes
        if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError)
    )
    if pending is not None and pending_queues.get(key) is pending:
        # A task cancelled before its first step never enters the worker's
        # cleanup handler. Only reclaim that worker's original inbox.
        pending_queues.pop(key, None)
        await _settle(cancel_pending(key, pending, asyncio.CancelledError()), failures, None)
    if journaled_followup_ids and journal_session is not None:
        # Explicit session cancellation owns the follow-ups accepted before
        # it began. Server shutdown uses aclose() directly and keeps this
        # journal intact for startup recovery.
        await _settle(
            sessions.state.acknowledge_followups(key, journaled_followup_ids), failures, None
        )
    sub_cancelled = await _settle(cancel_children(key), failures, 0)
    exec_cancelled = await _settle(processes.terminate_by_owner(key), failures, 0)
    if stop_goal and recovery is not None and journal_session is not None:
        await _settle(recovery.turn_stopped(key), failures, None)
    if len(failures) == 1:
        raise failures[0]
    if failures:
        raise BaseExceptionGroup("Conversation stop failed", failures)
    return cancelled + sub_cancelled + exec_cancelled
