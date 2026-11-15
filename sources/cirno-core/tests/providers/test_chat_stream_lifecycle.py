"""Long streams release raw chunks and always close their HTTP stream."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from weakref import WeakSet

import cirno_core.providers.openai_compat_provider as compat
import pytest
from cirno_core.providers.model_api import ModelAPICapabilities
from cirno_core.providers.openai_compat_provider import OpenAICompatProvider


def provider_for(stream):
    provider = OpenAICompatProvider(
        api_key="fixture", default_model="fixture-model",
        model_api=ModelAPICapabilities(("chat_completions",), "chat_completions"),
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=stream))))
    provider._ensure_client = AsyncMock(return_value=client)
    return provider


@pytest.mark.parametrize("reason", ["stop", "tool_calls"])
@pytest.mark.parametrize("keepalive", [False, True])
async def test_finished_generation_does_not_wait_for_missing_usage(monkeypatch, reason, keepalive):
    monkeypatch.setattr(compat, "_CHAT_USAGE_TRAILER_TIMEOUT_S", 0.01)

    class Stream:
        closed = False

        async def __aiter__(self):
            delta = {"content": "Verified answer"} if reason == "stop" else {"tool_calls": [{
                "index": 0, "id": "checkpoint", "function": {
                    "name": "memory__checkpoint", "arguments": '{"content":"Verified work"}',
                },
            }]}
            yield {"choices": [{"delta": delta, "finish_reason": reason}]}
            while True:
                if not keepalive:
                    await asyncio.Event().wait()
                await asyncio.sleep(0.001)
                yield {"choices": []}

        async def close(self):
            self.closed = True

    stream = Stream()
    provider = provider_for(stream)
    provider.stream_idle_timeout_s = 180
    result = await asyncio.wait_for(provider.chat_stream_with_retry(
        [{"role": "user", "content": "Continue"}],
    ), 0.5)
    assert result.finish_reason == reason
    assert result.usage is None
    if reason == "stop":
        assert result.content == "Verified answer"
    else:
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].arguments == {"content": "Verified work"}
    client = await provider._ensure_client()
    client.chat.completions.create.assert_awaited_once()
    assert stream.closed


async def test_finished_stream_still_collects_delayed_usage_within_grace(monkeypatch):
    monkeypatch.setattr(compat, "_CHAT_USAGE_TRAILER_TIMEOUT_S", 0.5)

    class Stream:
        closed = False

        async def __aiter__(self):
            yield {"choices": [{"delta": {"content": "Done"}, "finish_reason": "stop"}]}
            await asyncio.sleep(0.01)
            yield {"choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 5,
                                           "prompt_cache_hit_tokens": 90}}
            raise AssertionError("Do not wait for EOF after finish and usage")

        async def close(self):
            self.closed = True

    stream = Stream()
    result = await provider_for(stream).chat_stream([{"role": "user", "content": "Continue"}])
    assert result.content == "Done"
    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 5
    assert result.usage.cache_read_tokens == 90
    assert stream.closed


async def test_long_stream_does_not_retain_sdk_chunks_and_preserves_final_usage():
    alive = WeakSet()
    maximum_live = 0
    count = 20_000

    class Chunk:
        def __init__(self, payload):
            self.payload = payload
            alive.add(self)

        def model_dump(self):
            return self.payload

    class Stream:
        closed = False

        def __aiter__(self):
            return self.generate()

        async def generate(self):
            nonlocal maximum_live
            for index in range(count):
                maximum_live = max(maximum_live, len(alive))
                yield Chunk({"choices": [{"delta": {"reasoning_content": f"step {index}\n"}}]})
            yield Chunk({"choices": [{"delta": {"content": "Verified result"}, "finish_reason": "stop"}]})
            yield Chunk({"choices": [], "usage": {"prompt_tokens": 32000, "completion_tokens": 70000,
                                                   "prompt_cache_hit_tokens": 31000}})

        async def close(self):
            self.closed = True

    stream = Stream()
    result = await provider_for(stream).chat_stream([{"role": "user", "content": "Long research"}])
    assert result.finish_reason == "stop"
    assert result.content == "Verified result"
    assert result.reasoning_content.startswith("step 0\n")
    assert result.reasoning_content.endswith(f"step {count - 1}\n")
    assert result.reasoning_content.count("\n") == count
    assert result.usage.input_tokens == 32000
    assert result.usage.output_tokens == 70000
    assert result.usage.cache_read_tokens == 31000
    assert maximum_live <= 2, "the provider kept already-decoded SDK chunks alive"
    assert not alive
    assert stream.closed


@pytest.mark.parametrize("ending", ["cancel", "timeout", "invalid_chunk"])
async def test_stream_resource_closes_after_cancel_timeout_or_parse_failure(ending):
    class Stream:
        closed = False
        started = asyncio.Event()

        def __aiter__(self):
            return self

        async def __anext__(self):
            self.started.set()
            if ending == "invalid_chunk":
                return object()
            await asyncio.Event().wait()

        async def close(self):
            self.closed = True

    stream = Stream()
    provider = provider_for(stream)
    if ending == "timeout":
        provider.stream_idle_timeout_s = 0.01
    task = asyncio.create_task(provider.chat_stream([{"role": "user", "content": "Continue"}]))
    await stream.started.wait()
    if ending == "cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        result = await asyncio.wait_for(task, 2)
        assert result.finish_reason == "error"
        if ending == "timeout":
            assert result.error_kind == "timeout"
        else:
            assert "Unsupported chat chunk type" in result.content
    assert stream.closed


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_nonfinite_request_timeout_uses_bounded_default(monkeypatch, value):
    monkeypatch.setenv("CIRNO_OPENAI_COMPAT_TIMEOUT_S", value)
    provider = OpenAICompatProvider(api_key="fixture")
    assert provider.request_timeout_s == 120


async def test_repeated_stop_waits_for_http_stream_to_close():
    started, closing, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class Stream:
        closed = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            started.set()
            await asyncio.Event().wait()

        async def close(self):
            closing.set()
            await release.wait()
            self.closed = True

    stream = Stream()
    task = asyncio.create_task(provider_for(stream).chat_stream([{"role": "user", "content": "Continue"}]))
    await started.wait()
    task.cancel()
    await closing.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stream.closed


async def test_ambiguous_gateway_deltas_return_retryable_error_without_partial_tools():
    class Stream:
        closed = False

        def __aiter__(self):
            return self.generate()

        async def generate(self):
            for identity, arguments in (
                ("first", '{"content":"unfinished'),
                ("second", '{"content":"new reply"}'),
            ):
                yield {"choices": [{"delta": {"tool_calls": [{
                    "index": 0, "id": identity,
                    "function": {"name": "user__message", "arguments": arguments},
                }]}}]}
            yield {"choices": [{"delta": {"tool_calls": [{
                "index": 0, "function": {"arguments": "}"},
            }]}}]}

        async def close(self):
            self.closed = True

    stream = Stream()
    response = await provider_for(stream).chat_stream([{"role": "user", "content": "Reply"}])
    assert response.finish_reason == "error"
    assert response.tool_calls == []
    assert "no ID for a reused index" in response.content
    assert response.error_kind == "invalid_response"
    assert stream.closed


async def test_repetition_interrupt_closes_http_stream_without_provider_retry():
    from cirno_core.agent.runner.repetition import OutputRepetitionGuard, RepeatedOutputDetected
    from cirno_core.config.repetition import OutputRepetitionConfig

    class Stream:
        closed = False
        async def __aiter__(self):
            for _ in range(1000):
                yield {'choices':[{'delta':{'content':'停住。'}, 'finish_reason':None}]}
        async def close(self):
            self.closed = True

    stream = Stream()
    provider = provider_for(stream)
    guard = OutputRepetitionGuard(OutputRepetitionConfig(), [])
    async def check(delta):
        guard.check(delta)
    try:
        with pytest.raises(RepeatedOutputDetected):
            await provider.chat_stream_with_retry([{'role':'user','content':'work'}], on_content_delta=check)
        assert stream.closed
        client = await provider._ensure_client()
        assert client.chat.completions.create.await_count == 1
        assert not asyncio.current_task().cancelling()
    finally:
        await provider.aclose()
