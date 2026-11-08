"""Real message delivery after a provider ignores the Router reply contract."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from cirno_core.agent.runner.engine import AgentRunner
from cirno_core.agent.tools.context import RequestContext, request_context
from cirno_core.agent.tools.message import MessageTool, capture_message_deliveries
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.providers.base import LLMProvider
from cirno_core.providers.contracts import LLMResponse
from cirno_core.providers.tool_calls import ToolCallRequest
from cirno_core.session.keys import ROUTER_CHAT_ID, ROUTER_SESSION_KEY
from sources.development.testing.runtime import make_run_spec


def run_spec(responses, send, *, required=True):
    provider = MagicMock(spec=LLMProvider)
    provider.chat = AsyncMock(side_effect=responses)
    provider.chat_stream_with_retry = provider.chat
    tools = ToolRegistry()
    tools.register(MessageTool(send_callback=send))
    spec = make_run_spec(provider, tools=tools, model="test-model", max_iterations=4,
                         max_tool_result_chars=2000, initial_messages=[{"role": "user", "content": "Hello"}],
                         session_key=ROUTER_SESSION_KEY, require_visible_reply=required)
    return spec, provider


@pytest.mark.asyncio
async def test_plain_router_greeting_is_repaired_with_one_actual_message_tool_call():
    delivered = []
    async def send(message):
        delivered.append(message)
    spec, provider = run_spec([
        LLMResponse(content="Hello!"),
        LLMResponse(content=None, tool_calls=[ToolCallRequest(id="greet", name="message", arguments={"content": "Hello!"})]),
        LLMResponse(content="Sent."),
    ], send)
    with request_context(RequestContext(channel="websocket", chat_id=ROUTER_CHAT_ID, session_key=ROUTER_SESSION_KEY)), capture_message_deliveries():
        result = await AgentRunner().run(spec)
    assert [item.content for item in delivered] == ["Hello!"]
    assert result.final_content == ""
    assert provider.chat.await_count == 3
    reminders = [item for item in result.messages if item.get("_hidden_history")]
    assert len(reminders) == 1
    assert "user__message" in reminders[0]["content"]


@pytest.mark.asyncio
async def test_repeated_plain_text_is_an_explicit_error_not_a_successful_empty_chat():
    send = AsyncMock()
    spec, provider = run_spec([LLMResponse(content="Hello!"), LLMResponse(content="Hello again!")], send)
    with pytest.raises(RuntimeError, match="did not deliver"):
        await AgentRunner().run(spec)
    assert provider.chat.await_count == 2
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_background_turn_keeps_its_silent_completion_contract():
    spec, provider = run_spec([LLMResponse(content="No update needed.")], AsyncMock(), required=False)
    result = await AgentRunner().run(spec)
    assert result.final_content == "No update needed."
    assert provider.chat.await_count == 1
