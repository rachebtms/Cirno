"""The server terminal is a real PTY, with replay and deterministic cleanup."""

import asyncio
import os

import pytest
from cirno_server.webui.terminals import Terminals


async def test_concurrent_terminal_inputs_keep_order_without_blocking_other_terminals(monkeypatch):
    from types import SimpleNamespace

    from cirno_server.webui.terminals import TerminalSession

    manager = Terminals()
    manager.sessions = {
        "one": TerminalSession(SimpleNamespace(returncode=None), 987_001, "One"),
        "two": TerminalSession(SimpleNamespace(returncode=None), 987_002, "Two"),
    }
    loop = asyncio.get_running_loop()
    waiting = asyncio.Event()
    callbacks = {}
    writes = []
    released = False

    def write(fd, data):
        if fd == 987_001 and bytes(data) == b"first" and not released:
            raise BlockingIOError()
        writes.append((fd, bytes(data)))
        return len(data)

    def add_writer(fd, callback):
        callbacks[fd] = callback
        waiting.set()

    monkeypatch.setattr("cirno_server.webui.terminals.os.write", write)
    monkeypatch.setattr(loop, "add_writer", add_writer)
    monkeypatch.setattr(loop, "remove_writer", lambda fd: callbacks.pop(fd, None))
    first = asyncio.create_task(manager.write("one", "first"))
    second = None
    try:
        async with asyncio.timeout(2):
            await waiting.wait()
            second = asyncio.create_task(manager.write("one", "second"))
            await asyncio.sleep(0)
            await manager.write("two", "independent")
            assert writes == [(987_002, b"independent")]
            released = True
            callbacks[987_001]()
            await asyncio.gather(first, second)
        assert writes == [(987_002, b"independent"), (987_001, b"first"), (987_001, b"second")]
        assert callbacks == {}
    finally:
        tasks = [task for task in (first, second) if task is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_closing_terminal_wakes_blocked_input_without_removing_a_reused_fd_writer(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from cirno_server.webui.terminals import TerminalSession

    manager = Terminals()
    manager.sessions["old"] = TerminalSession(SimpleNamespace(returncode=0, wait=AsyncMock()), 987_003, "Old")
    loop = asyncio.get_running_loop()
    waiting = asyncio.Event()
    callbacks = {}

    def write(*_args):
        raise BlockingIOError()

    def add_writer(fd, callback):
        callbacks[fd] = callback
        waiting.set()

    monkeypatch.setattr("cirno_server.webui.terminals.os.write", write)
    monkeypatch.setattr("cirno_server.webui.terminals.os.close", lambda _: None)
    monkeypatch.setattr(loop, "add_writer", add_writer)
    monkeypatch.setattr(loop, "remove_writer", lambda fd: callbacks.pop(fd, None))
    monkeypatch.setattr(loop, "remove_reader", lambda _: None)
    pending = asyncio.create_task(manager.write("old", "input"))
    try:
        async with asyncio.timeout(2):
            await waiting.wait()
            await manager.close("old")
            replacement = lambda: None
            # A new PTY can receive the descriptor just closed by this tab.
            callbacks[987_003] = replacement
            await asyncio.sleep(0)
            assert pending.done()
            with pytest.raises(KeyError, match="closed"):
                await pending
            assert callbacks[987_003] is replacement
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)


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
async def test_server_generated_terminal_id_can_reconnect_without_a_second_shell(tmp_path):
    manager = Terminals()
    try:
        first = await manager.create(cwd=str(tmp_path))
        original = manager.get(first["id"])
        second = await manager.create(cwd=str(tmp_path), key=first["id"])
        assert second == first
        assert len(manager.sessions) == 1
        assert manager.get(second["id"]) is original
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
