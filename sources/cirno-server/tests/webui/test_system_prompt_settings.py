"""Owner additions persist separately and are captured once per model run."""

from unittest.mock import MagicMock

import pytest

from cirno_core.agent.context import ContextBuilder, TranscriptInput
from cirno_core.agent.loop import AgentLoop
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.config.home import set_instance_path
from cirno_core.config.loader import load_config, save_config
from cirno_core.config.prompts import DEFAULT_SHARED_PROMPT, SystemPrompts
from cirno_core.config.schema import Config
from cirno_core.providers.base import LLMProvider
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_server.webui.settings.api import update_runtime_config_settings
from cirno_server.webui.settings.contracts import WebUISettingsError


@pytest.fixture(autouse=True)
def home(tmp_path):
    set_instance_path(tmp_path)
    yield
    set_instance_path(None)


def test_additions_apply_shared_then_the_selected_role_and_can_be_fully_cleared(tmp_path):
    builder = ContextBuilder(tmp_path)
    builder.system_prompts = SystemPrompts(shared="SHARED_OWNER_TEXT", router="ROUTER_OWNER_TEXT", worker="WORKER_OWNER_TEXT")
    router = builder.build_system_prompt(session_key=ROUTER_SESSION_KEY)
    worker = builder.build_system_prompt(session_key="websocket:worker")
    for prompt, own, other in [(router, "ROUTER_OWNER_TEXT", "WORKER_OWNER_TEXT"), (worker, "WORKER_OWNER_TEXT", "ROUTER_OWNER_TEXT")]:
        assert prompt.index("SHARED_OWNER_TEXT") < prompt.index(own)
        assert other not in prompt and DEFAULT_SHARED_PROMPT not in prompt
    maintenance = builder.build_system_prompt(session_key="dream:batch")
    assert "SHARED_OWNER_TEXT" not in maintenance
    assert "memory maintenance executor" in maintenance
    builder.system_prompts = SystemPrompts(shared="")
    assert "additional system instructions" not in builder.build_system_prompt(session_key=ROUTER_SESSION_KEY)


@pytest.mark.asyncio
async def test_saved_additions_apply_next_turn_without_restarting_or_rewriting_an_admitted_prompt(tmp_path):
    path = tmp_path / "custom-instance.json"
    save_config(Config(), path)
    config = load_config(path)
    provider = MagicMock(spec=LLMProvider)
    provider.get_default_model.return_value = "test"
    loop = AgentLoop.from_config(config, provider=provider, tool_registry=ToolRegistry())
    captured = loop.context.current_system_prompts()
    transcript = TranscriptInput([], "hello")
    before = loop.context.build_transcript(transcript, session_key=ROUTER_SESSION_KEY, system_prompts=captured)
    try:
        values = {f"agents.defaults.system_prompts.{role}": role + "\ncustom instructions" for role in ("shared", "router", "worker")}
        payload = update_runtime_config_settings(values, config_path=path)
        assert not payload["requires_restart"]
        assert all(payload["runtime_config"][key] == value for key, value in values.items())
        assert load_config(path).agents.defaults.system_prompts.shared == values["agents.defaults.system_prompts.shared"]
        assert loop.context.build_transcript(transcript, session_key=ROUTER_SESSION_KEY, system_prompts=captured) == before
        assert "router\ncustom instructions" in loop.context.build_system_prompt(session_key=ROUTER_SESSION_KEY)
        assert "worker\ncustom instructions" in loop.subagents.tools.prompt()
        update_runtime_config_settings({key: "" for key in values}, config_path=path)
        assert "additional system instructions" not in loop.context.build_system_prompt(session_key=ROUTER_SESSION_KEY)
    finally:
        await loop.aclose()


@pytest.mark.parametrize("invalid", [True, None, ["text"], "x" * 32001])
def test_invalid_addition_rejects_the_whole_patch(tmp_path, invalid):
    path = tmp_path / "config.json"
    save_config(Config(), path)
    before = path.read_bytes()
    with pytest.raises(WebUISettingsError):
        update_runtime_config_settings({"agents.defaults.system_prompts.shared": "valid",
                                        "agents.defaults.system_prompts.worker": invalid}, config_path=path)
    assert path.read_bytes() == before
