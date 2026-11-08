"""Command preparation and process cleanup failures must remain visible."""

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cirno_core.agent.tools.registry import is_tool_error_result
from cirno_core.agent.tools.shell import ExecTool
from cirno_core.processes import launch, lifecycle, platform


@pytest.mark.parametrize(
    "failure",
    [
        PermissionError("path lookup denied"),
        RuntimeError("symlink loop"),
        ValueError("invalid path"),
    ],
)
async def test_unresolved_command_path_never_launches_or_requests_approval(
    tmp_path, monkeypatch, failure
):
    target = tmp_path / "unreadable"
    tool = ExecTool(working_dir=str(tmp_path), restrict_to_workspace=True)
    resolve = Path.resolve

    def failing_resolve(path, *args, **kwargs):
        if path == target:
            raise failure
        return resolve(path, *args, **kwargs)

    spawn = AsyncMock(side_effect=AssertionError("Invalid paths must not launch"))
    monkeypatch.setattr(Path, "resolve", failing_resolve)
    monkeypatch.setattr(launch, "spawn_process", spawn)
    params = {"command": f'cat "{target}"'}
    assert tool.approval_reason(params) is None
    result = await tool.execute(**params)
    assert is_tool_error_result(result)
    assert "could not be resolved" in result
    assert str(failure) in result
    spawn.assert_not_awaited()


def test_sandbox_bind_resolution_failure_is_not_silently_discarded(tmp_path, monkeypatch):
    target = tmp_path / "unreadable-bind"
    resolve = Path.resolve

    def failing_resolve(path, *args, **kwargs):
        if path == target:
            raise PermissionError("bind path lookup denied")
        return resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", failing_resolve)
    with pytest.raises(PermissionError, match="bind path lookup denied"):
        ExecTool(sandbox="bwrap", sandbox_ro_binds=[str(target)])


def test_unexpected_child_reaping_error_propagates(monkeypatch):
    monkeypatch.setattr(
        lifecycle.os, "waitpid", Mock(side_effect=PermissionError("reaping denied")), raising=False
    )
    monkeypatch.setattr(lifecycle.os, "WNOHANG", 1, raising=False)
    with pytest.raises(PermissionError, match="reaping denied"):
        lifecycle.reap_pid(999)


async def test_unconfirmed_process_exit_is_not_reported_as_success(monkeypatch):
    process = SimpleNamespace(
        pid=999, returncode=None, kill=Mock(), wait=AsyncMock(side_effect=TimeoutError)
    )
    reap = Mock()
    monkeypatch.setattr(lifecycle, "reap_pid", reap)
    with pytest.raises(TimeoutError):
        await lifecycle.kill_process(process)
    process.kill.assert_called_once()
    reap.assert_called_once_with(999)


@pytest.mark.parametrize(
    "failure",
    [
        FileNotFoundError("taskkill unavailable"),
        subprocess.CalledProcessError(5, "taskkill"),
        subprocess.TimeoutExpired("taskkill", 5),
    ],
)
async def test_windows_tree_failure_still_reaps_root_and_reports_failure(monkeypatch, failure):
    process = SimpleNamespace(
        pid=999, returncode=None, kill=Mock(), wait=AsyncMock(return_value=-9)
    )
    monkeypatch.setattr(platform, "IS_WINDOWS", True)
    taskkill = Mock(side_effect=failure)
    monkeypatch.setattr(lifecycle.subprocess, "run", taskkill)
    reap = Mock()
    monkeypatch.setattr(lifecycle, "reap_pid", reap)
    with pytest.raises(RuntimeError, match="Failed to terminate process tree"):
        await lifecycle.kill_process_tree(process)
    process.kill.assert_called_once()
    process.wait.assert_awaited_once()
    reap.assert_called_once_with(999)
    assert taskkill.call_args.kwargs["check"] is True
    assert taskkill.call_args.kwargs["timeout"] == 5
