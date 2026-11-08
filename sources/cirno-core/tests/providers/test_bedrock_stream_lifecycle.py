"""Progress reaches the caller and interrupted SDK streams retain an owner."""

import asyncio
from threading import Event
from types import SimpleNamespace

import pytest
from cirno_core.providers.bedrock.provider import BedrockProvider


class EventStream:
    def __init__(self, events):
        self.events = iter(events)
        self.closed = 0

    def __iter__(self):
        return self

    def __next__(self):
        return next(self.events)

    def close(self):
        self.closed += 1


def provider_for(stream):
    return BedrockProvider(client=SimpleNamespace(converse_stream=lambda **kwargs: {"stream": stream}))


@pytest.mark.asyncio
async def test_reasoning_and_tool_progress_arrive_before_the_final_response():
    stream = EventStream([
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"reasoningContent": {"text": "checking"}}}},
        {"contentBlockStop": {"contentBlockIndex": 0}},
        {"contentBlockStart": {"contentBlockIndex": 1, "start": {"toolUse": {"toolUseId": "call-1", "name": "memory.search"}}}},
        {"contentBlockDelta": {"contentBlockIndex": 1, "delta": {"toolUse": {"input": '{"query":"snow"}'}}}},
        {"messageStop": {"stopReason": "tool_use"}},
    ])
    thinking, tools = [], []

    async def receive_thinking(text):
        assert stream.closed == 0
        thinking.append(text)

    async def receive_tool(delta):
        assert stream.closed == 0
        tools.append(delta)

    result = await provider_for(stream).chat_stream([{"role": "user", "content": "hello"}],
        on_thinking_delta=receive_thinking, on_tool_call_delta=receive_tool)
    assert thinking == ["checking"]
    assert tools == [
        {"index": 1, "call_id": "call-1", "name": "memory.search", "arguments_delta": ""},
        {"index": 1, "call_id": "call-1", "name": "memory.search", "arguments_delta": '{"query":"snow"}'},
    ]
    assert result.reasoning_content == "checking"
    assert result.tool_calls[0].arguments == {"query": "snow"}
    assert stream.closed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "eof", "callback_error", "cancel"])
async def test_stream_closes_on_every_generation_exit(outcome):
    stream = EventStream([
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "hello"}}},
        *([] if outcome == "eof" else [{"messageStop": {"stopReason": "end_turn"}}]),
    ])
    entered = asyncio.Event()

    async def callback(text):
        entered.set()
        if outcome == "callback_error":
            raise ValueError("render callback failed")
        if outcome == "cancel":
            await asyncio.Event().wait()

    task = asyncio.create_task(provider_for(stream).chat_stream([], on_content_delta=callback))
    await asyncio.wait_for(entered.wait(), 1)
    if outcome == "cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
    else:
        result = await asyncio.wait_for(task, 1)
        assert result.finish_reason == ("stop" if outcome == "success" else "error")
    assert stream.closed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["cancel", "idle_timeout"])
async def test_stopped_blocking_read_is_closed_and_reaped(outcome):
    entered, released, settled = Event(), Event(), Event()

    class BlockingStream(EventStream):
        def __next__(self):
            entered.set()
            try:
                assert released.wait(2)
                raise StopIteration
            finally:
                settled.set()

        def close(self):
            super().close()
            released.set()

    stream = BlockingStream([])
    provider = provider_for(stream)
    provider.stream_idle_timeout_s = 0.03 if outcome == "idle_timeout" else 1
    task = asyncio.create_task(provider.chat_stream([]))
    assert await asyncio.to_thread(entered.wait, 1)
    if outcome == "cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
    else:
        result = await asyncio.wait_for(task, 1)
        assert result.error_kind == "timeout"
    assert stream.closed == 1
    assert settled.is_set()


@pytest.mark.asyncio
async def test_repeated_cancel_during_request_open_waits_for_response_cleanup():
    entered, released = Event(), Event()
    stream = EventStream([])

    def request(**kwargs):
        entered.set()
        assert released.wait(2)
        return {"stream": stream}

    provider = BedrockProvider(client=SimpleNamespace(converse_stream=request))
    task = asyncio.create_task(provider.chat_stream([]))
    assert await asyncio.to_thread(entered.wait, 1)
    try:
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        released.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
    assert stream.closed == 1
