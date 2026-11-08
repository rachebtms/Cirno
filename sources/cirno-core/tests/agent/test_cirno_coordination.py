"""Cirno reports, heartbeat recovery, titles and password Node contracts."""

import json
from unittest.mock import AsyncMock

import pytest
from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.coordination import SetSessionTitleTool
from cirno_core.agent.tools.session_messages import SendSessionMessageTool
from cirno_core.bus.queue import MessageBus
from cirno_core.config.home import set_instance_path
from cirno_core.runtime.heartbeat import enqueue_heartbeat
from cirno_core.storage.instance import InstanceData
from cirno_core.nodes.service import Nodes
from cirno_core.session.manager import SessionManager
from cirno_core.session.recovery.pending import pending_followups
from cirno_server.webui.instance_api import instance_action


@pytest.fixture
async def setup(tmp_path):
    home = tmp_path / "home"
    set_instance_path(home)
    sessions = SessionManager(home / "workspace", sessions_root=home / "sessions")
    await sessions.state.get("websocket:work")
    from cirno_core.session.router_session import ensure_router_session
    await ensure_router_session(sessions)
    bus = MessageBus()
    yield home, sessions, bus
    await sessions.state.aclose()
    set_instance_path(None)


async def test_heartbeat_queues_once_and_survives_restart(setup):
    home, sessions, bus = setup
    assert await enqueue_heartbeat(sessions, bus, "Check active work")
    assert not await enqueue_heartbeat(sessions, bus, "Check active work")
    incoming = await bus.consume_inbound()
    assert incoming.session_key == "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"
    assert incoming.sender_id == "heartbeat"
    assert not incoming.is_user_input
    header = await sessions.state.read("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb")
    assert header.metadata["title"] == "@cirno"
    recovered = pending_followups(header)
    assert len(recovered) == 1 and not recovered[0].is_user_input
    assert recovered[0].metadata["_heartbeat"] is True


async def test_reports_to_cirno_are_addressed_to_its_queue(setup):
    _, sessions, bus = setup
    sender = SendSessionMessageTool(sessions=sessions, bus=bus)
    with request_context(
        RequestContext(channel="websocket", chat_id="work", session_key="websocket:work")
    ):
        result = await sender.execute(
            to="Cirno", content="Result and attachment at /tmp/report.md", expect_reply=False
        )
    assert result.startswith("Queued to @")
    inbound = await bus.consume_inbound()
    assert inbound.session_key == "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"
    assert inbound.metadata["_session_message"]["source_session_key"] == "websocket:work"


async def test_agent_titles_notify_sidebar_and_preserve_manual_titles(setup):
    _, sessions, bus = setup
    tool = SetSessionTitleTool(sessions, bus)
    with request_context(
        RequestContext(channel="websocket", chat_id="work", session_key="websocket:work")
    ):
        assert await tool.execute(title="核对配置") == "Conversation title updated."
        assert (await sessions.state.read_metadata("websocket:work"))["metadata"][
            "title"
        ] == "核对配置"
        event = await bus.consume_outbound()
        assert event.chat_id == "work"
        await sessions.state.update_metadata("websocket:work", {"title_user_edited": True})
        result = await tool.execute(title="Another")
        assert "chosen by the user" in str(result)


async def test_password_nodes_redact_and_preserve_credentials(setup, monkeypatch):
    home, sessions, bus = setup
    data = InstanceData(home / "state")
    nodes = Nodes(data)
    connection = {"host": "localhost", "username": "test", "auth_method": "password", "password": "test-only-secret"}
    credential = nodes.credentials.save(label="Test", kind="ssh", ssh=connection, node_enabled=True, agent_visible=True)
    saved = nodes.list_nodes()[0]
    assert saved["has_password"] and "password" not in saved
    nodes.credentials.save(id=credential["id"], label="Renamed", kind="ssh", ssh={**connection, "password": ""})
    assert nodes.node(saved["id"]).password == "test-only-secret"
    assert "test-only-secret" not in json.dumps(nodes.list_nodes())
    node = nodes.node(saved["id"])
    assert "BatchMode=no" in nodes.arguments(node)
    nodes.credentials.save(id=saved["id"], label="Renamed", kind="ssh", ssh={**connection, "auth_method": "key"})
    assert not nodes.node(saved["id"]).password
    assert data.path.stat().st_mode & 0o777 == 0o600
    execute = AsyncMock(return_value="direct output")
    monkeypatch.setattr(Nodes, "execute", execute)
    result = await instance_action(
        {"action": "nodes.execute", "values": {"id": saved["id"], "command": "pwd"}},
        sessions=sessions,
        bus=bus,
    )
    assert result["output"] == "direct output"
    assert data.list("node_jobs") == []


async def test_full_access_write_is_not_limited_to_home_exceptions(setup):
    from cirno_core.agent.tools.context import ToolContext
    from cirno_core.agent.tools.filesystem import WriteFileTool
    from cirno_core.config.tools import ToolsConfig

    home, _, _ = setup
    workspace = home / "workspace"
    workspace.mkdir(exist_ok=True)
    target = workspace / "report.md"
    tool = WriteFileTool.create(
        ToolContext(config=ToolsConfig(restrict_to_workspace=False), workspace=str(workspace))
    )
    result = await tool.execute(path=str(target), content="saved")
    assert "Error" not in result and target.read_text() == "saved"


async def test_heartbeat_run_consumes_journal_and_delivers_tool_reply(setup):
    from unittest.mock import MagicMock

    from cirno_core.agent.loop import AgentLoop
    from cirno_core.providers.generation import GenerationSettings
    from cirno_core.providers.contracts import LLMResponse
    from cirno_core.providers.tool_calls import ToolCallRequest

    home, _, bus = setup
    provider = MagicMock(aclose=AsyncMock())
    provider.get_default_model.return_value = "test-model"
    provider.generation = GenerationSettings()
    provider.estimate_prompt_tokens.return_value = (100, "test")
    provider.chat_stream_with_retry = AsyncMock(
        side_effect=[
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCallRequest(
                        id="reply", name="message", arguments={"content": "Heartbeat ready"}
                    )
                ],
            ),
            LLMResponse(content=""),
        ]
    )
    loop = AgentLoop(bus=bus, provider=provider, workspace=home / "workspace", model="test-model")
    from cirno_core.agent.turn_delivery import TurnDeliveryFactory
    from cirno_core.session.webui_turns.routing import WebuiTurnRoutePolicy
    loop.turn_delivery_factory = TurnDeliveryFactory(bus, route_policy=WebuiTurnRoutePolicy(loop.sessions))
    try:
        await enqueue_heartbeat(loop.sessions, bus, "Send one useful update")
        message = await bus.consume_inbound()
        assert (await loop.turn_delivery_factory.create(message, message.session_key)).route.publish_lifecycle
        response = await loop.processing.process(message)
        assert response is None
        assert not pending_followups(await loop.sessions.state.read("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"))
        visible = []
        while bus.outbound_size:
            outbound = await bus.consume_outbound()
            if outbound.content:
                visible.append(outbound)
        assert any(
            row.content == "Heartbeat ready"
            and row.channel == "websocket"
            and row.chat_id == "b1ec9323-2155-5f24-bc56-1da2f59aeecb"
            for row in visible
        )
    finally:
        await loop.aclose()


@pytest.mark.parametrize("session_key", ["websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", "websocket:work"])
@pytest.mark.parametrize("background", [False, True])
async def test_reply_protocol_is_in_system_prompt_for_cirno_only(setup, session_key, background):
    from unittest.mock import MagicMock

    from cirno_core.agent.loop import AgentLoop
    from cirno_core.bus.events import InboundMessage
    from cirno_core.providers.generation import GenerationSettings
    from cirno_core.providers.contracts import LLMResponse
    from cirno_core.session.router_session import ensure_router_session

    home, _, bus = setup
    provider = MagicMock(aclose=AsyncMock())
    provider.get_default_model.return_value = "test-model"
    provider.generation = GenerationSettings()
    provider.estimate_prompt_tokens.return_value = (100, "test")
    provider.chat_stream_with_retry = AsyncMock(return_value=LLMResponse(content="Nothing to report"))
    loop = AgentLoop(bus=bus, provider=provider, workspace=home / "workspace", model="test-model")
    try:
        await ensure_router_session(loop.sessions)
        await loop.processing.process(InboundMessage(
            channel="system" if background else "websocket",
            sender_id="heartbeat" if background else "user",
            chat_id=session_key.split(":", 1)[1],
            content="Check active work" if background else "你好",
            input_role="system" if background else "user",
            session_key_override=session_key,
            metadata={"_heartbeat": True} if background else {},
        ))
        messages = provider.chat_stream_with_retry.call_args.kwargs["messages"]
        system = messages[0]["content"]
        assert messages[0]["role"] == "system"
        if session_key == "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb":
            assert "MUST call `user__message(content=..., media=[...])`" in system
            assert "including greetings" in system
            assert "Direct greetings and questions still require a reply" in system
            assert "finish silently" in system
        else:
            assert "# Personal Router Conversation" not in system
        # A silent background check must finish without a forced tool retry.
        assert provider.chat_stream_with_retry.await_count == 1
        while bus.outbound_size:
            row = await bus.consume_outbound()
            assert not (row.content == "Nothing to report" and row.metadata.get("_record_channel_delivery"))
    finally:
        await loop.aclose()

async def test_project_is_bound_before_chat_attach(setup):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from cirno_server.webui.commands.router import WebUICommandRouter
    home, sessions, _ = setup
    project = InstanceData(home / "state").save('projects', {'name':'Independent project'})
    scope = SimpleNamespace(payload=lambda: {'kind':'directory','path':str(home/'workspace')})
    router = object.__new__(WebUICommandRouter)
    transport = SimpleNamespace(webui_attach=MagicMock(), webui_send_event=AsyncMock())
    router._transport = transport
    router.gateway = SimpleNamespace(session_manager=sessions)
    router._workspaces = SimpleNamespace(scope_for_new_chat=lambda *args, **kwargs: scope, stage_scope=AsyncMock())
    router._session_projection = SimpleNamespace(attach_fields=AsyncMock(return_value={}))
    router._outbound = SimpleNamespace(hydrate=AsyncMock())
    router.workspace_project_selection_available = lambda connection: True
    async def resolve(connection, factory, *, request_id=None): return factory()
    router.messages = SimpleNamespace(workspace_scope_or_error=resolve)
    await router.dispatch(object(), 'test-client', {'type':'new_chat','project_id':project['id']})
    key = 'websocket:' + transport.webui_attach.call_args.args[1]
    metadata = (await sessions.state.read_metadata(key))['metadata']
    assert metadata['project_id'] == project['id']
    assert metadata['workspace_scope'] == scope.payload()
    transport.webui_attach.reset_mock()
    await router.dispatch(object(), 'test-client', {'type':'new_chat','project_id':'missing'})
    transport.webui_attach.assert_not_called()


async def test_fixed_cirno_name_and_role_prompt_use_session_identity(setup):
    from cirno_core.agent.tools.coordination import CreateSessionTool

    _, sessions, bus = setup
    await sessions.state.mutate_metadata("websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb", lambda metadata: metadata.clear())  # Identity determines the role.
    context = RequestContext(channel="websocket", chat_id="b1ec9323-2155-5f24-bc56-1da2f59aeecb", session_key="websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb")
    with request_context(context):
        result = await SetSessionTitleTool(sessions, bus).execute(title="Wrong title")
    assert not getattr(result, "is_error", False)
    assert "title" not in (await sessions.state.read_metadata(context.session_key))["metadata"]
    assert bus.outbound_size == 0
    provider = CreateSessionTool(sessions)
    block = await provider._provide_runtime_context(context)
    assert "@cirno (personal Router)" in block.content
    assert "conversations__set_title" not in block.content
    ordinary = await provider._provide_runtime_context(RequestContext(
        channel="websocket", chat_id="work", session_key="websocket:work",
    ))
    assert "Use conversations__set_title early" in ordinary.content
    from cirno_core.session.webui_turns.titles import maybe_generate_webui_title
    provider = AsyncMock()
    await sessions.state.update_metadata(context.session_key, {"webui": True})
    assert not await maybe_generate_webui_title(
        sessions=sessions, session_key=context.session_key, provider=provider, model="test",
    )
    provider.chat_stream_with_retry.assert_not_called()


@pytest.mark.parametrize("recreate", [False, True])
async def test_old_turn_cannot_rename_deleted_or_replaced_conversation(setup, recreate):
    _, sessions, bus = setup
    header = await sessions.state.read_header("websocket:work")
    await sessions.state.delete(header.key)
    if recreate:
        await sessions.state.get(header.key)
        await sessions.state.update_metadata(header.key, {"title": "Replacement"})
    with request_context(RequestContext(
        channel="websocket", chat_id="work", session_key=header.key,
        session_generation=header.generation,
    )):
        result = await SetSessionTitleTool(sessions, bus).execute(title="Stale title")
    assert result.is_error
    assert bus.outbound_size == 0
    current = await sessions.state.read_header(header.key)
    if recreate:
        assert current.metadata["title"] == "Replacement"
    else:
        assert current is None


async def test_manual_rename_wins_when_tool_is_already_in_flight(setup, monkeypatch):
    _, sessions, bus = setup
    original = sessions.state.mutate_metadata
    async def concurrent_rename(key, change, **kwargs):
        await original(key, lambda metadata: metadata.update(title="User choice", title_user_edited=True))
        return await original(key, change, **kwargs)
    monkeypatch.setattr(sessions.state, "mutate_metadata", concurrent_rename)
    with request_context(RequestContext(channel="websocket", chat_id="work", session_key="websocket:work")):
        result = await SetSessionTitleTool(sessions, bus).execute(title="Model choice")
    assert "chosen by the user" in result
    assert (await sessions.state.read_header("websocket:work")).metadata["title"] == "User choice"
    assert bus.outbound_size == 0


@pytest.mark.parametrize("recreate", [False, True])
async def test_stale_goal_tools_cannot_recreate_or_mutate_conversation(setup, recreate):
    from cirno_core.agent.goals.permission import goal_mutation_permission
    from cirno_core.agent.tools.long_task import CreateGoalTool, GetGoalTool, UpdateGoalTool

    _, sessions, _ = setup
    header = await sessions.state.read_header("websocket:work")
    await sessions.state.delete(header.key)
    if recreate:
        await sessions.state.get(header.key)
        await sessions.state.update_metadata(header.key, {"goal_state": {
            "goal_id": "replacement", "status": "active", "objective": "New work",
        }})
    with request_context(RequestContext(
        channel="websocket", chat_id="work", session_key=header.key,
        session_generation=header.generation,
    )), goal_mutation_permission(True):
        assert (await CreateGoalTool(sessions).execute(objective="Old work")).is_error
        assert (await UpdateGoalTool(sessions).execute(action="complete")).is_error
        assert (await GetGoalTool(sessions).execute()).is_error
    current = await sessions.state.read_header(header.key)
    if recreate:
        assert current.metadata["goal_state"]["status"] == "active"
        assert current.metadata["goal_state"]["goal_id"] == "replacement"
    else:
        assert current is None


@pytest.mark.parametrize("failure", ["invalid-pid", "cancelled"])
async def test_interrupted_node_submission_records_unknown_outcome(setup, monkeypatch, failure):
    import asyncio

    home, _, _ = setup
    nodes = Nodes(InstanceData(home / "state"))
    execute = AsyncMock(return_value="SSH login banner\n42")
    if failure == "cancelled":
        execute.side_effect = asyncio.CancelledError()
    monkeypatch.setattr(nodes, "execute", execute)
    with pytest.raises(asyncio.CancelledError if failure == "cancelled" else RuntimeError):
        await nodes.start_job("test-node", "run-task")
    jobs = nodes.data.list("node_jobs")
    assert len(jobs) == 1
    assert jobs[0]["state"] == "submission_unknown"
    assert jobs[0]["error"]


async def test_inflight_goal_completion_cannot_overwrite_user_pause(setup, monkeypatch):
    from cirno_core.agent.tools.long_task import UpdateGoalTool
    from cirno_core.agent.tools.registry import ToolRegistry

    _, sessions, bus = setup
    header = await sessions.state.read_header("websocket:work")
    await sessions.state.update_metadata(header.key, {"goal_state": {
        "goal_id": "work-goal", "status": "active", "objective": "Finish work",
    }})
    original = sessions.state.mutate_metadata

    async def user_pauses_first(key, change, **kwargs):
        def pause(metadata):
            metadata["goal_state"] = {**metadata["goal_state"], "status": "paused", "recap": "User paused"}
        await original(key, pause)
        return await original(key, change, **kwargs)

    monkeypatch.setattr(sessions.state, "mutate_metadata", user_pauses_first)
    registry = ToolRegistry()
    registry.register(UpdateGoalTool(sessions, bus))
    with request_context(RequestContext(
        channel="websocket", chat_id="work", session_key=header.key, session_generation=header.generation,
    )):
        result = await registry.execute("goals__update", {"action": "complete"})
    assert result.is_error and "Goal changed" in result
    goal = (await sessions.state.read_header(header.key)).metadata["goal_state"]
    assert goal["status"] == "paused" and goal["recap"] == "User paused"
    assert bus.outbound_size == 0


async def test_reset_keeps_cirno_identity_but_discards_old_goal_and_reports(setup):
    _, sessions, _ = setup
    key = "websocket:b1ec9323-2155-5f24-bc56-1da2f59aeecb"
    before = await sessions.state.get_header(key)
    identity = dict(before.metadata)
    await sessions.state.update_metadata(key, {
        "goal_state": {"status": "active", "objective": "Old task"},
        "_sustained_goal_continuation_rounds": 7,
        "work_report": {"id": "old"}, "work_report_pending": [{"id": "old"}],
    })
    await sessions.state.reset(key)
    after = await sessions.state.read_header(key)
    assert after.generation != before.generation
    assert after.metadata == identity


async def test_goal_continuation_enables_webui_execution_stream(setup):
    from cirno_core.agent.turn_delivery import TurnDeliveryFactory
    from cirno_core.bus.events import InboundMessage
    from cirno_core.session.webui_turns.routing import WebuiTurnRoutePolicy

    _, sessions, bus = setup
    await sessions.state.update_metadata("websocket:work", {"webui": True})
    delivery = (await TurnDeliveryFactory(bus, route_policy=WebuiTurnRoutePolicy(sessions)).create(
        InboundMessage(channel="websocket", chat_id="work", sender_id="system:goal", content="Continue",
                       metadata={"_internal_continuation": True, "_skip_user_persist": True}),
        "websocket:work", enable_stream=True,
    ))
    assert delivery.streaming
    assert delivery.route.metadata["webui"] is True
    assert delivery.route.metadata["_wants_stream"] is True
    assert delivery.route.turn_id
