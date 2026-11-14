"""A rejected write supplies enough current state to merge instead of looping."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.instance_features import MemoryTool
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.agent.tools.execution import execute_tool_calls
from cirno_core.agent.hook import AgentHook, AgentHookContext
from cirno_core.agent.ptc.registry import PtcToolRegistry
from cirno_core.providers.tool_calls import ToolCallRequest
from cirno_memory.repository import MemoryRepository


@pytest.fixture
def memory(tmp_path, monkeypatch):
    monkeypatch.setattr("cirno_core.agent.tools.instance_features.get_home_path", lambda: tmp_path)
    sessions = SimpleNamespace(state=SimpleNamespace(read_metadata=AsyncMock(return_value={"metadata": {}})))
    registry = ToolRegistry()
    registry.register(MemoryTool(sessions))
    return MemoryRepository(tmp_path), registry


def context(key="websocket:one"):
    return request_context(RequestContext(channel="websocket", chat_id="one", session_key=key))


async def call(registry, action, **values):
    result = await registry.execute("memory__" + action, values)
    # The normal execution pipeline appends its shared recovery hint to errors.
    return result, json.JSONDecoder().raw_decode(result)[0]


async def test_checkpoint_missing_revision_recovers_without_another_read(memory):
    repo, registry = memory
    with context():
        _, first = await call(registry, "checkpoint", content="155 papers indexed; next: read three papers", source="indexes/papers.md")
        error, conflict = await call(registry, "checkpoint", content="Three papers read", source="literature/plans/reading-ledger.md")
        assert error.is_error
        assert conflict["error"] == "memory_revision_required"
        assert conflict["write_applied"] is False
        assert "changed" not in conflict["message"]
        current = conflict["current"]
        assert current["id"] == first["id"]
        assert current["revision"] == 1
        assert current["content"] == "155 papers indexed; next: read three papers"
        assert current["source"] == "indexes/papers.md"
        assert "memory.checkpoint" in conflict["recovery"]
        assert len(repo.history(first["id"], session_key="websocket:one")) == 1
        result, saved = await call(registry, "checkpoint", content="155 papers indexed; three papers read; next: compare findings", source="literature/plans/reading-ledger.md", expected_revision=current["revision"])
    assert not getattr(result, "is_error", False)
    assert saved["id"] == first["id"] and saved["revision"] == 2
    assert repo.read(first["id"], session_key="websocket:one", revision=1)["content"] == "155 papers indexed; next: read three papers"


@pytest.mark.parametrize("action", ["checkpoint", "update"])
async def test_stale_revision_returns_a_consistent_snapshot_and_preserves_new_work(memory, action):
    repo, registry = memory
    key = "websocket:one"
    if action == "checkpoint":
        first = repo.checkpoint(key, "Original progress", "test:original")
        newer = repo.checkpoint(key, "New progress from another writer", "test:new", expected_revision=1)
        identity_args = {}
    else:
        first = repo.save("Original finding", source="test:original", session_key=key)
        newer = repo.save("New finding from another writer", source="test:new", session_key=key, memory_id=first["id"], expected_revision=1)
        identity_args = {"memory_id": first["id"]}
    with context():
        error, conflict = await call(registry, action, content="Stale replacement", source="test:stale", expected_revision=1, **identity_args)
        assert error.is_error
        assert conflict["error"] == "memory_revision_conflict"
        assert conflict["expected_revision"] == 1 and conflict["current"]["revision"] == 2
        assert conflict["current"]["id"] == first["id"]
        assert conflict["current"]["content"] == repo.read(newer["id"], session_key=key)["content"]
        assert conflict["current"]["source"] == newer["source"]
        # A new edit between conflict and retry must still reject the stale merge.
        latest = repo.save("Further progress", source="test:latest", session_key=key, memory_id=first["id"], expected_revision=2)
        error, conflict = await call(registry, action, content="Merged but now stale", source="test:merge", expected_revision=2, **identity_args)
    assert error.is_error and conflict["current"]["revision"] == 3
    assert conflict["current"]["content"] == "Further progress"
    assert conflict["current"]["revision"] == latest["revision"]
    assert len(repo.history(first["id"], session_key=key)) == 3
    assert repo.read(first["id"], session_key=key)["content"] == "Further progress"


async def test_conflict_never_discloses_another_conversations_record(memory):
    repo, registry = memory
    private = repo.save("PRIVATE EVIDENCE", source="private:source", session_key="websocket:other")
    with context():
        result = await registry.execute("memory__update", {"memory_id": private["id"], "expected_revision": 1, "content": "Overwrite", "source": "test"})
    assert result.is_error
    assert "scope" in result
    assert "PRIVATE EVIDENCE" not in result and "private:source" not in result
    assert '"current"' not in result


def test_checkpoint_schema_explains_the_first_and_following_writes(memory):
    _, registry = memory
    schemas = {item["function"]["name"]: item["function"] for item in registry.get_definitions()}
    checkpoint = schemas["memory__checkpoint"]
    assert "first save" in checkpoint["description"].lower()
    assert "subsequent saves" in checkpoint["description"]
    assert "expected_revision" not in checkpoint["parameters"]["required"]
    assert "expected_revision" in schemas["memory__update"]["parameters"]["required"]


def test_memory_write_schemas_do_not_advertise_search_only_scopes_and_layers(memory):
    _, registry = memory
    schemas = {item["function"]["name"]: item["function"]["parameters"]["properties"] for item in registry.get_definitions()}
    for name in ("memory__save", "memory__update"):
        assert schemas[name]["scope"]["enum"] == ["session", "project", "user"]
        assert schemas[name]["layer"]["enum"] == ["event", "knowledge"]
        assert "belongs to a Project" in schemas[name]["scope"]["description"]
    assert "all" in schemas["memory__search"]["scope"]["enum"]
    assert "all" in schemas["memory__search"]["layer"]["enum"]


async def execute(registry, name, arguments, hook):
    return await execute_tool_calls(
        registry, [ToolCallRequest("attempt", name, arguments)], concurrent=False,
        external_lookup_counts={}, workspace_violation_counts={}, hook=hook,
        context=AgentHookContext(iteration=1, messages=[]),
    )


async def test_native_checkpoint_conflict_is_an_error_not_a_successful_write(memory):
    repo, registry = memory
    first = repo.checkpoint("websocket:one", "128 papers", "test:original")
    hook = AgentHook()
    hook.on_execute_tool_error = AsyncMock()
    hook.after_execute_tool = AsyncMock()
    with context():
        results, events = await execute(registry, "memory__checkpoint", {"content": "167 papers", "source": "test:attempt"}, hook)
    assert events[0]["status"] == "error"
    assert json.JSONDecoder().raw_decode(results[0])[0]["write_applied"] is False
    hook.on_execute_tool_error.assert_awaited_once()
    hook.after_execute_tool.assert_not_awaited()
    assert repo.read(first["id"], session_key="websocket:one")["revision"] == 1
    assert repo.read(first["id"], session_key="websocket:one")["content"] == "128 papers"


async def test_missing_update_revision_fails_before_tool_execution(memory):
    repo, registry = memory
    first = repo.save("128 papers", source="test", session_key="websocket:one")
    with context():
        results, events = await execute(registry, "memory__update", {"memory_id": first["id"], "content": "167 papers", "source": "test"}, AgentHook())
    assert events[0]["status"] == "error"
    assert "Required parameters: expected_revision" in results[0]
    assert repo.read(first["id"], session_key="websocket:one")["revision"] == 1


async def test_legacy_grouped_save_conflict_guides_the_supported_update_operation(memory):
    repo, registry = memory
    first = repo.save("128 papers", source="test", session_key="websocket:one")
    with context():
        result = await registry.execute("memory", {"action": "save", "memory_id": first["id"], "content": "167 papers", "source": "test"})
    payload = json.JSONDecoder().raw_decode(result)[0]
    assert result.is_error and payload["write_applied"] is False
    assert "memory.update" in payload["recovery"]
    assert "memory_id=current.id" in payload["recovery"]
    assert payload["current"]["revision"] == 1
    assert repo.read(first["id"], session_key="websocket:one")["content"] == "128 papers"


@pytest.mark.parametrize("caught", [False, True])
async def test_ptc_keeps_nested_checkpoint_failure_even_when_program_handles_it(memory, caught):
    repo, native = memory
    first = repo.checkpoint("websocket:one", "128 papers", "test:original")
    hook = AgentHook()
    hook.on_execute_tool_error = AsyncMock()
    code = 'await tools.memory.checkpoint(content="167 papers", source="test:attempt")'
    if caught:
        code = 'try:\n    ' + code + '\nexcept ToolError as error:\n    print(str(error))'
    with context():
        results, events = await execute(PtcToolRegistry(native), "ptc__run", {"code": code, "description": "Save progress"}, hook)
    assert events[0]["status"] == ("ok" if caught else "error")
    assert any(call.args[1].name == "memory__checkpoint" for call in hook.on_execute_tool_error.await_args_list)
    assert '"write_applied": false' in results[0]
    assert '"error": "memory_revision_required"' in results[0]
    assert repo.read(first["id"], session_key="websocket:one")["revision"] == 1
