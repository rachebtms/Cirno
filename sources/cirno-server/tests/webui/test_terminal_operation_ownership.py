"""Terminal admission/cleanup ownership using only fake processes and descriptors."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from cirno_server.webui.terminals import Terminals


async def test_cancelled_admission_settles_and_retains_its_retry_identity(monkeypatch):
    manager = Terminals()
    entered, release = asyncio.Event(), asyncio.Event()
    key = str(uuid4())

    async def create(**values):
        entered.set()
        await release.wait()
        manager.sessions[values['identifier']] = SimpleNamespace(label='Fake')
        return {'id': values['identifier'], 'label': 'Fake'}

    monkeypatch.setattr(manager, '_create', create)
    task = asyncio.create_task(manager.create(cwd='/fake', key=key))
    try:
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (await manager.create(cwd='/fake', key=key))['id'] == key
        assert len(manager.sessions) == 1
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_shutdown_waits_for_inflight_admission_before_closing(monkeypatch):
    manager = Terminals()
    entered, release = asyncio.Event(), asyncio.Event()
    key = str(uuid4())
    closed = []

    async def create(**values):
        entered.set()
        await release.wait()
        manager.sessions[values['identifier']] = SimpleNamespace(label='Fake')
        return {'id': values['identifier']}

    async def close(identifier):
        closed.append(identifier)
        manager.sessions.pop(identifier, None)
        return {'ok': True}

    monkeypatch.setattr(manager, '_create', create)
    monkeypatch.setattr(manager, '_close', close)
    starting = asyncio.create_task(manager.create(cwd='/fake', key=key))
    closing = None
    try:
        await entered.wait()
        closing = asyncio.create_task(manager.close_all())
        await asyncio.sleep(0)
        assert not closing.done()
        release.set()
        await asyncio.gather(starting, closing)
        assert closed == [key]
        assert manager.sessions == {}
    finally:
        release.set()
        for task in [starting, closing]:
            if task is not None:
                task.cancel()
        await asyncio.gather(*[t for t in [starting, closing] if t is not None], return_exceptions=True)


async def test_queued_admission_cannot_escape_a_shutdown_that_started_while_it_waited(monkeypatch):
    manager = Terminals()
    entered, release = asyncio.Event(), asyncio.Event()
    created = []
    first_key, queued_key = str(uuid4()), str(uuid4())

    async def create(**values):
        created.append(values['identifier'])
        entered.set()
        await release.wait()
        manager.sessions[values['identifier']] = SimpleNamespace(label='Fake')
        return {'id': values['identifier']}

    async def close(identifier):
        manager.sessions.pop(identifier, None)
        return {'ok': True}

    monkeypatch.setattr(manager, '_create', create)
    monkeypatch.setattr(manager, '_close', close)
    first = asyncio.create_task(manager.create(cwd='/fake', key=first_key))
    queued = closing = None
    try:
        await entered.wait()
        queued = asyncio.create_task(manager.create(cwd='/fake', key=queued_key))
        await asyncio.sleep(0)
        closing = asyncio.create_task(manager.close_all())
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(first, closing)
        with pytest.raises(ValueError, match='shutting down'):
            await queued
        assert created == [first_key]
        assert manager.sessions == {}
        # A later server start can reuse the manager; a fresh request is allowed.
        assert (await manager.create(cwd='/fake', key=queued_key))['id'] == queued_key
    finally:
        release.set()
        tasks = [t for t in [first, queued, closing] if t is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_cancelled_close_keeps_admission_locked_until_cleanup_settles(monkeypatch):
    manager = Terminals()
    entered, release = asyncio.Event(), asyncio.Event()
    key = str(uuid4())
    creates = []

    async def close(identifier):
        entered.set()
        await release.wait()
        return {'ok': True}

    async def create(**values):
        creates.append(values['identifier'])
        return {'id': values['identifier']}

    monkeypatch.setattr(manager, '_close', close)
    monkeypatch.setattr(manager, '_create', create)
    closing = asyncio.create_task(manager.close(key))
    starting = None
    try:
        await entered.wait()
        closing.cancel()
        await asyncio.sleep(0)
        assert not closing.done()
        starting = asyncio.create_task(manager.create(cwd='/fake', key=key))
        await asyncio.sleep(0)
        assert creates == []
        closing.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await closing
        await starting
        assert creates == [key]
    finally:
        release.set()
        tasks = [t for t in [closing, starting] if t is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.parametrize("failure_stage", ["blocking", "reader", "resize"])
async def test_post_spawn_setup_failure_closes_fake_process_and_both_descriptors(tmp_path, monkeypatch, failure_stage):
    import pty

    import cirno_server.webui.terminals as module

    manager = Terminals()
    process = SimpleNamespace(returncode=None, pid=987654, wait=AsyncMock())
    descriptors, signals = [], []
    def fail(*args):
        raise OSError('Cannot configure PTY')
    monkeypatch.setattr(module, 'os', SimpleNamespace(
        name='posix', environ={}, set_blocking=fail if failure_stage == 'blocking' else lambda *_: None, close=descriptors.append,
        killpg=lambda *args: signals.append(args),
    ))
    monkeypatch.setattr(pty, 'openpty', lambda: (987001, 987002))
    monkeypatch.setattr(module.asyncio, 'create_subprocess_exec', AsyncMock(return_value=process))
    loop = asyncio.get_running_loop()
    readers = {}
    monkeypatch.setattr(loop, 'add_reader', fail if failure_stage == 'reader' else lambda fd, callback: readers.update({fd: callback}))
    monkeypatch.setattr(loop, 'remove_reader', lambda fd: readers.pop(fd, None))
    monkeypatch.setattr(loop, 'remove_writer', lambda _: None)
    monkeypatch.setattr(manager, 'resize', fail if failure_stage == 'resize' else lambda *_: {'ok': True})
    with pytest.raises(OSError, match='Cannot configure PTY'):
        await manager.create(cwd=str(tmp_path))
    assert sorted(descriptors) == [987001, 987002]
    process.wait.assert_awaited_once()
    assert readers == {}
    assert len(signals) == 1
    assert manager.sessions == {}


async def test_new_admission_is_rejected_while_shutdown_is_draining(monkeypatch):
    manager = Terminals()
    manager.sessions['existing'] = SimpleNamespace(label='Fake')
    entered, release = asyncio.Event(), asyncio.Event()
    creates = []
    async def close(identifier):
        entered.set()
        await release.wait()
        manager.sessions.pop(identifier, None)
    async def create(**values):
        creates.append(values['identifier'])
        return {'id': values['identifier']}
    monkeypatch.setattr(manager, '_close', close)
    monkeypatch.setattr(manager, '_create', create)
    closing = asyncio.create_task(manager.close_all())
    starting = None
    try:
        await entered.wait()
        starting = asyncio.create_task(manager.create(cwd='/fake'))
        await asyncio.sleep(0)
        assert starting.done()
        with pytest.raises(ValueError, match='shutting down'):
            await starting
        assert creates == []
        closing.cancel()
        await asyncio.sleep(0)
        assert not closing.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await closing
        assert manager.sessions == {}
    finally:
        release.set()
        tasks = [t for t in [closing, starting] if t is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
