"""Creation failures remain correlated while other conversations share a socket."""

import json
from unittest.mock import AsyncMock

import pytest

from cirno_core.bus.queue import MessageBus
from cirno_core.session.manager import SessionManager
from cirno_server.channels.websocket.config import WebSocketConfig
from cirno_server.channels.websocket.runtime import WebSocketChannel
from cirno_server.webui.services import build_server_services


@pytest.fixture
async def channel(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sessions = SessionManager(workspace, sessions_root=tmp_path / "sessions")
    bus = MessageBus()
    config = WebSocketConfig(allow_from=["*"], websocket_requires_token=False)
    gateway = build_server_services(
        config=config, bus=bus, session_manager=sessions, static_dist_path=None,
        workspace_path=workspace, default_restrict_to_workspace=True,
        config_path=tmp_path / "config.json", runtime_model_name=None,
    )
    owner = WebSocketChannel(config, bus, gateway=gateway)
    connection = AsyncMock()
    connection.remote_address = ("127.0.0.1", 40001)
    try:
        yield owner, connection
    finally:
        await owner.stop()
        await sessions.state.aclose()


@pytest.mark.parametrize("command", [
    {"type": "new_chat", "ptc_mode": 1},
    {"type": "new_temporary_chat", "ptc_mode": 1},
    {"type": "fork_chat", "source_chat_id": "bad/id", "before_user_index": 0},
    {"type": "new_chat", "workspace_scope": {"project_path": "/cirno-fixture-missing-workspace", "access_mode": "restricted"}},
])
async def test_rejected_creation_echoes_the_exact_request_id(channel, command):
    owner, connection = channel
    await owner._dispatch_envelope(connection, "fixture", {**command, "request_id": "this-creation"})
    response = json.loads(connection.send.await_args.args[0])
    assert response["event"] == "error" and response["request_id"] == "this-creation"
    assert not owner._subs
