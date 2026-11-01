"""Message tools preserve target identity through gateway delivery recording."""

from functools import partial

import pytest

from cirno.agent.tools.context import RequestContext, request_context
from cirno.agent.tools.message import MessageTool
from cirno.bus.queue import MessageBus
from cirno.bus.events import OutboundMessage
from cirno.session.state import SessionConflictError
from cirno.channels.websocket.runtime import WebSocketChannel, WebSocketConfig
from cirno.cli.gateway_runtime import _deliver_to_channel
from cirno.session.display_history import HISTORY_GENERATION_METADATA_KEY
from cirno.session.manager import SessionManager
from cirno.webui.gateway_services import build_gateway_services


@pytest.fixture
async def delivery(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "attachment.txt").write_text("attachment", encoding="utf-8")
    sessions = SessionManager(workspace, sessions_root=tmp_path / "sessions")
    bus = MessageBus()
    tool = MessageTool(
        send_callback=partial(_deliver_to_channel, bus=bus, session_manager=sessions),
        workspace=workspace,
    )
    try:
        yield sessions, bus, tool
    finally:
        await sessions.state.aclose()


@pytest.mark.parametrize("channel,chat_id,key,metadata", [
    ("slack", "C123", "slack:C123:111.222", {"slack": {"thread_ts": "111.222"}}),
    ("telegram", "-100123", "telegram:-100123:topic:42", {"message_thread_id": 42}),
])
async def test_thread_media_is_recorded_in_its_admitted_session(delivery, channel, chat_id, key, metadata):
    sessions, bus, tool = delivery
    session = await sessions.state.get(key)
    coarse_key = f"{channel}:{chat_id}"
    await sessions.state.get(coarse_key)
    await _deliver_to_channel(
        OutboundMessage(channel, chat_id, "caption", media=["attachment.txt"], metadata=metadata),
        bus=bus, session_manager=sessions, record=True,
        session_key=key, session_generation=session.generation,
    )
    sent = bus.outbound.get_nowait()
    assert sent.metadata == metadata
    assert len(sent.media) == 1
    assert [message["content"] for message in (await sessions.state.read(key)).messages] == ["caption"]
    assert (await sessions.state.read(coarse_key)).messages == []


async def test_first_cross_target_media_creates_its_own_session(delivery):
    sessions, bus, tool = delivery
    origin = await sessions.state.get("websocket:global")
    with request_context(RequestContext(
        "websocket", "global", session_key=origin.key, session_generation=origin.generation,
    )):
        result = await tool.execute(
            content="caption", channel="telegram", chat_id="fresh",
            media=["attachment.txt"],
        )

    assert result == "Message sent to telegram:fresh with 1 attachments"
    sent = bus.outbound.get_nowait()
    assert sent.metadata == {}
    target = await sessions.state.read("telegram:fresh")
    assert [message["content"] for message in target.messages] == ["caption"]
    assert (await sessions.state.read(origin.key)).messages == []


@pytest.mark.parametrize("operation", ["reset", "delete"])
async def test_old_turn_media_cannot_recreate_or_write_a_replaced_target(delivery, operation):
    sessions, bus, tool = delivery
    session = await sessions.state.get("slack:C123:111.222")
    await getattr(sessions.state, operation)(session.key)
    with pytest.raises(SessionConflictError):
        await _deliver_to_channel(
            OutboundMessage("slack", "C123", "late caption", media=["attachment.txt"]),
            bus=bus, session_manager=sessions, record=True,
            session_key=session.key, session_generation=session.generation,
        )
    assert bus.outbound.empty()
    target = await sessions.state.read(session.key)
    assert target is None or target.messages == []
    assert await sessions.state.read("slack:C123") is None


async def test_cross_target_reset_after_admission_revokes_media(delivery, monkeypatch):
    sessions, bus, tool = delivery
    original = sessions.state.record_delivery

    async def reset_before_recording(key, *args, **kwargs):
        await sessions.state.reset(key)
        await original(key, *args, **kwargs)

    monkeypatch.setattr(sessions.state, "record_delivery", reset_before_recording)
    result = await tool.execute(
        content="late caption", channel="email", chat_id="fresh@example.invalid",
        media=["attachment.txt"],
    )
    assert "replaced session" in result
    assert bus.outbound.empty()
    assert (await sessions.state.read("email:fresh@example.invalid")).messages == []


@pytest.fixture
async def webui_delivery(delivery, tmp_path, monkeypatch):
    sessions, bus, tool = delivery
    data = tmp_path / "instance"
    data.mkdir()
    monkeypatch.setattr("cirno.config.paths.get_data_dir", lambda: data)
    config = WebSocketConfig.model_validate({
        "enabled": True, "allowFrom": ["*"], "host": "127.0.0.1", "port": 0,
    })
    gateway = build_gateway_services(
        config=config, bus=bus, session_manager=sessions, static_dist_path=None,
        workspace_path=sessions.workspace, default_restrict_to_workspace=True,
        runtime_model_name=None, runtime_surface="browser", runtime_capabilities_overrides=None,
        config_path=data / "config.json",
    )
    return sessions, bus, tool, WebSocketChannel(config, bus, gateway=gateway)




async def test_cross_channel_text_is_saved_in_webui_history(webui_delivery):
    sessions, bus, tool, channel = webui_delivery
    alias = await sessions.state.get_header("websocket:chat")
    await _deliver_to_channel(
        OutboundMessage("websocket", "chat", "notice"), bus=bus,
        session_manager=sessions, record=True,
        session_key=alias.key, session_generation=alias.generation,
    )
    sent = bus.outbound.get_nowait()
    await channel.send(sent)
    facts = await sessions.state.project_history(alias.key, lambda history: history.all_facts())
    assert [fact.content["text"] for fact in facts] == ["notice"]


@pytest.mark.parametrize("operation", ["reset", "delete"])
async def test_webui_destination_revocation_after_admission_blocks_history(
    webui_delivery, monkeypatch, operation,
):
    sessions, bus, tool, channel = webui_delivery
    target = await sessions.state.get_header("websocket:chat")
    original = bus.publish_outbound

    async def revoke_before_enqueue(message):
        assert message.metadata[HISTORY_GENERATION_METADATA_KEY] == target.generation
        await getattr(sessions.state, operation)(target.key)
        await original(message)

    monkeypatch.setattr(bus, "publish_outbound", revoke_before_enqueue)
    result = await tool.execute(content="late notice", channel="websocket", chat_id="chat")
    assert result == "Message sent to websocket:chat"
    await channel.send(bus.outbound.get_nowait())
    assert await sessions.state.project_history(target.key, lambda history: history.all_facts()) == []
    current = await sessions.state.read(target.key)
    assert current is None or current.generation != target.generation


@pytest.mark.parametrize("media", [None, ["attachment.txt"]])
async def test_direct_webui_send_does_not_create_a_missing_destination(webui_delivery, media):
    sessions, bus, tool, _ = webui_delivery
    result = await tool.execute(
        content="notice", channel="websocket", chat_id="missing", media=media,
    )
    assert result.startswith("Error sending message:")
    assert bus.outbound.empty()
    assert await sessions.state.read("websocket:missing") is None


async def test_temporary_webui_media_stays_nonpersistent(webui_delivery):
    sessions, bus, tool, channel = webui_delivery
    target = await sessions.state.register_transient("websocket:temporary")
    await _deliver_to_channel(
        OutboundMessage("websocket", "temporary", "caption", media=["attachment.txt"],
                        metadata={HISTORY_GENERATION_METADATA_KEY: target.generation}),
        bus=bus, session_manager=sessions, record=True,
        session_key=target.key, session_generation=target.generation,
    )
    await channel.send(bus.outbound.get_nowait())
    assert await sessions.state.project_history(target.key, lambda history: history.revision) is None


async def test_async_question_is_mirrored_with_structured_data(delivery):
    from cirno.agent.tools.ask_user import AskUserTool
    sessions, bus, original = delivery
    tool = AskUserTool(send_callback=original._send_callback)
    session = await sessions.state.get('telegram:question')
    with request_context(RequestContext('telegram', 'question', session_key=session.key, session_generation=session.generation)):
        result = await tool.execute('Which format?', options=['CSV', 'JSON'])
    assert 'posted' in result
    mirrored = (await sessions.state.read(session.key)).messages[-1]
    assert mirrored['agent_ui'] == bus.outbound.get_nowait().metadata['_agent_ui']
