"""Search reloads belong to their creating instance and never block admission."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cirno_core.agent.loop import AgentLoop
from cirno_core.agent.tools.context import ToolContext
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.agent.tools.web.search import WebSearchTool
from cirno_core.agent.tools.web_config import WebSearchConfig, WebToolsConfig
from cirno_core.bus.queue import MessageBus
from cirno_core.config.network import NetworkConfig
from cirno_core.config.schema import Config
from cirno_core.config.tools import ToolsConfig


@pytest.mark.parametrize("explicit_source", [True, False])
async def test_created_search_tool_keeps_its_config_owner_after_global_switch(tmp_path, monkeypatch, explicit_source):
    owner = tmp_path / "owner" / "config.json"
    other = tmp_path / "other" / "config.json"
    selected = [other if explicit_source else owner]
    cfg = WebSearchConfig(provider="brave", api_key="owner-fixture")
    other_cfg = WebSearchConfig(provider="brave", api_key="other-fixture")
    loaded = []

    def load(path=None):
        actual = path if path is not None else selected[0]
        loaded.append(actual)
        return SimpleNamespace(tools=SimpleNamespace(web=SimpleNamespace(search=cfg if actual == owner else other_cfg)))

    monkeypatch.setattr("cirno_core.config.loader.get_config_path", lambda: selected[0])
    monkeypatch.setattr("cirno_core.config.loader.load_config", load)
    monkeypatch.setattr("cirno_core.config.loader.resolve_config_env_vars", lambda value: value)
    adapter = AsyncMock(return_value="Fixture search output")
    monkeypatch.setattr("cirno_core.agent.tools.web.searches.brave.search", adapter)
    ctx = ToolContext(
        config=ToolsConfig(web=WebToolsConfig(search=cfg)), workspace=str(tmp_path),
        provider_snapshot_loader=Mock(),
    )
    if explicit_source:
        ctx.source_config_path = owner
    tool = WebSearchTool.create(ctx)
    selected[0] = other
    assert await tool.execute("Local fixture query") == "Fixture search output"
    assert loaded == [owner]
    assert adapter.call_args.args[0].config.api_key == "owner-fixture"


def test_exclusive_admission_does_not_reload_configuration():
    config = WebSearchConfig(provider="brave", api_key="fixture")
    loader = Mock(return_value=config)
    tool = WebSearchTool(config=config, config_loader=loader)
    assert tool.exclusive is False
    loader.assert_not_called()


async def test_slow_config_reload_keeps_loop_responsive_and_cancellation_stops_search(monkeypatch):
    entered, finished, release = threading.Event(), threading.Event(), threading.Event()
    config = WebSearchConfig(provider="brave", api_key="fixture")

    def load():
        entered.set()
        try:
            release.wait(.3)
            return config
        finally:
            finished.set()

    adapter = AsyncMock(return_value="Fixture output")
    monkeypatch.setattr("cirno_core.agent.tools.web.searches.brave.search", adapter)
    tool = WebSearchTool(config=config, config_loader=load)
    operation = asyncio.create_task(tool.execute("Local fixture query"))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        assert not finished.is_set(), "Configuration loader blocked the event loop"
        operation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await operation
        adapter.assert_not_awaited()
    finally:
        release.set()
        await asyncio.gather(operation, return_exceptions=True)
        assert await asyncio.to_thread(finished.wait, 1)


def test_from_config_forwards_the_bound_source_to_loop_construction(tmp_path):
    class Capture:
        def __init__(self, **values):
            self.values = values
            self.context = SimpleNamespace(current_system_prompts=Mock())
            self.subagents = SimpleNamespace(tools=SimpleNamespace())
            self.consolidator = SimpleNamespace()
            self.persistence = SimpleNamespace(release_archive=Mock())

    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    owner = tmp_path / "owner" / "config.json"
    config.bind_source_path(owner)
    result = AgentLoop.from_config.__func__(
        Capture, config, tool_registry=ToolRegistry(), provider=Mock(),
        session_manager=Mock(), preset_snapshot_loader=Mock(),
    )
    assert result.values["source_config_path"] == owner


def test_default_tool_context_carries_the_source_without_creating_clients(tmp_path, monkeypatch):
    captured = []
    monkeypatch.setattr("cirno_core.agent.approval.service.OperationApproval", Mock())
    monkeypatch.setattr("cirno_core.agent.conversation_control.ConversationControl", Mock())
    monkeypatch.setattr("cirno_core.agent.tools.loader.ToolLoader.load", lambda _self, ctx, _registry: captured.append(ctx) or [])
    source = tmp_path / "owner" / "config.json"
    agent = SimpleNamespace(
        sessions=Mock(), bus=MessageBus(), runtime_resolver=Mock(), goal_continuation_limit=0,
        tools_config=ToolsConfig(), network_config=NetworkConfig(), workspace=tmp_path,
        subagents=Mock(), cron_service=None, _exec_session_manager=Mock(),
        context=SimpleNamespace(timezone="UTC", memory=SimpleNamespace(
            workspace=tmp_path, dream=SimpleNamespace(source_config_path=source),
        )), workspace_scopes=SimpleNamespace(sandbox_status=None),
        tools=ToolRegistry(), register_runtime_context_provider=Mock(),
    )
    AgentLoop._register_default_tools(agent, provider_snapshot_loader=None, source_config_path=source)
    assert captured[0].source_config_path == source
    assert captured[0].instance_config_path == source
    assert captured[0].home_path == tmp_path


async def test_config_reload_wait_is_inside_the_search_deadline(monkeypatch):
    from cirno_core.agent.tools.registry import is_tool_error_result

    entered, finished, release = threading.Event(), threading.Event(), threading.Event()
    config = WebSearchConfig(provider="brave", api_key="fixture")
    config.timeout = .02

    def load():
        entered.set()
        try:
            release.wait(.3)
            return config
        finally:
            finished.set()

    adapter = AsyncMock(return_value="Unexpected request")
    monkeypatch.setattr("cirno_core.agent.tools.web.searches.brave.search", adapter)
    tool = WebSearchTool(config=config, config_loader=load)
    operation = asyncio.create_task(tool.execute("Local fixture query"))
    try:
        result = await asyncio.wait_for(asyncio.shield(operation), .15)
        assert is_tool_error_result(result)
        assert "tool deadline" in result
        adapter.assert_not_awaited()
    finally:
        release.set()
        await asyncio.gather(operation, return_exceptions=True)
        assert await asyncio.to_thread(finished.wait, 1)


async def test_task_search_inherits_the_owning_source_without_a_provider_loader(tmp_path, monkeypatch):
    from cirno_core.agent.subagents import tools as task_tools
    from cirno_core.agent.subagents.manager import SubagentManager
    from cirno_core.agent.tools.loader import ToolLoader

    source = tmp_path / "owner" / "config.json"
    config = Config()
    config.tools.web.search = WebSearchConfig(provider="brave", api_key="owning-fixture")
    load = Mock(return_value=config)
    monkeypatch.setattr("cirno_core.config.loader.load_config", load)
    monkeypatch.setattr("cirno_core.config.loader.resolve_config_env_vars", lambda value: value)
    monkeypatch.setattr("cirno_core.config.loader.get_config_path", lambda: tmp_path / "other.json")
    loader = ToolLoader(test_classes=[WebSearchTool])
    monkeypatch.setattr(loader, "_discover_plugins", lambda: {})
    monkeypatch.setattr(task_tools, "ToolLoader", lambda: loader)
    adapter = AsyncMock(return_value="Owner fixture result")
    monkeypatch.setattr("cirno_core.agent.tools.web.searches.brave.search", adapter)
    manager = SubagentManager(tmp_path, MessageBus(), 1000, consolidator=Mock(), source_config_path=source)
    try:
        tool = manager.tools.build(exec_manager=SimpleNamespace()).get("web_search")
        assert await tool.execute("Local fixture") == "Owner fixture result"
        load.assert_called_once_with(source)
    finally:
        await manager.close()


async def test_shorter_refreshed_budget_counts_time_already_spent_loading(monkeypatch):
    from cirno_core.agent.tools.registry import is_tool_error_result

    entered, release = threading.Event(), threading.Event()
    initial = WebSearchConfig(provider="brave", api_key="fixture")
    initial.timeout = .3
    refreshed = initial.model_copy(deep=True)
    refreshed.timeout = .001

    def load():
        entered.set()
        assert release.wait(.5)
        return refreshed

    adapter = AsyncMock(return_value="Unexpected request")
    monkeypatch.setattr("cirno_core.agent.tools.web.searches.brave.search", adapter)
    operation = asyncio.create_task(WebSearchTool(config=initial, config_loader=load).execute("Fixture"))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        await asyncio.sleep(.01)
    finally:
        release.set()
    assert is_tool_error_result(await operation)
    adapter.assert_not_awaited()
