"""The server terminal is a real PTY, with replay and deterministic cleanup."""

import asyncio
import os

import pytest
from cirno_server.webui.terminals import Terminals


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="POSIX PTY")
async def test_local_terminal_runs_interactive_commands_replays_and_closes(tmp_path):
    manager = Terminals()
    try:
        opened = await manager.create(cwd=str(tmp_path), cols=92, rows=28)
        identifier = opened["id"]
        await manager.write(identifier, "printf 'CIRNO_PTY_OK'; pwd; stty size\n")
        async with asyncio.timeout(5):
            while True:
                result = manager.read(identifier)
                if (
                    "CIRNO_PTY_OK" in result["data"]
                    and str(tmp_path) in result["data"]
                    and "28 92" in result["data"]
                ):
                    break
                await asyncio.sleep(0.02)
        assert manager.read(identifier, result["cursor"])["data"] == ""
        session = manager.get(identifier)
        session.output = "tail"
        session.offset = 100
        assert manager.read(identifier, 1)["reset"] is True
        await manager.close(identifier)
        assert session.process.returncode is not None
        with pytest.raises(KeyError):
            manager.read(identifier)
        assert await manager.close(identifier) == {"ok": True}
    finally:
        await manager.close_all()


@pytest.mark.asyncio
async def test_terminal_capacity_does_not_spawn_more_processes(tmp_path):
    manager = Terminals()
    manager.sessions = dict.fromkeys(map(str, range(12)))
    with pytest.raises(ValueError, match="12 terminal"):
        await manager.create(cwd=str(tmp_path))


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="POSIX PTY")
async def test_idle_terminal_does_not_occupy_the_shared_io_executor(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=1))
    manager = Terminals()
    try:
        await manager.create(cwd=str(tmp_path))
        await asyncio.sleep(0.05)
        assert (
            await asyncio.wait_for(asyncio.to_thread(lambda: "available"), timeout=1) == "available"
        )
    finally:
        await manager.close_all()


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="POSIX PTY")
async def test_closing_an_exited_terminal_does_not_signal_a_retained_pid(tmp_path, monkeypatch):
    manager = Terminals()
    try:
        opened = await manager.create(cwd=str(tmp_path))
        identifier = opened["id"]
        session = manager.get(identifier)
        await manager.write(identifier, "exit\n")
        await asyncio.wait_for(session.process.wait(), 5)

        def forbidden(*args):
            raise AssertionError("An exited terminal's PID must not be signalled later")

        monkeypatch.setattr(os, "killpg", forbidden)
        await manager.close(identifier)
    finally:
        await manager.close_all()


def test_terminal_reports_exit_only_after_pty_output_is_drained():
    from types import SimpleNamespace

    from cirno_server.webui.terminals import TerminalSession

    manager = Terminals()
    session = TerminalSession(SimpleNamespace(returncode=0), -1, "Local", output="last output")
    manager.sessions["done"] = session
    assert manager.read("done")["exit_code"] is None
    session.eof = True
    result = manager.read("done")
    assert result["data"] == "last output"
    assert result["exit_code"] == 0


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="POSIX PTY")
async def test_browser_tab_reconnect_reuses_its_live_shell(tmp_path):
    from uuid import uuid4

    manager = Terminals()
    key = str(uuid4())
    try:
        first, second = await asyncio.gather(
            manager.create(cwd=str(tmp_path), key=key),
            manager.create(cwd=str(tmp_path), key=key),
        )
        assert first["id"] == second["id"] == key
        assert len(manager.sessions) == 1
        original = manager.get(key)
        assert (await manager.create(cwd=str(tmp_path), key=key))["id"] == key
        assert manager.get(key) is original
        await manager.close(key)
        await manager.create(cwd=str(tmp_path), key=key)
        assert manager.get(key) is not original
    finally:
        await manager.close_all()


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="POSIX PTY")
async def test_closing_a_tab_during_shell_startup_does_not_leave_a_process(tmp_path, monkeypatch):
    from uuid import uuid4

    manager = Terminals()
    entered, release = asyncio.Event(), asyncio.Event()
    original = manager._create

    async def delayed(**kwargs):
        entered.set()
        await release.wait()
        return await original(**kwargs)

    monkeypatch.setattr(manager, "_create", delayed)
    key = str(uuid4())
    starting = asyncio.create_task(manager.create(cwd=str(tmp_path), key=key))
    await entered.wait()
    closing = asyncio.create_task(manager.close(key))
    release.set()
    try:
        await starting
        await closing
        assert key not in manager.sessions
    finally:
        await manager.close_all()
