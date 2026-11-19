"""Cancelled output observations retain consumed logs for the same session owner."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from cirno_core.processes.sessions import ExecSessionManager
from cirno_core.processes.sessions.observer import observe_session
from cirno_core.processes.sessions.session import ExecSession

from sources.development.testing.processes import cancel_session_tasks, fake_session_process


@pytest.mark.parametrize("text,retained,dropped", [
    ("prefix-ready", "prefix-ready", 0),
    ("A" * 12000 + "B" * 8000, "A" * 5000 + "B" * 5000, 10000),
])
@pytest.mark.parametrize("repeated_cancel", [False, True])
async def test_cancelled_wait_restores_logs_and_truncation_before_later_output(text, retained, dropped, repeated_cancel):
    process, _ = fake_session_process()
    session = ExecSession(session_id="fixture", process=process, command="fake", cwd=".",
                          timeout=None, owner_session_key="cli:owner")
    manager = ExecSessionManager()
    manager._sessions["fixture"] = session
    original_poll = session.poll
    waiting = asyncio.Event()
    calls = 0

    async def poll(_wait, maximum, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return await original_poll(0, maximum, **kwargs)
        waiting.set()
        await asyncio.Event().wait()

    session._stdout.append(text)
    session.poll = poll
    session.write = AsyncMock(return_value=None)
    task = asyncio.create_task(observe_session(manager, session_id="fixture", input="control\n",
        close_stdin=False, wait_for="not-yet-finished", until_exit=False,
        timeout_ms=1000, owner_session_key="cli:owner"))
    try:
        await asyncio.wait_for(waiting.wait(), 1)
        if repeated_cancel:
            await manager._lock.acquire()
        task.cancel()
        if repeated_cancel:
            for _ in range(3):
                await asyncio.sleep(0)
            assert not task.done()
            task.cancel()
            manager._lock.release()
        with pytest.raises(asyncio.CancelledError):
            await task
        session.poll = original_poll
        session._stdout.append("-new-output")
        result = await manager.write(session_id="fixture", chars=None, close_stdin=False,
            terminate=False, yield_time_ms=0, max_output_chars=50000, owner_session_key="cli:owner")
        assert result.output == retained + "-new-output"
        assert result.truncated_chars == dropped
        again = await manager.write(session_id="fixture", chars=None, close_stdin=False,
            terminate=False, yield_time_ms=0, max_output_chars=50000, owner_session_key="cli:owner")
        assert again.output == "" and again.truncated_chars == 0
        session.write.assert_awaited_once_with("control\n")
    finally:
        if manager._lock.locked():
            manager._lock.release()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await cancel_session_tasks(session)
