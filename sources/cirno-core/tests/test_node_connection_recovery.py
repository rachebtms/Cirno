"""SSH recovery respects completion receipts, deadlines and side effects."""

import asyncio
import json
import shutil
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cirno_core.agent.tools.instance_features import NodeTool
from cirno_core.agent.tools.registry import is_tool_error_result
from cirno_core.nodes.commands import CommandOutcomeUnknown, CommandResult, SSHProcessError, command_result
from cirno_core.nodes.service import Node, Nodes
from cirno_core.storage.instance import InstanceData


@pytest.mark.parametrize("code", [0, 2, 255])
@pytest.mark.parametrize("disconnect", [False, True])
def test_complete_receipt_wins_over_a_later_tunnel_failure(code, disconnect):
    transport = CommandResult("verified output", f"program diagnostic\nreceipt:{code}\n" + ("Connection to frps closed by remote host.\n" if disconnect else ""), 255 if disconnect else 0)
    result = command_result(transport, "receipt:")
    assert result.exit_code == code and result.stdout == "verified output"
    assert result.stderr.startswith("program diagnostic") and "receipt:" not in result.stderr
    assert bool(result.connection_warning) is disconnect
    if disconnect:
        assert "frps" in result.stderr and "do not repeat" in result.connection_warning


@pytest.mark.parametrize("receipt", ["", "\nreceipt:0", "\nreceipt:bad\n", "\nreceipt:256\n"])
def test_partial_or_invalid_receipts_keep_execution_unconfirmed(receipt):
    with pytest.raises(CommandOutcomeUnknown) as error:
        command_result(CommandResult("partial output", receipt + "Connection to frps closed", 255), "receipt:")
    details = error.value.to_dict()
    assert details["state"] == "execution_unknown" and details["resubmit_safe"] is False
    assert details["stdout"] == "partial output" and details["ssh_exit_code"] == 255


async def test_direct_execute_does_not_replay_an_unconfirmed_command_and_informs_the_model(tmp_path, monkeypatch):
    nodes = Nodes.__new__(Nodes)
    nodes.data = SimpleNamespace(state_dir=tmp_path)
    nodes.node = lambda _: Node(name="GPU", host="server", username="owner")
    nodes.arguments = lambda _: ["ssh"]
    nodes._run_result = AsyncMock(return_value=CommandResult("already wrote data", "Connection to frps closed by remote host", 255))
    monkeypatch.setattr("cirno_core.agent.tools.instance_features.Nodes", lambda **kwargs: nodes)
    result = await NodeTool().execute("execute", node_id="gpu", command="write-data")
    assert is_tool_error_result(result)
    assert json.loads(result)["state"] == "execution_unknown"
    assert json.loads(result)["resubmit_safe"] is False
    nodes._run_result.assert_awaited_once()


async def test_direct_execute_recovers_a_completed_nonzero_command_without_replaying_it(tmp_path, monkeypatch):
    nodes = Nodes.__new__(Nodes)
    nodes.data = SimpleNamespace(state_dir=tmp_path)
    nodes.node = lambda _: Node(name="GPU", host="server", username="owner", working_directory=str(tmp_path))
    nodes.arguments = lambda _: ["ssh"]
    spawn = nodes._run_result
    counter = tmp_path / "executions"

    async def disconnected_after_receipt(args, *other, **kwargs):
        real = await spawn(["sh", "-c", args[-1]])
        return CommandResult(real.stdout, real.stderr + "Connection to frps closed by remote host", 255)

    nodes._run_result = AsyncMock(side_effect=disconnected_after_receipt)
    monkeypatch.setattr("cirno_core.agent.tools.instance_features.Nodes", lambda **kwargs: nodes)
    result = await NodeTool().execute("execute", node_id="gpu", command=f"printf run >>'{counter}'; printf 'verified output'; exit 2")
    details = json.loads(result)
    assert not is_tool_error_result(result) and details["exit_code"] == 2
    assert details["connection_warning"] and details["stdout"] == "verified output"
    assert counter.read_text() == "run"
    nodes._run_result.assert_awaited_once()


async def test_read_only_status_reconnects_and_recovers_the_original_job(tmp_path):
    nodes = Nodes(InstanceData(tmp_path))
    job = nodes.data.save("node_jobs", {"node_id": "gpu", "state": "running"})
    nodes.execute = AsyncMock(side_effect=[SSHProcessError(CommandResult("", "Connection to frps closed by remote host", 255)), "EXIT:0\nfinished"])
    result = await nodes.inspect_job(job["id"])
    assert result["state"] == "completed" and result["output"] == "finished"
    assert nodes.execute.await_count == 2
    first, second = nodes.execute.await_args_list
    assert first.args == second.args
    assert "nohup" not in first.args[1] and "kill -TERM" not in first.args[1]
    assert 0 < second.kwargs["timeout"] < first.kwargs["timeout"]


@pytest.mark.parametrize("diagnostic", ["Permission denied (publickey).", "Host key verification failed.", "REMOTE HOST IDENTIFICATION HAS CHANGED!", "Permission denied (password).\nConnection to frps closed by remote host."])
async def test_authentication_and_host_key_failures_are_not_retried(diagnostic):
    nodes = Nodes.__new__(Nodes)
    nodes.execute = AsyncMock(side_effect=SSHProcessError(CommandResult("", diagnostic, 255)))
    with pytest.raises(SSHProcessError):
        await nodes.read_status("gpu", "status")
    nodes.execute.assert_awaited_once()


async def test_stop_is_not_replayed_after_a_connection_failure(tmp_path):
    nodes = Nodes(InstanceData(tmp_path))
    job = nodes.data.save("node_jobs", {"node_id": "gpu", "state": "running"})
    nodes.execute = AsyncMock(side_effect=SSHProcessError(CommandResult("", "Connection to frps closed by remote host", 255)))
    with pytest.raises(SSHProcessError):
        await nodes.inspect_job(job["id"], stop=True)
    nodes.execute.assert_awaited_once()


async def test_status_reconnect_obeys_one_total_deadline():
    nodes = Nodes.__new__(Nodes)
    calls = 0

    async def wait(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise SSHProcessError(CommandResult("", "Connection reset by peer", 255))
        await asyncio.sleep(10)

    nodes.execute = wait
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        await nodes.read_status("gpu", "status", timeout=.8)
    assert calls == 2 and time.monotonic() - started < 1.5


async def test_cancellation_during_reconnect_delay_prevents_another_connection():
    nodes = Nodes.__new__(Nodes)
    entered = asyncio.Event()

    async def fail(*args, **kwargs):
        entered.set()
        raise SSHProcessError(CommandResult("", "Connection reset by peer", 255))

    nodes.execute = AsyncMock(side_effect=fail)
    task = asyncio.create_task(nodes.read_status("gpu", "status"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    nodes.execute.assert_awaited_once()


@pytest.mark.skipif(not shutil.which("ssh"), reason="Requires the OpenSSH client")
async def test_effective_ssh_options_include_keepalive_and_handshake_retries_without_connecting(tmp_path):
    nodes = Nodes.__new__(Nodes)
    nodes.data = SimpleNamespace(state_dir=tmp_path)
    args = nodes.arguments(Node(name="Fixture", host="fixture.invalid", username="owner"))
    # -G only expands configuration; -F excludes the owner's own SSH config.
    output = await nodes._run([args[0], "-G", "-F", "/dev/null", *args[1:], "owner@fixture.invalid"])
    for option in ["serveraliveinterval 15", "serveralivecountmax 3", "connectionattempts 3", "stricthostkeychecking true"]:
        assert option in output


async def test_lost_launch_ack_and_a_failed_first_probe_recover_without_resubmission(tmp_path):
    nodes = Nodes(InstanceData(tmp_path))
    nodes.node = lambda _: Node(name="GPU", host="server", username="owner")
    disconnected = SSHProcessError(CommandResult("", "Connection to frps closed by remote host", 255))
    nodes.execute = AsyncMock(side_effect=[disconnected, disconnected, "EXIT:0\nexperiment completed"])
    job = await nodes.start_job("gpu", "train")
    assert job["state"] == "completed" and job["output"] == "experiment completed"
    assert len(nodes.data.list("node_jobs")) == 1
    calls = nodes.execute.await_args_list
    assert len(calls) == 3 and "nohup setsid" in calls[0].args[1]
    assert all("nohup setsid" not in call.args[1] for call in calls[1:])
    assert calls[1].args[1] == calls[2].args[1] and job["id"] in calls[1].args[1]


async def test_timeout_preserves_partial_output_and_marks_the_command_unconfirmed(tmp_path, monkeypatch):
    import sys
    nodes = Nodes.__new__(Nodes)
    nodes.data = SimpleNamespace(state_dir=tmp_path)
    nodes.node = lambda _: Node(name="GPU", host="server", username="owner")
    nodes.arguments = lambda _: ["ssh"]
    spawn = nodes._run_result

    async def timed_out(args, *other, **kwargs):
        return await spawn([sys.executable, "-u", "-c", "import sys,time; print('program started'); print('initial diagnostic', file=sys.stderr); time.sleep(10)"], timeout=.2)

    nodes._run_result = AsyncMock(side_effect=timed_out)
    monkeypatch.setattr("cirno_core.agent.tools.instance_features.Nodes", lambda **kwargs: nodes)
    result = await NodeTool().execute("execute", node_id="gpu", command="run-once")
    details = json.loads(result)
    assert is_tool_error_result(result) and details["state"] == "execution_unknown"
    assert details["resubmit_safe"] is False and "timed out" in details["error"]
    assert details["stdout"] == "program started\n" and details["stderr"] == "initial diagnostic\n"
    nodes._run_result.assert_awaited_once()


async def test_receipt_received_before_ssh_timeout_still_confirms_the_command(tmp_path, monkeypatch):
    nodes = Nodes.__new__(Nodes)
    nodes.data = SimpleNamespace(state_dir=tmp_path)
    nodes.node = lambda _: Node(name="GPU", host="server", username="owner", working_directory=str(tmp_path))
    nodes.arguments = lambda _: ["ssh"]
    spawn = nodes._run_result
    counter = tmp_path / "executions"

    async def timed_out_after_receipt(args, *other, **kwargs):
        # Allow shell startup under parallel test load; the trailing sleep still times out.
        return await spawn(["sh", "-c", args[-1] + "; sleep 10"], timeout=2)

    nodes._run_result = AsyncMock(side_effect=timed_out_after_receipt)
    monkeypatch.setattr("cirno_core.agent.tools.instance_features.Nodes", lambda **kwargs: nodes)
    result = await NodeTool().execute("execute", node_id="gpu", command=f"printf run >>'{counter}'; printf done")
    details = json.loads(result)
    assert not is_tool_error_result(result) and details["exit_code"] == 0
    assert "timed out" in details["connection_warning"] and details["stdout"] == "done"
    assert counter.read_text() == "run"
    nodes._run_result.assert_awaited_once()


async def test_successful_status_payload_is_not_polluted_by_ssh_stderr(tmp_path):
    nodes = Nodes.__new__(Nodes)
    nodes.data = InstanceData(tmp_path)
    nodes.node = lambda _: Node(name="GPU", host="server", username="owner")
    nodes.arguments = lambda _: ["ssh"]
    nodes._run_result = AsyncMock(return_value=CommandResult("EXIT:0\n", "SSH forwarding diagnostic\n", 0))
    job = nodes.data.save("node_jobs", {"node_id": "gpu", "state": "running"})
    observed = await nodes.inspect_job(job["id"])
    assert observed["state"] == "completed" and observed["output"] == ""
    nodes._run_result.assert_awaited_once()
