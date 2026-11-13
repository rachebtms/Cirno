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


@pytest.mark.parametrize("ending", ["invalid_json", "length"])
async def test_failed_reply_regenerates_complete_message_without_replaying_delivered_parts(ending):
    delivered = []

    async def send(message):
        delivered.append(message)

    broken = ToolCallRequest("broken", "user__message", '{"content":"Second part')
    calls = [broken]
    if ending == "length":
        calls.insert(0, ToolCallRequest("also-discarded", "user__message", {"content": "Must not send"}))
    spec, provider = run_spec([
        LLMResponse(None, tool_calls=[ToolCallRequest("first", "user__message", {"content": "First part"})]),
        LLMResponse("Internal notes", tool_calls=calls, finish_reason="length" if ending == "length" else "tool_calls"),
        LLMResponse(None, tool_calls=[ToolCallRequest("new-reply", "user__message", {"content": "Second part"})]),
        LLMResponse("Sent."),
    ], send)
    with request_context(RequestContext(channel="websocket", chat_id=ROUTER_CHAT_ID, session_key=ROUTER_SESSION_KEY)), capture_message_deliveries():
        result = await AgentRunner().run(spec)
    assert [message.content for message in delivered] == ["First part", "Second part"]
    assert result.final_content == ""
    assert provider.chat.await_count == 4
    if ending == "length":
        prompt = next(message["content"] for message in result.messages if message.get("_hidden_history"))
        assert "None of the tool calls" in prompt
        assert "not a delivered reply" in prompt
        assert "Do not continue partial JSON" in prompt
        assert "already_delivered_tail" not in prompt
        assert not any(message.get("tool_call_id") in {"broken", "also-discarded"} for message in result.messages)
    else:
        error = next(message["content"] for message in result.messages if message.get("tool_call_id") == "broken")
        assert "Unterminated string" in error
        assert "No message was sent by this call" in error
        assert "do not continue the malformed argument string" in error
        assert "parts already delivered successfully" in error
    assert broken.arguments == '{"content":"Second part'
