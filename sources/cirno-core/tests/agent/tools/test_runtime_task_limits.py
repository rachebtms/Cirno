"""Runtime result limits reach the task execution and final-result consumers."""

from types import MethodType, SimpleNamespace

import pytest
from cirno_core.agent.loop import AgentLoop
from cirno_core.agent.subagents.contracts import SubagentLimits
from cirno_core.agent.tools.registry import is_tool_error_result
from cirno_core.agent.tools.runtime_control import AgentRuntimeControl
from cirno_core.agent.tools.self import MyTool
from cirno_core.agent.tools.shell_config import ExecToolConfig
from cirno_core.agent.tools.web_config import WebToolsConfig


def target(tmp_path):
    value = SimpleNamespace(
        model="fixture", model_preset=None, model_presets={}, max_iterations=40,
        context_window_tokens=8192, workspace=tmp_path, provider_retry_mode="standard",
        max_tool_result_chars=16000, tool_names=[], exec_config=ExecToolConfig(),
        web_config=WebToolsConfig(), restrict_to_workspace=False,
        subagents=SimpleNamespace(limits=SubagentLimits(40, 16000)),
    )
    value._sync_subagent_runtime_limits = MethodType(AgentLoop._sync_subagent_runtime_limits, value)
    value.set_runtime_max_tool_result_chars = lambda limit: AgentLoop.set_runtime_max_tool_result_chars(value, limit)
    return value


@pytest.mark.parametrize("limit", [256, 64000])
async def test_runtime_result_limit_updates_task_execution_limits(tmp_path, limit):
    value = target(tmp_path)
    tool = MyTool(AgentRuntimeControl(value), modify_allowed=True)
    response = await tool.execute("set", key="max_tool_result_chars", value=limit)
    assert not is_tool_error_result(response)
    assert value.max_tool_result_chars == limit
    assert value.subagents.limits.max_tool_result_chars == limit
    assert value.subagents.limits.max_iterations == 40


def test_next_turn_synchronization_includes_result_limits(tmp_path):
    value = target(tmp_path)
    value.max_tool_result_chars = 4096
    value._sync_subagent_runtime_limits()
    assert value.subagents.limits.max_tool_result_chars == 4096
