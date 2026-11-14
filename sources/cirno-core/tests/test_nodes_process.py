"""No SSH connection is needed to verify OpenSSH subprocess cleanup."""

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cirno_core.nodes.service import Nodes


async def test_cancelled_host_key_fingerprint_reaps_its_process(monkeypatch):
    create = asyncio.create_subprocess_exec
    spawned = asyncio.Event()
    processes = []

    async def spawn(*args, **kwargs):
        process = await create(sys.executable, "-c", "import time; time.sleep(60)", **kwargs)
        processes.append(process)
        spawned.set()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    nodes = Nodes.__new__(Nodes)
    nodes._run = AsyncMock(return_value="public host key fixture")
    task = asyncio.create_task(nodes.scan_host_key("example.invalid"))
    try:
        await asyncio.wait_for(spawned.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(asyncio.shield(task), 3)
        assert processes[0].returncode is not None
        assert processes[0].stdout.at_eof() and processes[0].stderr.at_eof()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        for process in processes:
            if process.returncode is None:
                process.kill()
            await process.communicate()


@pytest.mark.parametrize("fd", [1, 2])
@pytest.mark.parametrize("cancel", [False, True])
async def test_noisy_node_process_is_drained_and_reaped_after_timeout_or_stop(tmp_path, monkeypatch, fd, cancel):
    processes = []
    create = asyncio.create_subprocess_exec
    writing = asyncio.Event()

    async def spawn(*args, **kwargs):
        process = await create(*args, **kwargs)
        processes.append(process)
        stream = process.stdout if fd == 1 else process.stderr
        read = stream.read

        async def observe(size=-1):
            data = await read(size)
            if data:
                writing.set()
            return data
        stream.read = observe
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    nodes = Nodes.__new__(Nodes)
    nodes.data = SimpleNamespace(state_dir=tmp_path)
    command = [sys.executable, "-c", f"import os\nwhile True: os.write({fd}, b'x' * 1048576)"]
    task = asyncio.create_task(nodes._run(command, timeout=10 if cancel else .2))
    try:
        if cancel:
            await asyncio.wait_for(writing.wait(), 3)
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), 3)
        assert task.done()
        assert processes[0].returncode is not None
        assert processes[0].stdout.at_eof() and processes[0].stderr.at_eof()
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        for process in processes:
            if process.returncode is None:
                process.kill()
            await process.communicate()


@pytest.mark.skipif(sys.platform == "win32", reason="OpenSSH process groups use POSIX signals")
@pytest.mark.parametrize("cancel", [False, True], ids=["timeout", "stop"])
async def test_node_cleanup_stops_proxy_children_that_inherit_output_pipes(tmp_path, monkeypatch, cancel):
    import os
    import signal

    processes = []
    create = asyncio.create_subprocess_exec

    async def spawn(*args, **kwargs):
        process = await create(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    nodes = Nodes.__new__(Nodes)
    nodes.data = SimpleNamespace(state_dir=tmp_path)
    child_pid = tmp_path / "proxy.pid"
    code = (
        "import subprocess, sys, time\n"
        "from pathlib import Path\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"Path({str(child_pid)!r}).write_text(str(child.pid))\n"
        "time.sleep(60)\n"
    )
    task = asyncio.create_task(nodes._run([sys.executable, "-c", code], timeout=10 if cancel else .5))
    try:
        async with asyncio.timeout(3):
            while not child_pid.exists():
                await asyncio.sleep(.01)
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), 2)
        assert task.done(), "Cleanup must not remain blocked by an SSH proxy child's open pipes"
        assert processes[0].stdout.at_eof() and processes[0].stderr.at_eof()
    finally:
        # A failing implementation must not leave the test's simulated proxy alive.
        if child_pid.exists():
            try:
                os.kill(int(child_pid.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        for process in processes:
            if process.returncode is None:
                process.kill()
            await process.communicate()
