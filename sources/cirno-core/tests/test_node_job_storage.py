"""Remote job journals remain responsive and settle before cancellation returns."""

import asyncio
import os
import shlex
import shutil
import sys
from threading import Event
from unittest.mock import AsyncMock

import pytest

from cirno_core.nodes.service import Node, Nodes
from cirno_core.storage.instance import InstanceData


def node_service(tmp_path):
    nodes = Nodes(InstanceData(tmp_path))
    nodes.node = lambda _: Node(name="GPU", host="server", username="researcher")
    nodes.execute = AsyncMock(return_value="1234")
    return nodes


@pytest.mark.parametrize("operation", ["start", "inspect"])
async def test_job_journal_io_does_not_block_the_gateway(tmp_path, monkeypatch, operation):
    nodes = node_service(tmp_path)
    job = nodes.data.save("node_jobs", {"node_id": "gpu", "state": "running"})
    nodes.execute.return_value = "1234" if operation == "start" else "EXIT:0\nfinished"
    loop = asyncio.get_running_loop()

    for name in ("save", "get"):
        original = getattr(nodes.data, name)

        def stalled(*args, _operation=original, **kwargs):
            responsive = Event()
            loop.call_soon_threadsafe(responsive.set)
            assert responsive.wait(1), "A job journal operation blocked the gateway"
            return _operation(*args, **kwargs)

        monkeypatch.setattr(nodes.data, name, stalled)
    result = await nodes.start_job("gpu", "train") if operation == "start" else await nodes.inspect_job(job["id"])
    assert result["state"] == ("running" if operation == "start" else "completed")


async def test_cancelled_submission_settles_its_journal_before_returning(tmp_path, monkeypatch):
    nodes = node_service(tmp_path)
    entered, release = Event(), Event()
    original = nodes.data.save

    def delayed(kind, record):
        if record["state"] == "submitting":
            entered.set()
            assert release.wait(3)
        return original(kind, record)

    monkeypatch.setattr(nodes.data, "save", delayed)
    task = asyncio.create_task(nodes.start_job("gpu", "train"))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    nodes.execute.assert_not_called()
    records = nodes.data.list("node_jobs")
    assert len(records) == 1 and records[0]["state"] == "submission_unknown"


async def test_journal_admission_failure_never_submits_or_creates_an_unknown_remote_job(tmp_path, monkeypatch):
    nodes = node_service(tmp_path)
    def unavailable(*args, **kwargs):
        raise OSError("Job storage unavailable")
    monkeypatch.setattr(nodes.data, "save", unavailable)
    with pytest.raises(OSError, match="Job storage unavailable"):
        await nodes.start_job("gpu", "train")
    nodes.execute.assert_not_called()
    assert nodes.data.list("node_jobs") == []


@pytest.mark.skipif(os.name != "posix" or not shutil.which("ps"), reason="Requires POSIX process inspection")
@pytest.mark.parametrize("stopped", [False, True])
@pytest.mark.parametrize("matching", [False, True])
async def test_remote_job_status_checks_process_identity(tmp_path, stopped, matching, monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")
    nodes = node_service(tmp_path)
    job = nodes.data.save("node_jobs", {"node_id": "gpu", "state": "running"})
    home = tmp_path / "remote-home"
    directory = home / ".cirno" / "jobs" / job["id"]
    directory.mkdir(parents=True)
    process = (
        await asyncio.create_subprocess_exec(sys.executable, "-c", "import time; time.sleep(60)", "x" * 512, job["id"])
        if matching else None
    )
    # An unrelated live PID must not stand in for the job's original shell.
    (directory / "pid").write_text(str(process.pid if process else os.getpid()))
    (directory / "output.log").write_text("previous output")
    if stopped:
        (directory / "stop-requested").touch()

    async def remote(_node, script, **kwargs):
        return await nodes._run(["sh", "-c", f"HOME={shlex.quote(str(home))}; {script}"])

    nodes.execute = remote
    try:
        result = await nodes.inspect_job(job["id"])
        assert result["state"] == ("running" if matching else "stopped" if stopped else "unknown")
        assert result["output"] == "previous output"
    finally:
        if process:
            process.terminate()
            await process.wait()


@pytest.mark.skipif(os.name != "posix", reason="Requires POSIX process inspection")
async def test_exit_published_during_process_inspection_is_reported_as_completed(tmp_path, monkeypatch):
    nodes = node_service(tmp_path)
    job = nodes.data.save("node_jobs", {"node_id": "gpu", "state": "running"})
    home = tmp_path / "remote-home"
    directory = home / ".cirno" / "jobs" / job["id"]
    directory.mkdir(parents=True)
    binary = tmp_path / "bin"
    binary.mkdir()
    probe = binary / "ps"
    # The job finishes after inspection begins, before its PID probe returns.
    probe.write_text(f"#!/bin/sh\nprintf 0 > {shlex.quote(str(directory / 'exit'))}\nexit 1\n")
    probe.chmod(0o755)
    monkeypatch.setenv("PATH", str(binary) + os.pathsep + os.environ["PATH"])
    process = await asyncio.create_subprocess_exec(sys.executable, "-c", "import time; time.sleep(60)")
    (directory / "pid").write_text(str(process.pid))
    (directory / "output.log").write_text("finished output")

    async def remote(_node, script, **kwargs):
        return await nodes._run(["sh", "-c", f"HOME={shlex.quote(str(home))}; {script}"])

    nodes.execute = remote
    try:
        result = await nodes.inspect_job(job["id"])
        assert result["state"] == "completed" and result["output"] == "finished output"
    finally:
        process.terminate()
        await process.wait()
