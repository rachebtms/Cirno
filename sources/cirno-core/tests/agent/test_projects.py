"""Project tools and UI actions share durable membership operations."""

import asyncio
import json

import pytest

from cirno_core.agent.ptc.registry import PtcToolRegistry
from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.projects import ProjectsTool
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.agent.tools.selection import conversation_tools
from cirno_core.bus.queue import MessageBus
from cirno_core.config.home import set_instance_path
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.manager import SessionManager
from cirno_core.session.session_handles import SessionHandleResolver
from cirno_server.webui.instance_api import instance_action


@pytest.fixture
async def projects(tmp_path):
    set_instance_path(tmp_path)
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "state/sessions")
    cirno = await sessions.state.get(ROUTER_SESSION_KEY)
    await sessions.state.import_messages("websocket:worker", [{"role": "user", "content": "Keep this research"}])
    bus = MessageBus()
    registry = ToolRegistry()
    registry.register(ProjectsTool(sessions, bus))
    context = RequestContext(channel="websocket", chat_id="b1ec9323-2155-5f24-bc56-1da2f59aeecb", session_key=cirno.key, session_generation=cirno.generation)
    with request_context(context):
        yield sessions, bus, registry
    await sessions.state.aclose()
    set_instance_path(None)


async def call(registry, operation, **values):
    result = await registry.execute(f"projects__{operation}", values)
    assert not getattr(result, "is_error", False), str(result)
    return json.loads(result)


async def test_ui_and_tools_share_catalog_and_preserve_partial_updates(projects):
    sessions, bus, registry = projects
    saved = await instance_action({"action": "projects.save", "values": {
        "name": "Research", "description": "Verified evidence", "working_directory": "/research",
    }}, sessions=sessions, bus=bus)
    identifier = saved["project"]["id"]
    assert (await call(registry, "list"))["projects"] == saved["projects"]
    updated = (await call(registry, "update", id=identifier, name="New name"))["project"]
    assert updated == {**saved["project"], "name": "New name"}
    assert (await bus.consume_outbound()).event.scope == "projects"
    assert (await bus.consume_outbound()).event.scope == "projects"


async def test_membership_and_deletion_keep_conversations_and_files(projects, tmp_path):
    sessions, _, registry = projects
    file = tmp_path / "workspace/result.txt"
    file.parent.mkdir(exist_ok=True)
    file.write_text("Verified result")
    before = (await sessions.state.read("websocket:worker")).messages
    project = (await call(registry, "create", name="Research"))["project"]
    handle = await SessionHandleResolver(sessions).ahandle_for_session("websocket:worker")
    assert await call(registry, "assign", to="@" + handle.name, project_id=project["id"]) == {"ok": True}
    members = (await call(registry, "get", id=project["id"]))["conversations"]
    assert [row["session_key"] for row in members] == ["websocket:worker"]
    await call(registry, "delete", id=project["id"])
    restored = await sessions.state.read("websocket:worker")
    assert restored.metadata["project_id"] is None
    assert restored.messages == before
    assert file.read_text() == "Verified result"
    assert (await call(registry, "list"))["projects"] == []


async def test_unassign_and_explicit_membership_errors(projects):
    sessions, _, registry = projects
    handle = await SessionHandleResolver(sessions).ahandle_for_session("websocket:worker")
    await call(registry, "assign", to="@" + handle.name, project_id=None)
    for values in ({"to": "@cirno", "project_id": None}, {"to": "@missing", "project_id": None},
                   {"to": "@" + handle.name, "project_id": "missing"}, {"to": "@" + handle.name}):
        result = await registry.execute("projects__assign", values)
        assert result.is_error
    assert (await sessions.state.read_metadata("websocket:worker"))["metadata"]["project_id"] is None


async def test_ordinary_and_stale_cirno_cannot_manage_projects(projects):
    sessions, _, registry = projects
    assert "project" not in conversation_tools(registry, "websocket:worker").tool_names
    assert "projects__create" not in conversation_tools(registry, "websocket:worker", ptc_mode=True).model_instructions()
    for key, generation in (("websocket:worker", None), (ROUTER_SESSION_KEY, "cleared")):
        with request_context(RequestContext(channel="websocket", chat_id="b1ec9323-2155-5f24-bc56-1da2f59aeecb", session_key=key, session_generation=generation)):
            assert (await registry.execute("projects__create", {"name": "Unauthorized"})).is_error
    assert (await sessions.projects.action("list", {}))["projects"] == []


async def test_namespaced_schema_requires_destination_but_does_not_accept_action_override(projects):
    _, _, registry = projects
    schemas = {row["function"]["name"]: row["function"]["parameters"] for row in registry.get_definitions()}
    assert set(schemas["projects__assign"]["properties"]) == {"to", "project_id"}
    assert schemas["projects__assign"]["required"] == ["to", "project_id"]
    assert schemas["projects__list"]["properties"] == {}
    assert registry.prepare_call("projects__create", {"name": "Research", "action": "delete"})[2]
    ptc = PtcToolRegistry(registry)
    assert "projects" in ptc.model_instructions()


async def test_cancelled_deletion_finishes_cleanup_before_stopping(projects, monkeypatch):
    sessions, _, registry = projects
    project = (await call(registry, "create", name="Research"))["project"]
    await sessions.projects.action("assign", {"session_key": "websocket:worker", "project_id": project["id"]})
    entered, release = asyncio.Event(), asyncio.Event()
    original = sessions.projects._assign

    async def held(values):
        entered.set()
        await release.wait()
        await original(values)

    monkeypatch.setattr(sessions.projects, "_assign", held)
    deletion = asyncio.create_task(sessions.projects.action("delete", {"id": project["id"]}))
    await entered.wait()
    deletion.cancel()
    await asyncio.sleep(0)
    assert not deletion.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await deletion
    assert (await sessions.projects.action("list", {}))["projects"] == []
    assert (await sessions.state.read_metadata("websocket:worker"))["metadata"]["project_id"] is None


async def test_conversation_creation_and_project_deletion_share_membership_ownership(projects, monkeypatch):
    sessions, _, registry = projects
    project = (await call(registry, "create", name="Research"))["project"]
    entered, release = asyncio.Event(), asyncio.Event()
    original = sessions.state.open_with_metadata

    async def held(key, metadata, **kwargs):
        entered.set()
        await release.wait()
        return await original(key, metadata, **kwargs)

    monkeypatch.setattr(sessions.state, "open_with_metadata", held)
    creation = asyncio.create_task(sessions.projects.open_conversation(
        "websocket:new-worker", {"title": "New research"}, project["id"],
    ))
    await entered.wait()
    deletion = asyncio.create_task(sessions.projects.action("delete", {"id": project["id"]}))
    await asyncio.sleep(0)
    assert not deletion.done()
    release.set()
    await asyncio.gather(creation, deletion)
    metadata = (await sessions.state.read_metadata("websocket:new-worker"))["metadata"]
    assert metadata["title"] == "New research"
    assert metadata["project_id"] is None
    with pytest.raises(ValueError, match="Project not found"):
        await sessions.projects.open_conversation("websocket:late-worker", {}, project["id"])
    assert await sessions.state.read_header("websocket:late-worker") is None


@pytest.mark.parametrize("identifier", ["", 42, [], {}])
async def test_invalid_project_creation_does_not_persist_a_broken_conversation(projects, identifier):
    sessions, _, _ = projects
    with pytest.raises(ValueError, match="Project ID must be"):
        await sessions.projects.open_conversation("websocket:invalid-worker", {}, identifier)
    assert await sessions.state.read_header("websocket:invalid-worker") is None
