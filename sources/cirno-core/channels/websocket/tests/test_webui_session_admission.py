"""WebUI admission binds the generation of the session that executes the turn."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from cirno.agent.loop import AgentLoop
from cirno.bus.events import InboundMessage
from cirno.bus.queue import MessageBus
from cirno.channels.manager import ChannelManager
from cirno.channels.websocket.runtime import WebSocketChannel
from cirno.config.schema import Config
from cirno.providers.base import LLMProvider, LLMResponse
from cirno.runtime.context import public_history_message
from cirno.session.manager import SessionManager
from cirno.session.webui_turns import clear_websocket_turns


class _Provider(LLMProvider):
    def __init__(self) -> None:
        super().__init__(provider_name="test")
        self.calls = 0

    def get_default_model(self) -> str:
        return "test-model"

    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> LLMResponse:
        self.calls += 1
        return LLMResponse(content="hello back", finish_reason="stop")


class _Connection:
    remote_address = None

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))


@dataclass
class _Runtime:
    bus: MessageBus
    sessions: SessionManager
    loop: AgentLoop
    channel: WebSocketChannel
    connection: _Connection
    provider: _Provider

    async def message(self, chat_id: str, text: str = "hello") -> InboundMessage:
        await self.channel._dispatch_envelope(
            self.connection,
            "webui-client",
            {"type": "message", "chat_id": chat_id, "content": text, "webui": True},
        )
        return await self.bus.consume_inbound()

    async def execute(self, message: InboundMessage) -> None:
        await self.loop._enqueue_session_message(message)
        tasks = self.loop._active_tasks[self.loop._effective_session_key(message)]
        await asyncio.gather(*tuple(tasks))


@pytest.fixture
async def runtime(tmp_path: Path) -> AsyncIterator[_Runtime]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = Config.model_validate({"agents": {"defaults": {
        "workspace": str(workspace),
    }}})
    bus = MessageBus()
    sessions = SessionManager(workspace)
    provider = _Provider()
    loop = AgentLoop(
        bus=bus, provider=provider, workspace=workspace,
        session_manager=sessions,
    )
    manager = ChannelManager(
        config, bus, session_manager=sessions, webui_static_dist=False,
        config_path=tmp_path / "config.json",
    )
    channel = manager.channels["websocket"]
    assert isinstance(channel, WebSocketChannel)
    connection = _Connection()
    channel._webui_connections.add(connection)
    try:
        yield _Runtime(bus, sessions, loop, channel, connection, provider)
    finally:
        chat_ids = tuple(channel._subs)
        await channel._cleanup_connection(connection)
        channel.gateway.temporary_chats.close()
        for chat_id in chat_ids:
            clear_websocket_turns(chat_id)
        await loop.aclose()




@pytest.mark.parametrize("operation", ["reset", "delete"])
async def test_replaced_execution_session_rejects_accepted_input(
    runtime: _Runtime, operation: str,
) -> None:
    message = await runtime.message("chat-stale")
    key = runtime.loop._effective_session_key(message)
    if operation == "reset":
        await runtime.sessions.state.reset(key)
    else:
        await runtime.sessions.state.delete(key)

    await runtime.execute(message)

    assert runtime.provider.calls == 0
    remaining = await runtime.sessions.state.read(key)
    assert remaining is None or remaining.messages == []


async def test_failed_transport_admission_removes_new_sessions(
    runtime: _Runtime, monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def reject(message: InboundMessage) -> None:
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(runtime.bus, "publish_inbound", reject)
    with pytest.raises(RuntimeError, match="queue unavailable"):
        await runtime.message("chat-rejected")
    assert await runtime.sessions.state.list_sessions() == []


async def test_temporary_chat_retains_its_own_generation(history, runtime: _Runtime) -> None:
    await runtime.channel._dispatch_envelope(
        runtime.connection, "webui-client", {"type": "new_temporary_chat"},
    )
    chat_id = next(event["chat_id"] for event in runtime.connection.sent
                   if event["event"] == "attached")
    first = await runtime.message(chat_id)
    await runtime.execute(first)
    assert runtime.provider.calls == 1
    assert runtime.loop._effective_session_key(first) == f"websocket:{chat_id}"
    assert await runtime.sessions.state.list_sessions() == []
    assert history.read(f"websocket:{chat_id}") == []

    queued = await runtime.message(chat_id, "discarded input")
    await runtime.channel.gateway.temporary_chats.discard(runtime.connection, chat_id)
    await runtime.execute(queued)

    assert runtime.provider.calls == 1
    assert await runtime.sessions.state.read(first.session_key) is None
    assert await runtime.sessions.state.list_sessions() == []


async def test_concurrent_webui_chats_keep_context_and_stop_separate(runtime: _Runtime) -> None:
    """Stop A while both models await their first token; B must finish normally."""
    started = {chat: asyncio.Event() for chat in ("A", "B")}
    cancelled = {chat: asyncio.Event() for chat in started}
    release = {chat: asyncio.Event() for chat in started}
    inputs: dict[str, list[str]] = {}

    async def delayed_chat(messages: list[dict[str, Any]], **kwargs: Any) -> LLMResponse:
        user_inputs = [str(message["content"]) for message in messages if message["role"] == "user"]
        chat = "A" if "ONLY_A" in user_inputs[-1] else "B"
        inputs[chat] = user_inputs
        started[chat].set()
        try:
            await release[chat].wait()
        except asyncio.CancelledError:
            cancelled[chat].set()
            raise
        return LLMResponse(content=f"ANSWER_{chat}", finish_reason="stop")

    runtime.provider.chat = delayed_chat
    worker = asyncio.create_task(runtime.loop.run())
    try:
        for chat in started:
            await runtime.channel._dispatch_envelope(runtime.connection, "webui-client", {
                "type": "message", "chat_id": f"chat-{chat}", "content": f"ONLY_{chat}", "webui": True,
            })
            await asyncio.wait_for(started[chat].wait(), timeout=2)
        assert all(len(history) == 1 for history in inputs.values())
        assert "ONLY_B" not in inputs["A"][0]
        assert "ONLY_A" not in inputs["B"][0]

        await runtime.channel._dispatch_envelope(runtime.connection, "webui-client", {
            "type": "message", "chat_id": "chat-A", "content": "/stop", "webui": True,
        })
        await asyncio.wait_for(cancelled["A"].wait(), timeout=2)
        stopped = []
        async with asyncio.timeout(2):
            while not any("Stopped" in message.content for message in stopped):
                stopped.append(await runtime.bus.consume_outbound())
        assert all(message.chat_id == "chat-A" for message in stopped if "Stopped" in message.content)
        assert not any(message.content == "ANSWER_A" for message in stopped)
        assert not cancelled["B"].is_set()

        release["B"].set()
        async with asyncio.timeout(2):
            while True:
                message = await runtime.bus.consume_outbound()
                if message.content == "ANSWER_B":
                    assert message.chat_id == "chat-B"
                    break
        assert not cancelled["B"].is_set()
        for chat in started:
            session = await runtime.sessions.state.read(f"websocket:chat-{chat}")
            assert session is not None
            history = [public_history_message(record).get("content", "") for record in session.messages]
            assert not any(f"ONLY_{'B' if chat == 'A' else 'A'}" in str(content) for content in history)
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


@pytest.mark.parametrize("temporary", [False, True])
async def test_ptc_creation_is_session_scoped_and_retained(runtime: _Runtime, temporary):
    await runtime.channel._dispatch_envelope(runtime.connection, "webui-client", {
        "type": "new_temporary_chat" if temporary else "new_chat", "ptc_mode": True,
    })
    attached = next(event for event in runtime.connection.sent if event["event"] == "attached")
    key = f"websocket:{attached['chat_id']}"
    session = await runtime.sessions.state.read(key)
    assert session.metadata["ptc_mode"] is True
    if temporary:
        assert not session.policy.persist
        assert await runtime.sessions.state.list_sessions() == []
    else:
        reopened = SessionManager(runtime.sessions.workspace)
        persisted = await reopened.state.read(key)
        assert persisted.metadata["ptc_mode"] is True


async def test_ptc_creation_rejects_non_boolean_mode(runtime: _Runtime):
    await runtime.channel._dispatch_envelope(runtime.connection, "webui-client", {
        "type": "new_chat", "ptc_mode": "false",
    })
    assert runtime.connection.sent[-1]["event"] == "error"
    assert await runtime.sessions.state.list_sessions() == []
