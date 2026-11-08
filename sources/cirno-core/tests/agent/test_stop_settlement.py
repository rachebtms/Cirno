"""A stop succeeds only when its workers have settled successfully."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cirno_core.bus.events import InboundMessage
from cirno_core.command.builtin.control import cmd_stop
from cirno_core.command.router import CommandContext


async def test_stop_surfaces_failed_cleanup_after_stopping_owned_resources(loop_factory):
    loop = loop_factory()
    key = "websocket:stop-settlement"
    await loop.sessions.state.get(key)
    started = asyncio.Event()
    problem = OSError("Failed to persist the interrupted tool result")

    async def worker():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            raise problem

    task = asyncio.create_task(worker())
    loop._track_active_task(key, task)
    await started.wait()
    subagents = loop.subagents.cancel_by_session = AsyncMock(return_value=0)
    processes = loop._exec_session_manager.terminate_by_owner = AsyncMock(return_value=0)
    stopped = AsyncMock()
    loop.recovery_admission = SimpleNamespace(turn_stopped=stopped)
    message = InboundMessage("websocket", "owner", "stop-settlement", "/stop")
    context = CommandContext(msg=message, session=None, key=key, raw="/stop", loop=loop)
    try:
        with pytest.raises(OSError) as caught:
            await cmd_stop(context)
        assert caught.value is problem
        subagents.assert_awaited_once_with(key)
        processes.assert_awaited_once_with(key)
        stopped.assert_awaited_once_with(key)
        assert key not in loop._active_tasks
    finally:
        await asyncio.gather(task, return_exceptions=True)
        await loop.aclose()


async def test_cancelled_stop_caller_still_settles_the_accepted_stop(loop_factory):
    loop = loop_factory()
    key = "websocket:accepted-stop"
    await loop.sessions.state.get(key)
    started, settling, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def worker():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            settling.set()
            await release.wait()

    task = asyncio.create_task(worker())
    loop._track_active_task(key, task)
    await started.wait()
    stopped = AsyncMock()
    loop.recovery_admission = SimpleNamespace(turn_stopped=stopped)
    stop = asyncio.create_task(loop.cancel_session_work(key))
    try:
        await asyncio.wait_for(settling.wait(), 3)
        stop.cancel()
        await asyncio.sleep(0)
        assert not stop.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(stop, 3)
        assert task.cancelled()
        stopped.assert_awaited_once_with(key)
        assert key not in loop._active_tasks
    finally:
        release.set()
        await asyncio.gather(stop, task, return_exceptions=True)
        await loop.aclose()


@pytest.mark.parametrize("failed_stage", ["session_read", "goal_write", "children"])
async def test_stop_attempts_every_owned_cleanup_before_reporting_an_operation_failure(
    loop_factory,
    monkeypatch,
    failed_stage,
):
    loop = loop_factory()
    key = "websocket:failed-stop-step"
    await loop.sessions.state.get(key)
    await loop.sessions.state.update_metadata(
        key, {"goal_state": {"objective": "Work", "status": "active"}}
    )
    entered, cancelled = asyncio.Event(), asyncio.Event()
    problem = OSError("Fixture stop operation failed")

    async def worker():
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    task = asyncio.create_task(worker())
    loop._track_active_task(key, task)
    await entered.wait()
    children = AsyncMock(
        return_value=0, side_effect=problem if failed_stage == "children" else None
    )
    monkeypatch.setattr(loop.subagents, "cancel_by_session", children)
    processes = AsyncMock(return_value=0)
    monkeypatch.setattr(loop._exec_session_manager, "terminate_by_owner", processes)
    stopped = AsyncMock()
    loop.recovery_admission = SimpleNamespace(turn_stopped=stopped)
    if failed_stage == "session_read":
        monkeypatch.setattr(loop.sessions.state, "read", AsyncMock(side_effect=problem))
    elif failed_stage == "goal_write":
        monkeypatch.setattr(loop.sessions.state, "update_metadata", AsyncMock(side_effect=problem))
    try:
        with pytest.raises(OSError) as caught:
            await loop.cancel_session_work(key)
        assert caught.value is problem
        assert cancelled.is_set()
        children.assert_awaited_once_with(key)
        processes.assert_awaited_once_with(key)
        if failed_stage != "session_read":
            stopped.assert_awaited_once_with(key)
        assert key not in loop._active_tasks
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await loop.aclose()
