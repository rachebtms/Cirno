"""Listing and interaction enforce the same runtime session ownership boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.exec_session import ExecSessionTool
from cirno_core.agent.tools.registry import is_tool_error_result
from cirno_core.processes.sessions import ExecSessionManager
from cirno_core.processes.sessions.contracts import SessionPoll


def setup(owner):
    manager = ExecSessionManager()
    session = SimpleNamespace(
        owner_session_key=owner, finished_at=None,
        write=AsyncMock(return_value=None), close_stdin=AsyncMock(return_value=None),
        kill=AsyncMock(), poll=AsyncMock(return_value=SessionPoll("private output", False, None)),
        return_output=AsyncMock(),
    )
    manager._sessions["fixture"] = session
    return manager, session


@pytest.mark.parametrize("action", ["poll", "input", "close", "terminate"])
async def test_scoped_caller_cannot_interact_with_an_unscoped_host_session(action):
    manager, session = setup(None)
    values = {
        "poll": {"timeout_ms": 0}, "input": {"input": "change state\n", "timeout_ms": 0},
        "close": {"close_stdin": True, "timeout_ms": 0}, "terminate": {"terminate": True},
    }[action]
    with request_context(RequestContext("websocket", "worker", session_key="websocket:worker")):
        result = await ExecSessionTool(manager=manager).execute(session_id="fixture", **values)
    assert is_tool_error_result(result) and "session not found" in result
    session.write.assert_not_awaited()
    session.close_stdin.assert_not_awaited()
    session.kill.assert_not_awaited()
    session.poll.assert_not_awaited()


@pytest.mark.parametrize("owner,caller", [(None, None), ("websocket:worker", "websocket:worker")])
async def test_the_original_owner_can_still_poll_and_write(owner, caller):
    manager, session = setup(owner)
    poll = await manager.write(session_id="fixture", chars="input", close_stdin=True, terminate=False,
                               yield_time_ms=0, max_output_chars=100, owner_session_key=caller)
    assert poll.output == "private output"
    session.write.assert_awaited_once_with("input")
    session.close_stdin.assert_awaited_once()
    session.poll.assert_awaited_once()


@pytest.mark.parametrize("owner,caller", [(None, "cli:other"), ("cli:owner", None), ("cli:owner", "cli:other")])
async def test_restored_logs_cannot_be_injected_into_another_owner(owner, caller):
    manager, session = setup(owner)
    await manager.return_output(session_id="fixture", output="foreign logs", truncated_chars=0,
                                owner_session_key=caller)
    session.return_output.assert_not_awaited()


async def test_returning_output_never_recreates_a_closed_session():
    manager, session = setup("cli:owner")
    manager._sessions.clear()
    await manager.return_output(session_id="fixture", output="old logs", truncated_chars=0,
                                owner_session_key="cli:owner")
    assert manager._sessions == {}
    session.return_output.assert_not_awaited()
