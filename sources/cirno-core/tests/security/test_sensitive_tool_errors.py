"""Sensitive error observations retain privacy through the normal tool pipeline."""

import json
from unittest.mock import MagicMock

import pytest
from cirno_core.agent.governance.contracts import ContextGovernanceConfig
from cirno_core.agent.governance.results import normalize_tool_result
from cirno_core.agent.hook import AgentHook, AgentHookContext
from cirno_core.agent.tools.base import Tool, ToolResult
from cirno_core.agent.tools.execution import execute_tool_calls
from cirno_core.agent.tools.registry import ToolRegistry, with_tool_error_hint
from cirno_core.providers.base import LLMProvider
from cirno_core.providers.tool_calls import ToolCallRequest
from cirno_core.utils.progress_events import build_tool_event_finish_payloads
from cirno_vault.redaction import CREDENTIAL_RESULT_HIDDEN, tool_history, tool_result
from loguru import logger


class SensitiveErrorTool(Tool):
    name = "fixture_private_error"
    description = "Return a sensitive error fixture"
    parameters = {"type": "object", "properties": {}}

    def __init__(self, content):
        self.content = content

    async def execute(self):
        return ToolResult(self.content, is_error=True, sensitive=True)


def test_error_guidance_preserves_result_status_and_privacy():
    result = with_tool_error_hint(ToolResult("private diagnostic", is_error=True, sensitive=True))
    assert isinstance(result, ToolResult)
    assert result.is_error
    assert result.sensitive
    assert with_tool_error_hint(result) is result
    assert tool_result("fixture_private_error", result) == CREDENTIAL_RESULT_HIDDEN


def test_failed_credential_read_keeps_its_diagnostic_in_the_durable_copy():
    result = with_tool_error_hint(ToolResult.error("Credential not found"))
    assert isinstance(result, ToolResult)
    assert result.is_error
    assert not result.sensitive
    assert tool_result("credentials__read", result) is result


async def test_direct_registry_preserves_sensitive_error_observation():
    registry = ToolRegistry()
    registry.register(SensitiveErrorTool("fixture-private-diagnostic"))
    result = await registry.execute("fixture_private_error", {})
    assert result.is_error
    assert result.sensitive
    assert "fixture-private-diagnostic" in result
    assert tool_result("fixture_private_error", result) == CREDENTIAL_RESULT_HIDDEN


@pytest.mark.parametrize("detail", ["service rejected", "outside the configured workspace", "private address"])
async def test_execution_keeps_private_errors_out_of_activity_logs_and_spills(tmp_path, detail):
    secret = "fixture-private-error-content"
    registry = ToolRegistry()
    registry.register(SensitiveErrorTool(f"{detail}: {secret}"))
    observations = []
    logs = []

    async def checkpoint(call, result):
        observations.append(result)

    handler = logger.add(lambda message: logs.append(str(message)), format="{message}")
    try:
        results, events = await execute_tool_calls(
            registry, [ToolCallRequest("private-error", "fixture_private_error", {})],
            concurrent=False, external_lookup_counts={}, workspace_violation_counts={},
            hook=AgentHook(), context=AgentHookContext(iteration=0, messages=[]),
            on_result=checkpoint,
        )
    finally:
        logger.remove(handler)
    result = results[0]
    assert result.is_error
    assert result.sensitive
    assert secret in result, "The current model still needs its live observation"
    assert observations[0] is result
    assert events[0]["status"] == "error"
    assert secret not in str(events)
    assert secret not in "\n".join(logs)
    assert tool_result("fixture_private_error", result) == CREDENTIAL_RESULT_HIDDEN
    durable = tool_history([{
        "role": "tool", "name": "fixture_private_error", "tool_call_id": "private-error", "content": result,
    }])
    assert secret not in json.dumps(durable)
    activity = build_tool_event_finish_payloads(AgentHookContext(
        iteration=0, messages=[], tool_calls=[ToolCallRequest("private-error", "fixture_private_error", {})],
        tool_results=results, tool_events=events,
    ))
    assert secret not in json.dumps(activity)
    assert activity[0]["phase"] == "error"
    normalized = normalize_tool_result(
        ContextGovernanceConfig(provider=MagicMock(spec=LLMProvider), model="fixture", tools=registry,
                                workspace=tmp_path, session_key="fixture:private", max_tool_result_chars=20),
        "private-error", "fixture_private_error", result,
    )
    assert normalized.is_error
    assert secret not in normalized
    assert not list(tmp_path.rglob("*"))
