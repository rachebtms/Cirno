"""Temporary disposal retains retry ownership and settles accepted cleanup."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cirno_server.webui.commands.router import WebUICommandRouter
from cirno_server.webui.temporary_chats import TemporaryChatError, WebUITemporaryChats


async def make_chat(history, tmp_path):
    bus = SimpleNamespace(publish_inbound=AsyncMock())
    chats = WebUITemporaryChats(bus=bus, session_manager=history.sessions, workspaces=SimpleNamespace(), logger=Mock())
    owner = object()
    chat_id = await chats.create(owner, trusted_webui=True)
    attachment = tmp_path / "private-input.txt"
    attachment.write_text("Private temporary content")
    chats.register_media(owner, chat_id, [str(attachment)])
    return chats, bus, owner, chat_id, attachment


@pytest.mark.parametrize("stage", ["state", "control"])
async def test_failed_disposal_can_retry_without_losing_attachment_or_owner(history, tmp_path, monkeypatch, stage):
    chats, bus, owner, chat_id, attachment = await make_chat(history, tmp_path)
    original = history.sessions.state.discard
    calls = 0

    async def discard(key):
        nonlocal calls
        calls += 1
        if calls == 1 and stage == "state":
            raise OSError("state disposal failed")
        await original(key)

    monkeypatch.setattr(history.sessions.state, "discard", discard)
    if stage == "control":
        bus.publish_inbound.side_effect = [OSError("control enqueue failed"), None]
    with pytest.raises(OSError):
        await chats.discard(owner, chat_id)
    assert chats.owns(owner, chat_id)
    assert attachment.exists()
    await chats.discard(owner, chat_id)
    assert not chats.owns(owner, chat_id)
    assert not attachment.exists()
    assert await history.sessions.state.read_header("websocket:" + chat_id) is None
    assert not chats.should_persist_transcript(chat_id)
    chats.close()


@pytest.mark.parametrize("stage", ["state", "control"])
async def test_repeated_cancellation_finishes_disposal_before_return(history, tmp_path, monkeypatch, stage):
    chats, bus, owner, chat_id, attachment = await make_chat(history, tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    original = history.sessions.state.discard

    async def discard(key):
        if stage == "state":
            entered.set()
            await release.wait()
        await original(key)

    async def enqueue(_message):
        if stage == "control":
            entered.set()
            await release.wait()

    monkeypatch.setattr(history.sessions.state, "discard", discard)
    bus.publish_inbound.side_effect = enqueue
    task = asyncio.create_task(chats.discard(owner, chat_id))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
    assert not chats.owns(owner, chat_id)
    assert not attachment.exists()
    assert await history.sessions.state.read_header("websocket:" + chat_id) is None
    bus.publish_inbound.assert_awaited_once()
    chats.close()


async def test_connection_cleanup_attempts_all_chats_and_bookkeeping_after_one_failure():
    owner = object()
    router = WebUICommandRouter.__new__(WebUICommandRouter)
    router._transport = SimpleNamespace(
        webui_connection_chats=lambda _owner: ("broken", "persistent", "good"),
        webui_detach=Mock(), webui_clear_connection_default=Mock(),
    )
    router._temporary_chats = SimpleNamespace(
        owns=lambda _owner, chat_id: chat_id != "persistent",
        chat_ids_for_owner=lambda _owner: ("broken", "good", "not-attached"),
    )
    problem = OSError("one cleanup failed")

    async def discard(_owner, chat_id):
        if chat_id == "broken":
            raise problem

    router.discard_owned_chat = AsyncMock(side_effect=discard)
    router.gateway = SimpleNamespace(endpoint=SimpleNamespace(discard_connection=Mock()))
    router.requests = SimpleNamespace(discard_connection_if_idle=Mock())
    with pytest.raises(OSError) as caught:
        await router.cleanup_connection(owner)
    assert caught.value is problem
    assert [call.args[1] for call in router.discard_owned_chat.await_args_list] == ["broken", "good", "not-attached"]
    router._transport.webui_detach.assert_any_call(owner, "persistent")
    router._transport.webui_clear_connection_default.assert_called_once_with(owner)
    router.gateway.endpoint.discard_connection.assert_called_once_with(owner)
    router.requests.discard_connection_if_idle.assert_called_once_with(owner)


@pytest.mark.parametrize("replacement", [False, True])
async def test_disposal_rejects_another_owner_or_a_persistent_replacement(history, tmp_path, replacement):
    chats, bus, owner, chat_id, attachment = await make_chat(history, tmp_path)
    key = "websocket:" + chat_id
    if replacement:
        await history.sessions.state.discard(key)
        await history.sessions.state.get_header(key)
        assert (await history.sessions.state.read_header(key)).policy.persist
    with pytest.raises(TemporaryChatError, match="temporary_chat_unavailable"):
        await chats.discard(owner if replacement else object(), chat_id)
    assert chats.owns(owner, chat_id)
    assert attachment.exists()
    bus.publish_inbound.assert_not_awaited()
    chats.close()
