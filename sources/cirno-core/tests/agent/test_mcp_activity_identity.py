"""MCP display identity survives fake execution and durable history projection."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.agent.hook import CompositeHook
from cirno_core.agent.progress_hook import AgentProgressHook
from cirno_core.agent.ptc.registry import PtcToolRegistry, RunCodeTool
from cirno_core.agent.runner.engine import AgentRunner
from cirno_core.agent.session_activity import SessionActivity
from cirno_core.agent.tools.mcp.wrappers import MCPPromptWrapper, MCPResourceWrapper, MCPToolWrapper
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.bus.agent_events import EventSink
from cirno_core.bus.outbound_events import ProgressEvent
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.tool_calls import ToolCallRequest
from cirno_core.session.model import Session
from cirno_core.session.transcript.thread import build_session_thread_response

from sources.development.testing.runtime import make_run_spec


@pytest.mark.parametrize("kind", ["tool", "resource", "prompt"])
@pytest.mark.parametrize("ptc", [False, True])
async def test_mcp_identity_is_explicit_in_live_and_replayed_activity(monkeypatch, kind, ptc):
    server = "research_tools"
    original = "browser.navigate" if kind == "tool" else "research_notes"
    definition = SimpleNamespace(name=original, description="Fixture", inputSchema={"type": "object", "properties": {}}, annotations=None, uri="fixture://notes", arguments=[])
    wrapper = {"tool": MCPToolWrapper, "resource": MCPResourceWrapper, "prompt": MCPPromptWrapper}[kind](None, server, definition)
    wrapper.execute = AsyncMock(return_value="fixture result")
    native = ToolRegistry()
    native.register(wrapper)
    tools = PtcToolRegistry(native) if ptc else native
    if ptc:
        async def run_fixture(self, **kwargs):
            value, failed = await kwargs["dispatch"](wrapper.name, {}, "fixture")
            assert not failed
            return value
        monkeypatch.setattr(RunCodeTool, "run", run_fixture)
    call = ToolCallRequest(id="fixture-call", name="ptc__run" if ptc else wrapper.name, arguments={"code": "not executed", "description": "Fixture"} if ptc else {})
    responses = iter([LLMResponse(content="", tool_calls=[call]), LLMResponse(content="Done")])
    provider = MagicMock()
    provider.chat_stream_with_retry = AsyncMock(side_effect=lambda *args, **kwargs: next(responses))
    activity = SessionActivity()
    events = []
    async def publish(event):
        activity.remember(event)
        events.append(event)
    hook = CompositeHook([activity, AgentProgressHook(EventSink(publish))])
    result = await AgentRunner().run(make_run_spec(provider, initial_messages=[], tools=tools, model="fixture", max_iterations=2, max_tool_result_chars=4096, concurrent_tools=False, hook=hook))
    assert result.final_content == "Done"
    expected_name = original if kind == "tool" else f"{kind}_{original}"
    payloads = [payload for event in events if isinstance(event, ProgressEvent) for payload in event.tool_events or [] if payload["name"] == wrapper.name]
    assert [payload["phase"] for payload in payloads] == ["start", "end"]
    assert [(payload.get("mcp_server"), payload.get("mcp_tool")) for payload in payloads] == [(server, expected_name)] * 2

    # This serializes only the detached presentation transcript, never provider input.
    saved = json.loads(json.dumps(activity.transcript(result.messages)))
    session = Session(key="websocket:fixture", messages=saved)
    replay = build_session_thread_response(session)
    replayed = [tool for event in replay["events"] for tool in event.get("tool_events", []) if tool["name"] == wrapper.name]
    assert [(tool.get("mcp_server"), tool.get("mcp_tool")) for tool in replayed] == [(server, expected_name)]
    assert '"mcp_server"' not in json.dumps(session.get_history())
    assert '"mcp_tool"' not in json.dumps(session.get_history())
    for model_call in provider.chat_stream_with_retry.call_args_list:
        for message in model_call.kwargs["messages"]:
            assert "tool_events" not in message
            assert "tool_activity" not in message
            assert "mcp_server" not in message
