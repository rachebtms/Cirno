"""Native search does not accidentally select an idle stdin pipe as its input."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.agent.tools.rg import RgTool
from cirno_core.agent.tools.shell import ExecTool
from cirno_core.processes.sessions.contracts import SessionPoll


@pytest.mark.parametrize("yield_time", [None, 0, 25])
async def test_rg_defaults_to_closed_input_even_when_yield_is_explicit(tmp_path, yield_time):
    manager = SimpleNamespace(start=AsyncMock(return_value=("fixture", SessionPoll("", True, 1))))
    result = await RgTool(working_dir=str(tmp_path), session_manager=manager).execute(
        args=["needle"], yield_time_ms=yield_time
    )
    assert manager.start.await_args.kwargs["stdin"] == asyncio.subprocess.DEVNULL
    assert manager.start.await_args.kwargs["command"] == ["rg", "needle"]
    assert "Exit code: 1" in result
    assert not getattr(result, "is_error", False)


@pytest.mark.parametrize("tool_type", [ExecTool, RgTool])
@pytest.mark.parametrize("stdin", ["closed", "pipe"])
async def test_explicit_input_policy_is_forwarded_without_changing_argv(tmp_path, tool_type, stdin):
    manager = SimpleNamespace(
        start=AsyncMock(return_value=("fixture", SessionPoll("", False, None)))
    )
    tool = tool_type(working_dir=str(tmp_path), session_manager=manager)
    args = (
        {"args": ["needle", "-"]}
        if tool_type is RgTool
        else {"command": ["fixture", "literal arg"]}
    )
    result = await tool.execute(**args, stdin=stdin, yield_time_ms=None)
    assert manager.start.await_args.kwargs["stdin"] == (
        asyncio.subprocess.DEVNULL if stdin == "closed" else asyncio.subprocess.PIPE
    )
    assert "session_id: fixture" in result


@pytest.mark.parametrize("tool_type", [ExecTool, RgTool])
async def test_invalid_input_policy_is_rejected_before_launch(tmp_path, tool_type):
    manager = SimpleNamespace(start=AsyncMock())
    tool = tool_type(working_dir=str(tmp_path), session_manager=manager)
    args = {"args": ["needle"]} if tool_type is RgTool else {"command": "fixture"}
    result = await tool.execute(**args, stdin="invalid")
    assert getattr(result, "is_error", False)
    assert "stdin" in result
    manager.start.assert_not_awaited()


@pytest.mark.parametrize("tool_type,name", [(ExecTool, "shell__exec"), (RgTool, "files__rg")])
@pytest.mark.parametrize("stdin", ["closed", "pipe", "invalid"])
async def test_public_input_schema_and_dispatch_are_consistent(tmp_path, tool_type, name, stdin):
    manager = SimpleNamespace(start=AsyncMock(return_value=("fixture", SessionPoll("", True, 0))))
    registry = ToolRegistry()
    registry.register(tool_type(working_dir=str(tmp_path), session_manager=manager))
    params = {"args": ["needle"]} if tool_type is RgTool else {"command": "fixture"}
    result = await registry.execute(name, {**params, "stdin": stdin})
    if stdin == "invalid":
        assert getattr(result, "is_error", False)
        manager.start.assert_not_awaited()
    else:
        assert not getattr(result, "is_error", False)
        assert manager.start.await_args.kwargs["stdin"] == (
            asyncio.subprocess.PIPE if stdin == "pipe" else asyncio.subprocess.DEVNULL
        )


@pytest.mark.parametrize("yield_time", [None, 0, 25])
async def test_shell_retains_legacy_input_default(tmp_path, yield_time):
    manager = SimpleNamespace(start=AsyncMock(return_value=("fixture", SessionPoll("", True, 0))))
    await ExecTool(working_dir=str(tmp_path), session_manager=manager).execute(
        command="fixture", yield_time_ms=yield_time
    )
    assert manager.start.await_args.kwargs["stdin"] == (
        asyncio.subprocess.DEVNULL if yield_time is None else asyncio.subprocess.PIPE
    )
