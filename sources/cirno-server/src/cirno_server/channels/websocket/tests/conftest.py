"""Shared isolation for WebSocket tests that persist runtime state."""

import asyncio
from pathlib import Path

import pytest
from cirno_server.channels.websocket.runtime import WebSocketChannel


@pytest.fixture(autouse=True)
def isolate_websocket_runtime_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep transcripts and other runtime files out of the active user data directory."""
    monkeypatch.setattr("cirno_core.config.paths.get_data_dir", lambda: tmp_path)


@pytest.fixture(autouse=True)
def _select_web_test_home(tmp_path, monkeypatch):
    monkeypatch.setattr("cirno_core.config.home._instance_path", tmp_path)


@pytest.fixture
async def start_listener():
    """Start test-owned ephemeral listeners and join them even if setup/assertions fail."""
    listeners = []

    async def start(channel: WebSocketChannel):
        assert channel.config.port == 0
        task = asyncio.create_task(channel.start())
        listeners.append((channel, task))
        async with asyncio.timeout(5):
            while True:
                if task.done():
                    await task
                    raise AssertionError("listener stopped before becoming ready")
                server = channel._server
                if server is not None and server.sockets and server.is_serving():
                    return server.sockets[0].getsockname()[1], task
                await asyncio.sleep(0.01)

    try:
        yield start
    finally:
        for channel, task in reversed(listeners):
            try:
                await asyncio.wait_for(channel.stop(), timeout=5)
                await asyncio.wait_for(asyncio.shield(task), timeout=5)
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
