"""Runtime-local command ownership and the original owner's logging policy."""

import re
import sys

import pytest
from cirno_core.agent.tools.context import RequestContext, ToolContext, request_context
from cirno_core.agent.tools.exec_session import ExecSessionTool, ListExecSessionsTool
from cirno_core.agent.tools.shell import ExecTool
from cirno_core.config.tools import ToolsConfig
from cirno_core.processes import lifecycle
from cirno_core.processes.sessions import ExecSessionManager
from loguru import logger


def _session_id(result: str) -> str:
    match = re.search(r"session_id:\s*([0-9a-f]+)", result)
    assert match, result
    return match.group(1)


async def test_default_tool_contexts_cannot_read_or_close_each_others_processes(tmp_path):
    first = ToolContext(config=ToolsConfig(), workspace=str(tmp_path))
    other = ToolContext(config=ToolsConfig(), workspace=str(tmp_path))
    executor = ExecTool.create(first)
    observer = ExecSessionTool.create(first)
    try:
        initial = await executor.execute(
            command=[
                sys.executable,
                "-u",
                "-c",
                "import sys; print('received:' + sys.stdin.read())",
            ],
            yield_time_ms=0,
        )
        session_id = _session_id(initial)
        assert await ListExecSessionsTool.create(other).execute() == "No active exec sessions."
        rejected = await ExecSessionTool.create(other).execute(session_id=session_id, timeout_ms=0)
        assert "session not found" in rejected
        assert await other.exec_session_manager.close_all() == 0

        result = await observer.execute(
            session_id=session_id,
            input="owner retained",
            close_stdin=True,
            until_exit=True,
            timeout_ms=5000,
        )
        assert "received:owner retained" in result
        assert "Exit code: 0" in result
    finally:
        await first.exec_session_manager.close_all()
        await other.exec_session_manager.close_all()


@pytest.mark.parametrize("owner_logs_content", [True, False])
async def test_cleanup_keeps_original_logging_policy_when_caller_changes(
    tmp_path, monkeypatch, owner_logs_content
):
    manager = ExecSessionManager()
    tool = ExecTool(working_dir=str(tmp_path), session_manager=manager)
    original_kill = lifecycle.kill_process_tree
    attempts = 0
    records = []

    async def failing_then_successful_cleanup(process):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("private cleanup detail")
        await original_kill(process)

    monkeypatch.setattr(lifecycle, "kill_process_tree", failing_then_successful_cleanup)
    sink = logger.add(lambda message: records.append(message.record))
    try:
        with request_context(
            RequestContext(
                channel="cli",
                chat_id="owner",
                session_key="cli:owner",
                log_content=owner_logs_content,
            )
        ):
            initial = await tool.execute(
                command=[sys.executable, "-u", "-c", "import sys; sys.stdin.read()"],
                yield_time_ms=0,
            )
        _session_id(initial)
        with request_context(
            RequestContext(
                channel="cli",
                chat_id="supervisor",
                log_content=not owner_logs_content,
            )
        ):
            with pytest.raises(OSError, match="private cleanup detail"):
                await manager.terminate_by_owner("cli:owner")
            failures = [
                row for row in records if "Failed to terminate exec session" in row["message"]
            ]
            assert len(failures) == 1
            assert (failures[0]["exception"] is not None) is owner_logs_content
            assert "private cleanup detail" not in failures[0]["message"]
            assert await manager.terminate_by_owner("cli:owner") == 1
        assert not manager.has_pending_work
    finally:
        await manager.close_all()
        logger.remove(sink)
