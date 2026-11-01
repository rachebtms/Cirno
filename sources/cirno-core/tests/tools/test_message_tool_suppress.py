"""Test message tool suppress logic for final replies."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from cirno.agent.context import TranscriptInput
from cirno.agent.loop import AgentLoop
from cirno.agent.tools.message import MessageTool
from cirno.bus.events import InboundMessage, OutboundMessage
from cirno.bus.queue import MessageBus
from cirno.providers.base import LLMResponse, ToolCallRequest
from cirno.utils.progress_events import output_events


def _make_loop(tmp_path: Path) -> AgentLoop:
    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    return AgentLoop(bus=bus, provider=provider, workspace=tmp_path, model="test-model")


class TestMessageToolSuppressLogic:
    """Final reply suppressed only when message tool sends to the same target."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("ephemeral", [False, True])
    async def test_suppress_when_sent_to_same_target(
        self,
        tmp_path: Path,
        ephemeral: bool,
    ) -> None:
        loop = _make_loop(tmp_path)
        tool_call = ToolCallRequest(
            id="call1", name="message",
            arguments={"content": "Hello", "channel": "websocket", "chat_id": "global"},
        )
        calls = iter([
            LLMResponse(content="", tool_calls=[tool_call]),
            LLMResponse(content="Done", tool_calls=[]),
        ])
        loop.provider.chat_stream_with_retry = AsyncMock(side_effect=lambda *a, **kw: next(calls))
        loop.tools.get_definitions = MagicMock(return_value=[])

        sent: list[OutboundMessage] = []
        mt = loop.tools.get("message")
        if isinstance(mt, MessageTool):
            mt.set_send_callback(AsyncMock(side_effect=lambda m: sent.append(m)))

        msg = InboundMessage(channel="websocket", sender_id="user1", chat_id="global", content="Send")
        result = await loop._process_message(msg, ephemeral=ephemeral)

        assert len(sent) == 1
        assert result is None  # suppressed

    @pytest.mark.asyncio
    async def test_regular_conversation_does_not_advertise_or_execute_message(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        tool_call = ToolCallRequest(id="forbidden", name="message", arguments={"content": "No", "channel": "telegram", "chat_id": "external"})
        loop.provider.chat_stream_with_retry = AsyncMock(side_effect=[
            LLMResponse(content="", tool_calls=[tool_call]),
            LLMResponse(content="A normal reply."),
        ])
        sender = AsyncMock()
        loop.tools.get("message").set_send_callback(sender)
        result = await loop._process_message(InboundMessage(channel="telegram", sender_id="user", chat_id="ordinary", content="hi"))
        sender.assert_not_awaited()
        assert result.content == "A normal reply."
        assert all(schema["function"]["name"] != "message" for schema in loop.provider.chat_stream_with_retry.call_args_list[0].kwargs["tools"])

    @pytest.mark.asyncio
    async def test_not_suppress_when_no_message_tool_used(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        loop.provider.chat_stream_with_retry = AsyncMock(return_value=LLMResponse(content="Hello!", tool_calls=[]))
        loop.tools.get_definitions = MagicMock(return_value=[])

        msg = InboundMessage(channel="feishu", sender_id="user1", chat_id="chat123", content="Hi")
        result = await loop._process_message(msg)

        assert result is not None
        assert "Hello" in result.content

    @pytest.mark.asyncio
    async def test_internal_message_check_keeps_final_response(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        tool_call = ToolCallRequest(
            id="call1", name="message",
            arguments={"content": "all clear", "channel": "feishu", "chat_id": "chat123"},
        )
        calls = iter([
            LLMResponse(content="", tool_calls=[tool_call]),
            LLMResponse(content="Heartbeat summary", tool_calls=[]),
        ])
        loop.provider.chat_stream_with_retry = AsyncMock(side_effect=lambda *a, **kw: next(calls))
        loop.tools.get_definitions = MagicMock(return_value=[])

        mt = loop.tools.get("message")
        assert isinstance(mt, MessageTool)
        token = mt.set_suppress_delivery(True)
        try:
            msg = InboundMessage(
                channel="feishu", sender_id="user1", chat_id="chat123", content="Check",
            )
            result = await loop._process_message(msg)
        finally:
            mt.reset_suppress_delivery(token)

        assert result is not None
        assert result.content == "Heartbeat summary"

    @pytest.mark.asyncio
    async def test_injected_followup_with_message_tool_does_not_emit_empty_fallback(
        self, tmp_path: Path
    ) -> None:
        loop = _make_loop(tmp_path)
        tool_call = ToolCallRequest(
            id="call1", name="message",
            arguments={"content": "Tool reply", "channel": "websocket", "chat_id": "global"},
        )
        calls = iter([
            LLMResponse(content="First answer", tool_calls=[]),
            LLMResponse(content="", tool_calls=[tool_call]),
            LLMResponse(content="", tool_calls=[]),
            LLMResponse(content="", tool_calls=[]),
            LLMResponse(content="", tool_calls=[]),
        ])
        pending_queue: asyncio.Queue[InboundMessage] = asyncio.Queue()

        async def next_response(*_args, **_kwargs):
            response = next(calls)
            if response.content == "First answer":
                pending_queue.put_nowait(InboundMessage(
                    channel="websocket",
                    sender_id="user1",
                    chat_id="global",
                    content="follow-up",
                ))
            return response

        loop.provider.chat_stream_with_retry = AsyncMock(side_effect=next_response)
        loop.tools.get_definitions = MagicMock(return_value=[])

        sent: list[OutboundMessage] = []
        mt = loop.tools.get("message")
        if isinstance(mt, MessageTool):
            mt.set_send_callback(AsyncMock(side_effect=lambda m: sent.append(m)))

        msg = InboundMessage(channel="websocket", sender_id="user1", chat_id="global", content="Start")
        result = await loop._process_message(msg, pending_queue=pending_queue)

        assert len(sent) == 1
        assert sent[0].content == "Tool reply"
        assert result is None

    async def test_progress_hides_internal_reasoning(self, tmp_path: Path) -> None:
        loop = _make_loop(tmp_path)
        tool_call = ToolCallRequest(id="call1", name="read_file", arguments={"path": "foo.txt"})
        calls = iter([
            LLMResponse(
                content="Visible<think>hidden</think>",
                tool_calls=[tool_call],
                reasoning_content="secret reasoning",
                thinking_blocks=[{"signature": "sig", "thought": "secret thought"}],
            ),
            LLMResponse(content="Done", tool_calls=[]),
        ])
        loop.provider.chat_stream_with_retry = AsyncMock(side_effect=lambda *a, **kw: next(calls))
        loop.tools.get_definitions = MagicMock(return_value=[])
        loop.tools.execute = AsyncMock(return_value="ok")

        progress: list[tuple[str, bool]] = []

        async def on_progress(content: str, *, tool_hint: bool = False) -> None:
            progress.append((content, tool_hint))

        result = await loop._run_agent_loop(
            TranscriptInput(history=[], current_message=None),
            runtime=loop.llm_runtime(),
            events=output_events(on_progress=on_progress),
        )

        assert result.final_content == "Done"
        assert progress == [
            ("Visible", False),
            ("", True),
        ]

class TestMessageToolSchema:

    def test_schema_describes_cirno_and_regular_conversation_delivery(self) -> None:
        tool = MessageTool()
        assert "Cirno coordination conversation" in tool.description
        assert "MUST use this tool" in tool.description
        assert "normal final replies are delivered automatically" in tool.description
        assert "not available in regular conversations" in tool.description
        assert "existing local file paths" in tool.parameters["properties"]["media"]["description"]

@pytest.mark.asyncio
async def test_message_reply_does_not_echo_in_stream_or_model_history(tmp_path):
    loop = _make_loop(tmp_path)
    call = ToolCallRequest(id="send", name="message", arguments={"content": "Hello once"})
    rounds = 0
    async def respond(**kwargs):
        nonlocal rounds
        rounds += 1
        if rounds == 1:
            return LLMResponse(content="", tool_calls=[call])
        await kwargs["on_content_delta"]("Hello once")
        return LLMResponse(content="Hello once", tool_calls=[])
    loop.provider.chat_stream_with_retry = respond
    mt = loop.tools.get("message")
    mt.set_send_callback(AsyncMock())
    deltas = []
    async def stream(text):
        deltas.append(text)
    result = await loop._process_message(
        InboundMessage(channel="websocket", sender_id="user", chat_id="global", content="hi"),
        on_stream=stream,
    )
    assert result is None
    assert deltas == []
    session = await loop.sessions.state.read("websocket:global")
    assert not any(m.get("content") == "Hello once" and not m.get("_channel_delivery") for m in session.messages)


@pytest.mark.asyncio
async def test_question_delivery_does_not_hide_following_answer(tmp_path):
    loop = _make_loop(tmp_path)
    call = ToolCallRequest(id="ask", name="ask_user", arguments={"question": "Which format?"})
    loop.provider.chat_stream_with_retry = AsyncMock(side_effect=[
        LLMResponse(content="", tool_calls=[call]), LLMResponse(content="I continued independently."),
    ])
    result = await loop._process_message(InboundMessage(channel="websocket", sender_id="user", chat_id="question-test", content="start"))
    assert result is not None
    assert result.content == "I continued independently."

@pytest.mark.asyncio
@pytest.mark.parametrize("ptc", [False, True])
@pytest.mark.parametrize("channel", ["websocket", "telegram", "cli"])
async def test_regular_conversation_cannot_use_message_even_through_ptc(tmp_path, ptc, channel):
    loop = _make_loop(tmp_path)
    await loop.sessions.state.open_with_metadata(f"{channel}:regular", {"ptc_mode": ptc})
    calls = []
    async def respond(**kwargs):
        calls.append(kwargs)
        return LLMResponse(content="A normal reply.")
    loop.provider.chat_stream_with_retry = respond
    result = await loop._process_message(InboundMessage(channel=channel, sender_id="user", chat_id="regular", content="hello"))
    assert result.content == "A normal reply."
    request = calls[0]
    assert "Regular Conversation" in request["messages"][0]["content"]
    assert "# Cirno Conversation" not in request["messages"][0]["content"]
    assert all(s["function"]["name"] != "message" for s in request["tools"])
    if ptc:
        assert '"name":"message"' not in request["messages"][0]["content"]


@pytest.mark.asyncio
async def test_regular_message_guard_cannot_be_bypassed_with_hidden_ui_argument():
    from cirno.agent.tools.context import RequestContext, request_context
    callback = AsyncMock()
    tool = MessageTool(send_callback=callback)
    with request_context(RequestContext(channel="websocket", chat_id="regular", session_key="websocket:regular")):
        result = await tool.execute("not allowed", _agent_ui={"kind": "user_question"})
    assert "available only in the Cirno conversation" in result
    callback.assert_not_awaited()
