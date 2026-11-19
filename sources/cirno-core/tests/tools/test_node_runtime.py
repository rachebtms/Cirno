"""Local and SSH commands use one configured runtime policy, without replay."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cirno_core.agent.tools.instance_features import NodeTool
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.agent.tools.shell import ExecTool
from cirno_core.agent.tools.shell_config import ExecToolConfig
from cirno_core.nodes.commands import CommandOutcomeUnknown, CommandResult
from cirno_core.nodes.service import Nodes


@pytest.mark.parametrize(("default", "limit", "values", "effective"), [
    (600, 900, {}, 600),
    (600, 900, {"max_runtime": 700}, 700),
    (600, 900, {"timeout": 900}, 900),
    (0, 900, {}, None),
    (600, 0, {"max_runtime": 0}, None),
    (600, 0, {"timeout": 0}, None),
])
async def test_runtime_reaches_ssh_once_and_matches_local_shell(tmp_path, monkeypatch, default, limit, values, effective):
    config = ExecToolConfig(max_runtime=default, max_runtime_limit=limit)
    execute = AsyncMock(return_value=CommandResult("saved", "", 0))
    monkeypatch.setattr("cirno_core.agent.tools.instance_features.Nodes", lambda **kw: SimpleNamespace(execute_command=execute))
    ctx = SimpleNamespace(config=SimpleNamespace(exec=config), source_config_path=tmp_path / "config.json")
    remote = NodeTool.create(ctx)
    local = ExecTool(max_runtime=default, max_runtime_limit=limit)
    assert remote.parameters["properties"]["max_runtime"] == local.parameters["properties"]["max_runtime"]
    assert local.preparation.resolve_timeout(values.get("max_runtime", values.get("timeout"))) == effective
    registry = ToolRegistry()
    registry.register(remote)
    definitions = {row["function"]["name"]: row["function"]["parameters"] for row in registry.get_definitions()}
    assert definitions["nodes__execute"]["properties"]["max_runtime"] == local.parameters["properties"]["max_runtime"]
    assert "timeout" not in definitions["nodes__start"]["properties"]
    result = await registry.execute("nodes__execute", {"node_id": "node", "command": "save-result", **values})
    assert json.loads(result)["stdout"] == "saved"
    execute.assert_awaited_once_with("node", "save-result", timeout=effective)


@pytest.mark.parametrize("values", [
    {"timeout": 10, "max_runtime": 20}, {"max_runtime": 601},
    {"timeout": 0}, {"timeout": -1}, {"timeout": True}, {"timeout": 1.5},
])
async def test_invalid_runtime_is_rejected_before_remote_access(tmp_path, monkeypatch, values):
    construct = AsyncMock()
    monkeypatch.setattr("cirno_core.agent.tools.instance_features.Nodes", construct)
    tool = NodeTool(source_config_path=tmp_path / "config.json", exec_config=ExecToolConfig(max_runtime_limit=600))
    result = await tool.execute("execute", node_id="node", command="write", **values)
    assert result.is_error
    construct.assert_not_called()


async def test_unconfirmed_execution_with_custom_runtime_is_not_retried(tmp_path, monkeypatch):
    execute = AsyncMock(side_effect=CommandOutcomeUnknown(CommandResult("partial", "disconnected", 255)))
    monkeypatch.setattr("cirno_core.agent.tools.instance_features.Nodes", lambda **kw: SimpleNamespace(execute_command=execute))
    result = await NodeTool(source_config_path=tmp_path / "config.json").execute(
        "execute", node_id="node", command="write", max_runtime=600,
    )
    assert result.is_error and json.loads(result)["resubmit_safe"] is False
    execute.assert_awaited_once_with("node", "write", timeout=600)


@pytest.mark.parametrize("timeout", [None, 0, 600])
async def test_unlimited_and_finite_ssh_transport_deadlines(monkeypatch, timeout):
    process = SimpleNamespace(
        stdout=SimpleNamespace(read=AsyncMock(side_effect=[b"result", b""])),
        stderr=SimpleNamespace(read=AsyncMock(return_value=b"")), wait=AsyncMock(), returncode=0,
    )
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
    real_timeout, seen = asyncio.timeout, []

    def deadline(seconds):
        seen.append(seconds)
        return real_timeout(seconds)

    monkeypatch.setattr(asyncio, "timeout", deadline)
    result = await Nodes.__new__(Nodes)._run_result(["ssh", "node"], timeout=timeout)
    assert result.stdout == "result"
    assert seen == [None if timeout == 0 else timeout]


async def test_durable_start_rejects_runtime_override_instead_of_ignoring_it(tmp_path):
    result = await NodeTool(source_config_path=tmp_path / "config.json").execute(
        "start", node_id="node", command="train", timeout=600,
    )
    assert result.is_error and "only to nodes.execute" in result
