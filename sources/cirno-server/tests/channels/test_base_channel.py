from types import SimpleNamespace

import pytest
from cirno_core.bus.events import OutboundMessage
from cirno_core.bus.queue import MessageBus
from cirno_server.channels.base import BaseChannel


class _DummyChannel(BaseChannel):
    name = "dummy"
    _sent: list[OutboundMessage]

    def __init__(self, config, bus):
        super().__init__(config, bus)
        self._sent = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send(self, msg: OutboundMessage) -> None:
        self._sent.append(msg)


def test_is_allowed_requires_exact_match() -> None:
    channel = _DummyChannel(SimpleNamespace(allow_from=["allow@email.com"]), MessageBus())

    assert channel.is_allowed("allow@email.com") is True
    assert channel.is_allowed("attacker|allow@email.com") is False


def test_is_allowed_supports_dict_allow_from_alias() -> None:
    channel = _DummyChannel({"allowFrom": ["alice"]}, MessageBus())

    assert channel.is_allowed("alice") is True


def test_is_allowed_denies_empty_dict_allow_from() -> None:
    channel = _DummyChannel({"allow_from": []}, MessageBus())

    assert channel.is_allowed("alice") is False


def test_is_allowed_handles_none_allow_from() -> None:
    channel = _DummyChannel({"allow_from": None}, MessageBus())
    assert channel.is_allowed("alice") is False

    channel2 = _DummyChannel({"allowFrom": None}, MessageBus())
    assert channel2.is_allowed("alice") is False


def test_is_allowed_star_allows_all() -> None:
    channel = _DummyChannel({"allowFrom": ["*"]}, MessageBus())
    assert channel.is_allowed("anyone") is True


@pytest.mark.asyncio
@pytest.mark.parametrize("config", [{"allowFrom": []}, {"enabled": True}, {"allow_from": ["friend"]}])
async def test_unauthorized_input_is_not_published_or_answered(config) -> None:
    bus = MessageBus()
    channel = _DummyChannel(config, bus)
    await channel._handle_message("stranger", "chat1", "hello")
    assert bus.inbound_size == 0
    assert channel._sent == []


@pytest.mark.asyncio
async def test_authorized_input_preserves_sender_and_session_envelope() -> None:
    bus = MessageBus()
    channel = _DummyChannel({"allowFrom": ["member-lid"]}, bus)
    await channel._handle_message(
        "member-lid", "private-chat", "hello", media=["/tmp/file.txt"],
        metadata={"source": "private"}, session_key="websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb",
        require_existing_session=True, session_generation="current-generation",
    )
    msg = await bus.consume_inbound()
    assert msg.sender_id == "member-lid"
    assert msg.chat_id == "private-chat"
    assert msg.content == "hello"
    assert msg.media == ["/tmp/file.txt"]
    assert msg.metadata == {"source": "private"}
    assert msg.session_key_override == "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"
    assert msg.require_existing_session is True
    assert msg.session_generation == "current-generation"
