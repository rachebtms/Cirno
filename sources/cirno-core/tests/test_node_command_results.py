"""Command exit codes and SSH transport outcomes are distinct, without a server."""

import json
import shlex
from types import SimpleNamespace

import pytest

from cirno_core.agent.tools.registry import is_tool_error_result
from cirno_core.agent.tools.instance_features import NodeTool
from cirno_core.nodes.commands import CommandResult
from cirno_core.nodes.service import Node, Nodes


def local_node(tmp_path):
    nodes = Nodes.__new__(Nodes)
    nodes.data = SimpleNamespace(state_dir=tmp_path)
    node = Node(name="Fixture", host="server", username="owner", working_directory=str(tmp_path))
    nodes.node = lambda _: node
    nodes.arguments = lambda _: ["ssh"]
    spawn = nodes._run_result
    commands = []

    async def run(args, timeout=120, **kwargs):
        commands.append(args[-1])
        return await spawn(["sh", "-c", args[-1]], timeout)

    nodes._run_result = run
    return nodes, node, commands


@pytest.mark.parametrize("code", [0, 2, 255])
async def test_remote_exit_status_preserves_both_streams_and_runs_once(tmp_path, monkeypatch, code):
    nodes, _, commands = local_node(tmp_path)
    counter = tmp_path / "executions"
    command = f"printf run >>{shlex.quote(str(counter))}; printf 'ordinary output'; printf 'diagnostic output' >&2; exit {code}"
    monkeypatch.setattr("cirno_core.agent.tools.instance_features.Nodes", lambda **kwargs: nodes)
    result = await NodeTool().execute("execute", node_id="fixture", command=command)
    assert not is_tool_error_result(result)
    assert json.loads(result) == {"stdout": "ordinary output", "stderr": "diagnostic output", "exit_code": code}
    assert counter.read_text() == "run"
    assert len(commands) == 1


async def test_failed_initialization_is_a_command_result_and_does_not_execute_body(tmp_path):
    nodes, node, _ = local_node(tmp_path)
    init = tmp_path / "init.sh"
    init.write_text("printf 'initialization failed' >&2\nreturn 23\n")
    node.init_script = str(init)
    result = await nodes.execute_command("fixture", "touch should-not-exist")
    assert result.exit_code == 23 and "initialization failed" in result.stderr
    assert not (tmp_path / "should-not-exist").exists()


@pytest.mark.parametrize("code", [0, 255])
async def test_missing_receipt_or_dropped_connection_is_not_a_command_success(tmp_path, code):
    nodes, _, _ = local_node(tmp_path)

    async def disconnected(*args, **kwargs):
        return CommandResult("partial stdout", "Connection to frps closed by remote host", code)

    nodes._run_result = disconnected
    with pytest.raises(RuntimeError) as error:
        await nodes.execute_command("fixture", "write something")
    assert "partial stdout" in str(error.value)
    assert "Connection to frps closed" in str(error.value)
    if code == 0:
        assert "outcome unconfirmed" in str(error.value)
