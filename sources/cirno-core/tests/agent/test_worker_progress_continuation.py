"""Worker prose remains visible between reasoning and tool iterations."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.agent.progress_hook import AgentProgressHook
from cirno_core.agent.runner.engine import AgentRunner
from cirno_core.bus.agent_events import EventSink
from cirno_core.bus.outbound_events import ProgressEvent, StreamDeltaEvent, StreamEndEvent
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.tool_calls import ToolCallRequest
from sources.development.testing.runtime import make_run_spec


@pytest.mark.parametrize("deltas", [True, False])
async def test_worker_updates_remain_visible_across_tool_rounds(deltas):
    events = []
    iteration = 0
    updates = ["I will inspect the experiment.", "The baseline passed; I will verify the candidate.", "Both checks passed."]
    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.prepare_call.return_value = (None, {}, None)
    tools.execute = AsyncMock(return_value="verified")

    async def publish(event):
        events.append(event)

    async def request(*, on_content_delta, on_thinking_delta, **kwargs):
        nonlocal iteration
        index = iteration
        iteration += 1
        await on_thinking_delta(f"Reasoning round {index}.")
        if deltas:
            await on_content_delta(updates[index])
        return LLMResponse(
            content=updates[index], reasoning_content=f"Reasoning round {index}.",
            finish_reason="tool_calls" if index < 2 else "stop",
            tool_calls=[ToolCallRequest(id=f"check-{index}", name="check", arguments={})] if index < 2 else [],
        )

    provider = MagicMock(chat_stream_with_retry=request)
    result = await AgentRunner().run(make_run_spec(
        provider, model="deepseek-flash", session_key="websocket:worker", tools=tools,
        initial_messages=[{"role": "user", "content": "Verify both experiments"}],
        max_iterations=3, max_tool_result_chars=2048,
        hook=AgentProgressHook(EventSink(publish), streaming=True, session_key="websocket:worker"),
    ))
    visible = [event.content for event in events if isinstance(event, StreamDeltaEvent)]
    # Providers/fallbacks may return complete response content without invoking the
    # requested streaming callback. Intermediate prose must still precede its tool.
    assert visible[:2] == updates[:2]
    assert result.final_content == updates[-1]
    assert tools.execute.await_count == 2
    first_update = next(i for i, event in enumerate(events) if isinstance(event, StreamDeltaEvent))
    first_tool = next(i for i, event in enumerate(events) if isinstance(event, ProgressEvent) and event.tool_hint)
    assert first_update < first_tool
    assert sum(isinstance(event, StreamEndEvent) and event.resuming for event in events) == 2
    assert [event.content for event in events if isinstance(event, ProgressEvent) and event.reasoning_delta] == [
        f"Reasoning round {index}." for index in range(3)
    ]
