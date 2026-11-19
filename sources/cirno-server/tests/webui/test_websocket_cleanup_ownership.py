"""Repeated cancellation cannot detach accepted connection cleanup from its owner."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cirno_server.channels.websocket.runtime import WebSocketChannel
from cirno_server.channels.websocket.writers import ConnectionWriters


class Connection:
    def __init__(self):
        self.started = asyncio.Event()
        self.cancelling = asyncio.Event()
        self.release = asyncio.Event()
        self.finished = asyncio.Event()

    async def send(self, _raw):
        self.started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.cancelling.set()
            await self.release.wait()
            self.finished.set()
            raise


@pytest.mark.parametrize('stage', ['writer', 'commands'])
async def test_cleanup_drains_through_repeated_cancellation(stage):
    connection = Connection()
    command_started, command_release, command_finished = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def cleanup_commands(_connection):
        command_started.set()
        if stage == 'commands':
            await command_release.wait()
        command_finished.set()

    channel = WebSocketChannel.__new__(WebSocketChannel)
    channel.logger = Mock()
    channel._uploads = SimpleNamespace(revoke=Mock())
    channel._commands = SimpleNamespace(cleanup_connection=AsyncMock(side_effect=cleanup_commands))
    channel.gateway = SimpleNamespace(endpoint=SimpleNamespace(discard_connection=Mock()))
    channel._subs, channel._conn_chats, channel._conn_default = {}, {}, {}
    channel.writers = ConnectionWriters(channel._cleanup_connection, channel.logger)
    channel._attach(connection, 'cleanup-chat')
    channel._conn_default[connection] = 'cleanup-chat'
    if stage == 'writer':
        await channel.writers.send(connection, 'first')
        await asyncio.wait_for(connection.started.wait(), 1)
        await channel.writers.send(connection, 'queued')
    task = asyncio.create_task(channel._cleanup_connection(connection))
    try:
        await asyncio.wait_for((connection.cancelling if stage == 'writer' else command_started).wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), 'Cleanup stopped owning its pending work'
    finally:
        connection.release.set()
        command_release.set()
        await asyncio.gather(task, return_exceptions=True)
        state = channel.writers.states.get(connection)
        if state and state.writer:
            await asyncio.gather(state.writer, return_exceptions=True)
    assert task.cancelled()
    assert command_finished.is_set()
    if stage == 'writer':
        assert connection.finished.is_set()
    assert not channel.writers.has_pending
    assert not channel.writers.connections
    assert not channel._subs and not channel._conn_chats and not channel._conn_default
    channel.gateway.endpoint.discard_connection.assert_called_once_with(connection)
