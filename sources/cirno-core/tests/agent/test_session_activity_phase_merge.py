"""Durable presentation follows the same tool-phase merge rules as live UI."""

import json

import pytest
from cirno_core.agent.hook import AgentHookContext
from cirno_core.agent.session_activity import SessionActivity
from cirno_core.bus.outbound_events import ProgressEvent
from cirno_core.session.model import Session
from cirno_core.session.transcript.thread import build_session_thread_response


@pytest.mark.parametrize("terminal", ["end", "error"])
async def test_late_start_cannot_regress_a_persisted_terminal_tool_phase(terminal):
    messages = []
    activity = SessionActivity()
    await activity.before_iteration(AgentHookContext(iteration=0, messages=messages))
    messages.append({"role": "assistant", "content": "", "tool_calls": [{"id": "fixture", "type": "function", "function": {"name": "mcp_research_tools_read", "arguments": "{}"}}]})
    complete = {"call_id": "fixture", "name": "mcp_research_tools_read", "phase": terminal, "arguments": {}, "result": "Done", "mcp_server": "research_tools", "mcp_tool": "read"}
    activity.remember(ProgressEvent(tool_events=[complete]))
    activity.remember(ProgressEvent(tool_events=[{**complete, "phase": "start", "result": None}]))
    saved = activity.transcript(messages)
    assert saved[0]["tool_events"] == [complete]
    assert "tool_events" not in messages[0]
    replay = build_session_thread_response(Session(key="websocket:fixture", messages=json.loads(json.dumps(saved))))
    assert [event["phase"] for record in replay["events"] for event in record.get("tool_events", [])] == [terminal]


async def test_finish_merges_start_identity_instead_of_discarding_its_display_fields():
    activity = SessionActivity()
    start = {"call_id": "fixture", "name": "mcp_research_tools_read", "phase": "start", "arguments": {}, "mcp_server": "research_tools", "mcp_tool": "read"}
    finish = {"call_id": "fixture", "name": start["name"], "phase": "end", "result": "Done"}
    activity.remember(ProgressEvent(tool_events=[start]))
    activity.remember(ProgressEvent(tool_events=[finish]))
    [row] = activity.transcript()
    assert row["tool_events"] == [{**start, **finish}]
