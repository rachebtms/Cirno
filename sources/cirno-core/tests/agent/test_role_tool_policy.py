"""Role catalogs and direct-work admission use the same native/PTC boundary."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from contextlib import asynccontextmanager

import pytest

from cirno_core.agent.hook import AgentHook, AgentHookContext
from cirno_core.agent.ptc.registry import PtcToolRegistry
from cirno_core.agent.runner.engine import AgentRunner
from cirno_core.agent.tools.base import Tool
from cirno_core.agent.tools.execution import execute_tool_calls
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.agent.tools.role_policy import RoleToolPolicy
from cirno_core.agent.tools.selection import conversation_tools
from cirno_core.providers.base import LLMProvider
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.tool_calls import ToolCallRequest
from cirno_core.session.keys import ROUTER_SESSION_KEY
from cirno_core.session.roles import ConversationRole, DirectExecutionLimits, RouterConversation, WorkerConversation
from sources.development.testing.runtime import make_run_spec


class Counter(Tool):
    name = "exec"
    description = "Count an actual operation"
    parameters = {"type": "object", "properties": {}}

    def __init__(self, name="exec"):
        self.name = name
        self.calls = 0

    async def execute(self, **kwargs):
        self.calls += 1
        return "ok"


def catalog(*names):
    tools = ToolRegistry()
    for name in names:
        tools.register(Counter(name))
    return tools


async def execute(tools, calls, policy, *, concurrent=False):
    return await execute_tool_calls(
        tools, calls, concurrent=concurrent, external_lookup_counts={},
        workspace_violation_counts={}, hook=AgentHook(), context=AgentHookContext(iteration=1, messages=[]),
        role_policy=policy,
    )


@pytest.mark.parametrize("ptc", [False, True])
def test_separate_catalogs_keep_coordination_out_of_worker_and_transient_agents_out_of_router(ptc):
    tools = catalog("exec", "memory", "message", "control_session", "control_goal", "project", "subagent")
    router = conversation_tools(tools, ROUTER_SESSION_KEY, ptc_mode=ptc)
    worker = conversation_tools(tools, "websocket:worker", ptc_mode=ptc)
    if ptc:
        router, worker = router.native, worker.native
    assert router.has("message") and router.has("project") and not router.has("subagent")
    assert worker.has("exec") and worker.has("subagent")
    assert not any(worker.has(name) for name in ("message", "project", "control_session", "control_goal"))


async def test_router_budget_spans_tool_batches_and_keeps_delegation_available():
    tools = catalog("exec", "create_session")
    schemas = tools.get_definitions()
    policy = RoleToolPolicy(RouterConversation())
    for index in range(10):
        results, events = await execute(tools, [ToolCallRequest(str(index), "shell__exec", {})], policy)
        assert events[0]["status"] == ("ok" if index < 9 else "error")
    assert tools.get("exec").calls == 9
    assert "conversations__create" in results[0]
    _, events = await execute(tools, [ToolCallRequest("delegate", "conversations__create", {})], policy)
    assert events[0]["status"] == "ok" and tools.get("create_session").calls == 1
    assert tools.get_definitions() == schemas


async def test_time_budget_stops_slow_work_and_blocks_further_direct_calls():
    tools = catalog("exec")
    finished = asyncio.Event()

    async def stalled(**kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    tools.get("exec").execute = stalled
    role = ConversationRole("router", ("SOUL.md",), "", False, True, frozenset(), DirectExecutionLimits(9, .02))
    policy = RoleToolPolicy(role)
    results, events = await execute(tools, [ToolCallRequest("slow", "shell__exec", {})], policy)
    assert finished.is_set() and events[0]["status"] == "error"
    assert "may have completed effects" in results[0]
    tools.get("exec").execute = AsyncMock()
    await execute(tools, [ToolCallRequest("later", "shell__exec", {})], policy)
    tools.get("exec").execute.assert_not_awaited()


async def test_worker_has_no_router_budget_but_cannot_call_hidden_supervision_tools():
    tools = catalog("exec", "control_session")
    policy = RoleToolPolicy(WorkerConversation())
    calls = [ToolCallRequest(str(i), "shell__exec", {}) for i in range(12)]
    _, events = await execute(tools, calls, policy)
    assert all(event["status"] == "ok" for event in events)
    _, events = await execute(tools, [ToolCallRequest("hidden", "conversations__control", {})], policy)
    assert events[0]["status"] == "error" and tools.get("control_session").calls == 0


async def test_ptc_nested_calls_share_the_router_budget_and_can_delegate_after_exhaustion():
    native = catalog("exec", "create_session")
    tools = PtcToolRegistry(native)
    code = """for i in range(10):
    try:
        await tools.shell.exec()
    except ToolError:
        print('delegating')
await tools.conversations.create()
"""
    results, events = await execute(tools, [ToolCallRequest("ptc", "ptc__run", {"code": code, "description": "check"})], RoleToolPolicy(RouterConversation()))
    assert events[0]["status"] == "ok", results
    assert native.get("exec").calls == 9 and native.get("create_session").calls == 1


async def test_runner_retains_the_policy_between_model_rounds():
    tools = catalog("exec", "create_session")
    provider = MagicMock(spec=LLMProvider)
    provider.chat = AsyncMock(side_effect=[
        LLMResponse(None, tool_calls=[ToolCallRequest(str(i), "shell__exec", {}) for i in range(6)]),
        LLMResponse(None, tool_calls=[ToolCallRequest(str(i + 6), "shell__exec", {}) for i in range(6)]),
        LLMResponse(None, tool_calls=[ToolCallRequest("delegate", "conversations__create", {})]),
        LLMResponse("done"),
    ])
    provider.chat_stream_with_retry = provider.chat
    spec = make_run_spec(provider, tools=tools, model="test", max_iterations=6,
                         max_tool_result_chars=2000, initial_messages=[{"role": "user", "content": "work"}],
                         session_key=ROUTER_SESSION_KEY)
    await AgentRunner().run(spec)
    assert tools.get("exec").calls == 9 and tools.get("create_session").calls == 1


async def test_parallel_tools_share_elapsed_time_instead_of_counting_it_twice(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("cirno_core.agent.tools.role_policy.time", SimpleNamespace(monotonic=lambda: clock[0]))
    policy = RoleToolPolicy(RouterConversation())
    async with policy.admit("shell__exec"):
        async with policy.admit("files__read"):
            clock[0] = 3.0
    assert policy.calls == 2 and policy.seconds == 3.0


async def test_upstream_timeout_keeps_its_original_diagnosis():
    policy = RoleToolPolicy(RouterConversation())
    with pytest.raises(TimeoutError, match="upstream timeout"):
        async with policy.admit("shell__exec"):
            raise TimeoutError("upstream timeout")
    async with policy.admit("files__read"):
        pass
    assert policy.calls == 2


async def test_exhausted_work_is_rejected_before_requesting_an_approval(monkeypatch):
    approvals = []

    @asynccontextmanager
    async def access(tool, params, request):
        approvals.append(tool.name)
        yield params

    monkeypatch.setattr("cirno_core.agent.approval.service.operation_access", access)
    tools = catalog("exec", "create_session")
    policy = RoleToolPolicy(RouterConversation())
    for index in range(10):
        await execute(tools, [ToolCallRequest(str(index), "shell__exec", {})], policy)
    assert approvals == ["exec"] * 9
    await execute(tools, [ToolCallRequest("delegate", "conversations__create", {})], policy)
    assert approvals[-1] == "create_session"


async def test_ptc_computation_timeout_explains_handoff_and_possible_completed_effects():
    role = ConversationRole("router", ("SOUL.md",), "", False, True, frozenset(), DirectExecutionLimits(9, .02))
    with pytest.raises(TimeoutError, match="Delegate unfinished.*may have completed effects"):
        async with RoleToolPolicy(role).admit("ptc__run"):
            await asyncio.Event().wait()
