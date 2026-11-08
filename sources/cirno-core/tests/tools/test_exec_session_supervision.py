from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest
from cirno_core.agent.tools.context import (
    RequestContext,
    bind_request_context,
    reset_request_context,
)
from cirno_core.processes import lifecycle as process_lifecycle
from cirno_core.processes.sessions.session import ExecSession
from loguru import logger

from sources.development.testing.processes import (
    cancel_session_tasks,
    fake_session_process,
)


async def test_exec_session_shared_kill_survives_cancelled_caller(monkeypatch):
    process, exited = fake_session_process()
    session = ExecSession(
        session_id="shared-kill", process=process, command="test", cwd=".",
        timeout=None, process_tree=True,
    )
    kill_started = asyncio.Event()
    release_kill = asyncio.Event()
    second_started = asyncio.Event()

    async def kill_process_tree(target):
        assert target is process
        kill_started.set()
        await release_kill.wait()
        process.returncode = -9
        exited.set()

    kill_tree = AsyncMock(side_effect=kill_process_tree)
    monkeypatch.setattr(process_lifecycle, "kill_process_tree", kill_tree)

    async def second_caller():
        second_started.set()
        await session.kill()

    first = asyncio.create_task(session.kill())
    second = None
    try:
        await asyncio.wait_for(kill_started.wait(), timeout=2)
        second = asyncio.create_task(second_caller())
        await asyncio.wait_for(second_started.wait(), timeout=2)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert process.returncode is None
        assert not second.done()
        kill_tree.assert_awaited_once_with(process)
        release_kill.set()
        await asyncio.wait_for(second, timeout=2)
        assert process.returncode == -9
        assert session.finish_reason == "cancelled"
        assert session.finished_at is not None
        kill_tree.assert_awaited_once_with(process)
    finally:
        release_kill.set()
        await asyncio.gather(first, *([second] if second is not None else []), return_exceptions=True)
        await cancel_session_tasks(session)


@pytest.mark.parametrize("log_content", [True, False])
async def test_exec_session_failed_kill_can_be_retried(monkeypatch, log_content):
    process, exited = fake_session_process()
    session = ExecSession(
        session_id="retry-kill", process=process, command="test", cwd=".",
        timeout=None, process_tree=True, log_content=log_content,
    )
    attempts = 0

    async def kill_process_tree(target):
        nonlocal attempts
        assert target is process
        attempts += 1
        if attempts == 1:
            raise OSError("temporary process-tree cleanup failure")
        process.returncode = -9
        exited.set()

    monkeypatch.setattr(process_lifecycle, "kill_process_tree", kill_process_tree)
    records = []
    sink = logger.add(lambda message: records.append(message.record), format="{message}")
    token = bind_request_context(RequestContext(
        channel="websocket", chat_id="test", log_content=log_content,
    ))
    try:
        with pytest.raises(OSError, match="temporary process-tree cleanup failure"):
            await session.kill()
        assert process.returncode is None
        assert session.finished_at is None
        await session.kill()
        assert process.returncode == -9
        assert session.finish_reason == "cancelled"
        assert session.finished_at is not None
        assert session.cleanup_error is None
        assert attempts == 2
        assert len(records) == 1
        assert (records[0]["exception"] is not None) is log_content
        assert "temporary process-tree cleanup failure" not in records[0]["message"]
    finally:
        reset_request_context(token)
        logger.remove(sink)
        await cancel_session_tasks(session)


async def test_exec_session_deadline_during_explicit_kill_is_not_timeout(monkeypatch):
    process, exited = fake_session_process()
    session = ExecSession(
        session_id="explicit-kill", process=process, command="test", cwd=".",
        timeout=None, process_tree=True,
    )
    kill_started = asyncio.Event()
    release_kill = asyncio.Event()
    watcher_joined = asyncio.Event()

    async def kill_process_tree(target):
        assert target is process
        kill_started.set()
        await release_kill.wait()
        process.returncode = -9
        exited.set()

    kill_tree = AsyncMock(side_effect=kill_process_tree)
    monkeypatch.setattr(process_lifecycle, "kill_process_tree", kill_tree)
    explicit_kill = asyncio.create_task(session.kill())
    watcher = None
    try:
        await asyncio.wait_for(kill_started.wait(), timeout=2)
        original_kill = session.kill

        async def join_existing_kill(reason="cancelled"):
            assert reason == "max_runtime"
            watcher_joined.set()
            await original_kill(reason)

        monkeypatch.setattr(session, "kill", join_existing_kill)
        session.deadline = time.monotonic() - 1
        watcher = asyncio.create_task(session._watch_timeout())
        await asyncio.wait_for(watcher_joined.wait(), timeout=2)
        assert session.finish_reason is None
        assert session.stopping
        assert not watcher.done()
        kill_tree.assert_awaited_once_with(process)
        release_kill.set()
        await asyncio.wait_for(asyncio.gather(explicit_kill, watcher), timeout=2)
        assert process.returncode == -9
        assert session.finish_reason == "cancelled"
        poll = await session.poll(0, 1000)
        assert poll.terminated
        assert not poll.timed_out
        kill_tree.assert_awaited_once_with(process)
    finally:
        release_kill.set()
        await asyncio.gather(
            explicit_kill, *([watcher] if watcher is not None else []), return_exceptions=True,
        )
        await cancel_session_tasks(session)
