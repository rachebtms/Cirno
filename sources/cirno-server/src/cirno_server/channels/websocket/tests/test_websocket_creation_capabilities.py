"""Conversation creation reports unavailable persistence without attaching a draft."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from cirno_server.channels.websocket.config import WebSocketConfig
from cirno_server.channels.websocket.runtime import WebSocketChannel
from cirno_server.webui.services import build_server_services


@pytest.mark.parametrize("selection", [{"project_id": "research"}, {"ptc_mode": True}])
async def test_creation_requiring_storage_reports_missing_capability(tmp_path, selection):
    config = WebSocketConfig(enabled=True, allow_from=["*"], host="127.0.0.1")
    services = build_server_services(
        config=config,
        bus=MagicMock(publish_inbound=AsyncMock()),
        session_manager=None,
        static_dist_path=None,
        workspace_path=tmp_path,
        default_restrict_to_workspace=False,
        runtime_model_name=None,
    )
    channel = WebSocketChannel(config, MagicMock(), gateway=services)
    connection = AsyncMock()
    connection.remote_address = ("127.0.0.1", 51001)
    sent = asyncio.Event()
    connection.send.side_effect = lambda _: sent.set()
    try:
        await channel._dispatch_envelope(connection, "client", {"type": "new_chat", **selection})
        await asyncio.wait_for(sent.wait(), timeout=1)
        assert [json.loads(call.args[0]) for call in connection.send.await_args_list] == [
            {"event": "error", "detail": "Conversation storage is unavailable"},
        ]
        assert channel.webui_connection_chats(connection) == ()
    finally:
        await channel.stop()
