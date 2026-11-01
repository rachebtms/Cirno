"""PTC exercises the real worker, tool pipeline, cancellation and permission hooks."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from cirno.agent.hook import AgentHook, AgentHookContext
from cirno.agent.ptc.registry import PtcToolRegistry
from cirno.agent.tools.base import Tool
from cirno.agent.tools.execution import execute_tool_calls
from cirno.agent.tools.registry import ToolRegistry
from cirno.providers.base import ToolCallRequest


class ExampleTool(Tool):
    name = "example"
    description = "Read a test result"
    parameters = {"type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"]}
    read_only = True

    async def execute(self, value):
        await asyncio.sleep(0.01)
        return json.dumps({"value": value, "large": "hidden evidence" * 100})


async def run(code, *, hook=None, native=None, timeout=5):
    native = native or ToolRegistry()
    if not native.has("example"):
        native.register(ExampleTool())
    tools = PtcToolRegistry(native)
    calls = [ToolCallRequest(id="program", name="run_code", arguments={"code": code, "description": "Test program", "timeout": timeout})]
    return await execute_tool_calls(tools, calls, concurrent=False,
        external_lookup_counts={}, workspace_violation_counts={}, hook=hook or AgentHook(),
        context=AgentHookContext(iteration=0, messages=[]))


async def test_program_filters_results_and_logs_nested_tools():
    hook = AgentHook()
    hook.before_execute_tool = AsyncMock()
    result, events = await run('values = await gather(tools.example(value=2), tools.example({"value": 3}))\nprint(sum(v["value"] for v in values))', hook=hook)
    assert result == ["5\n"]
    assert "hidden evidence" not in result[0]
    assert events[0]["status"] == "ok"
    nested = [call.args[1] for call in hook.before_execute_tool.call_args_list if call.args[1].name == "example"]
    assert [c.id for c in nested] == ["program:ptc:1", "program:ptc:2"]


async def test_only_run_code_is_directly_exposed():
    native = ToolRegistry()
    native.register(ExampleTool())
    registry = PtcToolRegistry(native)
    assert [s["function"]["name"] for s in registry.get_definitions()] == ["ptc__run"]
    assert registry.prepare_call("example", {"value": 1})[2]
    assert '"name":"example"' in registry.sdk_prompt()


@pytest.mark.parametrize("code,reason", [
    ('import os', 'Imports'), ('print(tools.__class__)', 'Private'),
    ('print(open("/etc/passwd").read())', 'NameError'),
    ('print("{x.__class__}".format(x=1))', 'format'),
    ('return await tools.unknown()', 'not available'),
    ('print("x" * 17000)', '16000'),
])
async def test_compute_worker_has_no_direct_host_access_and_bounded_output(code, reason):
    result, events = await run(code)
    assert reason in result[0]
    assert events[0]["status"] == "error"


async def test_schema_validation_still_applies_and_errors_can_be_handled():
    result, _ = await run('try:\n    await tools.example(value="no")\nexcept ToolError:\n    print("rejected")')
    assert result == ["rejected\n"]


async def test_native_guard_is_not_bypassed():
    hook = AgentHook()
    async def deny(context, call, tool, params):
        if call.name == "example":
            raise PermissionError("requires approval")
    hook.before_execute_tool = deny
    result, events = await run('await tools.example(value=1)', hook=hook)
    assert "requires approval" in result[0]
    assert events[0]["status"] == "error"


async def test_timeout_stops_worker():
    result, events = await run('while True:\n    pass', timeout=1)
    assert "deadline exceeded" in result[0]
    assert events[0]["status"] == "error"


async def test_stop_cancels_nested_tool_without_replaying():
    started = asyncio.Event()
    cancelled = asyncio.Event()
    tool = ExampleTool()
    async def wait(value):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    tool.execute = wait
    native = ToolRegistry()
    native.register(tool)
    hook = AgentHook()
    hook.on_provider_tool_event = AsyncMock()
    task = asyncio.create_task(run('await tools.example(value=1)', native=native, hook=hook))
    await asyncio.wait_for(started.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()
    assert hook.on_provider_tool_event.call_args.args[1]["error"] == "PTC program stopped."

async def test_session_enables_sdk_only_for_ptc_and_preserves_tool_result(tmp_path):
    from unittest.mock import MagicMock

    from cirno.agent.context import TranscriptInput
    from cirno.agent.loop import AgentLoop
    from cirno.bus.queue import MessageBus
    from cirno.providers.base import LLMResponse
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.chat_stream_with_retry = AsyncMock(side_effect=[
        LLMResponse(content="", tool_calls=[ToolCallRequest(id="code", name="run_code", arguments={
            "code": 'result = await tools.example(value=7)\nprint(result["value"])', "description": "Read a result"})]),
        LLMResponse(content="Seven"),
    ])
    loop = AgentLoop(bus=MessageBus(), provider=provider, workspace=tmp_path, model="test-model")
    tools = ToolRegistry()
    tools.register(ExampleTool())
    await loop.sessions.state.open_with_metadata("cli:ptc", {"ptc_mode": True})
    session = await loop.sessions.state.read("cli:ptc")
    result = await loop._run_agent_loop(TranscriptInput(history=[], current_message="test"),
        runtime=loop.llm_runtime(), tools=tools, session=session)
    assert result.final_content == "Seven"
    request = provider.chat_stream_with_retry.call_args_list[0].kwargs
    assert [s["function"]["name"] for s in request["tools"]] == ["ptc__run"]
    assert "PTC Mode is enabled" in request["messages"][0]["content"]
    assert any(m.get("role") == "tool" and m.get("content") == "7\n" for m in result.messages)


async def test_json_helper_import_is_available_without_loading_host_modules():
    result, _ = await run('import json as j\nprint(j.loads(\'{"count": 3}\')["count"])')
    assert result == ["3\n"]


async def test_parallel_ptc_sessions_keep_their_request_contexts():
    from cirno.agent.tools.context import RequestContext, current_request_context, request_context
    async def execute_in(chat):
        tool = ExampleTool()
        async def execute(value):
            await asyncio.sleep(0.01)
            return current_request_context().chat_id
        tool.execute = execute
        native = ToolRegistry()
        native.register(tool)
        with request_context(RequestContext(channel="websocket", chat_id=chat, session_key=f"websocket:{chat}")):
            return (await run('print(await tools.example(value=1))', native=native))[0][0]
    assert await asyncio.gather(execute_in("A"), execute_in("B")) == ["A\n", "B\n"]
