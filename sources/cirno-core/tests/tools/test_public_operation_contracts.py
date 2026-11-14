"""The public operation schema is also the pre-execution admission contract."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from cirno_core.agent.tools.cron import CronTool
from cirno_core.agent.tools.instance_features import InspectSkillTool, MemoryTool
from cirno_core.agent.tools.registry import ToolRegistry, is_tool_error_result
from cirno_core.agent.tools.self import MyTool
from cirno_core.agent.tools.subagent import SubagentTool


@pytest.fixture
def registry():
    registry = ToolRegistry()
    for tool in (
        MemoryTool(), SubagentTool(MagicMock()), CronTool(MagicMock()),
        InspectSkillTool(), MyTool(runtime_control=MagicMock()),
    ):
        registry.register(tool)
    return registry


@pytest.mark.parametrize("name, params, error", [
    ("memory__save", {"content": "Fact", "source": "test", "scope": "all"}, "scope"),
    ("memory__save", {"content": "Fact", "source": "test", "layer": "profile"}, "layer"),
    ("memory__search", {"scope": "all", "layer": "all"}, None),
    ("agents__create", {}, "task"),
    ("agents__send", {"task_id": "worker"}, "message"),
    ("agents__send", {"task_id": "worker", "message": "hello", "wait": True}, "wait"),
    ("agents__cancel", {}, "task_id"),
    ("agents__check", {}, None),
    ("runtime__check", {"value": 1}, "value"),
    ("runtime__set", {"key": "note"}, "value"),
    ("runtime__set", {"key": "note", "value": None}, None),
    ("automations__add", {"at": "2030-01-01T00:00:00Z"}, "message"),
    ("automations__remove", {}, "job_id"),
    ("automations__list", {"message": "ignored task"}, "message"),
    ("skills__validate", {}, "name"),
])
def test_public_operation_parameters_match_advertised_contract(registry, name, params, error):
    _, _, result = registry.prepare_call(name, params)
    if error:
        assert result is not None and error in result
    else:
        assert result is None


async def test_narrowed_memory_scope_is_rejected_before_the_writer_runs(registry):
    writer = registry.get("memory")
    writer.execute = AsyncMock(return_value="incorrectly persisted")
    result = await registry.execute("memory__save", {"content": "Fact", "source": "test", "scope": "all"})
    assert is_tool_error_result(result)
    writer.execute.assert_not_awaited()


@pytest.mark.parametrize("outcome", ["protected", "not_found"])
async def test_refused_automation_removal_preserves_error_status(outcome):
    service = MagicMock()
    service.remove_job.return_value = outcome
    service.get_job.return_value.name = "heartbeat"
    registry = ToolRegistry()
    registry.register(CronTool(service))
    result = await registry.execute("automations__remove", {"job_id": "existing-or-missing"})
    assert is_tool_error_result(result)
    assert "Cannot remove" in result if outcome == "protected" else "not found" in result
