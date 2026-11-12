"""A lost SSH acknowledgement must never launch an experiment twice."""

import asyncio
import os
import shlex
import shutil
import sys
from unittest.mock import AsyncMock

import pytest

from cirno_core.nodes.service import Node, Nodes
from cirno_core.storage.instance import InstanceData


def nodes_for(tmp_path):
    nodes = Nodes(InstanceData(tmp_path / "instance"))
    nodes.node = lambda _: Node(name="GPU", host="server", username="owner", working_directory=str(tmp_path))
    return nodes


@pytest.mark.parametrize("reply,state", [("RUNNING\ntraining", "running"), ("EXIT:0\nfinished", "completed"), ("EXIT:2\nfailed training", "failed"), ("UNKNOWN\n", "submission_unknown")])
async def test_lost_ack_is_reconciled_using_the_existing_id(tmp_path, reply, state):
    nodes = nodes_for(tmp_path)
    nodes.execute = AsyncMock(side_effect=[RuntimeError("Connection to frps closed by remote host"), reply])
    job = await nodes.start_job("gpu", "train")
    assert job["state"] == state
    assert job["resubmit_safe"] is False
    assert "frps" in job["submission_error"]
    assert len(nodes.data.list("node_jobs")) == 1
    assert nodes.execute.await_count == 2
    launch, probe = [call.args[1] for call in nodes.execute.await_args_list]
    assert "nohup setsid" in launch and "nohup setsid" not in probe
    assert job["id"] in probe
    assert nodes.data.get("node_jobs", job["id"])["state"] == state
    if state == "submission_unknown":
        assert job["next_action"] == {"tool": "nodes.status", "job_id": job["id"]}


async def test_repeated_transport_failure_returns_a_recoverable_job_not_a_relaunch(tmp_path):
    nodes = nodes_for(tmp_path)
    nodes.execute = AsyncMock(side_effect=RuntimeError("SSH tunnel down"))
    job = await nodes.start_job("gpu", "train")
    assert job["state"] == "submission_unknown" and job["verification_error"] == "SSH tunnel down"
    nodes.execute.side_effect = None
    nodes.execute.return_value = "EXIT:0\nexperiment finished while disconnected"
    recovered = await nodes.inspect_job(job["id"])
    assert recovered["state"] == "completed"
    assert "verification_error" not in recovered and "next_action" not in recovered
    assert len(nodes.data.list("node_jobs")) == 1


async def test_cancelling_a_submission_does_not_probe_or_retry(tmp_path):
    nodes = nodes_for(tmp_path)
    entered = asyncio.Event()

    async def disconnected(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    nodes.execute = AsyncMock(side_effect=disconnected)
    turn = asyncio.create_task(nodes.start_job("gpu", "train"))
    await entered.wait()
    turn.cancel()
    with pytest.raises(asyncio.CancelledError):
        await turn
    assert nodes.execute.await_count == 1
    assert nodes.data.list("node_jobs")[0]["state"] == "submission_unknown"


@pytest.mark.skipif(os.name != "posix", reason="Detached SSH jobs require POSIX")
async def test_real_detached_job_survives_lost_ack_and_is_not_reexecuted(tmp_path, monkeypatch):
    nodes = nodes_for(tmp_path)
    home = tmp_path / "remote-home"
    home.mkdir()
    if not shutil.which("setsid"):
        # Portable stand-in for Linux util-linux setsid; no downloaded tools.
        binary = tmp_path / "bin"
        binary.mkdir()
        setsid = binary / "setsid"
        setsid.write_text(f"#!{sys.executable}\nimport os,sys\nos.setsid()\nos.execvp(sys.argv[1],sys.argv[1:])\n")
        setsid.chmod(0o755)
        monkeypatch.setenv("PATH", str(binary) + os.pathsep + os.environ["PATH"])
    counter, done = tmp_path / "executions", tmp_path / "finish"
    command = f"printf run >>{shlex.quote(str(counter))}; while [ ! -f {shlex.quote(str(done))} ]; do sleep 0.02; done; printf finished"
    launches = 0

    async def remote(_node, script, **kwargs):
        nonlocal launches
        result = await nodes._run(["sh", "-c", script.replace("$HOME", str(home))])
        if "nohup setsid" in script:
            launches += 1
            async with asyncio.timeout(5):
                while not counter.exists():
                    await asyncio.sleep(.01)
            raise RuntimeError("Connection to frps closed by remote host")
        return result

    nodes.execute = remote
    try:
        job = await nodes.start_job("gpu", command)
        assert job["state"] == "running"
        done.touch()
        async with asyncio.timeout(5):
            while (await nodes.inspect_job(job["id"]))["state"] == "running":
                await asyncio.sleep(.01)
        final = await nodes.inspect_job(job["id"])
        assert final["state"] == "completed" and "finished" in final["output"]
        assert launches == 1 and counter.read_text() == "run"
    finally:
        done.touch()
