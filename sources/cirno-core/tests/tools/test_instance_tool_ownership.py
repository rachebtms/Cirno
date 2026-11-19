"""Instance tools keep the Home/configuration selected for their construction."""

import asyncio
import json
import threading
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cirno_core.agent.subagents.tools import SubagentTools
from cirno_core.agent.tools.context import RequestContext, ToolContext, request_context
from cirno_core.agent.tools.instance_features import InspectSkillTool, MemoryTool, NodeTool
from cirno_core.config.home import set_instance_path
from cirno_core.config.loader import set_config_path
from cirno_core.config.network import NetworkConfig
from cirno_core.config.tools import ToolsConfig
from cirno_core.memory.store import MemoryStore
from cirno_memory.repository import MemoryRepository


def select(root):
    set_instance_path(root)
    set_config_path(root / "config.json")


def context():
    return request_context(RequestContext("websocket", "fixture", session_key="websocket:fixture"))


async def test_memory_write_remains_in_its_original_home_after_global_selection_changes(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    select(first)
    tool = MemoryTool()
    select(second)
    with context():
        result = json.loads(await tool.execute("save", content="Original instance finding", source="test:original"))
    original = MemoryRepository(first / "home")
    assert original.read(result["id"], session_key="websocket:fixture")["content"] == "Original instance finding"
    assert not (second / "home" / "memory").exists()


async def test_memory_search_reloads_only_its_captured_configuration(tmp_path, monkeypatch):
    first, second = tmp_path / "first", tmp_path / "second"
    select(first)
    tool = MemoryTool()
    select(second)
    paths = []

    def config(path=None):
        from cirno_core.config.loader import get_config_path
        paths.append(path if path is not None else get_config_path())
        return SimpleNamespace(agents=SimpleNamespace(defaults=SimpleNamespace(memory=object(), timezone="UTC")))

    monkeypatch.setattr("cirno_core.config.loader.load_config", config)
    monkeypatch.setattr("cirno_memory.search.search", lambda *_args, **_kwargs: {"memories": []})
    with context():
        assert json.loads(await tool.execute("search", query="fixture"))["memories"] == []
    assert paths == [first / "config.json"]


async def test_skill_history_remains_in_its_original_home(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    select(first)
    directory = first / "home" / "skills-history" / "fixture"
    (directory / "version-one").mkdir(parents=True)
    (directory / "version-one.json").write_text(json.dumps({"valid": True, "errors": []}))
    tool = InspectSkillTool()
    select(second)
    result = json.loads(await tool.execute("fixture", "history"))
    assert len(result["versions"]) == 1
    assert result["versions"][0]["path"] == str(directory / "version-one")


async def test_node_catalog_uses_its_original_config_state_without_opening_ssh(tmp_path, monkeypatch):
    first, second = tmp_path / "first", tmp_path / "second"
    select(first)
    tool = NodeTool()
    select(second)

    class Nodes:
        def __init__(self, data=None, *, actor):
            from cirno_core.config.paths import get_data_dir
            assert actor == "agent"
            self.path = data.state_dir if data is not None else get_data_dir()

        def catalog(self):
            return {"state_dir": str(self.path)}

    monkeypatch.setattr("cirno_core.agent.tools.instance_features.Nodes", Nodes)
    result = json.loads(await tool.execute("list"))
    assert result["state_dir"] == str(first / "state")


async def test_consolidation_memory_tool_uses_the_store_home_not_global_home(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    select(first)
    store = MemoryStore(first / "home")
    select(second)
    tool = store.dream.build_tools().get("memory")
    with context():
        await tool.execute("status")
    assert (first / "home" / "memory" / "catalog.sqlite3").exists()
    assert not (second / "home" / "memory").exists()


def test_consolidation_reports_stay_in_the_owned_config_state(tmp_path, monkeypatch):
    import sqlite3

    first, second = tmp_path / "first", tmp_path / "second"
    select(first)
    store = MemoryStore(first / "home")
    select(second)
    monkeypatch.setattr("cirno_memory.repository.MemoryRepository.finish", lambda *_args, **_kwargs: {"retained": 0})
    assert store.dream.finish_batch("fixture") == {"retained": 0}
    path = first / "state" / "notifications" / "inbox.sqlite3"
    assert path.exists()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT id,status FROM notices").fetchall() == [("dream:fixture", "succeeded")]
    assert not (second / "state" / "notifications").exists()


@pytest.mark.parametrize("explicit_config", [False, True])
def test_subagent_tool_context_retains_home_and_config_from_its_owner(tmp_path, monkeypatch, explicit_config):
    from cirno_core.agent.tools.web.search import WebSearchTool

    first, second = tmp_path / "first", tmp_path / "second"
    select(first)
    path = first / "custom.json" if explicit_config else None
    owner = SubagentTools(tmp_path / "workspace", ToolsConfig(), NetworkConfig(), False, set(), source_config_path=path)
    select(second)
    captured = []
    monkeypatch.setattr("cirno_core.agent.subagents.tools.ToolLoader", lambda: SimpleNamespace(
        load=lambda ctx, _registry, **_kwargs: captured.append(ctx),
    ))
    monkeypatch.setattr("cirno_core.agent.subagents.tools.workspace_sandbox_status", lambda **_kwargs: None)
    owner.build(exec_manager=SimpleNamespace())
    assert captured[0].home_path == first / "home"
    assert captured[0].source_config_path == path
    assert captured[0].instance_config_path == (path or first / "config.json")
    # Explicit search configurations remain standalone unless disk reload was requested.
    search = WebSearchTool.create(captured[0])
    assert (search._config_loader is not None) is explicit_config


def test_subagent_prompt_uses_its_owned_skill_catalog_and_home(tmp_path, monkeypatch):
    first, second = tmp_path / "first", tmp_path / "second"
    select(first)
    owner = SubagentTools(tmp_path / "workspace", ToolsConfig(), NetworkConfig(), False, set())
    select(second)
    homes = []

    class Catalog:
        def __init__(self, *_args, home=None, **_kwargs):
            from cirno_core.config.home import get_home_path
            homes.append(home if home is not None else get_home_path())

        def snapshot(self):
            return nullcontext()

        def get_always_skills(self):
            return []

    monkeypatch.setattr("cirno_core.skills.loader.SkillsLoader", Catalog)
    monkeypatch.setattr("cirno_core.skills.context.SkillContext", lambda _catalog: SimpleNamespace(
        load_skills_for_context=lambda _active: "", build_skills_summary=lambda **_kwargs: "",
    ))
    prompt = owner.prompt()
    assert homes == [first / "home"]
    assert str(first / "home") in prompt
    assert str(second / "home") not in prompt


@pytest.mark.parametrize("role", ["router", "worker", "maintenance"])
def test_main_prompt_keeps_its_profiles_identity_and_awakening_in_the_owned_home(tmp_path, monkeypatch, role):
    from cirno_core.agent.context import ContextBuilder
    from cirno_core.session.keys import ROUTER_SESSION_KEY

    first, second = tmp_path / "first", tmp_path / "second"
    for root in (first, second):
        home = root / "home"
        home.mkdir(parents=True)
        for name in ("AGENTS.md", "SOUL.md", "WORKER.md", "USER.md", "BOOTSTRAP.md"):
            (home / name).write_text(f"{root.name} owned {name}", encoding="utf-8")

    class Catalog:
        def __init__(self, *_args, **_kwargs):
            pass

        def snapshot(self):
            return nullcontext()

        def get_always_skills(self, **_kwargs):
            return []

    monkeypatch.setattr("cirno_core.agent.context.SkillsLoader", Catalog)
    monkeypatch.setattr("cirno_core.agent.context.SkillContext", lambda _catalog: SimpleNamespace(
        build_skills_summary=lambda **_kwargs: "",
    ))
    key = {"router": ROUTER_SESSION_KEY, "worker": "websocket:fixture", "maintenance": "dream:fixture"}[role]
    select(first)
    builder = ContextBuilder(first / "home")
    original = builder.build_system_prompt(session_key=key)
    select(second)
    current = builder.build_system_prompt(session_key=key)
    assert current == original
    assert "first owned AGENTS.md" in current
    assert "second owned" not in current
    assert str(second / "home") not in current
    if role == "router":
        assert "first owned BOOTSTRAP.md" in current


@pytest.mark.parametrize("completed", [False, True])
async def test_recovery_uses_its_owned_awakening_completion_state(tmp_path, monkeypatch, completed):
    from cirno_core.bus.events import InboundMessage
    from cirno_core.config.agents import ResumeConfig
    from cirno_core.session.keys import ROUTER_SESSION_KEY
    from cirno_core.session.recovery.delivery import RecoveryDelivery

    first, second = tmp_path / "first", tmp_path / "second"
    for root, done in ((first, completed), (second, not completed)):
        home = root / "home"
        home.mkdir(parents=True)
        (home / "BOOTSTRAP.md").write_text("" if done else "First introduction", encoding="utf-8")
    state = SimpleNamespace(queue_followup=AsyncMock(return_value="awakening"), acknowledge_followups=AsyncMock())
    bus = SimpleNamespace(publish_inbound=AsyncMock())
    select(first)
    delivery = RecoveryDelivery(SimpleNamespace(state=state), bus, ResumeConfig())
    select(second)
    message = InboundMessage(channel="system", sender_id="system:awakening", chat_id="fixture",
                             content="First introduction", metadata={"_awakening": True})
    monkeypatch.setattr("cirno_core.session.recovery.delivery.pending_followups", lambda _session: [message])
    await delivery.requeue_pending_followups(SimpleNamespace(key=ROUTER_SESSION_KEY, generation="fixture"))
    assert bus.publish_inbound.await_count == (0 if completed else 1)
    assert state.acknowledge_followups.await_count == (1 if completed else 0)


def test_skill_availability_validates_the_same_home_as_skill_discovery(tmp_path, monkeypatch):
    from cirno_core.skills.loader import SkillsLoader

    first, second = tmp_path / "first", tmp_path / "second"
    for root in (first, second):
        directory = root / "home" / "skills" / "fixture"
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text("---\nname: fixture\ndescription: Fixture\n---\n" + root.name)
    select(first)
    loader = SkillsLoader(tmp_path / "workspace", builtin_skills_dir=tmp_path / "no-builtin")
    select(second)
    inspected = []

    def snapshot(path, *, home, document_content):
        assert home == first / "home"
        inspected.append((path, document_content))
        return {"valid": True, "errors": []}

    monkeypatch.setattr("cirno_core.agent.plugins.enabled_agent_plugin_skill_documents", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("cirno_core.skills.history.snapshot_skill", snapshot)
    assert loader.get_skill_availability("fixture") == (True, "")
    assert inspected[0][0] == first / "home" / "skills" / "fixture"
    assert inspected[0][1].endswith("first")


@pytest.mark.parametrize("explicit_config", [False, True])
async def test_memory_factory_uses_its_context_home_and_explicit_config(tmp_path, monkeypatch, explicit_config):
    first, second = tmp_path / "first", tmp_path / "second"
    select(first)
    sessions = SimpleNamespace(state=SimpleNamespace(read_metadata=AsyncMock(return_value={"metadata": {}})))
    path = first / "custom.json" if explicit_config else None
    ctx = ToolContext(config=ToolsConfig(), workspace=str(tmp_path), sessions=sessions,
                      source_config_path=path)
    select(second)
    tool = MemoryTool.create(ctx)
    assert NodeTool.create(ctx).state_dir == first / "state"
    paths = []

    def config(path=None):
        paths.append(path)
        return SimpleNamespace(agents=SimpleNamespace(defaults=SimpleNamespace(memory=object(), timezone="UTC")))

    monkeypatch.setattr("cirno_core.config.loader.load_config", config)
    monkeypatch.setattr("cirno_memory.search.search", lambda *_args, **_kwargs: {"memories": []})
    with context():
        await tool.execute("search", query="fixture")
    assert paths == [path or first / "config.json"]
    assert (first / "home" / "memory").exists()
    assert not (second / "home" / "memory").exists()


async def test_loop_and_consolidation_keep_the_explicit_config_owner(tmp_path, monkeypatch):
    from cirno_core.agent.loop import AgentLoop
    from cirno_core.bus.queue import MessageBus
    from cirno_core.providers.generation import GenerationSettings

    first, second = tmp_path / "first", tmp_path / "second"
    select(first)
    contexts = []

    def load(_loader, ctx, _registry):
        contexts.append(ctx)
        return []

    monkeypatch.setattr("cirno_core.agent.tools.loader.ToolLoader.load", load)

    class Provider:
        generation = GenerationSettings()

        def get_default_model(self):
            return "fixture"

    agent = AgentLoop(
        provider=Provider(),
        bus=MessageBus(), workspace=tmp_path / "workspace", source_config_path=first / "custom.json",
    )
    try:
        assert contexts[0].home_path == first / "home"
        assert contexts[0].instance_config_path == first / "custom.json"
        select(second)
        paths = []

        def config(path=None):
            paths.append(path)
            return SimpleNamespace(agents=SimpleNamespace(defaults=SimpleNamespace(
                dream=SimpleNamespace(batch_entries=2, batch_chars=200),
            )))

        monkeypatch.setattr("cirno_core.config.loader.load_config", config)
        assert agent.context.memory.dream.build_prompt() is None
        assert paths == [first / "custom.json"]
        memory = agent.context.memory.dream.build_tools().get("memory")
        assert memory.home_path == first / "home"
        assert memory.source_config_path == first / "custom.json"
    finally:
        await agent.sessions.state.aclose()


@pytest.mark.parametrize("kind", ["node", "skill"])
@pytest.mark.parametrize("fails", [False, True])
async def test_stopping_instance_tool_settles_accepted_local_writes(tmp_path, monkeypatch, kind, fails):
    select(tmp_path / "instance")
    loop = asyncio.get_running_loop()
    entered = asyncio.Event()
    release = threading.Event()
    completed = threading.Event()
    marker = tmp_path / "accepted-write.txt"

    def accepted_write():
        loop.call_soon_threadsafe(entered.set)
        try:
            assert release.wait(2), "Fixture did not release local write"
            marker.write_text("Local write settled", encoding="utf-8")
            if fails:
                raise OSError("Fixture late local write failure")
        finally:
            completed.set()

    if kind == "node":
        class Nodes:
            def __init__(self, *_args, **_kwargs):
                accepted_write()

            def catalog(self):
                raise AssertionError("Cancelled initialization must not continue")

        monkeypatch.setattr("cirno_core.agent.tools.instance_features.Nodes", Nodes)
        operation = asyncio.create_task(NodeTool().execute("list"))
    else:
        def inspect(*_args):
            accepted_write()
            return {"versions": []}

        monkeypatch.setattr("cirno_core.agent.tools.instance_features.inspect_skill", inspect)
        operation = asyncio.create_task(InspectSkillTool().execute("fixture", "validate"))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        operation.cancel()
        await asyncio.sleep(0)
        operation.cancel()
        await asyncio.sleep(0)
        pending = not operation.done()
    finally:
        release.set()
    try:
        with pytest.raises(asyncio.CancelledError):
            await operation
    finally:
        assert await asyncio.to_thread(completed.wait, 1)
    assert pending
    assert marker.read_text() == "Local write settled"
