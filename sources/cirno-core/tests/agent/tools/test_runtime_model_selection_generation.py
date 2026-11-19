"""Runtime preset updates must not write through a retired turn identity."""

import asyncio
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import pytest
from cirno_core.agent.conversation_models import ConversationModels
from cirno_core.agent.loop import AgentLoop
from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.registry import is_tool_error_result
from cirno_core.agent.tools.runtime_control import AgentRuntimeControl
from cirno_core.agent.tools.self import MyTool
from cirno_core.agent.tools.shell_config import ExecToolConfig
from cirno_core.agent.tools.web_config import WebToolsConfig
from cirno_core.session.manager import SessionManager
from cirno_core.session.model_selection import SESSION_MODEL_PRESET_METADATA_KEY


@pytest.fixture
async def selection(tmp_path):
    sessions = SessionManager(tmp_path / "workspace", sessions_root=tmp_path / "sessions")
    parent = await sessions.state.get_header("websocket:preset")
    runtime = SimpleNamespace(model_preset="next", model="fixture-model", context_window_tokens=8192)
    models = ConversationModels(
        SimpleNamespace(resolve_preset=Mock(return_value=runtime)), sessions, Mock(), None,
    )
    target = SimpleNamespace(
        models=models, model="fixture-old", model_preset=None, model_presets={}, max_iterations=1,
        context_window_tokens=4096, workspace=tmp_path, provider_retry_mode="standard",
        max_tool_result_chars=16000, tool_names=[], exec_config=ExecToolConfig(),
        web_config=WebToolsConfig(), restrict_to_workspace=False,
    )
    target.set_session_model_preset = MethodType(AgentLoop.set_session_model_preset, target)
    tool = MyTool(AgentRuntimeControl(target), modify_allowed=True)
    try:
        yield sessions, parent, models, tool
    finally:
        await sessions.state.aclose()


@pytest.mark.parametrize("replacement", ["reset", "delete"])
async def test_runtime_preset_from_retired_turn_cannot_modify_or_recreate_session(selection, replacement):
    sessions, parent, _models, tool = selection
    if replacement == "reset":
        await sessions.state.reset(parent.key)
    else:
        await sessions.state.delete(parent.key)
    with request_context(RequestContext(
        "websocket", "preset", session_key=parent.key, session_generation=parent.generation,
    )):
        result = await tool.execute("set", key="model_preset", value="next")
    assert is_tool_error_result(result)
    current = await sessions.state.read_header(parent.key)
    if replacement == "delete":
        assert current is None
    else:
        assert SESSION_MODEL_PRESET_METADATA_KEY not in current.metadata


async def test_current_turn_selection_and_explicit_administration_still_work(selection):
    sessions, parent, models, tool = selection
    with request_context(RequestContext(
        "websocket", "preset", session_key=parent.key, session_generation=parent.generation,
    )):
        result = await tool.execute("set", key="model_preset", value="next")
    assert not is_tool_error_result(result)
    assert (await sessions.state.read_header(parent.key)).metadata[SESSION_MODEL_PRESET_METADATA_KEY] == "next"
    await models.select_session("websocket:explicit-new", "next")
    assert (await sessions.state.read_header("websocket:explicit-new")).metadata[SESSION_MODEL_PRESET_METADATA_KEY] == "next"


async def test_replacement_while_update_is_pending_rechecks_generation_at_commit(selection, monkeypatch):
    sessions, parent, _models, tool = selection
    entered, release = asyncio.Event(), asyncio.Event()
    update = sessions.state.update_metadata

    async def delayed_update(*args, **kwargs):
        entered.set()
        await release.wait()
        return await update(*args, **kwargs)

    monkeypatch.setattr(sessions.state, "update_metadata", delayed_update)

    async def change():
        with request_context(RequestContext(
            "websocket", "preset", session_key=parent.key, session_generation=parent.generation,
        )):
            return await tool.execute("set", key="model_preset", value="next")

    pending = asyncio.create_task(change())
    try:
        await entered.wait()
        await sessions.state.reset(parent.key)
    finally:
        release.set()
    assert is_tool_error_result(await pending)
    assert SESSION_MODEL_PRESET_METADATA_KEY not in (await sessions.state.read_header(parent.key)).metadata
