import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cirno.agent.ptc.registry import PtcToolRegistry, RunCodeTool
from cirno.agent.tools.ask_user import AskUserTool
from cirno.agent.tools.context import RequestContext, request_context
from cirno.agent.tools.filesystem import ReadFileTool
from cirno.agent.tools.instance_features import MemoryTool, NodeTool
from cirno.agent.tools.registry import ToolRegistry
from cirno.webui.instance_api import instance_action


def test_public_names_are_grouped_and_actions_have_small_schemas():
    registry = ToolRegistry()
    registry.register(MemoryTool())
    registry.register(NodeTool())
    registry.register(ReadFileTool())
    schemas = {
        s["function"]["name"]: s["function"]["parameters"] for s in registry.get_definitions()
    }
    assert "memory__search" in schemas and "files__read" in schemas and "nodes__execute" in schemas
    assert "memory" not in schemas and "read_file" not in schemas
    assert set(schemas["memory__read"]["properties"]) == {"memory_id", "revision"}
    assert schemas["memory__read"]["required"] == ["memory_id"]
    assert "action" not in schemas["memory__search"]["properties"]
    assert "memory__confirm" not in schemas  # Only the Dream worker can confirm a batch.
    registry.unregister("memory")
    assert registry.get("memory__search") is None


def test_binding_cannot_change_the_selected_operation_or_pass_ignored_fields():
    registry = ToolRegistry()
    registry.register(MemoryTool())
    for values in [{"action": "save"}, {"content": "ignored"}, {"bad": True}]:
        _, _, error = registry.prepare_call("memory__search", values)
        assert error
    assert registry.prepare_call("memory__read", {})[2]
    _, params, error = registry.prepare_call("memory__read", {"memory_id": "one"})
    assert error is None and params == {"memory_id": "one", "action": "read"}


@pytest.mark.asyncio
async def test_model_and_settings_search_share_the_retrieval_service(monkeypatch):
    calls = []

    def search(repo, query, config, **filters):
        calls.append((query, config, filters))
        return {"memories": []}

    monkeypatch.setattr("cirno.memory.search.search", search)
    sessions = SimpleNamespace(
        state=SimpleNamespace(read_metadata=AsyncMock(return_value={"metadata": {}}))
    )
    registry = ToolRegistry()
    registry.register(MemoryTool(sessions))
    with request_context(
        RequestContext(channel="websocket", chat_id="one", session_key="websocket:one")
    ):
        result = await registry.execute(
            "memory__search", {"query": "exact result", "mode": "hybrid"}
        )
    assert json.loads(result)["memories"] == []
    await instance_action(
        {"action": "memory.list", "values": {"query": "exact result", "mode": "hybrid"}},
        sessions=sessions,
        bus=None,
    )
    assert [row[0] for row in calls] == ["exact result", "exact result"]
    assert calls[0][1] == calls[1][1]
    assert all(row[2]["mode"] == "hybrid" for row in calls)
    assert calls[0][2]["maintenance"] is False and calls[1][2]["maintenance"] is True


@pytest.mark.asyncio
async def test_ptc_nested_names_dispatch_the_same_tool_operation():
    calls = []

    async def dispatch(name, args, identity):
        calls.append((name, args))
        return {"found": 1}, False

    result = await RunCodeTool().run(
        'result = await tools.memory.search(query="value")\nprint(result["found"])',
        dispatch,
        ["memory__search"],
    )
    assert result.strip() == "1"
    assert calls == [("memory__search", {"query": "value"})]
    assert [s["function"]["name"] for s in PtcToolRegistry(ToolRegistry()).get_definitions()] == [
        "ptc__run"
    ]


@pytest.mark.asyncio
async def test_question_strings_are_not_silently_coerced():
    send = AsyncMock()
    registry = ToolRegistry()
    registry.register(AskUserTool(send_callback=send))
    for value in [False, 3, {"text": "question"}]:
        result = await registry.execute("user__ask", {"question": value})
        assert result.is_error and "string" in result
    send.assert_not_called()


def test_skill_history_reads_do_not_create_snapshots(tmp_path):
    from cirno.skills.history import inspect_skill

    directory = tmp_path / "skills" / "sample"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\nname: sample\ndescription: Example\n---\nOriginal instructions"
    )
    assert inspect_skill("sample", "history", tmp_path) == {"versions": []}
    assert not (tmp_path / "skills-history").exists()
    validated = inspect_skill("sample", "validate", tmp_path)
    assert validated["validation"]["valid"]
    (directory / "SKILL.md").write_text(
        "---\nname: sample\ndescription: Example\n---\nUpdated instructions"
    )
    versions = inspect_skill("sample", "history", tmp_path)["versions"]
    assert len(versions) == 1
    assert "Original instructions" in (Path(versions[0]["path"]) / "SKILL.md").read_text()


def test_flat_plugin_schema_is_preserved():
    class Plugin:
        name = "custom_plugin"
        description = "Plugin contract"
        def to_schema(self):
            return {"name": self.name, "parameters": {"type": "object", "properties": {}}, "custom": True}

        async def execute(self, **kwargs):
            return "ok"

    registry = ToolRegistry()
    registry.register(Plugin())
    assert registry.get_definitions() == [Plugin().to_schema()]
    assert registry.get("custom_plugin").name == "custom_plugin"


def test_conversation_tool_selection_and_ptc_keep_delivery_scoped():
    from cirno.agent.tools.message import MessageTool
    from cirno.agent.tools.selection import conversation_tools

    registry = ToolRegistry()
    registry.register(MessageTool())
    registry.register(ReadFileTool())
    regular = conversation_tools(registry, "websocket:ordinary")
    assert not regular.has("message") and regular.has("files__read")
    assert conversation_tools(registry, "websocket:global").has("user__message")
    assert conversation_tools(regular, "websocket:ordinary") is regular
    sdk = conversation_tools(registry, "websocket:ordinary", ptc_mode=True)
    assert [item["function"]["name"] for item in sdk.get_definitions()] == ["ptc__run"]
    assert "tools.user.message(content=" not in sdk.sdk_prompt()


@pytest.mark.parametrize("content", ['{"apps":', '[]', '{"apps": []}'])
def test_damaged_app_registry_is_not_treated_as_empty_or_overwritten(tmp_path, content):
    from cirno.apps.cli import CliAppError, CliAppManager

    manager = CliAppManager(workspace=tmp_path, data_dir=tmp_path / "apps")
    manager.installed_path.parent.mkdir()
    manager.installed_path.write_text(content)
    with pytest.raises(CliAppError, match="installed CLI Apps"):
        manager.installed_names()
    with pytest.raises(CliAppError, match="installed CLI Apps"):
        manager._record_installed({"name": "example"})
    assert manager.installed_path.read_text() == content
